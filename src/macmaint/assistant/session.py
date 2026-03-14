"""Session management for interactive assistant mode.

Handles conversation state persistence across multiple 'macmaint start' invocations.
"""

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

from macmaint.config import Config
from macmaint.utils.profile import ProfileManager
from macmaint.ai.anonymizer import DataAnonymizer


@dataclass
class ConversationMessage:
    """Single message in conversation history."""
    role: str  # "user", "assistant", "system", "tool"
    content: str
    timestamp: str  # ISO format
    
    # OpenAI function calling support
    tool_calls: Optional[List[Dict]] = None  # For assistant calling tools
    tool_call_id: Optional[str] = None       # For tool responses
    name: Optional[str] = None               # Tool name for tool responses
    
    def to_openai_format(self) -> Dict:
        """Convert to OpenAI API message format."""
        msg = {
            "role": self.role,
            "content": self.content
        }
        
        if self.tool_calls:
            msg["tool_calls"] = self.tool_calls
        
        if self.tool_call_id:
            msg["tool_call_id"] = self.tool_call_id
        
        if self.name:
            msg["name"] = self.name
        
        return msg
    
    @staticmethod
    def from_openai_format(msg: Dict) -> 'ConversationMessage':
        """Create from OpenAI API message."""
        return ConversationMessage(
            role=msg["role"],
            content=msg.get("content", ""),
            timestamp=datetime.now().isoformat(),
            tool_calls=msg.get("tool_calls"),
            tool_call_id=msg.get("tool_call_id"),
            name=msg.get("name")
        )
    
    def to_dict(self) -> Dict:
        """Serialize to dictionary."""
        return asdict(self)
    
    @staticmethod
    def from_dict(data: Dict) -> 'ConversationMessage':
        """Deserialize from dictionary."""
        return ConversationMessage(**data)


@dataclass
class SessionState:
    """Complete session state including conversation history."""
    session_id: str  # Format: "session_YYYYMMDD_HHMMSS_ffffff"
    started_at: str  # ISO timestamp
    last_active: str  # ISO timestamp (updated on each turn)
    messages: List[ConversationMessage]
    
    # Session-scoped settings
    trust_mode: Optional[str] = None  # None, "auto_fix_safe", "ask_always"
    current_workflow: Optional[str] = None  # e.g., "video_editing_optimization"
    
    # Metadata for display
    metadata: Dict = field(default_factory=dict)  # message_count, tokens_used, etc.
    
    def to_dict(self) -> Dict:
        """Serialize to dictionary for JSON storage."""
        return {
            "session_id": self.session_id,
            "started_at": self.started_at,
            "last_active": self.last_active,
            "messages": [msg.to_dict() for msg in self.messages],
            "trust_mode": self.trust_mode,
            "current_workflow": self.current_workflow,
            "metadata": self.metadata
        }
    
    @staticmethod
    def from_dict(data: Dict) -> 'SessionState':
        """Deserialize from dictionary."""
        return SessionState(
            session_id=data["session_id"],
            started_at=data["started_at"],
            last_active=data["last_active"],
            messages=[ConversationMessage.from_dict(m) for m in data["messages"]],
            trust_mode=data.get("trust_mode"),
            current_workflow=data.get("current_workflow"),
            metadata=data.get("metadata", {})
        )


class SessionManager:
    """Manages session lifecycle and persistence."""
    
    def __init__(self, config: Config, profile_manager: ProfileManager):
        """Initialize session manager.
        
        Args:
            config: Application configuration
            profile_manager: User profile manager for context
        """
        self.config = config
        self.profile_manager = profile_manager
        self.conversations_dir = Path.home() / ".macmaint" / "conversations"
        self.conversations_dir.mkdir(parents=True, exist_ok=True)
        self.anonymizer = DataAnonymizer()
        self.current_session: Optional[SessionState] = None
    
    # Session lifecycle
    
    def get_or_create_latest(self, force_new: bool = False) -> SessionState:
        """Resume most recent session or create new one.
        
        Args:
            force_new: If True, always create new session
        
        Returns:
            SessionState instance
        """
        if force_new:
            return self.create_new_session()
        
        # Find most recent session
        latest = self._find_latest_session()
        if latest:
            try:
                return self.load_session(latest)
            except Exception as e:
                # If loading fails, create new session
                print(f"Warning: Could not load session {latest}: {e}")
                return self.create_new_session()
        
        return self.create_new_session()
    
    def create_new_session(self) -> SessionState:
        """Create a new session.
        
        Returns:
            New SessionState instance
        """
        session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        session = SessionState(
            session_id=session_id,
            started_at=datetime.now().isoformat(),
            last_active=datetime.now().isoformat(),
            messages=[]
        )
        self.current_session = session
        return session
    
    def load_session(self, session_id: str) -> SessionState:
        """Load session from disk.
        
        Args:
            session_id: Session ID to load
        
        Returns:
            Loaded SessionState
        
        Raises:
            FileNotFoundError: If session file doesn't exist
        """
        session_file = self.conversations_dir / f"{session_id}.json"
        if not session_file.exists():
            raise FileNotFoundError(f"Session {session_id} not found")
        
        with open(session_file, 'r') as f:
            data = json.load(f)
        
        session = SessionState.from_dict(data)
        self.current_session = session
        return session
    
    def save_session(self, session: SessionState) -> None:
        """Save session to disk with anonymization.
        
        Args:
            session: Session to save
        """
        # Update metadata
        session.last_active = datetime.now().isoformat()
        session.metadata['message_count'] = len(session.messages)
        
        # Convert to dict
        session_dict = session.to_dict()
        
        # Anonymize sensitive data
        anonymized = self._anonymize_session_data(session_dict)
        
        # Truncate if too many messages (keep last 100)
        if len(anonymized['messages']) > 100:
            anonymized['messages'] = anonymized['messages'][-100:]
            anonymized['metadata']['truncated'] = True
        
        # Save to file
        session_file = self.conversations_dir / f"{session.session_id}.json"
        with open(session_file, 'w') as f:
            json.dump(anonymized, f, indent=2)
        
        # Update "latest" symlink
        self._update_latest_link(session.session_id)
    
    # Message management
    
    def add_message(
        self,
        session: SessionState,
        role: str,
        content: str,
        **kwargs
    ) -> None:
        """Add a message to the conversation.
        
        Args:
            session: Session to add message to
            role: Message role ("user", "assistant", "system", "tool")
            content: Message content
            **kwargs: Additional message attributes (tool_calls, tool_call_id, name)
        """
        msg = ConversationMessage(
            role=role,
            content=content,
            timestamp=datetime.now().isoformat(),
            **kwargs
        )
        session.messages.append(msg)
    
    def get_messages_for_api(
        self,
        session: SessionState,
        max_tokens: int = 6000
    ) -> List[Dict]:
        """Get messages in OpenAI format, truncating if needed.
        
        Strategy:
        - Always include system prompt (first message if role="system")
        - Include as many recent messages as fit in token budget
        - If approaching limit, keep system + last 20 messages
        
        Args:
            session: Session to get messages from
            max_tokens: Maximum token budget
        
        Returns:
            List of messages in OpenAI format
        """
        messages = [msg.to_openai_format() for msg in session.messages]
        
        if not messages:
            return []
        
        # Simple token estimation (1 token ≈ 4 chars)
        total_tokens = sum(len(json.dumps(m)) // 4 for m in messages)
        
        if total_tokens <= max_tokens:
            return messages
        
        # Keep system + last 20 messages
        system_msgs = [m for m in messages if m["role"] == "system"]
        other_msgs = [m for m in messages if m["role"] != "system"]
        
        if len(other_msgs) > 20:
            recent = other_msgs[-20:]
            return system_msgs + recent
        
        return messages
    
    # Trust mode management
    
    def set_trust_mode(self, session: SessionState, mode: str) -> None:
        """Set trust mode for current session.
        
        Args:
            session: Session to update
            mode: Trust mode ("auto_fix_safe" or "ask_always")
        """
        session.trust_mode = mode
        self.save_session(session)
    
    def get_trust_mode(self, session: SessionState) -> Optional[str]:
        """Get current trust mode.
        
        Args:
            session: Session to query
        
        Returns:
            Current trust mode or None
        """
        return session.trust_mode
    
    def clear_trust_mode(self, session: SessionState) -> None:
        """Clear trust mode (called on session exit).
        
        Args:
            session: Session to update
        """
        session.trust_mode = None
        self.save_session(session)
    
    # Utilities
    
    def list_sessions(self, limit: int = 10) -> List[Dict]:
        """List recent sessions.
        
        Args:
            limit: Maximum number of sessions to return
        
        Returns:
            List of session info dictionaries
        """
        session_files = sorted(
            self.conversations_dir.glob("session_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )[:limit]
        
        sessions = []
        for file in session_files:
            try:
                with open(file, 'r') as f:
                    data = json.load(f)
                sessions.append({
                    'session_id': data['session_id'],
                    'started_at': data['started_at'],
                    'last_active': data['last_active'],
                    'message_count': len(data['messages'])
                })
            except Exception:
                # Skip corrupted files
                continue
        
        return sessions
    
    def cleanup_old_sessions(self, retention_days: int = 30) -> int:
        """Delete sessions older than retention_days.
        
        Args:
            retention_days: Number of days to retain sessions
        
        Returns:
            Number of sessions deleted
        """
        cutoff = datetime.now() - timedelta(days=retention_days)
        deleted = 0
        
        for file in self.conversations_dir.glob("session_*.json"):
            try:
                if file.stat().st_mtime < cutoff.timestamp():
                    file.unlink()
                    deleted += 1
            except Exception:
                # Skip files we can't delete
                continue

        return deleted

    def delete_session(self, session_id: str) -> bool:
        """Delete a specific session by ID.

        Args:
            session_id: The session ID to delete.

        Returns:
            True if the file was deleted, False if it did not exist.

        Raises:
            ValueError: If session_id matches the currently active session.
        """
        if self.current_session and self.current_session.session_id == session_id:
            raise ValueError("Cannot delete the currently active session")

        session_file = self.conversations_dir / f"{session_id}.json"
        if not session_file.exists():
            return False

        session_file.unlink()

        # If the deleted session was the latest symlink target, remove the symlink too
        latest = self.conversations_dir / "latest.json"
        if latest.is_symlink():
            try:
                if latest.resolve() == session_file.resolve():
                    latest.unlink()
            except Exception:
                pass

        return True

    def delete_all_sessions(self) -> int:
        """Delete ALL saved sessions except the currently active one.

        Returns:
            Number of session files deleted.
        """
        deleted = 0
        active_id = self.current_session.session_id if self.current_session else None

        for file in self.conversations_dir.glob("session_*.json"):
            try:
                # Parse the session_id from filename (session_<id>.json)
                sid = file.stem  # e.g. "session_20240101_120000_abc"
                if active_id and sid == active_id:
                    continue
                file.unlink()
                deleted += 1
            except Exception:
                continue

        # Clean up latest.json symlink if it dangled
        latest = self.conversations_dir / "latest.json"
        if latest.is_symlink() and not latest.exists():
            try:
                latest.unlink()
            except Exception:
                pass

        return deleted
        
        return deleted
    
    def get_session_summary(self, session: SessionState) -> str:
        """Get human-readable session summary for display.
        
        Args:
            session: Session to summarize
        
        Returns:
            Formatted summary string
        """
        duration = "just started"
        if session.messages:
            start = datetime.fromisoformat(session.started_at)
            last = datetime.fromisoformat(session.last_active)
            minutes = (last - start).seconds // 60
            if minutes > 0:
                duration = f"{minutes} minute{'s' if minutes != 1 else ''}"
        
        return f"""Session: {session.session_id}
Started: {session.started_at}
Duration: {duration}
Messages: {len(session.messages)}
Trust Mode: {session.trust_mode or 'Not set'}"""
    
    # Private helpers
    
    def _find_latest_session(self) -> Optional[str]:
        """Find most recent session ID.
        
        Returns:
            Session ID or None if no sessions exist
        """
        # Check for symlink first
        latest_link = self.conversations_dir / "latest.json"
        if latest_link.is_symlink():
            try:
                target = latest_link.resolve()
                if target.exists():
                    return target.stem
            except Exception:
                pass
        
        # Fallback: find most recent by modification time
        session_files = sorted(
            self.conversations_dir.glob("session_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        if session_files:
            return session_files[0].stem
        
        return None
    
    def _update_latest_link(self, session_id: str) -> None:
        """Update symlink to latest session.
        
        Args:
            session_id: Session ID to link to
        """
        latest_link = self.conversations_dir / "latest.json"
        target = self.conversations_dir / f"{session_id}.json"
        
        # Remove existing link
        if latest_link.exists() or latest_link.is_symlink():
            try:
                latest_link.unlink()
            except Exception:
                pass
        
        # Create new symlink
        try:
            latest_link.symlink_to(target)
        except Exception:
            # Symlinks might not work on all systems, that's ok
            pass
    
    def _anonymize_session_data(self, session_dict: Dict) -> Dict:
        """Anonymize session data before saving.
        
        Args:
            session_dict: Session dictionary to anonymize
        
        Returns:
            Anonymized session dictionary
        """
        for msg in session_dict['messages']:
            # M6 fix: only anonymize plain-text assistant responses.
            # - tool role messages contain JSON with structural identifiers (tool_call_id,
            #   plist labels, etc.) — anonymizing them corrupts history on resume.
            # - assistant messages that carry tool_calls have structured JSON content too.
            # - user messages are left untouched (need context for conversation).
            if msg['role'] == 'assistant' and not msg.get('tool_calls') and msg.get('content'):
                msg['content'] = self.anonymizer._anonymize_string(msg['content'])
        
        return session_dict
