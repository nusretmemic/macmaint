"""Command-line interface for MacMaint."""
import sys
import click
from pathlib import Path

from macmaint import __version__
from macmaint.config import get_config
from macmaint.core.scanner import Scanner
from macmaint.core.fixer import Fixer
from macmaint.utils.formatters import (
    console, print_header, print_success, print_error,
    print_warning, print_info, print_issues_summary,
    format_percentage, format_bytes, create_progress,
    print_cache_breakdown, print_cache_table,
    print_memory_breakdown, print_process_categories
)


# ── Shared chat footer hint ───────────────────────────────────────────────────

def _print_chat_hint() -> None:
    """Print the standard 'try macmaint chat' footer hint."""
    from rich.panel import Panel
    from rich import box
    console.print()
    console.print(Panel(
        "  Type [bold cyan]macmaint chat[/bold cyan] for detailed analysis and AI-powered recommendations",
        style="dim",
        box=box.ROUNDED,
        border_style="cyan dim",
    ))


# ── Single-shot chat helper ───────────────────────────────────────────────────

def _launch_chat_with_question(question: str) -> None:
    """Initialise the AI assistant, send *question* as the first message, stream
    the response to the terminal, then exit.  This is used by the thin-wrapper
    commands (ask, explain, insights, analyze_disk, analyze_memory) so they
    all go through the same Orchestrator / tool-call pipeline as interactive
    chat, rather than the legacy AIClient path.
    """
    from rich.panel import Panel
    from rich.markdown import Markdown
    from rich import box

    from macmaint.assistant.session import SessionManager
    from macmaint.assistant.tools import ToolExecutor
    from macmaint.assistant.orchestrator import Orchestrator
    from macmaint.utils.profile import ProfileManager

    config = get_config()
    if not config.api_key:
        print_error("No API key found. Run 'macmaint init' to configure")
        sys.exit(1)

    profile_manager = ProfileManager()
    session_manager = SessionManager(config, profile_manager)
    tool_executor = ToolExecutor(config, profile_manager)

    try:
        orchestrator = Orchestrator(config, tool_executor, profile_manager)
    except Exception as e:
        print_error(f"Failed to initialise AI orchestrator: {e}")
        sys.exit(1)

    # Create a fresh single-use session
    session = session_manager.create_new_session()

    response_chunks = []

    def on_stream_chunk(chunk: str) -> None:
        response_chunks.append(chunk)

    def on_tool_call(tool_name: str, args: dict) -> None:
        display = tool_name.split(":")[-1] if ":" in tool_name else tool_name
        console.print(f"[dim cyan]  ⚙ {display}…[/dim cyan]")

    def on_tool_result(tool_name: str, result: dict) -> None:
        pass  # silence — the response panel will show the outcome

    try:
        session_manager.add_message(session, "user", question)
        response_message = orchestrator.process_message(
            session=session,
            user_message=question,
            on_stream_chunk=on_stream_chunk,
            on_tool_call=on_tool_call,
            on_tool_result=on_tool_result,
        )
        full_response = response_message.content or ""
        if full_response.strip():
            console.print()
            console.print(Panel(
                Markdown(full_response),
                border_style="cyan",
                padding=(1, 2),
                box=box.ROUNDED,
            ))
        session_manager.add_message(session, "assistant", full_response)
    except Exception as e:
        print_error(f"AI request failed: {e}")
    finally:
        session_manager.save_session(session)

    console.print()


# ── CLI group ─────────────────────────────────────────────────────────────────

@click.group()
@click.version_option(version=__version__)
def cli():
    """MacMaint - AI-powered Mac maintenance and optimization agent.

    Keep your Mac running smoothly with intelligent system monitoring,
    automated cleanup, and performance optimization.
    """
    pass


# ── init ──────────────────────────────────────────────────────────────────────

@cli.command()
@click.option('--api-key', help='OpenAI API key (or set OPENAI_API_KEY env var)')
def init(api_key):
    """Initialize MacMaint configuration."""
    print_header("MacMaint Setup")
    console.print()

    config = get_config()
    env_file = Path.home() / ".macmaint" / ".env"

    # --- Detect existing configuration ---
    existing_key = None
    if env_file.exists():
        try:
            content = env_file.read_text()
            for line in content.splitlines():
                if line.startswith("OPENAI_API_KEY="):
                    value = line.split("=", 1)[1].strip()
                    if value:
                        existing_key = value
                        break
        except (OSError, PermissionError):
            pass

    if existing_key and not api_key:
        # Show masked key: keep first 7 chars (e.g. "sk-proj") and last 4
        masked = existing_key[:7] + "..." + existing_key[-4:] if len(existing_key) > 11 else "sk-..."
        print_success(f"MacMaint is already configured (API key: {masked})")
        console.print()
        replace = click.confirm("Replace the existing API key?", default=False)
        if not replace:
            print_info("Configuration unchanged. Run 'macmaint scan' to analyze your system.")
            return
        console.print()

    # --- Prompt for a new key if not supplied via flag ---
    if not api_key:
        api_key = click.prompt("Enter your OpenAI API key", hide_input=True)

    if not api_key or not api_key.startswith("sk-"):
        print_error("Invalid API key format")
        sys.exit(1)

    # Save API key to .env file
    env_file.parent.mkdir(parents=True, exist_ok=True)
    with open(env_file, "w") as f:
        f.write(f"OPENAI_API_KEY={api_key}\n")

    # Save default configuration
    config.save()

    print_success(f"Configuration saved to {config.CONFIG_FILE}")
    print_success(f"API key saved to {env_file}")
    console.print()
    console.print("  [bold cyan]Get started with AI chat:[/bold cyan]   macmaint chat")
    console.print("  [dim]Or run a quick scan:[/dim]        macmaint scan")
    console.print()


# ── scan ──────────────────────────────────────────────────────────────────────

@cli.command()
@click.option('--no-ai', is_flag=True, help='Disable AI analysis')
@click.option('--verbose', is_flag=True, help='Show detailed output')
def scan(no_ai, verbose):
    """Scan system for maintenance issues."""
    print_header("MacMaint System Scan")
    console.print()

    config = get_config()

    # Check for API key if AI is enabled
    if not no_ai and not config.api_key:
        print_warning("No API key found. Run 'macmaint init' to configure, or use --no-ai flag")
        print_info("Continuing without AI analysis...")
        no_ai = True
        console.print()

    # Create scanner
    scanner = Scanner(use_ai=not no_ai)

    # Run scan with progress indicators
    with create_progress() as progress:
        task = progress.add_task("Analyzing system...", total=100)

        progress.update(task, advance=30, description="Analyzing Disk Space")
        progress.update(task, advance=30, description="Analyzing Memory")
        progress.update(task, advance=20, description="Analyzing CPU")

        metrics, issues = scanner.scan()

        if not no_ai:
            progress.update(task, advance=20, description="AI Analysis")
        else:
            progress.update(task, advance=20)

    console.print()

    # Print metrics summary if verbose
    if verbose:
        print_header("System Metrics")
        if metrics.disk:
            console.print(f"  Disk: {format_percentage(metrics.disk.percent_used)} used, {metrics.disk.free_gb:.1f} GB free")
        if metrics.memory:
            console.print(f"  Memory: {format_percentage(metrics.memory.percent_used)} used, {metrics.memory.available_gb:.1f} GB available")
        if metrics.cpu:
            console.print(f"  CPU: {metrics.cpu.cpu_percent:.1f}% average")
        if metrics.uptime_hours:
            console.print(f"  Uptime: {metrics.uptime_hours / 24:.1f} days")
        console.print()

    # Print issues
    print_issues_summary(issues)

    _print_chat_hint()


# ── fix ───────────────────────────────────────────────────────────────────────

@cli.command()
@click.option('--dry-run', is_flag=True, help='Simulate fixes without making changes')
@click.option('--yes', '-y', is_flag=True, help='Auto-confirm all actions (dangerous!)')
def fix(dry_run, yes):
    """Fix detected issues interactively."""
    print_header("MacMaint Fix Issues")
    console.print()

    if yes:
        print_warning("Auto-confirm mode enabled - all actions will be executed without prompts!")
        if not click.confirm("Are you sure you want to continue?"):
            print_info("Cancelled")
            return

    # First scan to get issues
    console.print("Scanning for issues...")
    scanner = Scanner(use_ai=False)  # Skip AI for fix command
    metrics, issues = scanner.scan()
    console.print()

    if not issues:
        print_success("No issues found!")
        _print_chat_hint()
        return

    # Execute fixes
    fixer = Fixer(dry_run=dry_run)

    # Override confirmation if --yes flag
    if yes:
        fixer.config.set("safety.require_confirmation", False)

    stats = fixer.fix_issues(issues)

    console.print()
    if stats["succeeded"] > 0:
        print_success(f"Successfully fixed {stats['succeeded']} issue(s)")
    if stats["failed"] > 0:
        print_error(f"Failed to fix {stats['failed']} issue(s)")

    _print_chat_hint()


# ── status ────────────────────────────────────────────────────────────────────

@cli.command()
def status():
    """Show quick system status."""
    print_header("MacMaint Status")
    console.print()

    scanner = Scanner(use_ai=False)
    status_info = scanner.quick_status()

    # Disk
    disk_percent = status_info["disk"]["percent_used"]
    disk_free = status_info["disk"]["free_gb"]
    console.print(f"  Disk: {format_percentage(disk_percent)} used ({disk_free:.1f} GB free)")

    # Memory
    mem_percent = status_info["memory"]["percent_used"]
    mem_avail = status_info["memory"]["available_gb"]
    console.print(f"  Memory: {format_percentage(mem_percent)} used ({mem_avail:.1f} GB available)")

    # CPU
    cpu_percent = status_info["cpu"]["percent"]
    console.print(f"  CPU: {cpu_percent:.1f}% current usage")

    # Uptime
    uptime_days = status_info["uptime_hours"] / 24
    console.print(f"  Uptime: {uptime_days:.1f} days")

    console.print()

    # Health indicator
    if disk_percent > 90 or mem_percent > 90:
        print_warning("System health: Needs attention")
        print_info("Run 'macmaint scan' for details")
    elif disk_percent > 80 or mem_percent > 80:
        print_warning("System health: Fair")
    else:
        print_success("System health: Good")

    _print_chat_hint()


# ── config ────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument('key', required=False)
@click.argument('value', required=False)
def config(key, value):
    """View or modify configuration."""
    cfg = get_config()

    if not key:
        # Show config file location
        print_info(f"Configuration file: {cfg.CONFIG_FILE}")
        print_info(f"Edit the file directly to modify settings")
        return

    if not value:
        # Get value
        val = cfg.get(key)
        if val is not None:
            console.print(f"{key} = {val}")
        else:
            print_error(f"Configuration key '{key}' not found")
    else:
        # Set value
        cfg.set(key, value)
        cfg.save()
        print_success(f"Set {key} = {value}")


# ── dashboard ─────────────────────────────────────────────────────────────────

def _create_battery_panel(metrics):
    """Build the battery health Rich Panel for the dashboard."""
    from rich.panel import Panel
    from rich.table import Table
    from rich import box

    battery = getattr(metrics, "battery", None)

    if battery is None:
        # Desktop Mac — no battery
        from rich.align import Align
        from rich.text import Text
        content = Align.center(Text("No Battery", style="dim"))
        return Panel(content, title="Battery Health", border_style="dim", box=box.ROUNDED)

    rows = []

    # Capacity with colour
    capacity = getattr(battery, "health_percent", None)
    cycles = getattr(battery, "cycle_count", None)
    if capacity is not None:
        if capacity >= 80:
            cap_style = "green"
        elif capacity >= 70:
            cap_style = "yellow"
        else:
            cap_style = "red"
        cyc_str = f" ({cycles} cycles)" if cycles is not None else ""
        rows.append(("Capacity", f"[{cap_style}]{capacity:.0f}%[/{cap_style}]{cyc_str}"))

    # Temperature
    temp = getattr(battery, "temperature_c", None)
    if temp is not None:
        if temp < 35:
            temp_icon = "✓"
            temp_style = "green"
        elif temp < 40:
            temp_icon = "⚠"
            temp_style = "yellow"
        elif temp < 50:
            temp_icon = "🔥"
            temp_style = "red"
        else:
            temp_icon = "❌"
            temp_style = "bold red"
        rows.append(("Temp", f"[{temp_style}]{temp:.0f}°C {temp_icon}[/{temp_style}]"))

    # Charging state
    charging_state = getattr(battery, "charging_state", None)
    if charging_state:
        rows.append(("Charging", str(charging_state)))

    # Age
    age_days = getattr(battery, "battery_age_days", None)
    if age_days is not None:
        age_years = age_days / 365.25
        rows.append(("Age", f"{age_years:.1f} years"))

    t = Table(box=box.SIMPLE, show_header=False, show_edge=False, padding=(0, 1))
    t.add_column(style="dim", no_wrap=True)
    t.add_column()
    for label, value in rows:
        t.add_row(label, value)

    # Pick border colour based on capacity
    if capacity is None:
        border = "cyan"
    elif capacity >= 80:
        border = "green"
    elif capacity >= 70:
        border = "yellow"
    else:
        border = "red"

    return Panel(t, title="Battery Health", border_style=border, box=box.ROUNDED)


@cli.command()
def dashboard():
    """Show system dashboard with health overview."""
    from rich.layout import Layout
    from rich.panel import Panel
    from rich.table import Table
    from rich import box

    print_header("MacMaint Dashboard")
    console.print()

    # Scan system
    scanner = Scanner(use_ai=False)

    with create_progress() as progress:
        task = progress.add_task("Loading dashboard...", total=100)
        metrics, issues = scanner.scan()
        progress.update(task, completed=100)

    console.print()

    # Calculate health score
    health_score = _calculate_health_score(metrics)
    health_status, health_color = _get_health_status(health_score)

    # Create four-column layout
    layout = Layout()
    layout.split_row(
        Layout(name="left"),
        Layout(name="center"),
        Layout(name="battery"),
        Layout(name="right"),
    )

    # Left: Health Score
    health_table = Table(box=box.ROUNDED, show_header=False, padding=(1, 2))
    health_table.add_row("[bold]Health Score[/bold]")
    health_table.add_row(f"[{health_color}]{health_score}/100[/{health_color}]")
    health_table.add_row(f"[{health_color}]{health_status}[/{health_color}]")
    layout["left"].update(Panel(health_table, title="System Health", border_style=health_color))

    # Center: Quick Metrics
    metrics_table = Table(box=box.SIMPLE, show_header=False)

    if metrics.disk:
        metrics_table.add_row("Disk", format_percentage(metrics.disk.percent_used), f"{metrics.disk.free_gb:.1f} GB free")
    if metrics.memory:
        metrics_table.add_row("Memory", format_percentage(metrics.memory.percent_used), f"{metrics.memory.available_gb:.1f} GB available")
    if metrics.cpu:
        metrics_table.add_row("CPU", f"{metrics.cpu.cpu_percent:.1f}%", f"Load: {metrics.cpu.load_average[0]:.2f}" if metrics.cpu.load_average else "")
    if metrics.memory and metrics.memory.swap_used_gb > 0:
        metrics_table.add_row("Swap", f"{metrics.memory.swap_used_gb:.1f} GB", "in use")

    layout["center"].update(Panel(metrics_table, title="Quick Metrics", border_style="cyan"))

    # Battery panel
    layout["battery"].update(_create_battery_panel(metrics))

    # Right: Top Issues
    critical = [i for i in issues if str(i.severity) == "IssueSeverity.CRITICAL" or "critical" in str(i.severity).lower()]
    warnings = [i for i in issues if str(i.severity) == "IssueSeverity.WARNING" or "warning" in str(i.severity).lower()]
    top_issues = (critical + warnings)[:5]

    issues_table = Table(box=box.SIMPLE, show_header=False, show_edge=False)

    if top_issues:
        for issue in top_issues:
            severity_str = str(issue.severity).split('.')[-1].lower() if '.' in str(issue.severity) else str(issue.severity).lower()
            if severity_str == "critical":
                icon = "[red]●[/red]"
            elif severity_str == "warning":
                icon = "[yellow]●[/yellow]"
            else:
                icon = "[blue]●[/blue]"

            issues_table.add_row(icon, issue.title[:45])
    else:
        issues_table.add_row("[green]✓[/green]", "No issues detected")

    layout["right"].update(Panel(issues_table, title=f"Top Issues ({len(issues)} total)", border_style="yellow"))

    console.print(layout)
    console.print()

    if len(issues) > 5:
        print_info(f"Run 'macmaint scan' to see all {len(issues)} issues")
    if issues:
        print_info("Run 'macmaint fix' to address these issues")

    _print_chat_hint()


# ── analyze-disk  →  chat redirect ───────────────────────────────────────────

@cli.command(name="analyze-disk")
@click.option('--tree', is_flag=True, hidden=True)
@click.option('--table', 'as_table', is_flag=True, hidden=True)
def analyze_disk(tree, as_table):
    """Analyze disk usage in detail (AI-powered via chat)."""
    print_header("Disk Analysis")
    console.print()
    _launch_chat_with_question(
        "Analyze my disk usage in detail. Show a full breakdown of what's using space, "
        "including cache files, large files, and any cleanup recommendations."
    )


# ── analyze-memory  →  chat redirect ─────────────────────────────────────────

@cli.command(name="analyze-memory")
@click.option('--processes', is_flag=True, hidden=True)
def analyze_memory(processes):
    """Analyze memory usage in detail (AI-powered via chat)."""
    print_header("Memory Analysis")
    console.print()
    _launch_chat_with_question(
        "Analyze my memory usage in detail. Show what's consuming the most memory, "
        "whether swap is being used, and any optimization recommendations."
    )


# ── trends  (hidden) ──────────────────────────────────────────────────────────

@cli.command(hidden=True)
@click.option('--days', default=7, help='Number of days to show (default: 7)')
def trends(days):
    """Show historical trends for system metrics."""
    from macmaint.utils.history import HistoryManager, create_sparkline, calculate_trend_direction
    from rich.table import Table
    from rich import box

    print_header(f"System Trends ({days} days)")
    console.print()

    history_manager = HistoryManager()
    snapshots = history_manager.get_snapshots(days)

    if len(snapshots) < 2:
        print_warning("Not enough historical data available")
        print_info(f"Run 'macmaint scan' regularly to build trend history")
        print_info(f"Found {len(snapshots)} snapshot(s), need at least 2")
        return

    console.print(f"Showing trends based on {len(snapshots)} snapshots\n")

    # Create trends table
    trends_table = Table(box=box.ROUNDED, show_header=True)
    trends_table.add_column("Metric", style="cyan", no_wrap=True)
    trends_table.add_column("Trend", style="yellow", width=25)
    trends_table.add_column("Change", justify="right", style="magenta")
    trends_table.add_column("Current", justify="right", style="green")

    # Define metrics to track
    metrics_to_track = [
        ("disk.percent_used", "Disk Usage", "%"),
        ("memory.percent_used", "Memory Usage", "%"),
        ("cpu.cpu_percent", "CPU Average", "%"),
        ("memory.swap_used_gb", "Swap Usage", "GB"),
    ]

    for metric_path, label, unit in metrics_to_track:
        trend_data = history_manager.get_trend_data(metric_path, days)

        if not trend_data:
            continue

        values = [v for _, v in trend_data]
        current_value = values[-1] if values else 0

        sparkline = create_sparkline(values, width=20)
        direction, change_pct = calculate_trend_direction(values)

        # Color code direction
        if direction == "↑":
            dir_color = "red" if "usage" in label.lower() else "green"
        elif direction == "↓":
            dir_color = "green" if "usage" in label.lower() else "red"
        else:
            dir_color = "yellow"

        trends_table.add_row(
            label,
            sparkline,
            f"[{dir_color}]{direction} {change_pct:.1f}%[/{dir_color}]",
            f"{current_value:.1f}{unit}"
        )

    console.print(trends_table)
    console.print()

    # Show date range
    first_date = snapshots[0]['date']
    last_date = snapshots[-1]['date']
    console.print(f"[dim]Data range: {first_date} to {last_date}[/dim]\n")


# ── ask  →  chat redirect ─────────────────────────────────────────────────────

@cli.command()
@click.argument('question', required=True)
def ask(question):
    """Ask a natural language question about your Mac.

    Example: macmaint ask "Why is my Mac running slow?"
    """
    print_header("AI Assistant")
    console.print()
    _launch_chat_with_question(question)


# ── explain  →  chat redirect ─────────────────────────────────────────────────

@cli.command()
@click.argument('issue_id', required=False)
def explain(issue_id):
    """Get a detailed explanation of a system issue.

    If no issue ID is provided, shows a list to select from.
    """
    from rich.prompt import Prompt

    print_header("Issue Explanation")
    console.print()

    # Scan to get issues so we can pick one interactively
    console.print("Scanning for issues...")
    scanner = Scanner(use_ai=False)

    with create_progress() as progress:
        task = progress.add_task("Scanning...", total=100)
        metrics, issues = scanner.scan()
        progress.update(task, completed=100)

    console.print()

    if not issues:
        print_success("No issues found!")
        return

    # If no issue ID provided, let user select
    if not issue_id:
        console.print("[bold]Available Issues:[/bold]\n")
        for idx, issue in enumerate(issues, 1):
            severity_str = str(issue.severity).split('.')[-1].lower() if '.' in str(issue.severity) else str(issue.severity).lower()
            if severity_str == "critical":
                icon = "[red]●[/red]"
            elif severity_str == "warning":
                icon = "[yellow]●[/yellow]"
            else:
                icon = "[blue]●[/blue]"

            console.print(f"  {idx}. {icon} {issue.title}")

        console.print()
        choice = Prompt.ask("Select issue number", default="1")

        try:
            idx = int(choice) - 1
            if idx < 0 or idx >= len(issues):
                print_error("Invalid selection")
                return
            selected_issue = issues[idx]
        except ValueError:
            print_error("Invalid selection")
            return
    else:
        # Find issue by ID
        selected_issue = None
        for issue in issues:
            if issue.issue_id == issue_id:
                selected_issue = issue
                break

        if not selected_issue:
            print_error(f"Issue '{issue_id}' not found")
            return

    question = (
        f"Explain in detail the following Mac maintenance issue and how to resolve it: "
        f"'{selected_issue.title}'. "
        f"Description: {getattr(selected_issue, 'description', '')}. "
        f"Include root cause, impact, and step-by-step fix instructions."
    )
    _launch_chat_with_question(question)


# ── insights  →  chat redirect ────────────────────────────────────────────────

@cli.command()
def insights():
    """Get proactive insights and maintenance recommendations.

    AI analyzes your system patterns and predicts future issues.
    """
    print_header("Proactive Insights")
    console.print()
    _launch_chat_with_question(
        "Give me proactive insights and maintenance recommendations for my Mac. "
        "Analyse my current system state, identify any trends or patterns, "
        "predict future issues, and suggest a maintenance plan."
    )


# ── chat ──────────────────────────────────────────────────────────────────────

@cli.command()
@click.option('--new', is_flag=True, help='Start a new conversation (ignore previous sessions)')
def chat(new):
    """Start interactive AI assistant mode.

    Launch a conversational interface where you can chat with the AI assistant
    to scan, fix, and optimize your Mac through natural language.
    """
    from macmaint.assistant.repl import AssistantREPL
    from macmaint.assistant.session import SessionManager
    from macmaint.assistant.tools import ToolExecutor
    from macmaint.assistant.orchestrator import Orchestrator
    from macmaint.utils.profile import ProfileManager

    print_header("MacMaint Interactive Assistant")
    console.print()

    # Load config and check API key
    config = get_config()
    if not config.api_key:
        print_error("No API key found. Run 'macmaint init' to configure")
        sys.exit(1)

    # Initialize components
    profile_manager = ProfileManager()
    session_manager = SessionManager(config, profile_manager)
    tool_executor = ToolExecutor(config, profile_manager)

    # Initialize orchestrator (Sprint 2)
    try:
        orchestrator = Orchestrator(config, tool_executor, profile_manager)
    except Exception as e:
        print_error(f"Failed to initialize AI orchestrator: {e}")
        sys.exit(1)

    # Start REPL
    repl = AssistantREPL(session_manager, tool_executor, orchestrator=orchestrator)

    try:
        repl.start(force_new=new)
    except KeyboardInterrupt:
        console.print("\n\nSession interrupted. Goodbye!")
    except Exception as e:
        print_error(f"Session error: {e}")
        if config.verbose:
            import traceback
            traceback.print_exc()


# ── Update command ────────────────────────────────────────────────────────────

@cli.command()
@click.option('--check-only', is_flag=True, help='Only check for updates, do not install')
@click.option('--force', is_flag=True, help='Bypass 24-hour cache and re-fetch from GitHub')
def update(check_only, force):
    """Check for a newer version of MacMaint and optionally install it.

    MacMaint is distributed via Homebrew, so updates are applied with
    'brew upgrade macmaint'.  Results are cached for 24 hours; use --force
    to bypass the cache.
    """
    from macmaint.utils.updater import check_for_updates, run_brew_upgrade
    from rich.panel import Panel
    from rich import box

    console.print()

    with create_progress() as progress:
        task = progress.add_task("Checking for updates…", total=None)
        info = check_for_updates(force=force)
        progress.update(task, completed=True)

    if info.get("error"):
        print_error(f"Update check failed: {info['error']}")
        return

    current = info["current_version"]
    latest  = info["latest_version"]
    cached  = " [dim](cached)[/dim]" if info["from_cache"] else ""

    if not info["update_available"]:
        console.print(Panel(
            f"  [bold bright_green]You're up to date![/bold bright_green]{cached}\n\n"
            f"  Current version:  [bold]{current}[/bold]\n"
            f"  Latest release:   [bold]{latest}[/bold]",
            border_style="green",
            box=box.ROUNDED,
            padding=(1, 3),
        ))
        return

    console.print(Panel(
        f"  [bold yellow]Update available![/bold yellow]{cached}\n\n"
        f"  Installed:  [bold]{current}[/bold]\n"
        f"  Latest:     [bold bright_cyan]{latest}[/bold bright_cyan]\n\n"
        f"  [dim]{info['release_url']}[/dim]",
        border_style="yellow",
        box=box.ROUNDED,
        padding=(1, 3),
    ))

    if check_only:
        console.print()
        print_info("Run [bold]macmaint update[/bold] (without --check-only) to install.")
        return

    console.print()
    if not click.confirm("Install update now via 'brew upgrade macmaint'?", default=True):
        print_info("Skipped. Run [bold]macmaint update[/bold] when you're ready.")
        return

    console.print()
    with create_progress() as progress:
        task = progress.add_task("Running brew upgrade macmaint…", total=None)
        result = run_brew_upgrade()
        progress.update(task, completed=True)

    console.print()
    if result["success"]:
        print_success("MacMaint updated successfully!")
        if result["output"]:
            console.print(f"[dim]{result['output']}[/dim]")
    else:
        print_error(f"Update failed: {result['error']}")
        if result["output"]:
            console.print(f"[dim]{result['output']}[/dim]")


# ── Session management commands ───────────────────────────────────────────────

@cli.group()
def session():
    """Manage conversation sessions.

    List, create, or delete saved chat sessions.
    """
    pass


@session.command(name="list")
@click.option('--limit', default=20, show_default=True, help='Maximum number of sessions to show')
def session_list(limit):
    """List saved conversation sessions."""
    from rich.table import Table
    from rich import box as rbox
    from macmaint.assistant.session import SessionManager
    from macmaint.utils.profile import ProfileManager

    config = get_config()
    sm = SessionManager(config, ProfileManager())
    sessions = sm.list_sessions(limit=limit)

    if not sessions:
        print_info("No saved sessions found.")
        return

    t = Table(box=rbox.SIMPLE_HEAD, show_header=True, header_style="bold cyan")
    t.add_column("Session ID", style="dim", no_wrap=True)
    t.add_column("Messages", justify="right")
    t.add_column("Started", style="bright_white")
    t.add_column("Last Active", style="bright_white")

    for s in sessions:
        from datetime import datetime as _dt
        def _fmt(iso):
            try:
                return _dt.fromisoformat(iso).strftime("%b %d %Y  %H:%M")
            except Exception:
                return iso
        t.add_row(s["session_id"], str(s["message_count"]), _fmt(s["started_at"]), _fmt(s["last_active"]))

    console.print()
    console.print(t)
    console.print(f"  [dim]{len(sessions)} session(s) stored in ~/.macmaint/conversations/[/dim]\n")


@session.command(name="new")
def session_new():
    """Start a new chat session (alias for: macmaint chat --new)."""
    from macmaint.assistant.repl import AssistantREPL
    from macmaint.assistant.session import SessionManager
    from macmaint.assistant.tools import ToolExecutor
    from macmaint.assistant.orchestrator import Orchestrator
    from macmaint.utils.profile import ProfileManager

    config = get_config()
    if not config.api_key:
        print_error("No API key found. Run 'macmaint init' to configure")
        import sys; sys.exit(1)

    profile_manager = ProfileManager()
    session_manager = SessionManager(config, profile_manager)
    tool_executor = ToolExecutor(config, profile_manager)

    try:
        orchestrator = Orchestrator(config, tool_executor, profile_manager)
    except Exception as e:
        print_error(f"Failed to initialize AI orchestrator: {e}")
        import sys; sys.exit(1)

    repl = AssistantREPL(session_manager, tool_executor, orchestrator=orchestrator)
    try:
        repl.start(force_new=True)
    except KeyboardInterrupt:
        console.print("\n\nSession interrupted. Goodbye!")


@session.command(name="delete")
@click.argument('session_id', required=False)
@click.option('--all', 'delete_all', is_flag=True, help='Delete ALL saved sessions')
@click.option('--yes', '-y', is_flag=True, help='Skip confirmation prompt')
def session_delete(session_id, delete_all, yes):
    """Delete a specific session or all sessions.

    SESSION_ID  The session ID to delete (from: macmaint session list).
    Use --all to wipe every saved session at once.
    """
    from macmaint.assistant.session import SessionManager
    from macmaint.utils.profile import ProfileManager

    if not session_id and not delete_all:
        print_error("Provide a SESSION_ID or use --all to delete everything.")
        print_info("Run 'macmaint session list' to see available sessions.")
        return

    config = get_config()
    sm = SessionManager(config, ProfileManager())

    if delete_all:
        sessions = sm.list_sessions(limit=1000)
        count = len(sessions)
        if count == 0:
            print_info("No sessions found.")
            return
        if not yes:
            click.confirm(f"Delete all {count} session(s)? This cannot be undone.", abort=True)
        deleted = sm.delete_all_sessions()
        print_success(f"Deleted {deleted} session(s).")
        return

    # Single session delete
    if not yes:
        click.confirm(f"Delete session '{session_id}'?", abort=True)

    try:
        deleted = sm.delete_session(session_id)
    except ValueError as e:
        print_error(str(e))
        return

    if deleted:
        print_success(f"Session '{session_id}' deleted.")
    else:
        print_error(f"Session '{session_id}' not found.")
        print_info("Run 'macmaint session list' to see available sessions.")


# ── Private helpers ───────────────────────────────────────────────────────────

def _calculate_health_score(metrics) -> int:
    """Calculate overall health score (0-100)."""
    score = 100

    if metrics.disk:
        if metrics.disk.percent_used >= 95:
            score -= 30
        elif metrics.disk.percent_used >= 85:
            score -= 15
        elif metrics.disk.percent_used >= 75:
            score -= 5

    if metrics.memory:
        if metrics.memory.percent_used >= 95:
            score -= 25
        elif metrics.memory.percent_used >= 85:
            score -= 12
        elif metrics.memory.percent_used >= 75:
            score -= 5

        if metrics.memory.swap_used_gb > 4:
            score -= 15
        elif metrics.memory.swap_used_gb > 2:
            score -= 8

    if metrics.cpu:
        if metrics.cpu.cpu_percent >= 90:
            score -= 10
        elif metrics.cpu.cpu_percent >= 70:
            score -= 5

    return max(0, score)


def _get_health_status(score: int) -> tuple:
    """Get health status and color from score."""
    if score >= 90:
        return "Excellent", "green"
    elif score >= 75:
        return "Good", "cyan"
    elif score >= 60:
        return "Fair", "yellow"
    elif score >= 40:
        return "Poor", "orange"
    else:
        return "Critical", "red"


if __name__ == "__main__":
    cli()
