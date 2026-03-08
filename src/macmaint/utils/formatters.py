"""Rich terminal formatting utilities."""
from typing import List, Optional, Dict
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.tree import Tree
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


def print_cache_breakdown(cache_breakdown: Dict):
    """Print cache breakdown as a tree view."""
    if not cache_breakdown:
        print_info("No cache data available")
        return
    
    tree = Tree("📦 [bold cyan]Cache Breakdown[/bold cyan]")
    
    # Sort categories by size
    sorted_categories = sorted(
        cache_breakdown.items(),
        key=lambda x: x[1].get('size_gb', 0) if isinstance(x[1], dict) else x[1].size_gb,
        reverse=True
    )
    
    total_size = 0
    total_files = 0
    
    for category_key, category_data in sorted_categories:
        # Handle both dict and CacheCategory object
        if isinstance(category_data, dict):
            name = category_data.get('name', category_key)
            size_gb = category_data.get('size_gb', 0)
            file_count = category_data.get('file_count', 0)
            percentage = category_data.get('percentage', 0)
        else:
            name = category_data.name
            size_gb = category_data.size_gb
            file_count = category_data.file_count
            percentage = category_data.percentage
        
        total_size += size_gb
        total_files += file_count
        
        # Color code by size
        if size_gb > 5:
            color = "red"
        elif size_gb > 1:
            color = "yellow"
        else:
            color = "green"
        
        branch = tree.add(
            f"[{color}]{name}[/{color}]: {size_gb:.2f} GB ({percentage:.1f}%) - {file_count:,} files"
        )
    
    console.print()
    console.print(tree)
    console.print(f"\n[bold]Total:[/bold] {total_size:.2f} GB across {total_files:,} files\n")


def print_cache_table(cache_breakdown: Dict):
    """Print cache breakdown as a table."""
    if not cache_breakdown:
        print_info("No cache data available")
        return
    
    table = Table(title="Cache Breakdown", box=box.ROUNDED, show_header=True)
    table.add_column("Category", style="cyan", no_wrap=True)
    table.add_column("Size", justify="right", style="yellow")
    table.add_column("Files", justify="right", style="blue")
    table.add_column("Percentage", justify="right", style="magenta")
    
    # Sort by size
    sorted_categories = sorted(
        cache_breakdown.items(),
        key=lambda x: x[1].get('size_gb', 0) if isinstance(x[1], dict) else x[1].size_gb,
        reverse=True
    )
    
    total_size = 0
    total_files = 0
    
    for category_key, category_data in sorted_categories:
        # Handle both dict and CacheCategory object
        if isinstance(category_data, dict):
            name = category_data.get('name', category_key)
            size_gb = category_data.get('size_gb', 0)
            file_count = category_data.get('file_count', 0)
            percentage = category_data.get('percentage', 0)
        else:
            name = category_data.name
            size_gb = category_data.size_gb
            file_count = category_data.file_count
            percentage = category_data.percentage
        
        total_size += size_gb
        total_files += file_count
        
        table.add_row(
            name,
            f"{size_gb:.2f} GB",
            f"{file_count:,}",
            f"{percentage:.1f}%"
        )
    
    # Add total row
    table.add_section()
    table.add_row(
        "[bold]TOTAL[/bold]",
        f"[bold]{total_size:.2f} GB[/bold]",
        f"[bold]{total_files:,}[/bold]",
        "[bold]100.0%[/bold]"
    )
    
    console.print()
    console.print(table)
    console.print()


def create_progress_bar(total: float, used: float, label: str = "") -> str:
    """Create a visual progress bar for percentages."""
    percentage = (used / total * 100) if total > 0 else 0
    bar_length = 20
    filled = int(bar_length * percentage / 100)
    bar = "█" * filled + "░" * (bar_length - filled)
    
    # Color code the bar
    if percentage >= 90:
        color = "red"
    elif percentage >= 75:
        color = "yellow"
    else:
        color = "green"
    
    return f"[{color}]{bar}[/{color}] {percentage:.1f}%"


def print_memory_breakdown(breakdown: Dict):
    """Print detailed memory breakdown with visual bars."""
    if not breakdown:
        print_info("Memory breakdown not available")
        return
    
    # Handle both dict and MemoryBreakdown object
    if isinstance(breakdown, dict):
        wired = breakdown.get('wired_gb', 0)
        active = breakdown.get('active_gb', 0)
        inactive = breakdown.get('inactive_gb', 0)
        compressed = breakdown.get('compressed_gb', 0)
        pressure = breakdown.get('pressure_level', 'normal')
    else:
        wired = breakdown.wired_gb
        active = breakdown.active_gb
        inactive = breakdown.inactive_gb
        compressed = breakdown.compressed_gb
        pressure = breakdown.pressure_level
    
    total = wired + active + inactive + compressed
    
    if total == 0:
        print_info("Memory breakdown not available")
        return
    
    console.print("\n[bold cyan]Memory Breakdown[/bold cyan]")
    console.print("─" * 50)
    
    # Pressure indicator
    pressure_colors = {
        'normal': 'green',
        'warning': 'yellow',
        'critical': 'red'
    }
    pressure_str = str(pressure).split('.')[-1] if '.' in str(pressure) else str(pressure)
    pressure_color = pressure_colors.get(pressure_str.lower(), 'white')
    console.print(f"Memory Pressure: [{pressure_color}]●[/{pressure_color}] {pressure_str.upper()}\n")
    
    # Memory type breakdown
    memory_types = [
        ('Wired', wired, 'red', 'Cannot be paged out (kernel, drivers)'),
        ('Active', active, 'yellow', 'Recently accessed, in use'),
        ('Inactive', inactive, 'blue', 'Not recently used, can be freed'),
        ('Compressed', compressed, 'magenta', 'Compressed to save space')
    ]
    
    for label, size_gb, color, description in memory_types:
        if total > 0:
            percentage = (size_gb / total) * 100
            bar = create_progress_bar(total, size_gb)
            console.print(f"[{color}]{label:12}[/{color}]: {size_gb:6.2f} GB {bar}")
            console.print(f"{'':14}  [dim]{description}[/dim]")
    
    console.print(f"\n[bold]Total:[/bold] {total:.2f} GB\n")


def print_process_categories(processes_by_category: Dict):
    """Print processes grouped by category with tables."""
    if not processes_by_category:
        print_info("No process categorization available")
        return
    
    categories = {
        'system': ('System Processes', 'cyan'),
        'application': ('Applications', 'green'),
        'background': ('Background Services', 'yellow')
    }
    
    for category_key, (title, color) in categories.items():
        processes = processes_by_category.get(category_key, [])
        
        if not processes:
            continue
        
        # Calculate total memory for this category
        total_memory = sum(
            p.get('memory_mb', 0) if isinstance(p, dict) else p.memory_mb 
            for p in processes
        )
        
        console.print(f"\n[bold {color}]{title}[/bold {color}] - {len(processes)} processes, {total_memory / 1024:.2f} GB")
        
        # Create table for top processes in this category
        table = Table(box=box.SIMPLE, show_header=True, show_edge=False)
        table.add_column("Process", style=color, no_wrap=True, max_width=30)
        table.add_column("Memory", justify="right", style="yellow")
        table.add_column("% of Total", justify="right", style="blue")
        
        # Show top 5 processes in each category
        top_processes = sorted(
            processes[:5],
            key=lambda p: p.get('memory_mb', 0) if isinstance(p, dict) else p.memory_mb,
            reverse=True
        )
        
        for proc in top_processes:
            if isinstance(proc, dict):
                name = proc.get('name', 'Unknown')
                memory_mb = proc.get('memory_mb', 0)
                memory_pct = proc.get('memory_percent', 0)
            else:
                name = proc.name
                memory_mb = proc.memory_mb
                memory_pct = proc.memory_percent
            
            table.add_row(
                name[:30],
                f"{memory_mb / 1024:.2f} GB",
                f"{memory_pct:.1f}%"
            )
        
        if len(processes) > 5:
            table.add_row(
                f"[dim]...and {len(processes) - 5} more[/dim]",
                "",
                ""
            )
        
        console.print(table)
    
    console.print()


