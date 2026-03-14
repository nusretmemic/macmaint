"""Unit tests for SessionManager and related data models."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from macmaint.assistant.session import (
    ConversationMessage,
    SessionManager,
    SessionState,
)


# ---------------------------------------------------------------------------
# ConversationMessage
# ---------------------------------------------------------------------------

class TestConversationMessage:
    def test_round_trip_dict(self):
        msg = ConversationMessage(
            role="user",
            content="Hello",
            timestamp=datetime.now().isoformat(),
        )
        assert ConversationMessage.from_dict(msg.to_dict()) == msg

    def test_to_openai_format_basic(self):
        msg = ConversationMessage(role="user", content="hi", timestamp="2026-01-01")
        fmt = msg.to_openai_format()
        assert fmt["role"] == "user"
        assert fmt["content"] == "hi"
        assert "tool_calls" not in fmt
        assert "tool_call_id" not in fmt

    def test_to_openai_format_with_tool_calls(self):
        tc = [{"id": "call_1", "type": "function", "function": {"name": "scan_system", "arguments": "{}"}}]
        msg = ConversationMessage(role="assistant", content=None, timestamp="2026-01-01", tool_calls=tc)
        fmt = msg.to_openai_format()
        assert fmt["tool_calls"] == tc

    def test_from_openai_format(self):
        raw = {"role": "assistant", "content": "Done."}
        msg = ConversationMessage.from_openai_format(raw)
        assert msg.role == "assistant"
        assert msg.content == "Done."


# ---------------------------------------------------------------------------
# SessionState
# ---------------------------------------------------------------------------

class TestSessionState:
    def test_round_trip_dict(self):
        state = SessionState(
            session_id="session_20260101_120000",
            started_at=datetime.now().isoformat(),
            last_active=datetime.now().isoformat(),
            messages=[
                ConversationMessage(role="user", content="hey", timestamp=datetime.now().isoformat())
            ],
            trust_mode="auto_fix_safe",
        )
        restored = SessionState.from_dict(state.to_dict())
        assert restored.session_id == state.session_id
        assert restored.trust_mode == "auto_fix_safe"
        assert len(restored.messages) == 1
        assert restored.messages[0].content == "hey"


# ---------------------------------------------------------------------------
# SessionManager (uses tmp_path for isolation)
# ---------------------------------------------------------------------------

@pytest.fixture
def session_manager(tmp_path, mock_config, mock_profile_manager):
    with patch("macmaint.assistant.session.DataAnonymizer") as MockAnon:
        MockAnon.return_value._anonymize_string = lambda s: s
        mgr = SessionManager(mock_config, mock_profile_manager)
        mgr.conversations_dir = tmp_path / "conversations"
        mgr.conversations_dir.mkdir()
        yield mgr


class TestSessionManager:
    def test_create_new_session(self, session_manager):
        session = session_manager.create_new_session()
        assert session.session_id.startswith("session_")
        assert session.messages == []
        assert session.trust_mode is None

    def test_force_new_ignores_existing(self, session_manager):
        s1 = session_manager.create_new_session()
        session_manager.save_session(s1)
        s2 = session_manager.get_or_create_latest(force_new=True)
        assert s2.session_id != s1.session_id

    def test_get_or_create_resumes_latest(self, session_manager):
        s1 = session_manager.create_new_session()
        session_manager.add_message(s1, "user", "hello")
        session_manager.save_session(s1)

        resumed = session_manager.get_or_create_latest(force_new=False)
        assert resumed.session_id == s1.session_id
        assert len(resumed.messages) == 1

    def test_save_and_load_roundtrip(self, session_manager):
        s = session_manager.create_new_session()
        session_manager.add_message(s, "user", "test message")
        session_manager.save_session(s)

        loaded = session_manager.load_session(s.session_id)
        assert loaded.session_id == s.session_id
        assert loaded.messages[0].content == "test message"

    def test_add_message(self, session_manager):
        s = session_manager.create_new_session()
        session_manager.add_message(s, "user", "ping")
        session_manager.add_message(s, "assistant", "pong")
        assert len(s.messages) == 2
        assert s.messages[0].role == "user"
        assert s.messages[1].role == "assistant"

    def test_truncation_to_100(self, session_manager):
        s = session_manager.create_new_session()
        for i in range(110):
            session_manager.add_message(s, "user", f"msg {i}")
        session_manager.save_session(s)

        loaded = session_manager.load_session(s.session_id)
        assert len(loaded.messages) == 100

    def test_trust_mode_set_get_clear(self, session_manager):
        s = session_manager.create_new_session()
        assert session_manager.get_trust_mode(s) is None

        session_manager.set_trust_mode(s, "auto_fix_safe")
        assert session_manager.get_trust_mode(s) == "auto_fix_safe"

        session_manager.clear_trust_mode(s)
        assert session_manager.get_trust_mode(s) is None

    def test_cleanup_old_sessions(self, session_manager):
        s = session_manager.create_new_session()
        session_manager.save_session(s)
        session_file = session_manager.conversations_dir / f"{s.session_id}.json"

        # Back-date the file's mtime by 35 days
        old_time = (datetime.now() - timedelta(days=35)).timestamp()
        import os
        os.utime(session_file, (old_time, old_time))

        deleted = session_manager.cleanup_old_sessions(retention_days=30)
        assert deleted == 1
        assert not session_file.exists()

    def test_list_sessions(self, session_manager):
        for _ in range(3):
            s = session_manager.create_new_session()
            session_manager.save_session(s)

        sessions = session_manager.list_sessions(limit=10)
        assert len(sessions) == 3
        for item in sessions:
            assert "session_id" in item
            assert "message_count" in item

    def test_get_session_summary(self, session_manager):
        s = session_manager.create_new_session()
        session_manager.add_message(s, "user", "hi")
        summary = session_manager.get_session_summary(s)
        assert s.session_id in summary
        assert "Messages: 1" in summary

    def test_load_nonexistent_raises(self, session_manager):
        with pytest.raises(FileNotFoundError):
            session_manager.load_session("session_does_not_exist")

    def test_get_messages_for_api_within_budget(self, session_manager):
        s = session_manager.create_new_session()
        session_manager.add_message(s, "user", "hello")
        session_manager.add_message(s, "assistant", "hi there")
        msgs = session_manager.get_messages_for_api(s)
        assert len(msgs) == 2

    def test_get_messages_for_api_truncates_when_over_budget(self, session_manager):
        s = session_manager.create_new_session()
        # Add 30 very long messages to exceed the token budget
        for i in range(30):
            session_manager.add_message(s, "user", "x" * 1000)
            session_manager.add_message(s, "assistant", "y" * 1000)
        msgs = session_manager.get_messages_for_api(s, max_tokens=500)
        assert len(msgs) <= 20
