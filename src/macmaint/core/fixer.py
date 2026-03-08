"""Interactive fix system for resolving issues."""
from pathlib import Path
from typing import Dict, List
from macmaint.models.issue import Issue, ActionType, FixAction
from macmaint.utils.formatters import console, confirm, print_success, print_error, print_warning
from macmaint.utils.safety import SafetyChecker
from macmaint.utils.system import expand_path, safe_remove_file
from macmaint.config import get_config


class Fixer:
    """Handles fixing system issues interactively."""
    
    def __init__(self, dry_run: bool = False):
        """Initialize fixer.
        
        Args:
            dry_run: If True, simulate actions without executing
        """
        self.config = get_config()
        self.dry_run = dry_run or self.config.get("safety.dry_run_default", False)
        self.safety_checker = SafetyChecker(
            exclude_paths=self.config.get("modules.disk.exclude_paths", [])
        )
    
    def fix_issues(self, issues: List[Issue]) -> Dict[str, int]:
        """Interactively fix issues.
        
        Args:
            issues: List of issues to fix
        
        Returns:
            Statistics dictionary with counts
        """
        stats = {
            "attempted": 0,
            "succeeded": 0,
            "failed": 0,
            "skipped": 0
        }
        
        # Filter issues that have fix actions
        fixable_issues = [i for i in issues if i.fix_actions]
        
        if not fixable_issues:
            print_warning("No fixable issues found")
            return stats
        
        console.print(f"\n[bold]Found {len(fixable_issues)} fixable issue(s)[/bold]\n")
        
        for idx, issue in enumerate(fixable_issues, 1):
            console.print(f"\n[bold cyan]Issue {idx}/{len(fixable_issues)}:[/bold cyan] {issue.title}")
            
            if issue.description:
                console.print(f"[dim]{issue.description}[/dim]")
            
            for action in issue.fix_actions:
                stats["attempted"] += 1
                
                if self._execute_action(issue, action):
                    stats["succeeded"] += 1
                else:
                    stats["failed"] += 1
        
        # Print summary
        console.print("\n[bold]Fix Summary:[/bold]")
        console.print(f"  Succeeded: [green]{stats['succeeded']}[/green]")
        console.print(f"  Failed: [red]{stats['failed']}[/red]")
        console.print(f"  Skipped: [yellow]{stats['skipped']}[/yellow]")
        
        return stats
    
    def _execute_action(self, issue: Issue, action: FixAction) -> bool:
        """Execute a single fix action.
        
        Args:
            issue: The issue being fixed
            action: The action to execute
        
        Returns:
            True if successful, False otherwise
        """
        console.print(f"\n  [yellow]→[/yellow] {action.description}")
        
        if action.estimated_impact:
            console.print(f"    [dim]Impact: {action.estimated_impact}[/dim]")
        
        # Special warning for cache cleanup
        if action.action_type == ActionType.DELETE_FILES and "cache" in issue.id.lower():
            console.print("\n    [bold yellow]⚠️  IMPORTANT: Cache Cleanup Warning[/bold yellow]")
            console.print("    [yellow]Cleaning browser caches will:[/yellow]")
            console.print("    [yellow]  • Log you out of websites[/yellow]")
            console.print("    [yellow]  • Require re-entering passwords and credentials[/yellow]")
            console.print("    [yellow]  • Remove saved form data and preferences[/yellow]")
            console.print("    [yellow]  • Clear website session data[/yellow]")
            console.print()
        
        # Check if confirmation required
        if action.requires_confirmation or self.config.require_confirmation:
            if not confirm(f"    Proceed?", default=False):
                print_warning("    Skipped")
                return False
        
        # Execute based on action type
        try:
            if action.action_type == ActionType.DELETE_FILES:
                return self._delete_files(action)
            elif action.action_type == ActionType.MANUAL:
                print_warning("    Manual action required - skipping automated execution")
                return False
            else:
                print_warning(f"    Action type {action.action_type} not yet implemented")
                return False
                
        except Exception as e:
            print_error(f"    Failed: {str(e)}")
            return False
    
    def _delete_files(self, action: FixAction) -> bool:
        """Delete files as specified in action.
        
        Args:
            action: Action containing file paths to delete
        
        Returns:
            True if successful
        """
        paths = action.details.get("paths", [])
        
        if not paths:
            print_warning("    No paths specified")
            return False
        
        # Collect all files to delete
        files_to_delete = []
        
        for path_str in paths:
            path = expand_path(path_str)
            
            if not path.exists():
                continue
            
            if path.is_dir():
                # Collect files in directory
                try:
                    for file in path.rglob('*'):
                        if file.is_file():
                            files_to_delete.append(file)
                except (OSError, PermissionError):
                    pass
            elif path.is_file():
                files_to_delete.append(path)
        
        if not files_to_delete:
            print_warning("    No files found to delete")
            return False
        
        # Safety checks
        max_files = self.config.get("safety.max_file_delete_count", 1000)
        is_valid, message = self.safety_checker.validate_file_list(files_to_delete, max_files)
        
        if not is_valid:
            print_error(f"    Safety check failed: {message}")
            return False
        
        # Delete files
        deleted_count = 0
        failed_count = 0
        
        console.print(f"    Deleting {len(files_to_delete)} files...")
        
        if self.dry_run:
            console.print(f"    [dim](DRY RUN - no files actually deleted)[/dim]")
            return True
        
        for file in files_to_delete:
            if safe_remove_file(file, dry_run=self.dry_run):
                deleted_count += 1
            else:
                failed_count += 1
        
        if deleted_count > 0:
            print_success(f"    Deleted {deleted_count} files")
        
        if failed_count > 0:
            print_warning(f"    Failed to delete {failed_count} files")
        
        return deleted_count > 0
