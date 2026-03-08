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


@click.group()
@click.version_option(version=__version__)
def cli():
    """MacMaint - AI-powered Mac maintenance and optimization agent.
    
    Keep your Mac running smoothly with intelligent system monitoring,
    automated cleanup, and performance optimization.
    """
    pass


@cli.command()
@click.option('--api-key', help='OpenAI API key (or set OPENAI_API_KEY env var)')
def init(api_key):
    """Initialize MacMaint configuration."""
    print_header("MacMaint Setup")
    console.print()
    
    config = get_config()
    
    # Get API key
    if not api_key:
        api_key = click.prompt("Enter your OpenAI API key", hide_input=True)
    
    if not api_key or not api_key.startswith("sk-"):
        print_error("Invalid API key format")
        sys.exit(1)
    
    # Save API key to .env file
    env_file = Path.home() / ".macmaint" / ".env"
    env_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(env_file, "w") as f:
        f.write(f"OPENAI_API_KEY={api_key}\n")
    
    # Save default configuration
    config.save()
    
    print_success(f"Configuration saved to {config.CONFIG_FILE}")
    print_success(f"API key saved to {env_file}")
    console.print()
    print_info("Run 'macmaint scan' to analyze your system")


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
    
    # Create three-column layout
    layout = Layout()
    layout.split_row(
        Layout(name="left"),
        Layout(name="center"),
        Layout(name="right")
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


@cli.command()
@click.option('--tree', is_flag=True, help='Show cache breakdown as tree view')
@click.option('--table', is_flag=True, help='Show cache breakdown as table')
def analyze_disk(tree, table):
    """Analyze disk usage with detailed cache breakdown."""
    print_header("Disk Analysis")
    console.print()
    
    # Scan disk module
    config = get_config()
    from macmaint.modules.disk import DiskModule
    
    disk_module = DiskModule(config.get_module_config("disk"))
    
    with create_progress() as progress:
        task = progress.add_task("Analyzing disk usage...", total=100)
        metrics, issues = disk_module.scan()
        progress.update(task, completed=100)
    
    console.print()
    
    # Show basic metrics
    from macmaint.models.metrics import DiskMetrics
    disk_metrics = DiskMetrics(**metrics)
    
    console.print(f"[bold]Disk Usage:[/bold] {disk_metrics.used_gb:.1f} GB / {disk_metrics.total_gb:.1f} GB ({disk_metrics.percent_used:.1f}%)")
    console.print(f"[bold]Free Space:[/bold] {disk_metrics.free_gb:.1f} GB\n")
    
    # Show cache breakdown
    if disk_metrics.cache_breakdown:
        if tree or not table:
            print_cache_breakdown(disk_metrics.cache_breakdown)
        if table:
            print_cache_table(disk_metrics.cache_breakdown)
    else:
        print_info("No detailed cache breakdown available")
    
    # Show large files if any
    if disk_metrics.large_files:
        console.print("\n[bold cyan]Large Files in Downloads[/bold cyan]")
        from rich.table import Table
        
        large_files_table = Table(box=box.SIMPLE, show_header=True)
        large_files_table.add_column("File", style="cyan")
        large_files_table.add_column("Size", justify="right", style="yellow")
        large_files_table.add_column("Age", justify="right", style="blue")
        
        for file_info in disk_metrics.large_files[:10]:
            filename = Path(file_info['path']).name
            large_files_table.add_row(
                filename[:50],
                f"{file_info['size_mb'] / 1024:.2f} GB",
                f"{file_info['age_days']} days"
            )
        
        console.print(large_files_table)
        console.print()


@cli.command()
@click.option('--processes', is_flag=True, help='Show processes grouped by category')
def analyze_memory(processes):
    """Analyze memory usage with detailed breakdown."""
    print_header("Memory Analysis")
    console.print()
    
    # Scan memory module
    config = get_config()
    from macmaint.modules.memory import MemoryModule
    
    memory_module = MemoryModule(config.get_module_config("memory"))
    
    with create_progress() as progress:
        task = progress.add_task("Analyzing memory usage...", total=100)
        metrics, issues = memory_module.scan()
        progress.update(task, completed=100)
    
    console.print()
    
    # Show basic metrics
    from macmaint.models.metrics import MemoryMetrics
    mem_metrics = MemoryMetrics(**metrics)
    
    console.print(f"[bold]Memory Usage:[/bold] {mem_metrics.used_gb:.1f} GB / {mem_metrics.total_gb:.1f} GB ({mem_metrics.percent_used:.1f}%)")
    console.print(f"[bold]Available:[/bold] {mem_metrics.available_gb:.1f} GB")
    
    if mem_metrics.swap_used_gb > 0:
        console.print(f"[bold]Swap Usage:[/bold] {mem_metrics.swap_used_gb:.1f} GB / {mem_metrics.swap_total_gb:.1f} GB")
    
    # Show memory breakdown
    if mem_metrics.breakdown:
        print_memory_breakdown(mem_metrics.breakdown)
    
    # Show process categories
    if processes and mem_metrics.processes_by_category:
        print_process_categories(mem_metrics.processes_by_category)
    elif mem_metrics.top_processes:
        console.print("\n[bold cyan]Top Memory Processes[/bold cyan]")
        from rich.table import Table
        
        proc_table = Table(box=box.SIMPLE, show_header=True)
        proc_table.add_column("Process", style="cyan")
        proc_table.add_column("Memory", justify="right", style="yellow")
        proc_table.add_column("% of Total", justify="right", style="blue")
        
        for proc in mem_metrics.top_processes[:10]:
            proc_table.add_row(
                proc.name[:30],
                f"{proc.memory_mb / 1024:.2f} GB",
                f"{proc.memory_percent:.1f}%"
            )
        
        console.print(proc_table)
        console.print()


@cli.command()
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


@cli.command()
@click.argument('question', required=True)
def ask(question):
    """Ask a natural language question about your Mac.
    
    Example: macmaint ask "Why is my Mac running slow?"
    """
    from macmaint.ai.client import AIClient
    from macmaint.utils.profile import ProfileManager
    
    print_header("AI Assistant")
    console.print()
    
    # Load config and check API key
    config = get_config()
    if not config.api_key:
        print_error("No API key found. Run 'macmaint init' to configure")
        sys.exit(1)
    
    # Load user profile
    profile_manager = ProfileManager()
    profile_summary = profile_manager.get_summary()
    
    # Scan current system
    console.print("Gathering system information...")
    scanner = Scanner(use_ai=False)
    
    with create_progress() as progress:
        task = progress.add_task("Scanning...", total=100)
        metrics, issues = scanner.scan()
        progress.update(task, completed=100)
    
    console.print()
    
    # Get AI response
    console.print("[cyan]Thinking...[/cyan]\n")
    ai_client = AIClient(config.api_key)
    
    try:
        response = ai_client.ask_question(question, metrics.to_dict(), issues, profile_summary)
        
        # Format and display response
        from rich.panel import Panel
        from rich.markdown import Markdown
        
        console.print(Panel(
            Markdown(response),
            title="[bold cyan]Answer[/bold cyan]",
            border_style="cyan",
            padding=(1, 2)
        ))
        console.print()
        
    except Exception as e:
        print_error(f"AI request failed: {str(e)}")
        sys.exit(1)


@cli.command()
@click.argument('issue_id', required=False)
def explain(issue_id):
    """Get a detailed explanation of a system issue.
    
    If no issue ID is provided, shows a list to select from.
    """
    from macmaint.ai.client import AIClient
    from macmaint.utils.profile import ProfileManager
    from rich.prompt import Prompt
    
    print_header("Issue Explanation")
    console.print()
    
    # Load config and check API key
    config = get_config()
    if not config.api_key:
        print_error("No API key found. Run 'macmaint init' to configure")
        sys.exit(1)
    
    # Scan to get issues
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
    
    # Get detailed explanation from AI
    console.print("[cyan]Analyzing issue...[/cyan]\n")
    
    profile_manager = ProfileManager()
    profile_summary = profile_manager.get_summary()
    
    ai_client = AIClient(config.api_key)
    
    try:
        explanation = ai_client.explain_issue(selected_issue, metrics.to_dict(), profile_summary)
        
        # Format and display
        from rich.panel import Panel
        from rich.markdown import Markdown
        
        console.print(Panel(
            Markdown(explanation),
            title=f"[bold cyan]{selected_issue.title}[/bold cyan]",
            border_style="cyan",
            padding=(1, 2)
        ))
        console.print()
        
    except Exception as e:
        print_error(f"AI request failed: {str(e)}")
        sys.exit(1)


@cli.command()
def insights():
    """Get proactive insights and maintenance recommendations.
    
    AI analyzes your system patterns and predicts future issues.
    """
    from macmaint.ai.client import AIClient
    from macmaint.utils.profile import ProfileManager
    from macmaint.utils.history import HistoryManager
    
    print_header("Proactive Insights")
    console.print()
    
    # Load config and check API key
    config = get_config()
    if not config.api_key:
        print_error("No API key found. Run 'macmaint init' to configure")
        sys.exit(1)
    
    # Load current metrics
    console.print("Analyzing system patterns...")
    scanner = Scanner(use_ai=False)
    
    with create_progress() as progress:
        task = progress.add_task("Scanning...", total=100)
        metrics, issues = scanner.scan()
        progress.update(task, completed=100)
    
    console.print()
    
    # Load historical trends
    history_manager = HistoryManager()
    snapshots = history_manager.get_snapshots(30)  # Last 30 days
    
    # Load user profile
    profile_manager = ProfileManager()
    profile_summary = profile_manager.get_summary()
    
    # Get AI insights
    console.print("[cyan]Generating insights...[/cyan]\n")
    ai_client = AIClient(config.api_key)
    
    try:
        insights_text = ai_client.get_proactive_insights(
            metrics.to_dict(), 
            issues, 
            snapshots, 
            profile_summary
        )
        
        # Format and display
        from rich.panel import Panel
        from rich.markdown import Markdown
        
        console.print(Panel(
            Markdown(insights_text),
            title="[bold cyan]AI Insights & Recommendations[/bold cyan]",
            border_style="cyan",
            padding=(1, 2)
        ))
        console.print()
        
        if len(snapshots) < 7:
            print_info(f"Tip: Run 'macmaint scan' regularly to get more accurate predictions (currently have {len(snapshots)} data points)")
        
    except Exception as e:
        print_error(f"AI request failed: {str(e)}")
        sys.exit(1)


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
