"""Interactive REPL interface for conversational AI assistant.

Provides a Rich terminal interface for multi-turn conversations with line-by-line streaming.
"""

import time
from typing import Optional

from rich.panel import Panel
from rich.prompt import Prompt
from rich import box

from macmaint.assistant.session import SessionManager, SessionState
from macmaint.assistant.tools import ToolExecutor
from macmaint.utils.formatters import console, confirm, print_error, print_success, print_info
from datetime import datetime


class AssistantREPL:
    """Interactive Read-Eval-Print Loop for conversational AI assistant."""
    
    def __init__(
        self,
        session_manager: SessionManager,
        tool_executor: ToolExecutor,
        orchestrator=None  # Will implement in Sprint 2
    ):
        """Initialize REPL.
        
        Args:
            session_manager: Session manager for conversation state
            tool_executor: Tool executor for running MacMaint operations
            orchestrator: AI orchestrator (Sprint 2, optional for Sprint 1)
        """
        self.session_manager = session_manager
        self.tool_executor = tool_executor
        self.orchestrator = orchestrator
        self.console = console  # Rich console from formatters.py
        self.session: Optional[SessionState] = None
    
    def start(self, force_new: bool = False) -> None:
        """Main REPL loop.
        
        Args:
            force_new: If True, always create new session (ignore previous)
        """
        try:
            # Initialize or resume session
            self.session = self.session_manager.get_or_create_latest(force_new)
            
            # Show welcome
            self._show_welcome(is_resumed=len(self.session.messages) > 0)
            
            # Main loop
            while True:
                try:
                    user_input = self._get_user_input()
                    
                    if self._should_exit(user_input):
                        self._handle_exit()
                        break
                    
                    if self._is_special_command(user_input):
                        self._handle_special_command(user_input)
                        continue
                    
                    # Process conversation turn
                    self._process_turn(user_input)
                    
                except KeyboardInterrupt:
                    self.console.print("\n")
                    if confirm("\nExit MacMaint Assistant?", default=False):
                        self._handle_exit()
                        break
                    else:
                        self.console.print("Continuing...\n")
                        continue
        
        finally:
            # Always save session on exit
            if self.session:
                self.session_manager.clear_trust_mode(self.session)
                self.session_manager.save_session(self.session)
    
    def _show_welcome(self, is_resumed: bool = False) -> None:
        """Display welcome message.
        
        Args:
            is_resumed: If True, show resume message instead of new session welcome
        """
        if is_resumed:
            self.console.print(Panel(
                f"[bold cyan]Welcome back to MacMaint Assistant![/bold cyan]\n\n"
                f"Resuming your previous conversation from:\n"
                f"{self.session.last_active}\n\n"
                f"Type [bold]'help'[/bold] for commands or [bold]'exit'[/bold] to quit",
                border_style="cyan",
                padding=(1, 2),
                box=box.ROUNDED
            ))
        else:
            self.console.print(Panel(
                "[bold cyan]Welcome to MacMaint AI Assistant![/bold cyan]\n\n"
                "I can help you:\n"
                "  • Scan your Mac for issues\n"
                "  • Fix problems automatically\n"
                "  • Optimize performance\n"
                "  • Answer questions about your system\n\n"
                "[dim]Try: \"Scan my Mac\" or \"How's my disk space?\"[/dim]\n"
                "[dim]Type 'help' for commands or 'exit' to quit[/dim]",
                border_style="cyan",
                padding=(1, 2),
                box=box.ROUNDED
            ))
        self.console.print()
    
    def _get_user_input(self) -> str:
        """Get user input with prompt.
        
        Returns:
            User input string (stripped)
        """
        try:
            return Prompt.ask("[bold green]You[/bold green]").strip()
        except EOFError:
            return "exit"
    
    def _should_exit(self, user_input: str) -> bool:
        """Check if user wants to exit.
        
        Args:
            user_input: User input string
        
        Returns:
            True if exit command detected
        """
        return user_input.lower() in ['exit', 'quit', 'bye', 'goodbye']
    
    def _is_special_command(self, user_input: str) -> bool:
        """Check if input is a special command.
        
        Args:
            user_input: User input string
        
        Returns:
            True if special command detected
        """
        return user_input.lower() in ['help', 'clear', 'history', 'status']
    
    def _handle_special_command(self, user_input: str) -> None:
        """Handle special commands.
        
        Args:
            user_input: User input string
        """
        cmd = user_input.lower()
        
        if cmd == 'help':
            self.console.print(Panel(
                "[bold]Available Commands:[/bold]\n\n"
                "  [cyan]help[/cyan]     - Show this help message\n"
                "  [cyan]clear[/cyan]    - Clear screen (conversation preserved)\n"
                "  [cyan]history[/cyan]  - Show recent sessions\n"
                "  [cyan]status[/cyan]   - Show current session info\n"
                "  [cyan]exit[/cyan]     - Exit assistant\n\n"
                "[bold]Example Questions:[/bold]\n\n"
                "  • \"Scan my Mac for issues\"\n"
                "  • \"Fix the disk space problem\"\n"
                "  • \"Show me my memory usage trends\"\n"
                "  • \"Optimize my Mac for video editing\"",
                border_style="blue",
                padding=(1, 2),
                box=box.ROUNDED
            ))
            self.console.print()
        
        elif cmd == 'clear':
            self.console.clear()
            self._show_welcome(is_resumed=True)
        
        elif cmd == 'history':
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
        
        elif cmd == 'status':
            summary = self.session_manager.get_session_summary(self.session)
            self.console.print(Panel(
                summary,
                title="Session Status",
                border_style="blue",
                box=box.ROUNDED
            ))
            self.console.print()
    
    def _process_turn(self, user_input: str) -> None:
        """Process one conversation turn.
        
        Args:
            user_input: User's message
        """
        # Add user message to session
        self.session_manager.add_message(self.session, "user", user_input)
        
        # Display assistant header
        self.console.print()
        self.console.print("[bold blue]Assistant:[/bold blue]")
        self.console.print()
        
        try:
            if self.orchestrator:
                # Real orchestrator with streaming (Sprint 2)
                response = self._call_orchestrator(user_input)
            else:
                # Fallback placeholder (should not happen in production)
                response = self._generate_placeholder_response(user_input)
            
            # Add assistant message to session
            self.session_manager.add_message(self.session, "assistant", response)
            
            # Save after each turn
            self.session_manager.save_session(self.session)
            
        except Exception as e:
            error_response = self._handle_error(e)
            self.session_manager.add_message(self.session, "assistant", error_response)
            self.session_manager.save_session(self.session)
        
        self.console.print()
    
    def _generate_placeholder_response(self, user_input: str) -> str:
        """Generate placeholder response for Sprint 1.
        
        This simulates the behavior without a real orchestrator.
        Will be replaced with real AI orchestrator in Sprint 2.
        
        Args:
            user_input: User's message
        
        Returns:
            Placeholder response string
        """
        # Simulate processing time
        with self.console.status("[cyan]Thinking...[/cyan]", spinner="dots"):
            time.sleep(1)
        
        # Check for common intents and provide helpful responses
        user_input_lower = user_input.lower()
        
        if "scan" in user_input_lower:
            response = (
                "I understand you want to scan your Mac for issues.\n\n"
                "In Sprint 2, I'll be able to actually run the scan and show you the results. "
                "For now, I'm demonstrating the conversation interface.\n\n"
                "The scan would check:\n"
                "• Disk space and large files\n"
                "• Memory usage and processes\n"
                "• CPU performance\n"
                "• Startup items\n"
                "• System caches"
            )
        elif "fix" in user_input_lower:
            response = (
                "I understand you want to fix some issues.\n\n"
                "In Sprint 2, I'll be able to identify and fix problems automatically. "
                "I'll ask for your permission before making any changes, unless you've enabled auto-fix mode."
            )
        elif "disk" in user_input_lower or "space" in user_input_lower:
            response = (
                "I understand you're asking about disk space.\n\n"
                "In Sprint 2, I'll be able to show you:\n"
                "• How much space you have free\n"
                "• What's using the most space\n"
                "• Suggestions for freeing up space\n"
                "• Cache files that can be safely deleted"
            )
        elif "memory" in user_input_lower or "ram" in user_input_lower:
            response = (
                "I understand you're asking about memory usage.\n\n"
                "In Sprint 2, I'll be able to show you:\n"
                "• Current memory usage\n"
                "• Top memory-consuming processes\n"
                "• Recommendations for optimization\n"
                "• Options to free up memory"
            )
        else:
            response = (
                f"I received your message: \"{user_input}\"\n\n"
                f"The full conversational AI with function calling will be implemented in Sprint 2. "
                f"For now, I'm demonstrating:\n\n"
                f"✓ Multi-turn conversations\n"
                f"✓ Session persistence across restarts\n"
                f"✓ Message history management\n"
                f"✓ Special commands (help, clear, history, status)\n\n"
                f"Try typing 'help' to see available commands, or 'exit' to quit."
            )
        
        # Display response line-by-line for demonstration
        self._display_response_line_by_line(response)
        
        return response
    
    def _display_response_line_by_line(self, response: str) -> None:
        """Display response line-by-line with brief pauses.
        
        Args:
            response: Response text to display
        """
        lines = response.split('\n')
        for line in lines:
            self.console.print(line)
            time.sleep(0.1)  # Brief pause for readability
    
    def _call_orchestrator(self, user_input: str) -> str:
        """Call the orchestrator to handle the conversation turn.
        
        Args:
            user_input: User's message
        
        Returns:
            Assistant's response
        """
        from rich.live import Live
        from rich.spinner import Spinner
        
        # Track response text and current tool
        response_text = ""
        current_tool_name = None
        current_tool_status = None
        
        def on_stream_chunk(chunk: str) -> None:
            """Handle streaming text chunks."""
            nonlocal response_text
            response_text += chunk
            # Print immediately for streaming effect
            self.console.print(chunk, end="")
        
        def on_tool_call(tool_name: str, args: dict) -> None:
            """Handle tool execution."""
            nonlocal current_tool_name, current_tool_status
            current_tool_name = tool_name
            current_tool_status = "running"
            
            # Show tool execution with progress indicator
            self.console.print()
            self.console.print(f"[cyan]⏳ Executing:[/cyan] {tool_name}...")
            self.console.print()
        
        try:
            # Call orchestrator with streaming
            response_message = self.orchestrator.process_message(
                session=self.session,
                user_message=user_input,
                on_stream_chunk=on_stream_chunk,
                on_tool_call=on_tool_call
            )
            
            # Show success if tool was called
            if current_tool_name:
                self.console.print()
                self.console.print(f"[green]✅ Completed:[/green] {current_tool_name}")
                self.console.print()
            
            return response_message.content
        
        except Exception as e:
            # Show error
            if current_tool_name:
                self.console.print()
                self.console.print(f"[red]❌ Failed:[/red] {current_tool_name}")
                self.console.print()
            
            # Get suggestions from orchestrator
            context = f"User asked: {user_input}"
            suggestions = self.orchestrator.suggest_alternatives(str(e), context)
            
            error_msg = f"\nI encountered an error: {str(e)}\n\n{suggestions}"
            self.console.print(error_msg)
            
            return error_msg
    
    def _handle_error(self, error: Exception) -> str:
        """Handle errors with user-friendly messages.
        
        Args:
            error: Exception that occurred
        
        Returns:
            Error response message
        """
        error_msg = str(error)
        print_error(f"\n{error_msg}\n")
        
        # For Sprint 1, just show error
        # In Sprint 2, orchestrator will suggest alternatives automatically
        return (
            f"I encountered an error: {error_msg}\n\n"
            f"In Sprint 2, I'll be able to automatically suggest alternative approaches. "
            f"For now, please try rephrasing your request or typing 'help' for guidance."
        )
    
    def _handle_exit(self) -> None:
        """Handle session exit with goodbye message and cleanup."""
        # Clear trust mode (session-scoped)
        self.session_manager.clear_trust_mode(self.session)
        
        # Save final state
        self.session_manager.save_session(self.session)
        
        # Cleanup old sessions
        deleted = self.session_manager.cleanup_old_sessions(retention_days=30)
        
        # Calculate session duration
        duration = "just now"
        if self.session.messages:
            start = datetime.fromisoformat(self.session.started_at)
            end = datetime.now()
            minutes = (end - start).seconds // 60
            if minutes > 0:
                duration = f"{minutes} minute{'s' if minutes != 1 else ''}"
        
        # Show goodbye with summary
        self.console.print(Panel(
            f"[bold cyan]Thanks for using MacMaint Assistant![/bold cyan]\n\n"
            f"Session duration: {duration}\n"
            f"Messages: {len(self.session.messages)}\n\n"
            f"[dim]Your conversation has been saved.[/dim]\n"
            f"[dim]Run 'macmaint start' to resume anytime.[/dim]",
            border_style="cyan",
            padding=(1, 2),
            box=box.ROUNDED
        ))
        
        if deleted > 0:
            self.console.print(f"[dim]Cleaned up {deleted} old session(s)[/dim]\n")
    
    def display_tool_execution(
        self,
        tool_name: str,
        arguments: dict,
        status: str = "running"
    ) -> None:
        """Display tool execution progress with rich indicators.
        
        Shows:
        - ⏳ Scanning your system... (with spinner) - running
        - ✅ Scan complete - found 3 issues - success  
        - ⚠️ Scan failed: Permission denied - error
        
        This method can be called from the orchestrator in Sprint 2.
        
        Args:
            tool_name: Name of the tool being executed
            arguments: Tool arguments
            status: Execution status (running, success, error)
        """
        tool_descriptions = {
            'scan_system': 'Scanning your system',
            'fix_issues': f"Fixing {len(arguments.get('issue_ids', []))} issue(s)",
            'clean_caches': 'Cleaning caches',
            'optimize_memory': 'Optimizing memory',
            'manage_startup_items': 'Managing startup items',
            'get_disk_analysis': 'Analyzing disk usage',
            'get_system_status': 'Checking system status',
            'show_trends': 'Analyzing trends',
            'create_maintenance_plan': 'Creating maintenance plan',
            'explain_issue': 'Analyzing issue details'
        }
        
        description = tool_descriptions.get(tool_name, f"Running {tool_name}")
        
        if status == "running":
            # This would be used with a context manager in Sprint 2
            # with self.console.status(f"[cyan]{description}...[/cyan]", spinner="dots"):
            #     # Execution happens here
            print_info(f"⏳ {description}...")
        
        elif status == "success":
            print_success(f"{description}")
        
        elif status == "error":
            print_error(f"{description} - failed")
