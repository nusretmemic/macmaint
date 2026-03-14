"""AI Orchestrator for conversational MacMaint assistant.

The orchestrator is responsible for:
- Processing user messages with OpenAI API
- Handling function calling and tool execution
- Delegating complex tasks to specialised sub-agents (Sprint 3)
- Managing streaming responses
- Error recovery and alternative suggestions
- Multi-step workflow coordination
"""

import json
from typing import Callable, Dict, List, Optional

from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam

from macmaint.config import Config
from macmaint.assistant.session import SessionState, ConversationMessage
from macmaint.assistant.tools import ToolExecutor, TOOLS
from macmaint.assistant.prompts import get_orchestrator_system_prompt
from macmaint.assistant.agents import create_agent
from macmaint.utils.profile import ProfileManager


class OrchestratorError(Exception):
    """Base exception for orchestrator errors."""
    pass


class Orchestrator:
    """Main AI orchestrator for conversational assistant.

    Uses GPT-4o with OpenAI function calling to understand user intent,
    execute tools, delegate to sub-agents, and provide intelligent responses.
    """

    def __init__(
        self,
        config: Config,
        tool_executor: ToolExecutor,
        profile_manager: ProfileManager,
    ):
        """Initialise orchestrator.

        Args:
            config:          Application configuration.
            tool_executor:   Tool executor for MacMaint operations.
            profile_manager: User profile manager for personalisation.
        """
        self.config = config
        self.tool_executor = tool_executor
        self.profile_manager = profile_manager

        api_key = config.api_key
        if not api_key:
            raise OrchestratorError(
                "OpenAI API key not found. Set OPENAI_API_KEY in ~/.macmaint/.env"
            )

        self.client = OpenAI(api_key=api_key)
        self.model = "gpt-4o"

        profile = self.profile_manager.load()
        profile_summary = {
            "cleanup_frequency": profile.usage_patterns.cleanup_frequency,
            "most_common_issues": (
                profile.usage_patterns.most_common_issues[:3]
                if profile.usage_patterns.most_common_issues
                else []
            ),
        }
        self.system_prompt = get_orchestrator_system_prompt(profile_summary)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process_message(
        self,
        session: SessionState,
        user_message: str,
        on_stream_chunk: Optional[Callable[[str], None]] = None,
        on_tool_call: Optional[Callable[[str, Dict], None]] = None,
    ) -> ConversationMessage:
        """Process a user message and return the assistant's response.

        Supports streaming text and tool-call / sub-agent progress callbacks.

        Args:
            session:         Current session state.
            user_message:    User's message text.
            on_stream_chunk: Called with each streamed text chunk.
            on_tool_call:    Called when a tool or sub-agent is invoked
                             (tool_name, args).

        Returns:
            ConversationMessage with the final assistant response.

        Raises:
            OrchestratorError: If processing fails.
        """
        try:
            messages = self._build_messages(session, user_message)
            response_text = self._run_streaming_loop(
                messages, on_stream_chunk, on_tool_call, session
            )
            return ConversationMessage(
                role="assistant",
                content=response_text,
                timestamp=None,  # set by SessionManager
            )
        except Exception as exc:
            raise OrchestratorError(f"Failed to process message: {exc}") from exc

    def suggest_alternatives(self, error_message: str, context: str) -> str:
        """Generate alternative suggestions when an error occurs."""
        try:
            prompt = (
                f"An error occurred while trying to help the user:\n\n"
                f"Context: {context}\nError: {error_message}\n\n"
                "Suggest 2-3 alternative approaches the user could try. "
                "Be specific and actionable."
            )
            messages: List[ChatCompletionMessageParam] = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": prompt},
            ]
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.8,
                max_tokens=500,
            )
            return resp.choices[0].message.content or "Could not generate alternatives."
        except Exception:
            return (
                "I encountered an error and couldn't process your request. "
                "Please try:\n"
                "1. Running a system scan: 'scan my Mac'\n"
                "2. Checking system status: 'how is my Mac doing?'\n"
                "3. Asking for help with a specific issue"
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_messages(
        self, session: SessionState, user_message: str
    ) -> List[ChatCompletionMessageParam]:
        messages: List[ChatCompletionMessageParam] = [
            {"role": "system", "content": self.system_prompt}
        ]
        for msg in session.messages:
            messages.append({"role": msg.role, "content": msg.content or ""})
        messages.append({"role": "user", "content": user_message})
        return messages

    def _run_streaming_loop(
        self,
        messages: List[ChatCompletionMessageParam],
        on_stream_chunk: Optional[Callable[[str], None]],
        on_tool_call: Optional[Callable[[str, Dict], None]],
        session: SessionState,
        max_rounds: int = 8,
    ) -> str:
        """Streaming tool-call loop.

        Each round either produces streamed text (done) or tool calls
        (which are executed / delegated, then the loop continues).
        """
        accumulated_text = ""

        for _round in range(max_rounds):
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                stream=True,
                temperature=0.7,
                max_tokens=2000,
            )

            round_text = ""
            tool_calls_data: List[Dict] = []
            current_tc: Optional[Dict] = None

            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta

                if delta.content:
                    round_text += delta.content
                    accumulated_text += delta.content
                    if on_stream_chunk:
                        on_stream_chunk(delta.content)

                if delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if current_tc is None or idx != current_tc.get("index"):
                            if current_tc is not None:
                                tool_calls_data.append(current_tc)
                            current_tc = {
                                "index": idx,
                                "id": tc_delta.id or "",
                                "type": "function",
                                "function": {
                                    "name": (
                                        tc_delta.function.name or ""
                                        if tc_delta.function else ""
                                    ),
                                    "arguments": (
                                        tc_delta.function.arguments or ""
                                        if tc_delta.function else ""
                                    ),
                                },
                            }
                        else:
                            if tc_delta.id:
                                current_tc["id"] += tc_delta.id
                            if tc_delta.function:
                                if tc_delta.function.name:
                                    current_tc["function"]["name"] += tc_delta.function.name
                                if tc_delta.function.arguments:
                                    current_tc["function"]["arguments"] += (
                                        tc_delta.function.arguments
                                    )

            if current_tc is not None:
                tool_calls_data.append(current_tc)

            # No tool calls → streaming finished, return
            if not tool_calls_data:
                return accumulated_text

            # Append assistant turn with tool_calls
            messages.append({
                "role": "assistant",
                "content": round_text or None,
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["function"]["name"],
                            "arguments": tc["function"]["arguments"],
                        },
                    }
                    for tc in tool_calls_data
                ],
            })

            # Execute each tool call
            for tc in tool_calls_data:
                fn_name = tc["function"]["name"]
                try:
                    fn_args = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError:
                    fn_args = {}

                if on_tool_call:
                    on_tool_call(fn_name, fn_args)

                try:
                    if fn_name == "delegate_to_sub_agent":
                        result = self._run_sub_agent(fn_args, session, on_tool_call)
                    else:
                        if fn_name == "fix_issues" and session.trust_mode:
                            fn_args["auto_approve"] = True
                        result = self.tool_executor.execute(fn_name, fn_args)
                except Exception as exc:
                    result = {
                        "success": False,
                        "error": str(exc),
                        "summary": f"{fn_name} failed: {exc}",
                    }

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(result),
                })

        # Exceeded max_rounds - return what we have
        return accumulated_text

    def _run_sub_agent(
        self,
        args: Dict,
        session: SessionState,
        on_tool_call: Optional[Callable[[str, Dict], None]],
    ) -> Dict:
        """Instantiate and run a sub-agent, returning its result as a dict.

        Args:
            args:        Arguments from the delegate_to_sub_agent tool call.
            session:     Current session (for trust_mode, etc.).
            on_tool_call: Progress callback forwarded to the sub-agent.
        """
        agent_name = args.get("agent", "")
        task = args.get("task", "")
        context: Dict = args.get("context") or {}

        # Propagate trust_mode into fix_agent context
        if agent_name == "fix_agent" and session.trust_mode:
            context.setdefault("auto_approve", True)

        try:
            agent = create_agent(agent_name, self.client, self.tool_executor)

            def _progress(tool_name: str) -> None:
                if on_tool_call:
                    on_tool_call(f"{agent_name}:{tool_name}", {})

            result = agent.run(task, context, on_progress=_progress)
            return {"success": True, "data": result, "summary": result.get("summary", "")}

        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
                "summary": f"Sub-agent '{agent_name}' failed: {exc}",
            }

