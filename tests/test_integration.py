"""Integration tests: Orchestrator → ToolExecutor pipeline (OpenAI fully mocked)."""

import json
from unittest.mock import MagicMock, patch

import pytest

from macmaint.assistant.orchestrator import Orchestrator, OrchestratorError
from macmaint.assistant.session import SessionManager, SessionState
from macmaint.assistant.tools import ToolExecutor


# ---------------------------------------------------------------------------
# Streaming chunk helpers
# ---------------------------------------------------------------------------

def _stream_chunk(content: str = None, tool_calls=None, finish_reason=None):
    """Build a minimal mock that looks like an OpenAI streaming chunk."""
    delta = MagicMock()
    delta.content = content
    delta.tool_calls = tool_calls or []

    choice = MagicMock()
    choice.delta = delta
    choice.finish_reason = finish_reason

    chunk = MagicMock()
    chunk.choices = [choice]
    return chunk


def _text_stream(text: str):
    """Yield one chunk per character, then a finish chunk."""
    for ch in text:
        yield _stream_chunk(content=ch)
    yield _stream_chunk(finish_reason="stop")


def _tool_call_stream(tool_name: str, arguments: dict, call_id: str = "call_abc"):
    """Yield a minimal streaming sequence that triggers one tool call."""
    args_str = json.dumps(arguments)

    tc_delta = MagicMock()
    tc_delta.index = 0
    tc_delta.id = call_id
    tc_delta.function = MagicMock()
    tc_delta.function.name = tool_name
    tc_delta.function.arguments = args_str

    yield _stream_chunk(tool_calls=[tc_delta])
    yield _stream_chunk(finish_reason="tool_calls")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_tool_executor(mock_config, mock_profile_manager):
    with (
        patch("macmaint.assistant.tools.Scanner"),
        patch("macmaint.assistant.tools.Fixer"),
        patch("macmaint.assistant.tools.HistoryManager"),
    ):
        executor = ToolExecutor(mock_config, mock_profile_manager)
        # Stub out the execute method so no real system calls happen
        executor.execute = MagicMock(return_value={
            "success": True,
            "data": {"issues": [], "issue_count": 0},
            "summary": "Scan complete. Found 0 issues.",
        })
        yield executor


@pytest.fixture
def mock_session(tmp_path, mock_config, mock_profile_manager):
    with patch("macmaint.assistant.session.DataAnonymizer") as MockAnon:
        MockAnon.return_value._anonymize_string = lambda s: s
        mgr = SessionManager(mock_config, mock_profile_manager)
        mgr.conversations_dir = tmp_path / "conversations"
        mgr.conversations_dir.mkdir()
        session = mgr.create_new_session()
        yield session, mgr


@pytest.fixture
def orchestrator(mock_config, mock_tool_executor, mock_profile_manager):
    with patch("macmaint.assistant.orchestrator.OpenAI"):
        orch = Orchestrator(mock_config, mock_tool_executor, mock_profile_manager)
        yield orch


# ---------------------------------------------------------------------------
# Orchestrator.__init__
# ---------------------------------------------------------------------------

class TestOrchestratorInit:
    def test_raises_without_api_key(self, mock_profile_manager):
        cfg = MagicMock()
        cfg.api_key = None
        with pytest.raises(OrchestratorError, match="API key"):
            Orchestrator(cfg, MagicMock(), mock_profile_manager)

    def test_model_is_gpt4o(self, orchestrator):
        assert orchestrator.model == "gpt-4o"


# ---------------------------------------------------------------------------
# Pure text response (no tool calls)
# ---------------------------------------------------------------------------

class TestOrchestratorTextResponse:
    def test_returns_streamed_text(self, orchestrator, mock_session):
        session, _ = mock_session
        orchestrator.client.chat.completions.create.return_value = (
            _text_stream("Hello from assistant!")
        )

        chunks = []
        msg = orchestrator.process_message(
            session=session,
            user_message="Hi",
            on_stream_chunk=chunks.append,
        )

        full = "".join(chunks)
        assert full == "Hello from assistant!"
        assert msg.content == "Hello from assistant!"
        assert msg.role == "assistant"

    def test_stream_chunk_callback_fires_per_character(self, orchestrator, mock_session):
        session, _ = mock_session
        text = "abc"
        orchestrator.client.chat.completions.create.return_value = _text_stream(text)

        chunks = []
        orchestrator.process_message(
            session=session,
            user_message="test",
            on_stream_chunk=chunks.append,
        )
        assert chunks == list(text)


# ---------------------------------------------------------------------------
# Tool call → tool result → final text response
# ---------------------------------------------------------------------------

class TestOrchestratorToolCall:
    def _make_final_text_stream(self, text: str):
        return list(_text_stream(text))

    def test_tool_call_triggers_executor(self, orchestrator, mock_session):
        session, _ = mock_session

        tool_stream = list(_tool_call_stream("scan_system", {"quick": False}))
        final_stream = list(_text_stream("Your Mac is healthy!"))

        orchestrator.client.chat.completions.create.side_effect = [
            iter(tool_stream),
            iter(final_stream),
        ]

        tool_calls_seen = []
        msg = orchestrator.process_message(
            session=session,
            user_message="scan my Mac",
            on_tool_call=lambda name, args: tool_calls_seen.append(name),
        )

        assert "scan_system" in tool_calls_seen
        orchestrator.tool_executor.execute.assert_called_once_with(
            "scan_system", {"quick": False}
        )
        assert msg.content == "Your Mac is healthy!"

    def test_tool_result_included_in_next_call(self, orchestrator, mock_session):
        session, _ = mock_session

        tool_stream = list(_tool_call_stream("get_system_status", {}))
        final_stream = list(_text_stream("All good."))

        orchestrator.client.chat.completions.create.side_effect = [
            iter(tool_stream),
            iter(final_stream),
        ]

        orchestrator.process_message(session=session, user_message="status?")

        # Second API call should include a tool result message
        second_call_args = orchestrator.client.chat.completions.create.call_args_list[1]
        messages_sent = second_call_args[1]["messages"]
        roles = [m["role"] for m in messages_sent]
        assert "tool" in roles

    def test_trust_mode_injects_auto_approve(self, orchestrator, mock_session):
        session, mgr = mock_session
        mgr.set_trust_mode(session, "auto_fix_safe")

        tool_stream = list(_tool_call_stream("fix_issues", {"issue_ids": ["x"]}))
        final_stream = list(_text_stream("Fixed!"))

        orchestrator.client.chat.completions.create.side_effect = [
            iter(tool_stream),
            iter(final_stream),
        ]

        orchestrator.process_message(session=session, user_message="fix issue x")

        called_args = orchestrator.tool_executor.execute.call_args
        assert called_args[0][1].get("auto_approve") is True


# ---------------------------------------------------------------------------
# Sub-agent delegation
# ---------------------------------------------------------------------------

class TestOrchestratorSubAgentDelegation:
    def test_delegate_to_sub_agent_runs_agent(self, orchestrator, mock_session):
        session, _ = mock_session

        delegate_stream = list(_tool_call_stream(
            "delegate_to_sub_agent",
            {"agent": "scan_agent", "task": "deep scan", "context": {}},
            call_id="call_delegate",
        ))
        final_stream = list(_text_stream("Deep scan complete."))

        orchestrator.client.chat.completions.create.side_effect = [
            iter(delegate_stream),
            iter(final_stream),
        ]

        agent_mock = MagicMock()
        agent_mock.run.return_value = {
            "health_score": 88,
            "issues": [],
            "summary": "All clear",
            "_agent": "scan_agent",
        }

        with patch("macmaint.assistant.orchestrator.create_agent", return_value=agent_mock):
            msg = orchestrator.process_message(
                session=session,
                user_message="do a deep scan",
            )

        agent_mock.run.assert_called_once()
        assert msg.content == "Deep scan complete."


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestOrchestratorErrors:
    def test_process_message_wraps_exception(self, orchestrator, mock_session):
        session, _ = mock_session
        orchestrator.client.chat.completions.create.side_effect = RuntimeError("network error")

        with pytest.raises(OrchestratorError, match="network error"):
            orchestrator.process_message(session=session, user_message="hi")

    def test_suggest_alternatives_returns_string(self, orchestrator):
        resp = MagicMock()
        resp.choices[0].message.content = "Try doing X or Y."
        orchestrator.client.chat.completions.create.return_value = resp

        result = orchestrator.suggest_alternatives("some error", "user asked X")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_suggest_alternatives_fallback_on_exception(self, orchestrator):
        orchestrator.client.chat.completions.create.side_effect = Exception("API down")
        result = orchestrator.suggest_alternatives("error", "context")
        assert "try" in result.lower()
