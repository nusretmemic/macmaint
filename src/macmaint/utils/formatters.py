"""Rich terminal formatting utilities."""
from typing import List, Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.prompt import Confirm
from rich import box

from macmaint.models.issue import Issue, IssueSeverity


console = Console()


def print_header(text: str):
    """Print a formatted header."""
    console.print(f"\n[bold cyan]{text}[/bold cyan]")
    console.print("─" * len(text))


def print_success(text: str):
    """Print a success message."""
    console.print(f"[green]✓[/green] {text}")


def print_error(text: str):
    """Print an error message."""
    console.print(f"[red]✗[/red] {text}")


def print_warning(text: str):
    """Print a warning message."""
    console.print(f"[yellow]⚠[/yellow]  {text}")


def print_info(text: str):
    """Print an info message."""
    console.print(f"[blue]ℹ[/blue]  {text}")


def confirm(question: str, default: bool = False) -> bool:
    """Ask for user confirmation."""
    return Confirm.ask(question, default=default)


def print_issues_summary(issues: List[Issue]):
    """Print a formatted summary of issues."""
    if not issues:
        print_success("No issues found!")
        return
    
    # Group issues by severity
    critical = [i for i in issues if i.severity == IssueSeverity.CRITICAL]
    warnings = [i for i in issues if i.severity == IssueSeverity.WARNING]
    info = [i for i in issues if i.severity == IssueSeverity.INFO]
    
    console.print()
    console.print(Panel(
        "[bold]System Health Report[/bold]",
        box=box.DOUBLE,
        expand=False
    ))
    console.print()
    
    if critical:
        console.print(f"[bold red]🔴 CRITICAL ({len(critical)} issue{'s' if len(critical) > 1 else ''})[/bold red]")
        for issue in critical:
            console.print(f"  • {issue.title}")
            if issue.ai_recommendation:
                console.print(f"    [dim]{issue.ai_recommendation}[/dim]")
        console.print()
    
    if warnings:
        console.print(f"[bold yellow]🟡 WARNING ({len(warnings)} issue{'s' if len(warnings) > 1 else ''})[/bold yellow]")
        for issue in warnings:
            console.print(f"  • {issue.title}")
            if issue.ai_recommendation:
                console.print(f"    [dim]{issue.ai_recommendation}[/dim]")
        console.print()
    
    if info:
        console.print(f"[bold blue]🔵 INFO ({len(info)} issue{'s' if len(info) > 1 else ''})[/bold blue]")
        for issue in info:
            console.print(f"  • {issue.title}")
        console.print()
    
    # Print available actions
    total_actions = sum(len(i.fix_actions) for i in issues)
    if total_actions > 0:
        console.print(f"[dim]Run 'macmaint fix' to address these issues[/dim]\n")


def print_metrics_table(title: str, data: dict):
    """Print a formatted table of metrics."""
    table = Table(title=title, box=box.SIMPLE)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    
    for key, value in data.items():
        table.add_row(key, str(value))
    
    console.print(table)


def format_bytes(bytes: float) -> str:
    """Format bytes to human-readable string."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes < 1024.0:
            return f"{bytes:.1f} {unit}"
        bytes /= 1024.0
    return f"{bytes:.1f} PB"


def format_percentage(value: float) -> str:
    """Format percentage with color coding."""
    if value >= 90:
        return f"[red]{value:.1f}%[/red]"
    elif value >= 75:
        return f"[yellow]{value:.1f}%[/yellow]"
    else:
        return f"[green]{value:.1f}%[/green]"


def create_progress() -> Progress:
    """Create a rich progress bar."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console,
        transient=True
    )
