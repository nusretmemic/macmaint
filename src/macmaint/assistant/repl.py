"""Interactive REPL interface for conversational AI assistant.

Provides a Rich terminal interface for multi-turn conversations with
line-by-line streaming and Markdown rendering.
"""

import sys
from typing import Dict, List, Optional, Tuple

from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich import box

from macmaint.assistant.session import SessionManager, SessionState
from macmaint.assistant.tools import ToolExecutor
from macmaint.utils.formatters import console, confirm, print_error, print_success, print_info
from datetime import datetime


# Human-readable labels for each tool name
TOOL_LABELS: Dict[str, str] = {
    "scan_system":            "Scanning your system",
    "fix_issues":             "Fixing issues",
    "clean_caches":           "Cleaning caches",
    "optimize_memory":        "Optimising memory",
    "manage_startup_items":   "Managing startup items",
    "get_disk_analysis":      "Analysing disk usage",
    "get_system_status":      "Checking system status",
    "show_trends":            "Analysing trends",
    "create_maintenance_plan":"Creating maintenance plan",
    "explain_issue":          "Analysing issue details",
    "delegate_to_sub_agent":  "Delegating to sub-agent",
}

SPECIAL_COMMANDS = {"help", "clear", "history", "status", "trust"}


class AssistantREPL:
    """Interactive Read-Eval-Print Loop for conversational AI assistant."""

    def __init__(
        self,
        session_manager: SessionManager,
        tool_executor: ToolExecutor,
        orchestrator=None,
    ):
        self.session_manager = session_manager
        self.tool_executor = tool_executor
        self.orchestrator = orchestrator
        self.console = console
        self.session: Optional[SessionState] = None

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def start(self, force_new: bool = False) -> None:
        """Main REPL loop."""
        try:
            self.session = self.session_manager.get_or_create_latest(force_new)
            self._show_welcome(is_resumed=len(self.session.messages) > 0)

            while True:
                try:
                    user_input = self._get_user_input()

                    if self._should_exit(user_input):
                        self._handle_exit()
                        break

                    if user_input.lower() in SPECIAL_COMMANDS:
                        self._handle_special_command(user_input)
                        continue

                    self._process_turn(user_input)

                except KeyboardInterrupt:
                    self.console.print("\n")
                    if confirm("\nExit MacMaint Assistant?", default=False):
                        self._handle_exit()
                        break
                    self.console.print("Continuing...\n")

        finally:
            if self.session:
                self.session_manager.clear_trust_mode(self.session)
                self.session_manager.save_session(self.session)

    # ------------------------------------------------------------------
    # Welcome / goodbye
    # ------------------------------------------------------------------

    def _show_welcome(self, is_resumed: bool = False) -> None:
        if is_resumed:
            body = (
                "[bold cyan]Welcome back to MacMaint Assistant![/bold cyan]\n\n"
                f"Resuming conversation from: {self.session.last_active}\n\n"
                "Type [bold]'help'[/bold] for commands or [bold]'exit'[/bold] to quit"
            )
        else:
            body = (
                "[bold cyan]Welcome to MacMaint AI Assistant![/bold cyan]\n\n"
                "I can help you:\n"
                "  • Scan your Mac for issues\n"
                "  • Fix problems automatically\n"
                "  • Optimise performance\n"
                "  • Answer questions about your system\n\n"
                "[dim]Try: \"Scan my Mac\" or \"How's my disk space?\"[/dim]\n"
                "[dim]Type 'help' for commands or 'exit' to quit[/dim]"
            )
        self.console.print(Panel(body, border_style="cyan", padding=(1, 2), box=box.ROUNDED))
        self.console.print()

    def _handle_exit(self) -> None:
        self.session_manager.clear_trust_mode(self.session)
        self.session_manager.save_session(self.session)
        deleted = self.session_manager.cleanup_old_sessions(retention_days=30)

        duration = "just now"
        if self.session.messages:
            start = datetime.fromisoformat(self.session.started_at)
            minutes = (datetime.now() - start).seconds // 60
            if minutes > 0:
                duration = f"{minutes} minute{'s' if minutes != 1 else ''}"

        self.console.print(Panel(
            f"[bold cyan]Thanks for using MacMaint Assistant![/bold cyan]\n\n"
            f"Session duration: {duration}\n"
            f"Messages: {len(self.session.messages)}\n\n"
            "[dim]Your conversation has been saved.[/dim]\n"
            "[dim]Run 'macmaint start' to resume anytime.[/dim]",
            border_style="cyan",
            padding=(1, 2),
            box=box.ROUNDED,
        ))
        if deleted > 0:
            self.console.print(f"[dim]Cleaned up {deleted} old session(s)[/dim]\n")

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------

    def _get_user_input(self) -> str:
        try:
            return Prompt.ask("[bold green]You[/bold green]").strip()
        except EOFError:
            return "exit"

    def _should_exit(self, user_input: str) -> bool:
        return user_input.lower() in {"exit", "quit", "bye", "goodbye"}

    # ------------------------------------------------------------------
    # Special commands
    # ------------------------------------------------------------------

    def _handle_special_command(self, user_input: str) -> None:
        cmd = user_input.lower()

        if cmd == "help":
            self._cmd_help()
        elif cmd == "clear":
            self.console.clear()
            self._show_welcome(is_resumed=True)
        elif cmd == "history":
            self._cmd_history()
        elif cmd == "status":
            self._cmd_status()
        elif cmd == "trust":
            self._cmd_trust()

    def _cmd_help(self) -> None:
        self.console.print(Panel(
            "[bold]Available Commands:[/bold]\n\n"
            "  [cyan]help[/cyan]     — Show this help message\n"
            "  [cyan]clear[/cyan]    — Clear screen (conversation preserved)\n"
            "  [cyan]history[/cyan]  — Show recent sessions\n"
            "  [cyan]status[/cyan]   — Show current session info\n"
            "  [cyan]trust[/cyan]    — Toggle auto-approve mode (trust mode)\n"
            "  [cyan]exit[/cyan]     — Exit assistant\n\n"
            "[bold]Example Questions:[/bold]\n\n"
            "  • \"Scan my Mac for issues\"\n"
            "  • \"Fix the disk space problem\"\n"
            "  • \"Show me my memory usage trends\"\n"
            "  • \"Optimise my Mac for video editing\"",
            border_style="blue",
            padding=(1, 2),
            box=box.ROUNDED,
        ))
        self.console.print()

    def _cmd_history(self) -> None:
        sessions = self.session_manager.list_sessions(limit=5)
        self.console.print("[bold]Recent Sessions:[/bold]\n")
        if sessions:
            for s in sessions:
                self.console.print(
                    f"  • {s['session_id']}: {s['message_count']} messages "
                    f"(last active: {s['last_active']})"
                )
        else:
            self.console.print("  [dim]No previous sessions found[/dim]")
        self.console.print()

    def _cmd_status(self) -> None:
        summary = self.session_manager.get_session_summary(self.session)
        self.console.print(Panel(
            summary, title="Session Status", border_style="blue", box=box.ROUNDED
        ))
        self.console.print()

    def _cmd_trust(self) -> None:
        """Toggle trust (auto-approve) mode for the current session."""
        current = self.session_manager.get_trust_mode(self.session)

        if current == "auto_fix_safe":
            self.session_manager.clear_trust_mode(self.session)
            self.console.print(
                Panel(
                    "[yellow]Trust mode disabled.[/yellow]\n\n"
                    "I will ask for confirmation before making any changes.",
                    border_style="yellow",
                    padding=(1, 2),
                    box=box.ROUNDED,
                )
            )
        else:
            self.session_manager.set_trust_mode(self.session, "auto_fix_safe")
            self.console.print(
                Panel(
                    "[green]Trust mode enabled.[/green]\n\n"
                    "I will automatically apply safe fixes without asking.\n"
                    "[dim]Type 'trust' again to disable.[/dim]",
                    border_style="green",
                    padding=(1, 2),
                    box=box.ROUNDED,
                )
            )
        self.console.print()

    # ------------------------------------------------------------------
    # Conversation turn
    # ------------------------------------------------------------------

    def _process_turn(self, user_input: str) -> None:
        self.session_manager.add_message(self.session, "user", user_input)
        self.console.print()
        self.console.print("[bold blue]Assistant:[/bold blue]")
        self.console.print()

        try:
            response = self._call_orchestrator(user_input)
            self.session_manager.add_message(self.session, "assistant", response)
            self.session_manager.save_session(self.session)
        except Exception as e:
            error_response = self._handle_error(e)
            self.session_manager.add_message(self.session, "assistant", error_response)
            self.session_manager.save_session(self.session)

        self.console.print()

    def _call_orchestrator(self, user_input: str) -> str:
        """Call the orchestrator with streaming, per-tool progress, and Markdown rendering."""

        # Buffer for the full streamed response text
        response_buffer: List[str] = []

        # Per-tool tracking: list of (tool_name, status) tuples
        tool_log: List[Tuple[str, str]] = []

        def on_stream_chunk(chunk: str) -> None:
            """Write each token directly to stdout to avoid Rich newlines."""
            response_buffer.append(chunk)
            sys.stdout.write(chunk)
            sys.stdout.flush()

        def on_tool_call(tool_name: str, args: dict) -> None:
            """Show a progress line for each tool invocation."""
            # Strip sub-agent prefix for display (e.g. "scan_agent:scan_system")
            display_name = tool_name.split(":")[-1] if ":" in tool_name else tool_name
            label = TOOL_LABELS.get(display_name, f"Running {display_name}")
            tool_log.append((display_name, "running"))
            # Newline before indicator so it doesn't run into streaming text
            self.console.print()
            self.console.print(f"[cyan]⏳ {label}...[/cyan]")
            self.console.print()

        try:
            response_message = self.orchestrator.process_message(
                session=self.session,
                user_message=user_input,
                on_stream_chunk=on_stream_chunk,
                on_tool_call=on_tool_call,
            )

            full_response = response_message.content or ""

            # If the response was streamed token-by-token, the text is already
            # on screen — just add a newline and render it again as Markdown.
            # If no streaming happened (tool-only turn with no final text),
            # nothing was printed yet so we render now.
            if response_buffer:
                # Tokens were printed raw — move to a new line then re-render
                # as Markdown so the user sees nicely formatted output.
                sys.stdout.write("\n")
                sys.stdout.flush()
                self.console.print()
                self.console.print(Markdown(full_response))
            else:
                # Pure tool-call turn — render the summary as Markdown
                self.console.print(Markdown(full_response))

            # Mark all tools as complete
            if tool_log:
                self.console.print()
                for tool_name, _ in tool_log:
                    label = TOOL_LABELS.get(tool_name, tool_name)
                    self.console.print(f"[green]✅ {label}[/green]")

            return full_response

        except Exception as e:
            if tool_log:
                last_tool, _ = tool_log[-1]
                label = TOOL_LABELS.get(last_tool, last_tool)
                self.console.print()
                self.console.print(f"[red]❌ {label} — failed[/red]")
                self.console.print()

            context = f"User asked: {user_input}"
            suggestions = self.orchestrator.suggest_alternatives(str(e), context)
            error_msg = f"I encountered an error: {e}\n\n{suggestions}"
            self.console.print(Markdown(error_msg))
            return error_msg

    def _handle_error(self, error: Exception) -> str:
        error_msg = str(error)
        print_error(f"\n{error_msg}\n")
        return f"I encountered an error: {error_msg}\n\nPlease try rephrasing your request or type 'help' for guidance."
