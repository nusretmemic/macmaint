"""Interactive REPL interface for conversational AI assistant.

Provides a Rich terminal interface for multi-turn conversations with
line-by-line streaming, Markdown rendering, and live tool-call spinners.
"""

import time
import threading
from typing import Dict, List, Optional, Tuple

from rich.align import Align
from rich.columns import Columns
from rich.console import Group
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.rule import Rule
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text
from rich import box

from macmaint.assistant.session import SessionManager, SessionState
from macmaint.assistant.tools import ToolExecutor
from macmaint.utils.formatters import console, confirm, print_error
from macmaint import __version__
from datetime import datetime


# ── Brand palette ────────────────────────────────────────────────────────────
PRIMARY   = "bright_cyan"
SECONDARY = "cyan"
ACCENT    = "bright_blue"
MUTED     = "grey62"
SUCCESS   = "bright_green"
WARNING   = "yellow"
DANGER    = "bright_red"

# ── ASCII wordmark ────────────────────────────────────────────────────────────
_WORDMARK = (
    " [bold bright_cyan]███╗   ███╗ █████╗  ██████╗[/bold bright_cyan]"
    "[bold cyan]███╗   ███╗ █████╗ ██╗███╗  ██╗████████╗[/bold cyan]\n"
    " [bold bright_cyan]████╗ ████║██╔══██╗██╔════╝[/bold bright_cyan]"
    "[bold cyan]████╗ ████║██╔══██╗██║████╗ ██║╚══██╔══╝[/bold cyan]\n"
    " [bold bright_cyan]██╔████╔██║███████║██║     [/bold bright_cyan]"
    "[bold cyan]██╔████╔██║███████║██║██╔██╗██║   ██║   [/bold cyan]\n"
    " [bold bright_cyan]██║╚██╔╝██║██╔══██║██║     [/bold bright_cyan]"
    "[bold cyan]██║╚██╔╝██║██╔══██║██║██║╚████║   ██║   [/bold cyan]\n"
    " [bold bright_cyan]██║ ╚═╝ ██║██║  ██║╚██████╗[/bold bright_cyan]"
    "[bold cyan]██║ ╚═╝ ██║██║  ██║██║██║ ╚███║   ██║   [/bold cyan]\n"
    " [bold bright_cyan]╚═╝     ╚═╝╚═╝  ╚═╝ ╚═════╝[/bold bright_cyan]"
    "[bold cyan]╚═╝     ╚═╝╚═╝  ╚═╝╚═╝╚═╝  ╚══╝   ╚═╝   [/bold cyan]"
)

# ── Human-readable tool labels ────────────────────────────────────────────────
TOOL_LABELS: Dict[str, str] = {
    "scan_system":             "Scanning your system",
    "fix_issues":              "Fixing issues",
    "clean_caches":            "Cleaning caches",
    "optimize_memory":         "Optimising memory",
    "manage_startup_items":    "Managing startup items",
    "get_disk_analysis":       "Analysing disk usage",
    "get_system_status":       "Checking system status",
    "show_trends":             "Analysing trends",
    "create_maintenance_plan": "Creating maintenance plan",
    "explain_issue":           "Analysing issue details",
    "delegate_to_sub_agent":   "Delegating to sub-agent",
}

# ── Tool icon palette ─────────────────────────────────────────────────────────
TOOL_ICONS: Dict[str, str] = {
    "scan_system":             "󰣇",   # nf-md-apple  (fallback: 🔍)
    "fix_issues":              "🔧",
    "clean_caches":            "🧹",
    "optimize_memory":         "⚡",
    "manage_startup_items":    "🚀",
    "get_disk_analysis":       "💾",
    "get_system_status":       "📊",
    "show_trends":             "📈",
    "create_maintenance_plan": "📋",
    "explain_issue":           "🔎",
    "delegate_to_sub_agent":   "🤖",
}

SPECIAL_COMMANDS = {"help", "clear", "history", "status", "trust", "new", "delete"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _rule(title: str = "", style: str = SECONDARY) -> Rule:
    return Rule(title=title, style=style)


def _dim_time(iso: str) -> str:
    """Render an ISO timestamp as a short human-friendly string."""
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%b %d, %Y  %H:%M")
    except Exception:
        return iso


# ─────────────────────────────────────────────────────────────────────────────

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

    # ── Entry point ───────────────────────────────────────────────────────────

    def start(self, force_new: bool = False) -> None:
        """Main REPL loop."""
        try:
            self.session = self.session_manager.get_or_create_latest(force_new)
            self._show_welcome(is_resumed=len(self.session.messages) > 0)
            self._check_for_update_async()

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
                    if confirm("\nExit MacMaint?", default=False):
                        self._handle_exit()
                        break
                    self.console.print(f"[{MUTED}]Continuing…[/{MUTED}]\n")

        finally:
            if self.session:
                self.session_manager.clear_trust_mode(self.session)
                self.session_manager.save_session(self.session)

    # ── Welcome / goodbye ─────────────────────────────────────────────────────

    def _show_welcome(self, is_resumed: bool = False) -> None:
        self.console.print()
        self.console.print(_wordmark_panel())
        self.console.print()

        if is_resumed:
            last = _dim_time(self.session.last_active)
            msg_count = len(self.session.messages)
            body = (
                f"[{PRIMARY}]Welcome back![/{PRIMARY}]  "
                f"[{MUTED}]Resuming conversation · {msg_count} message{'s' if msg_count != 1 else ''} · last active {last}[/{MUTED}]\n\n"
                f"[{MUTED}]Type [/][bold]help[/bold][{MUTED}] for commands or [/][bold]exit[/bold][{MUTED}] to quit.[/{MUTED}]"
            )
        else:
            body = (
                f"  [{PRIMARY}]What can I do for you today?[/{PRIMARY}]\n\n"
                f'  [bold bright_white]Scan[/bold bright_white]       [dim]"Scan my Mac and show what needs attention"[/dim]\n'
                f'  [bold bright_white]Fix[/bold bright_white]        [dim]"Clean up disk space"[/dim]\n'
                f'  [bold bright_white]Duplicates[/bold bright_white] [dim]"Find duplicate files in my Downloads"[/dim]\n'
                f'  [bold bright_white]Analyse[/bold bright_white]    [dim]"Show battery health trends"[/dim]\n'
                f'  [bold bright_white]Optimise[/bold bright_white]   [dim]"Optimise my Mac for video editing"[/dim]\n'
                f'  [bold bright_white]Ask[/bold bright_white]        [dim]"Why is my Mac running slow?"[/dim]\n\n'
                f"  [{MUTED}]What I can do:[/{MUTED}]\n"
                f"  [{MUTED}]· Scan for disk, memory, CPU, battery & startup issues[/{MUTED}]\n"
                f"  [{MUTED}]· Find and delete duplicate files (SHA256, parallel hashing)[/{MUTED}]\n"
                f"  [{MUTED}]· Clean caches, fix issues, manage startup items[/{MUTED}]\n"
                f"  [{MUTED}]· Show historical trends and create maintenance plans[/{MUTED}]\n\n"
                f"  [{MUTED}]Type [bold]help[/bold] for commands  ·  [bold]new[/bold] for a fresh session  ·  [bold]exit[/bold] to quit[/{MUTED}]"
            )

        self.console.print(Panel(
            body,
            border_style=SECONDARY,
            padding=(1, 3),
            box=box.ROUNDED,
        ))
        self.console.print()

    def _check_for_update_async(self) -> None:
        """Spawn a background thread to check for updates and print a nudge if available.

        The thread runs after the welcome screen is shown so it never blocks
        startup.  The nudge appears as a single dim line before the first prompt.
        The check uses the 24-hour cache, so network is not hit on every launch.
        """
        def _check():
            try:
                from macmaint.utils.updater import check_for_updates
                info = check_for_updates()
                if info.get("update_available"):
                    latest = info["latest_version"]
                    self.console.print(
                        f"  [yellow]⬆  MacMaint {latest} is available.[/yellow]"
                        f"  [dim]Run [bold]macmaint update[/bold] to install.[/dim]\n"
                    )
            except Exception:
                pass  # Never crash the REPL over a failed update check

        t = threading.Thread(target=_check, daemon=True)
        t.start()
        t.join(timeout=3)   # Wait up to 3 s; if cache miss and network slow, skip silently

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

        # Stats table
        t = Table.grid(padding=(0, 2))
        t.add_column(style=MUTED)
        t.add_column(style="bold bright_white")
        t.add_row("Session duration", duration)
        t.add_row("Messages exchanged", str(len(self.session.messages)))
        t.add_row("Conversation saved to", "~/.macmaint/conversations/")

        self.console.print()
        self.console.print(Panel(
            Group(
                Align.center(Text("Thanks for using MacMaint!", style=f"bold {PRIMARY}")),
                Text(""),
                t,
                Text(""),
                Align.center(Text("Run  macmaint start  to resume anytime.", style=MUTED)),
            ),
            border_style=PRIMARY,
            padding=(1, 4),
            box=box.DOUBLE_EDGE,
        ))
        self.console.print()
        if deleted > 0:
            self.console.print(f"[{MUTED}]  Cleaned up {deleted} old session(s)[/{MUTED}]\n")

    # ── Input ─────────────────────────────────────────────────────────────────

    def _get_user_input(self) -> str:
        self.console.print(_rule())
        try:
            return Prompt.ask(f"[bold {SUCCESS}] You[/bold {SUCCESS}]").strip()
        except EOFError:
            return "exit"

    def _should_exit(self, user_input: str) -> bool:
        return user_input.lower() in {"exit", "quit", "bye", "goodbye"}

    # ── Special commands ──────────────────────────────────────────────────────

    def _handle_special_command(self, user_input: str) -> None:
        cmd = user_input.lower()
        handlers = {
            "help":    self._cmd_help,
            "clear":   self._cmd_clear,
            "history": self._cmd_history,
            "status":  self._cmd_status,
            "trust":   self._cmd_trust,
            "new":     self._cmd_new,
            "delete":  self._cmd_delete,
        }
        handler = handlers.get(cmd)
        if handler:
            handler()

    def _cmd_clear(self) -> None:
        self.console.clear()
        self._show_welcome(is_resumed=True)

    def _cmd_help(self) -> None:
        # Commands table
        cmd_table = Table.grid(padding=(0, 2))
        cmd_table.add_column(style=f"bold {SECONDARY}", no_wrap=True)
        cmd_table.add_column(style="bright_white")
        rows = [
            ("help",    "Show this help message"),
            ("clear",   "Clear screen (conversation preserved)"),
            ("new",     "Start a new session (saves current first)"),
            ("delete",  "Delete saved sessions"),
            ("history", "Show recent sessions"),
            ("status",  "Show current session info"),
            ("trust",   "Toggle auto-approve mode"),
            ("exit",    "Exit the assistant"),
        ]
        for cmd, desc in rows:
            cmd_table.add_row(cmd, desc)

        # Examples table
        ex_table = Table.grid(padding=(0, 2))
        ex_table.add_column(style=MUTED, no_wrap=True)
        ex_table.add_column(style="italic bright_white")
        examples = [
            ("→", '"Scan my Mac for issues"'),
            ("→", '"Fix the disk space problem"'),
            ("→", '"Find duplicate files in Downloads"'),
            ("→", '"Find large duplicate files"'),
            ("→", '"Show me my memory usage trends"'),
            ("→", '"Optimise my Mac for video editing"'),
            ("→", '"What\'s using all my CPU?"'),
            ("→", '"Show battery health"'),
            ("→", '"What\'s draining my battery?"'),
            ("→", '"Create a maintenance plan"'),
        ]
        for arrow, ex in examples:
            ex_table.add_row(arrow, ex)

        body = Group(
            Text(f"Commands", style=f"bold {PRIMARY}"),
            Text(""),
            cmd_table,
            Text(""),
            Text("Example questions", style=f"bold {PRIMARY}"),
            Text(""),
            ex_table,
        )

        self.console.print()
        self.console.print(Panel(
            body,
            title=f"[bold {ACCENT}] MacMaint Help [/bold {ACCENT}]",
            border_style=ACCENT,
            padding=(1, 3),
            box=box.ROUNDED,
        ))
        self.console.print()

    def _cmd_history(self) -> None:
        sessions = self.session_manager.list_sessions(limit=8)
        self.console.print()

        if not sessions:
            self.console.print(Panel(
                f"[{MUTED}]No previous sessions found.[/{MUTED}]",
                title=f"[bold {ACCENT}] Session History [/bold {ACCENT}]",
                border_style=ACCENT,
                box=box.ROUNDED,
            ))
        else:
            t = Table(box=box.SIMPLE_HEAD, show_header=True, header_style=f"bold {SECONDARY}")
            t.add_column("Session ID", style=MUTED, no_wrap=True)
            t.add_column("Messages", justify="right", style="bright_white")
            t.add_column("Last Active", style="bright_white")

            for s in sessions:
                is_current = s["session_id"] == self.session.session_id
                sid = f"[bold {PRIMARY}]{s['session_id']}  ← current[/bold {PRIMARY}]" if is_current else s["session_id"]
                t.add_row(
                    sid,
                    str(s["message_count"]),
                    _dim_time(s["last_active"]),
                )

            self.console.print(Panel(
                t,
                title=f"[bold {ACCENT}] Session History [/bold {ACCENT}]",
                border_style=ACCENT,
                padding=(0, 1),
                box=box.ROUNDED,
            ))

        self.console.print()

    def _cmd_status(self) -> None:
        s = self.session
        trust = self.session_manager.get_trust_mode(s)
        trust_label = (
            f"[bold {SUCCESS}]enabled (auto-fix safe)[/bold {SUCCESS}]"
            if trust == "auto_fix_safe"
            else f"[{MUTED}]disabled[/{MUTED}]"
        )

        t = Table.grid(padding=(0, 2))
        t.add_column(style=MUTED)
        t.add_column(style="bold bright_white")
        t.add_row("Session ID",  s.session_id)
        t.add_row("Started",     _dim_time(s.started_at))
        t.add_row("Last active", _dim_time(s.last_active))
        t.add_row("Messages",    str(len(s.messages)))
        t.add_row("Trust mode",  trust_label)

        self.console.print()
        self.console.print(Panel(
            t,
            title=f"[bold {ACCENT}] Session Status [/bold {ACCENT}]",
            border_style=ACCENT,
            padding=(1, 3),
            box=box.ROUNDED,
        ))
        self.console.print()

    def _cmd_trust(self) -> None:
        current = self.session_manager.get_trust_mode(self.session)
        self.console.print()

        if current == "auto_fix_safe":
            self.session_manager.clear_trust_mode(self.session)
            self.console.print(Panel(
                f"[bold {WARNING}]Trust mode disabled.[/bold {WARNING}]\n\n"
                f"[{MUTED}]I will ask for confirmation before making any changes.[/{MUTED}]",
                border_style=WARNING,
                padding=(1, 3),
                box=box.ROUNDED,
            ))
        else:
            self.session_manager.set_trust_mode(self.session, "auto_fix_safe")
            self.console.print(Panel(
                f"[bold {SUCCESS}]Trust mode enabled.[/bold {SUCCESS}]\n\n"
                f"[{MUTED}]Safe fixes will be applied automatically without confirmation.\n"
                f"Type [bold]trust[/bold] again to disable.[/{MUTED}]",
                border_style=SUCCESS,
                padding=(1, 3),
                box=box.ROUNDED,
            ))
        self.console.print()

    def _cmd_new(self) -> None:
        """Start a brand-new session, saving the current one first."""
        self.session_manager.save_session(self.session)
        self.session = self.session_manager.create_new_session()
        # Reset in-session scan cache so the new session starts clean
        self.tool_executor._last_scan_results = None
        self.tool_executor._last_scan_time = None
        self.console.clear()
        self._show_welcome(is_resumed=False)
        self.console.print(f"[{MUTED}]  New session started.[/{MUTED}]\n")

    def _cmd_delete(self) -> None:
        """Delete one or all saved sessions from within the REPL."""
        from rich.prompt import Confirm
        sessions = self.session_manager.list_sessions(limit=100)

        self.console.print()

        if not sessions:
            self.console.print(Panel(
                f"[{MUTED}]No saved sessions to delete.[/{MUTED}]",
                border_style=ACCENT,
                box=box.ROUNDED,
            ))
            self.console.print()
            return

        # Show the list
        t = Table(box=box.SIMPLE_HEAD, show_header=True, header_style=f"bold {SECONDARY}")
        t.add_column("#", style=MUTED, justify="right", no_wrap=True)
        t.add_column("Session ID", style=MUTED, no_wrap=True)
        t.add_column("Messages", justify="right", style="bright_white")
        t.add_column("Last Active", style="bright_white")

        for idx, s in enumerate(sessions, 1):
            is_current = s["session_id"] == self.session.session_id
            sid = (
                f"[bold {PRIMARY}]{s['session_id']}  ← current[/bold {PRIMARY}]"
                if is_current else s["session_id"]
            )
            t.add_row(str(idx), sid, str(s["message_count"]), _dim_time(s["last_active"]))

        self.console.print(Panel(
            t,
            title=f"[bold {ACCENT}] Delete Sessions [/bold {ACCENT}]",
            border_style=ACCENT,
            padding=(0, 1),
            box=box.ROUNDED,
        ))
        self.console.print()
        self.console.print(f"  [{MUTED}]Enter a session number, a session ID, or[/{MUTED}] [bold]all[/bold] [{MUTED}]to delete everything.[/{MUTED}]")
        self.console.print(f"  [{MUTED}]Press Enter to cancel.[/{MUTED}]\n")

        from rich.prompt import Prompt as _Prompt
        choice = _Prompt.ask(f"[bold {SECONDARY}]Delete[/bold {SECONDARY}]", default="").strip()

        if not choice:
            self.console.print(f"[{MUTED}]Cancelled.[/{MUTED}]\n")
            return

        if choice.lower() == "all":
            non_current = [s for s in sessions if s["session_id"] != self.session.session_id]
            if not non_current:
                self.console.print(f"[{MUTED}]Only the current session exists — nothing else to delete.[/{MUTED}]\n")
                return
            if not Confirm.ask(f"Delete all {len(non_current)} other session(s)?", default=False):
                self.console.print(f"[{MUTED}]Cancelled.[/{MUTED}]\n")
                return
            deleted = self.session_manager.delete_all_sessions()
            self.console.print(f"[bold {SUCCESS}]Deleted {deleted} session(s).[/bold {SUCCESS}]\n")
            return

        # Resolve by number or by ID
        target_id: Optional[str] = None
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(sessions):
                target_id = sessions[idx]["session_id"]
        else:
            # Check if it matches any session_id substring/exact
            matches = [s for s in sessions if s["session_id"] == choice]
            if matches:
                target_id = matches[0]["session_id"]

        if not target_id:
            self.console.print(f"[bold {WARNING}]No matching session for '{choice}'.[/bold {WARNING}]\n")
            return

        try:
            ok = self.session_manager.delete_session(target_id)
        except ValueError as e:
            self.console.print(f"[bold {WARNING}]{e}[/bold {WARNING}]\n")
            return

        if ok:
            self.console.print(f"[bold {SUCCESS}]Session '{target_id}' deleted.[/bold {SUCCESS}]\n")
        else:
            self.console.print(f"[bold {WARNING}]Session '{target_id}' not found.[/bold {WARNING}]\n")

    # ── Conversation turn ─────────────────────────────────────────────────────

    def _process_turn(self, user_input: str) -> None:
        self.session_manager.add_message(self.session, "user", user_input)
        self.console.print()

        # Assistant label
        self.console.print(
            f"[bold {PRIMARY}]  MacMaint[/bold {PRIMARY}]"
            f"[{MUTED}]  ·  thinking…[/{MUTED}]"
        )
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
        """Call the orchestrator with streaming, live tool spinners, and Markdown rendering."""

        response_buffer: List[str] = []

        # Per-tool tracking: list of (display_name, status, label, icon, start_time)
        tool_log: List[Dict] = []

        # Live-spinner state: the Live context is opened on first tool call and
        # kept open until the orchestrator returns (so spinners animate while
        # the model is thinking between tool calls).
        live_ctx: Optional[Live] = None
        live_lock = threading.Lock()

        def _render_tool_table() -> Table:
            """Build the live-rendered tool-progress table."""
            t = Table.grid(padding=(0, 1))
            t.add_column(width=3)   # icon
            t.add_column()          # label + elapsed
            t.add_column(width=3)   # status glyph
            for entry in tool_log:
                icon  = entry["icon"]
                label = entry["label"]
                status = entry["status"]
                elapsed = entry.get("elapsed", "")

                if status == "running":
                    spin = Spinner("dots", style=f"bold {SECONDARY}")
                    label_text = Text(f" {label}", style=f"bold {PRIMARY}")
                    elapsed_text = Text(f"  {elapsed}", style=MUTED)
                    glyph = spin
                    combined = Text.assemble(label_text, elapsed_text)
                    t.add_row(Text(icon), combined, spin)
                elif status == "done":
                    t.add_row(
                        Text(icon),
                        Text(f" {label}", style=MUTED),
                        Text("✓", style=f"bold {SUCCESS}"),
                    )
                else:  # error
                    err = entry.get("error_detail", "")
                    err_suffix = f"  {err}" if err else ""
                    t.add_row(
                        Text(icon),
                        Text.assemble(
                            Text(f" {label}", style=MUTED),
                            Text(err_suffix, style=f"bold {DANGER}"),
                        ),
                        Text("✗", style=f"bold {DANGER}"),
                    )
            return t

        def on_stream_chunk(chunk: str) -> None:
            # Buffer silently — we render the complete response as a Rich Panel
            # once streaming finishes.  Writing raw bytes to stdout mid-Live
            # would corrupt the spinner display and produce word-per-line output.
            response_buffer.append(chunk)

        def on_tool_call(tool_name: str, args: dict) -> None:
            nonlocal live_ctx
            display_name = tool_name.split(":")[-1] if ":" in tool_name else tool_name
            label = TOOL_LABELS.get(display_name, f"Running {display_name}")
            icon  = TOOL_ICONS.get(display_name, "⚙")
            entry = {
                "name":    display_name,
                "label":   label,
                "icon":    icon,
                "status":  "running",
                "started": time.monotonic(),
                "elapsed": "",
            }
            with live_lock:
                tool_log.append(entry)
                if live_ctx is None:
                    live_ctx = Live(
                        _render_tool_table(),
                        console=self.console,
                        refresh_per_second=12,
                        transient=False,
                    )
                    live_ctx.start()
                else:
                    live_ctx.update(_render_tool_table())

        def _finish_tool(success: bool = True, error_detail: str = "") -> None:
            """Mark the most-recent running tool as done/error."""
            for entry in reversed(tool_log):
                if entry["status"] == "running":
                    elapsed = time.monotonic() - entry["started"]
                    entry["elapsed"] = f"({elapsed:.1f}s)"
                    entry["status"] = "done" if success else "error"
                    if error_detail:
                        entry["error_detail"] = error_detail
                    break
            if live_ctx:
                live_ctx.update(_render_tool_table())

        # Thread that keeps elapsed time ticking in the live display
        _stop_ticker = threading.Event()

        def _ticker():
            while not _stop_ticker.is_set():
                time.sleep(0.25)
                if live_ctx:
                    for entry in tool_log:
                        if entry["status"] == "running":
                            elapsed = time.monotonic() - entry["started"]
                            entry["elapsed"] = f"({elapsed:.1f}s)"
                    with live_lock:
                        if live_ctx:
                            live_ctx.update(_render_tool_table())

        ticker_thread = threading.Thread(target=_ticker, daemon=True)
        ticker_thread.start()

        def on_tool_result(tool_name: str, result: dict) -> None:
            success = result.get("success", True)
            error_detail = result.get("error", "") if not success else ""
            _finish_tool(success=success, error_detail=error_detail)

        try:
            response_message = self.orchestrator.process_message(
                session=self.session,
                user_message=user_input,
                on_stream_chunk=on_stream_chunk,
                on_tool_call=on_tool_call,
                on_tool_result=on_tool_result,
            )

        except Exception as exc:
            _finish_tool(success=False)
            _stop_ticker.set()
            if live_ctx:
                live_ctx.stop()

            if tool_log:
                self.console.print()

            context = f"User asked: {user_input}"
            suggestions = self.orchestrator.suggest_alternatives(str(exc), context)
            error_msg = f"I encountered an error: {exc}\n\n{suggestions}"
            self.console.print(Panel(
                Markdown(error_msg),
                border_style=DANGER,
                padding=(1, 2),
                box=box.ROUNDED,
            ))
            return error_msg

        finally:
            _stop_ticker.set()
            if live_ctx:
                live_ctx.stop()
                live_ctx = None

        full_response = response_message.content or ""

        # Print a separator between tool output and the assistant's text reply
        if tool_log:
            self.console.print()

        if full_response.strip():
            self.console.print(Panel(
                Markdown(full_response),
                border_style=SECONDARY,
                padding=(1, 2),
                box=box.ROUNDED,
            ))

        return full_response

    def _handle_error(self, error: Exception) -> str:
        error_msg = str(error)
        print_error(f"\n{error_msg}\n")
        return (
            f"I encountered an error: {error_msg}\n\n"
            "Please try rephrasing your request or type 'help' for guidance."
        )


# ── Wordmark helper ───────────────────────────────────────────────────────────

def _wordmark_panel() -> Panel:
    """Return a centred ASCII-art title panel."""
    subtitle = Text.assemble(
        ("  AI-powered macOS maintenance assistant  ", f"{MUTED}"),
    )
    body = Group(
        Align.center(Text.from_markup(_WORDMARK)),
        Align.center(subtitle),
        Align.center(Text.from_markup(
            f"[{MUTED}]v{__version__}   ·   type [bold]help[/bold] to get started[/{MUTED}]"
        )),
    )
    return Panel(
        body,
        border_style=PRIMARY,
        padding=(1, 2),
        box=box.DOUBLE_EDGE,
    )
