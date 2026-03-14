"""MacMaint Interactive Assistant Module.

This module provides conversational AI capabilities for MacMaint through:
- Session management with cross-session persistence
- OpenAI function tools for MacMaint operations
- Interactive REPL interface
- AI orchestrator with streaming and function calling
- Specialised sub-agents for deep diagnostics, fixes, and trend analysis

Sprint 1: Foundation (session, tools, REPL)           – COMPLETED
Sprint 2: Orchestrator (GPT-4o, streaming, functions) – COMPLETED
Sprint 3: Sub-agents  (ScanAgent, FixAgent, Analysis) – COMPLETED
"""

__version__ = "0.4.0-dev"

from macmaint.assistant.session import (
    ConversationMessage,
    SessionState,
    SessionManager,
)

from macmaint.assistant.tools import (
    TOOLS,
    ToolExecutor,
)

from macmaint.assistant.repl import AssistantREPL

from macmaint.assistant.orchestrator import (
    Orchestrator,
    OrchestratorError,
)

from macmaint.assistant.agents import (
    SubAgent,
    ScanAgent,
    FixAgent,
    AnalysisAgent,
    create_agent,
    AGENT_REGISTRY,
)

from macmaint.assistant.prompts import (
    get_orchestrator_system_prompt,
    get_scan_agent_prompt,
    get_fix_agent_prompt,
    get_analysis_agent_prompt,
)

__all__ = [
    # Session management
    "ConversationMessage",
    "SessionState",
    "SessionManager",
    # Tools
    "TOOLS",
    "ToolExecutor",
    # REPL
    "AssistantREPL",
    # Orchestrator
    "Orchestrator",
    "OrchestratorError",
    # Sub-agents
    "SubAgent",
    "ScanAgent",
    "FixAgent",
    "AnalysisAgent",
    "create_agent",
    "AGENT_REGISTRY",
    # Prompts
    "get_orchestrator_system_prompt",
    "get_scan_agent_prompt",
    "get_fix_agent_prompt",
    "get_analysis_agent_prompt",
]

