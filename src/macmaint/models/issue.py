"""Issue data models for MacMaint."""
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class IssueSeverity(str, Enum):
    """Severity levels for system issues."""
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class IssueCategory(str, Enum):
    """Categories of system issues."""
    DISK = "disk"
    MEMORY = "memory"
    CPU = "cpu"
    SYSTEM = "system"
    STARTUP = "startup"
    NETWORK = "network"
    UPDATES = "updates"


class ActionType(str, Enum):
    """Types of fix actions."""
    DELETE_FILES = "delete_files"
    KILL_PROCESS = "kill_process"
    DISABLE_STARTUP_ITEM = "disable_startup_item"
    UPDATE_SOFTWARE = "update_software"
    MANUAL = "manual"


class FixAction(BaseModel):
    """A specific action to fix an issue."""
    action_type: ActionType
    description: str
    details: Dict[str, Any] = Field(default_factory=dict)
    estimated_impact: Optional[str] = None
    safe: bool = True
    requires_confirmation: bool = True


class Issue(BaseModel):
    """Represents a detected system issue."""
    id: str
    title: str
    description: str
    severity: IssueSeverity
    category: IssueCategory
    metrics: Dict[str, Any] = Field(default_factory=dict)
    fix_actions: List[FixAction] = Field(default_factory=list)
    ai_recommendation: Optional[str] = None
    
    def __str__(self) -> str:
        """String representation of the issue."""
        severity_icons = {
            IssueSeverity.CRITICAL: "🔴",
            IssueSeverity.WARNING: "🟡",
            IssueSeverity.INFO: "🔵",
        }
        icon = severity_icons.get(self.severity, "")
        return f"{icon} {self.title}"
