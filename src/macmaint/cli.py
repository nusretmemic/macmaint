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
    format_percentage, format_bytes, create_progress
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


if __name__ == "__main__":
    cli()
