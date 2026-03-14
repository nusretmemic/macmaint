"""Sub-agent implementations for MacMaint Sprint 3.

Each sub-agent is a focused specialist that:
- Uses gpt-4o-mini (cost-efficient)
- Receives a narrow task from the Orchestrator
- Calls only the tools it needs
- Returns a structured JSON result

Agents
------
ScanAgent     – system diagnostics and issue prioritisation
FixAgent      – safe execution of maintenance fixes
AnalysisAgent – historical trend analysis and projections
"""

import json
import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam

from macmaint.assistant.prompts import (
    get_scan_agent_prompt,
    get_fix_agent_prompt,
    get_analysis_agent_prompt,
)
from macmaint.assistant.tools import ToolExecutor, TOOLS

# Sub-agents get a focused subset of the full tool list
_SCAN_TOOLS = [
    t for t in TOOLS
    if t["function"]["name"] in {"scan_system", "get_system_status", "get_disk_analysis"}
]

_FIX_TOOLS = [
    t for t in TOOLS
    if t["function"]["name"] in {"fix_issues", "clean_caches", "optimize_memory", "manage_startup_items"}
]

_ANALYSIS_TOOLS = [
    t for t in TOOLS
    if t["function"]["name"] in {"show_trends", "get_system_status", "create_maintenance_plan"}
]


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------

class SubAgent(ABC):
    """Base class for all MacMaint sub-agents."""

    #: Override in subclasses
    NAME: str = "sub_agent"
    MODEL: str = "gpt-4o-mini"

    def __init__(self, client: OpenAI, tool_executor: ToolExecutor):
        self.client = client
        self.tool_executor = tool_executor

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        task: str,
        context: Optional[Dict] = None,
        on_progress: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        """Run the sub-agent on a task and return a structured result.

        Args:
            task:        Natural-language task description from the Orchestrator.
            context:     Optional dict of extra context (e.g. trust_mode, issue_ids).
            on_progress: Optional callback for progress updates (tool names, etc.).

        Returns:
            Parsed JSON dict from the sub-agent, plus a top-level ``_agent`` key.
        """
        messages = self._build_initial_messages(task, context)
        tools = self._get_tools()

        result = self._agentic_loop(messages, tools, on_progress)
        result["_agent"] = self.NAME
        result["_task"] = task
        return result

    # ------------------------------------------------------------------
    # Overridable helpers
    # ------------------------------------------------------------------

    @abstractmethod
    def _get_system_prompt(self) -> str:
        """Return the system prompt for this agent."""

    def _get_tools(self) -> List[Dict]:
        """Return the OpenAI tool schemas available to this agent."""
        return []

    # ------------------------------------------------------------------
    # Internal loop
    # ------------------------------------------------------------------

    def _build_initial_messages(
        self, task: str, context: Optional[Dict]
    ) -> List[ChatCompletionMessageParam]:
        messages: List[ChatCompletionMessageParam] = [
            {"role": "system", "content": self._get_system_prompt()},
        ]
        user_content = task
        if context:
            user_content += f"\n\nContext: {json.dumps(context)}"
        messages.append({"role": "user", "content": user_content})
        return messages

    def _agentic_loop(
        self,
        messages: List[ChatCompletionMessageParam],
        tools: List[Dict],
        on_progress: Optional[Callable[[str], None]],
        max_iterations: int = 6,
    ) -> Dict[str, Any]:
        """Run the tool-calling agentic loop until the model stops calling tools.

        Returns the parsed JSON body from the final assistant message.
        """
        for _iteration in range(max_iterations):
            kwargs: Dict[str, Any] = {
                "model": self.MODEL,
                "messages": messages,
                "temperature": 0.2,   # sub-agents need determinism
                "max_tokens": 2000,
            }
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"

            response = self.client.chat.completions.create(**kwargs)
            message = response.choices[0].message

            # ---- no tool calls → this is the final answer ----
            if not message.tool_calls:
                content = message.content or "{}"
                return self._parse_json_response(content)

            # ---- execute tool calls ----
            # Append assistant turn (with tool_calls)
            messages.append({
                "role": "assistant",
                "content": message.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in message.tool_calls
                ],
            })

            for tc in message.tool_calls:
                fn_name = tc.function.name
                try:
                    fn_args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    fn_args = {}

                if on_progress:
                    on_progress(fn_name)

                try:
                    tool_result = self.tool_executor.execute(fn_name, fn_args)
                except Exception as exc:
                    tool_result = {
                        "success": False,
                        "error": str(exc),
                        "summary": f"{fn_name} failed: {exc}",
                    }

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(tool_result),
                })

        # Safety valve – should not normally be reached
        return {
            "error": "max_iterations reached",
            "summary": "Sub-agent did not produce a final answer within the iteration limit.",
        }

    def _parse_json_response(self, content: str) -> Dict[str, Any]:
        """Extract the JSON object from the model's final response.

        Handles fenced code blocks like ```json ... ```.
        """
        stripped = content.strip()

        # Strip ```json ... ``` fences if present
        if stripped.startswith("```"):
            lines = stripped.splitlines()
            # Remove first line (```json or ```) and last line (```)
            inner = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
            stripped = inner.strip()

        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            # Fall back: wrap raw text so callers always get a dict
            return {"raw": content, "summary": content[:300]}


# ---------------------------------------------------------------------------
# ScanAgent
# ---------------------------------------------------------------------------

class ScanAgent(SubAgent):
    """Specialist for system diagnostics and issue prioritisation."""

    NAME = "scan_agent"

    def _get_system_prompt(self) -> str:
        return get_scan_agent_prompt()

    def _get_tools(self) -> List[Dict]:
        return _SCAN_TOOLS


# ---------------------------------------------------------------------------
# FixAgent
# ---------------------------------------------------------------------------

class FixAgent(SubAgent):
    """Specialist for safely applying maintenance fixes."""

    NAME = "fix_agent"

    def _get_system_prompt(self) -> str:
        return get_fix_agent_prompt()

    def _get_tools(self) -> List[Dict]:
        return _FIX_TOOLS


# ---------------------------------------------------------------------------
# AnalysisAgent
# ---------------------------------------------------------------------------

class AnalysisAgent(SubAgent):
    """Specialist for historical trend analysis and projections."""

    NAME = "analysis_agent"

    def _get_system_prompt(self) -> str:
        return get_analysis_agent_prompt()

    def _get_tools(self) -> List[Dict]:
        return _ANALYSIS_TOOLS


# ---------------------------------------------------------------------------
# Registry helper
# ---------------------------------------------------------------------------

AGENT_REGISTRY: Dict[str, type] = {
    "scan_agent": ScanAgent,
    "fix_agent": FixAgent,
    "analysis_agent": AnalysisAgent,
}


def create_agent(
    agent_name: str,
    client: OpenAI,
    tool_executor: ToolExecutor,
) -> SubAgent:
    """Factory function to instantiate a sub-agent by name.

    Args:
        agent_name:    One of "scan_agent", "fix_agent", "analysis_agent".
        client:        Shared OpenAI client.
        tool_executor: Shared ToolExecutor.

    Returns:
        Instantiated SubAgent.

    Raises:
        ValueError: If agent_name is not recognised.
    """
    cls = AGENT_REGISTRY.get(agent_name)
    if cls is None:
        raise ValueError(
            f"Unknown agent '{agent_name}'. "
            f"Available: {list(AGENT_REGISTRY.keys())}"
        )
    return cls(client, tool_executor)
