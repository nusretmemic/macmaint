"""Unit tests for SubAgent base class and concrete agent implementations."""

import json
from unittest.mock import MagicMock, patch

import pytest

from macmaint.assistant.agents import (
    ScanAgent,
    FixAgent,
    AnalysisAgent,
    SubAgent,
    create_agent,
    AGENT_REGISTRY,
    _SCAN_TOOLS,
    _FIX_TOOLS,
    _ANALYSIS_TOOLS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_openai_response(content: str, tool_calls=None):
    """Build a minimal mock that looks like an OpenAI chat completion response."""
    message = MagicMock()
    message.content = content
    message.tool_calls = tool_calls or []
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    return response


def _make_tool_call(name: str, arguments: dict, call_id: str = "call_1"):
    tc = MagicMock()
    tc.id = call_id
    tc.function.name = name
    tc.function.arguments = json.dumps(arguments)
    return tc


# ---------------------------------------------------------------------------
# Tool subset tests
# ---------------------------------------------------------------------------

class TestAgentToolSubsets:
    def test_scan_tools_names(self):
        names = {t["function"]["name"] for t in _SCAN_TOOLS}
        assert names == {"scan_system", "get_system_status", "get_disk_analysis"}

    def test_fix_tools_names(self):
        names = {t["function"]["name"] for t in _FIX_TOOLS}
        assert names == {"fix_issues", "clean_caches", "manage_startup_items"}

    def test_analysis_tools_names(self):
        names = {t["function"]["name"] for t in _ANALYSIS_TOOLS}
        assert names == {"show_trends", "get_system_status", "create_maintenance_plan"}


# ---------------------------------------------------------------------------
# SubAgent._parse_json_response
# ---------------------------------------------------------------------------

class TestParseJsonResponse:
    @pytest.fixture
    def agent(self, mock_profile_manager):
        client = MagicMock()
        executor = MagicMock()
        return ScanAgent(client, executor)

    def test_plain_json(self, agent):
        result = agent._parse_json_response('{"health_score": 80}')
        assert result["health_score"] == 80

    def test_fenced_json(self, agent):
        content = '```json\n{"health_score": 90}\n```'
        result = agent._parse_json_response(content)
        assert result["health_score"] == 90

    def test_invalid_json_falls_back(self, agent):
        result = agent._parse_json_response("This is not JSON at all.")
        assert "raw" in result
        assert "summary" in result


# ---------------------------------------------------------------------------
# SubAgent._agentic_loop — no tool calls (single-shot)
# ---------------------------------------------------------------------------

class TestAgenticLoopNoToolCalls:
    def test_returns_parsed_json_immediately(self, mock_profile_manager):
        client = MagicMock()
        executor = MagicMock()
        agent = ScanAgent(client, executor)

        final_json = json.dumps({"health_score": 75, "issues": [], "summary": "All good"})
        client.chat.completions.create.return_value = _make_openai_response(final_json)

        result = agent.run("scan the system", context={})
        assert result["health_score"] == 75
        assert result["_agent"] == "scan_agent"
        assert result["_task"] == "scan the system"


# ---------------------------------------------------------------------------
# SubAgent._agentic_loop — one tool call then final answer
# ---------------------------------------------------------------------------

class TestAgenticLoopWithToolCall:
    def test_tool_called_and_result_appended(self, mock_profile_manager):
        client = MagicMock()
        executor = MagicMock()
        executor.execute.return_value = {
            "success": True,
            "data": {"issues": [], "issue_count": 0},
            "summary": "Scan done",
        }

        agent = ScanAgent(client, executor)

        # First call: model requests a tool
        tc = _make_tool_call("scan_system", {"quick": False})
        first_response = _make_openai_response(None, tool_calls=[tc])

        # Second call: model returns final JSON
        final_json = json.dumps({"health_score": 90, "issues": [], "summary": "Clean"})
        second_response = _make_openai_response(final_json)

        client.chat.completions.create.side_effect = [first_response, second_response]

        result = agent.run("scan my system")
        assert result["health_score"] == 90
        executor.execute.assert_called_once_with("scan_system", {"quick": False})

    def test_on_progress_callback_fires(self, mock_profile_manager):
        client = MagicMock()
        executor = MagicMock()
        executor.execute.return_value = {"success": True, "data": {}, "summary": "done"}

        agent = AnalysisAgent(client, executor)
        tc = _make_tool_call("show_trends", {"days": 7})
        first_response = _make_openai_response(None, tool_calls=[tc])
        final_response = _make_openai_response('{"summary": "trends ok"}')
        client.chat.completions.create.side_effect = [first_response, final_response]

        calls = []
        agent.run("show trends", on_progress=calls.append)
        assert "show_trends" in calls

    def test_tool_exception_continues_loop(self, mock_profile_manager):
        """If a tool raises, the loop should feed the error back and continue."""
        client = MagicMock()
        executor = MagicMock()
        executor.execute.side_effect = RuntimeError("disk unavailable")

        agent = ScanAgent(client, executor)
        tc = _make_tool_call("scan_system", {})
        first_response = _make_openai_response(None, tool_calls=[tc])
        final_response = _make_openai_response('{"summary": "recovered", "issues": []}')
        client.chat.completions.create.side_effect = [first_response, final_response]

        result = agent.run("scan")
        assert "summary" in result


# ---------------------------------------------------------------------------
# Max iterations safety valve
# ---------------------------------------------------------------------------

class TestAgenticLoopMaxIterations:
    def test_max_iterations_returns_error_dict(self, mock_profile_manager):
        client = MagicMock()
        executor = MagicMock()
        executor.execute.return_value = {"success": True, "data": {}, "summary": "ok"}

        agent = FixAgent(client, executor)
        # Always return a tool call so the loop never terminates naturally
        tc = _make_tool_call("fix_issues", {"issue_ids": ["x"]})
        client.chat.completions.create.return_value = _make_openai_response(None, tool_calls=[tc])

        result = agent.run("fix everything")
        assert "error" in result
        assert "max_iterations" in result["error"]


# ---------------------------------------------------------------------------
# create_agent factory
# ---------------------------------------------------------------------------

class TestCreateAgent:
    def test_creates_scan_agent(self):
        agent = create_agent("scan_agent", MagicMock(), MagicMock())
        assert isinstance(agent, ScanAgent)

    def test_creates_fix_agent(self):
        agent = create_agent("fix_agent", MagicMock(), MagicMock())
        assert isinstance(agent, FixAgent)

    def test_creates_analysis_agent(self):
        agent = create_agent("analysis_agent", MagicMock(), MagicMock())
        assert isinstance(agent, AnalysisAgent)

    def test_unknown_agent_raises(self):
        with pytest.raises(ValueError, match="Unknown agent"):
            create_agent("nonexistent_agent", MagicMock(), MagicMock())

    def test_registry_complete(self):
        assert set(AGENT_REGISTRY.keys()) == {"scan_agent", "fix_agent", "analysis_agent"}
