"""OpenAI function tool definitions and execution for MacMaint operations.

Defines all MacMaint capabilities as OpenAI functions and provides execution wrappers.
"""

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import json

from macmaint.config import Config
from macmaint.core.scanner import Scanner
from macmaint.core.fixer import Fixer
from macmaint.utils.profile import ProfileManager
from macmaint.utils.history import HistoryManager
from macmaint.models.metrics import SystemMetrics
from macmaint.models.issue import Issue


# OpenAI Function Tool Schemas
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "scan_system",
            "description": "Scan the Mac for maintenance issues, performance problems, and optimization opportunities. Returns detailed system metrics (disk, memory, CPU, network, battery, startup items) and a list of identified issues with severity levels.",
            "parameters": {
                "type": "object",
                "properties": {
                    "quick": {
                        "type": "boolean",
                        "description": "If true, perform a quick scan (faster, ~10 seconds). If false, perform deep scan (~30 seconds). Default: false"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "fix_issues",
            "description": "Fix one or more identified issues. Can delete cache files, kill processes, disable startup items, etc. Respects user's trust mode for safe fixes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "issue_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of issue IDs to fix (from scan_system results). Example: ['disk_cache_chrome', 'memory_high']"
                    },
                    "auto_approve": {
                        "type": "boolean",
                        "description": "If true and user has enabled trust mode, automatically approve safe fixes without confirmation. Default: false"
                    }
                },
                "required": ["issue_ids"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "explain_issue",
            "description": "Get a detailed explanation of a specific issue, including technical details, why it matters, what fixing it will do, and potential risks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "issue_id": {
                        "type": "string",
                        "description": "The issue ID to explain (from scan_system results)"
                    }
                },
                "required": ["issue_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "clean_caches",
            "description": "Clean system and application caches to free up disk space. Can target specific categories (browser, system, app) and respect size limits.",
            "parameters": {
                "type": "object",
                "properties": {
                    "categories": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": ["browser", "system", "app", "logs", "temp"]
                        },
                        "description": "Cache categories to clean. If empty, clean all safe categories."
                    },
                    "size_limit_mb": {
                        "type": "integer",
                        "description": "Maximum space to free in MB. If specified, stop after freeing this much space."
                    }
                },
                "required": []
            }
        }
    },

    {
        "type": "function",
        "function": {
            "name": "manage_startup_items",
            "description": "Manage startup items and login items. Can list, enable, or disable items to improve boot time.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["list", "disable", "enable"],
                        "description": "Action to perform"
                    },
                    "item_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Startup item IDs to enable/disable (required for enable/disable actions)"
                    }
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_disk_analysis",
            "description": "Get detailed disk space breakdown showing what's using space: apps, system files, caches, user data, etc.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_system_status",
            "description": "Quick health check showing current disk space, memory usage, CPU load, and any critical issues. Faster than full scan.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "show_trends",
            "description": "Show historical trends for disk space, memory, and performance over the specified time period.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Number of days of history to show. Default: 7, Max: 30"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_maintenance_plan",
            "description": "Generate a personalized maintenance schedule based on user patterns and system needs. Returns recommended tasks and frequency.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_files",
            "description": (
                "Permanently delete specific files by their absolute path. "
                "Only use paths that were returned by scan_system or get_disk_analysis (large_files list). "
                "Always confirm with the user before calling this tool. "
                "Will refuse to delete directories or paths outside the user's home directory."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Absolute file paths to delete. Must be paths previously returned by scan results."
                    }
                },
                "required": ["paths"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "find_duplicates",
            "description": (
                "Scan directories for duplicate files using SHA256 hash matching. "
                "Identifies files with identical content, calculates wasted disk space, "
                "and recommends which copies to keep (newest) and which to delete. "
                "Supports dry-run mode and persists scan history. "
                "Safe: only scans paths inside the user's home directory."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Directories to scan for duplicates. "
                            "If omitted, scans Downloads, Documents, Desktop, Pictures, Music, Movies."
                        )
                    },
                    "min_size_mb": {
                        "type": "number",
                        "description": "Minimum file size in MB to consider. Default: 1. Smaller = more thorough but slower."
                    },
                    "deep_scan": {
                        "type": "boolean",
                        "description": "If true, scan the entire home directory (slow). Default: false."
                    },
                    "dry_run": {
                        "type": "boolean",
                        "description": "If true, return results without recording to history. Default: false."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_for_updates",
            "description": (
                "Check whether a newer version of MacMaint is available on GitHub. "
                "Returns the installed version, latest release version, and whether an "
                "update is available. Results are cached for 24 hours. "
                "Use when the user asks about updates, version, or 'is macmaint up to date'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "force": {
                        "type": "boolean",
                        "description": "If true, bypass the 24-hour cache and fetch fresh from GitHub. Default: false."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delegate_to_sub_agent",
            "description": (
                "Delegate a complex or specialised task to one of three focused sub-agents "
                "that each use gpt-4o-mini for cost efficiency. "
                "Use scan_agent for deep diagnostics, fix_agent to execute fixes, "
                "analysis_agent for historical trend analysis and projections. "
                "The sub-agent runs autonomously and returns a structured JSON result."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "agent": {
                        "type": "string",
                        "enum": ["scan_agent", "fix_agent", "analysis_agent"],
                        "description": (
                            "Which sub-agent to invoke:\n"
                            "- scan_agent: run scan_system / get_system_status, prioritise issues\n"
                            "- fix_agent: execute fix_issues / clean_caches for given issue IDs\n"
                            "- analysis_agent: analyse show_trends data, produce projections"
                        )
                    },
                    "task": {
                        "type": "string",
                        "description": "Plain-English task description for the sub-agent."
                    },
                    "context": {
                        "type": "object",
                        "description": (
                            "Optional context passed to the sub-agent, e.g.: "
                            "{\"issue_ids\": [\"cache_browser\"], \"auto_approve\": true, \"days\": 14}"
                        )
                    }
                },
                "required": ["agent", "task"]
            }
        }
    }
]


class ToolExecutor:
    """Executes MacMaint tools and returns formatted results."""
    
    def __init__(self, config: Config, profile_manager: ProfileManager):
        """Initialize tool executor.
        
        Args:
            config: Application configuration
            profile_manager: User profile manager
        """
        self.config = config
        self.profile_manager = profile_manager
        self.scanner = Scanner(use_ai=False)  # Reuse existing scanner
        self.fixer = Fixer()  # Reuse existing fixer
        self.history_manager = HistoryManager()
        
        # Cache for scan results (avoid re-scanning)
        self._last_scan_results: Optional[Tuple[SystemMetrics, List[Issue]]] = None
        self._last_scan_time: Optional[datetime] = None
        self._scan_cache_path = Path.home() / ".macmaint" / "last_scan_cache.json"
        self._last_duplicate_scan: Optional[Dict] = None

        # H8: Restore last scan from disk so results survive across `macmaint chat` restarts
        self._load_scan_cache()
    
    def _load_scan_cache(self) -> None:
        """H8: Load persisted scan results from disk (survive across sessions).

        Cache is ignored if it is more than 30 minutes old so stale data is
        never surfaced to the user without re-scanning.
        """
        try:
            if not self._scan_cache_path.exists():
                return
            with open(self._scan_cache_path, 'r') as f:
                raw = json.load(f)
            cache_time = datetime.fromisoformat(raw['cached_at'])
            age_seconds = (datetime.now() - cache_time).total_seconds()
            if age_seconds > 1800:  # 30 minutes
                return
            metrics = SystemMetrics.model_validate(raw['metrics'])
            issues = [Issue.model_validate(i) for i in raw['issues']]
            self._last_scan_results = (metrics, issues)
            self._last_scan_time = cache_time
        except Exception:
            # Never let a bad cache file break startup
            pass

    def _save_scan_cache(self, metrics: SystemMetrics, issues: List[Issue]) -> None:
        """H8: Persist scan results to disk so the next session can reuse them."""
        try:
            self._scan_cache_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                'cached_at': datetime.now().isoformat(),
                'metrics': metrics.model_dump(),
                'issues': [i.model_dump() for i in issues],
            }
            with open(self._scan_cache_path, 'w') as f:
                json.dump(payload, f, indent=2)
        except Exception:
            pass

    def execute(self, function_name: str, arguments: Dict) -> Dict:
        """Execute a tool and return standardized result.
        
        Args:
            function_name: Name of the tool to execute
            arguments: Tool arguments
        
        Returns:
            {
                "success": bool,
                "data": Any,  # Tool-specific result
                "error": Optional[str],  # Error message if failed
                "summary": str  # Human-readable summary
            }
        """
        try:
            # Get the tool method
            method_name = f"_{function_name}"
            if not hasattr(self, method_name):
                return {
                    "success": False,
                    "data": None,
                    "error": f"Unknown tool: {function_name}",
                    "summary": f"Tool '{function_name}' not found"
                }
            
            method = getattr(self, method_name)
            result = method(**arguments)

            # Tools that need a prior scan return a structured signal instead
            # of raising — pass it straight through without re-wrapping.
            if result.get('needs_scan'):
                return result

            return {
                "success": True,
                "data": result['data'],
                "error": None,
                "summary": result['summary']
            }
        
        except Exception as e:
            error_msg = str(e)
            return {
                "success": False,
                "data": None,
                "error": error_msg,
                "summary": f"Failed to execute {function_name}: {error_msg}"
            }
    
    # Tool implementations
    
    def _scan_system(self, quick: bool = False) -> Dict:
        """Execute system scan.
        
        Args:
            quick: If True, perform quick scan
        
        Returns:
            Dict with 'data' and 'summary' keys
        """
        # Check if we have recent results (< 5 minutes old)
        if (self._last_scan_results and self._last_scan_time and 
            (datetime.now() - self._last_scan_time).total_seconds() < 300):
            metrics, issues = self._last_scan_results
        else:
            # Perform scan
            metrics, issues = self.scanner.scan()
            self._last_scan_results = (metrics, issues)
            self._last_scan_time = datetime.now()
            # H8: persist to disk so next session doesn't require a re-scan
            self._save_scan_cache(metrics, issues)
        
        # Save to history — include issue count so _show_trends can track it
        snapshot = metrics.to_dict()
        snapshot['_issue_count'] = len(issues)
        self.history_manager.save_snapshot(snapshot)
        
        # Format for AI consumption
        issue_list = [
            {
                'id': issue.id,
                'title': issue.title,
                'severity': str(issue.severity),
                'category': str(issue.category),
                'description': issue.description,
                'can_fix': len(issue.fix_actions) > 0
            }
            for issue in issues
        ]
        
        # Count by severity
        critical = len([i for i in issues if 'critical' in str(i.severity).lower()])
        warning = len([i for i in issues if 'warning' in str(i.severity).lower()])
        info = len([i for i in issues if 'info' in str(i.severity).lower()])
        
        return {
            'data': {
                'metrics': metrics.to_dict(),
                'issues': issue_list,
                'issue_count': len(issues),
                'critical_count': critical,
                'warning_count': warning,
                'info_count': info
            },
            'summary': f"Scan complete. Found {len(issues)} issues ({critical} critical, {warning} warnings, {info} info)"
        }
    
    def _fix_issues(self, issue_ids: List[str], auto_approve: bool = False) -> Dict:
        """Fix specified issues.
        
        Args:
            issue_ids: List of issue IDs to fix
            auto_approve: If True, auto-approve safe fixes
        
        Returns:
            Dict with 'data' and 'summary' keys
        """
        # Get issues from last scan
        if not self._last_scan_results:
            return {
                'success': False,
                'needs_scan': True,
                'summary': "No scan results available. Run scan_system first, then retry fix_issues."
            }
        
        _, issues = self._last_scan_results
        
        # Filter to requested issues
        to_fix = [i for i in issues if i.id in issue_ids]
        
        if not to_fix:
            return {
                'data': {'fixed': [], 'failed': [], 'stats': {}},
                'summary': f"No matching issues found for IDs: {', '.join(issue_ids)}"
            }
        
        # Execute fixes
        # Note: For Sprint 1, we're calling the existing fixer
        # In Sprint 2, we'll add auto_approve support
        stats = self.fixer.fix_issues(to_fix)
        
        # Update profile
        for issue in to_fix:
            if stats['succeeded'] > 0:
                self.profile_manager.track_fix(str(issue.category), {'issue_id': issue.id, 'title': issue.title})
        
        return {
            'data': {
                'fixed': stats['succeeded'],
                'failed': stats['failed'],
                'skipped': stats.get('skipped', 0),
                'stats': stats
            },
            'summary': f"Fixed {stats['succeeded']} issue(s), {stats['failed']} failed, {stats.get('skipped', 0)} skipped"
        }
    
    def _explain_issue(self, issue_id: str) -> Dict:
        """Explain a specific issue in detail.
        
        Args:
            issue_id: Issue ID to explain
        
        Returns:
            Dict with 'data' and 'summary' keys
        """
        # Get issues from last scan
        if not self._last_scan_results:
            return {
                'success': False,
                'needs_scan': True,
                'summary': "No scan results available. Run scan_system first, then retry explain_issue."
            }
        
        _, issues = self._last_scan_results
        
        # Find the issue
        issue = None
        for i in issues:
            if i.id == issue_id:
                issue = i
                break
        
        if not issue:
            raise ValueError(f"Issue '{issue_id}' not found")
        
        # Format detailed explanation
        explanation = {
            'id': issue.id,
            'title': issue.title,
            'description': issue.description,
            'severity': str(issue.severity),
            'category': str(issue.category),
            'metrics': issue.metrics,
            'fix_actions': [
                {
                    'type': str(action.action_type),
                    'description': action.description,
                    'impact': action.estimated_impact,
                    'safe': action.safe
                }
                for action in issue.fix_actions
            ],
            'ai_recommendation': issue.ai_recommendation
        }
        
        return {
            'data': explanation,
            'summary': f"Issue '{issue.title}' is a {issue.severity} {issue.category} issue"
        }
    
    def _clean_caches(self, categories: List[str] = None, size_limit_mb: int = None) -> Dict:
        """Clean system and application caches.

        Args:
            categories: Cache categories to clean (browser, system, app, logs, temp).
                        If omitted, cleans all safe categories.
            size_limit_mb: Stop after freeing this many MB (None = no limit).

        Returns:
            Dict with 'data' and 'summary' keys
        """
        import shutil

        target_categories = set(categories) if categories else {'browser', 'system', 'app'}
        size_limit_bytes = size_limit_mb * 1024 * 1024 if size_limit_mb else None

        # Map category keywords to disk-module cache_breakdown keys
        category_prefixes = {
            'browser': ('browser_',),
            'system':  ('system',),
            'app':     ('app_support',),
        }

        # Get cache paths from last scan if available, otherwise do a quick disk scan
        disk_data: Dict = {}
        if self._last_scan_results:
            metrics, _ = self._last_scan_results
            metrics_dict = metrics.to_dict()
            disk_data = metrics_dict.get('disk', {}) or {}

        cache_breakdown: Dict = disk_data.get('cache_breakdown', {}) or {}

        total_freed_bytes = 0
        total_files_deleted = 0
        cleaned: List[str] = []
        failed: List[str] = []

        for breakdown_key, category_obj in cache_breakdown.items():
            # Determine which user-facing category this belongs to
            matched_category = None
            for cat, prefixes in category_prefixes.items():
                if any(breakdown_key.startswith(p) for p in prefixes):
                    matched_category = cat
                    break

            if matched_category not in target_categories:
                continue

            # category_obj may be a dict (from to_dict()) or a Pydantic model
            if hasattr(category_obj, 'path'):
                cache_path_str = category_obj.path
            elif isinstance(category_obj, dict):
                cache_path_str = category_obj.get('path', '')
            else:
                continue

            cache_path = Path(cache_path_str)
            if not cache_path.exists():
                continue

            try:
                for item in cache_path.iterdir():
                    if size_limit_bytes and total_freed_bytes >= size_limit_bytes:
                        break
                    try:
                        if item.is_file():
                            freed = item.stat().st_size
                            item.unlink()
                            total_freed_bytes += freed
                            total_files_deleted += 1
                        elif item.is_dir():
                            freed = sum(
                                f.stat().st_size
                                for f in item.rglob('*') if f.is_file()
                            )
                            shutil.rmtree(item, ignore_errors=True)
                            total_freed_bytes += freed
                            total_files_deleted += 1
                    except (OSError, PermissionError):
                        pass
                cleaned.append(breakdown_key)
            except (OSError, PermissionError) as exc:
                failed.append(f"{breakdown_key}: {exc}")

        # Also clean /tmp and $TMPDIR if 'temp' requested
        if 'temp' in target_categories or (not categories):
            import os
            temp_paths = [Path('/tmp'), Path(os.getenv('TMPDIR', '/tmp'))]
            for temp_path in temp_paths:
                if not temp_path.exists():
                    continue
                try:
                    for item in temp_path.iterdir():
                        if size_limit_bytes and total_freed_bytes >= size_limit_bytes:
                            break
                        try:
                            if item.is_file():
                                freed = item.stat().st_size
                                item.unlink()
                                total_freed_bytes += freed
                                total_files_deleted += 1
                        except (OSError, PermissionError):
                            pass
                    if 'temp' not in cleaned:
                        cleaned.append('temp')
                except (OSError, PermissionError):
                    pass

        freed_mb = round(total_freed_bytes / (1024 * 1024), 1)

        # Track cleanup in profile
        self.profile_manager.track_cleanup()

        # Invalidate the scan cache so the next disk check reflects the cleanup.
        # Without this, _get_disk_analysis / scan_system would return pre-cleanup
        # sizes for up to 5 minutes (in-memory TTL) or 30 minutes (disk cache TTL).
        self._last_scan_results = None
        self._last_scan_time = None
        try:
            if self._scan_cache_path.exists():
                self._scan_cache_path.unlink()
        except (OSError, PermissionError):
            pass

        return {
            'data': {
                'categories_cleaned': cleaned,
                'space_freed_mb': freed_mb,
                'files_deleted': total_files_deleted,
                'failed': failed,
            },
            'summary': f"Cleaned {len(cleaned)} cache categories, freed {freed_mb} MB ({total_files_deleted} files deleted)"
        }
    
    def _optimize_memory(self, aggressive: bool = False) -> Dict:
        """Memory optimization is not yet implemented."""
        return {
            'data': {'processes_killed': 0, 'memory_freed_mb': 0},
            'summary': "Memory optimization is not available yet. Use get_system_status to see memory usage and top processes."
        }
    
    @staticmethod
    def _run_with_sudo(shell_cmd: str) -> "subprocess.CompletedProcess":
        """Run a shell command with administrator privileges via osascript.

        Triggers macOS's native password dialog.  Returns a CompletedProcess-like
        object with ``returncode``, ``stdout``, and ``stderr`` attributes.
        """
        import subprocess

        escaped = shell_cmd.replace('"', '\\"')
        osascript_cmd = [
            'osascript', '-e',
            f'do shell script "{escaped}" with administrator privileges',
        ]
        return subprocess.run(osascript_cmd, capture_output=True, text=True, timeout=30)

    def _manage_startup_items(self, action: str, item_ids: List[str] = None, use_sudo: bool = False) -> Dict:
        """Manage startup items.
        
        Args:
            action: Action to perform (list, disable, enable)
            item_ids: Startup item IDs
        
        Returns:
            Dict with 'data' and 'summary' keys
        """
        # Get startup items from last scan
        if action == "list":
            if not self._last_scan_results:
                return {
                    'success': False,
                    'needs_scan': True,
                    'summary': "No scan results available. Run scan_system first, then retry manage_startup_items."
                }

            metrics, _ = self._last_scan_results
            startup_data = metrics.startup or {}
            # StartupMetrics uses login_items / launch_agents / launch_daemons
            if hasattr(startup_data, 'login_items'):
                # Still a Pydantic object — convert first
                startup_dict = startup_data.model_dump() if hasattr(startup_data, 'model_dump') else {}
            else:
                startup_dict = startup_data if isinstance(startup_data, dict) else {}

            login_items    = startup_dict.get('login_items', [])
            launch_agents  = startup_dict.get('launch_agents', [])
            launch_daemons = startup_dict.get('launch_daemons', [])
            items = login_items + launch_agents + launch_daemons

            return {
                'data': {
                    'items':               items,
                    'count':               len(items),
                    'login_items_count':   len(login_items),
                    'launch_agents_count': len(launch_agents),
                    'launch_daemons_count': len(launch_daemons),
                },
                'summary': f"Found {len(items)} startup items ({len(login_items)} login, {len(launch_agents)} agents, {len(launch_daemons)} daemons)"
            }
        
        # For disable/enable, look up items from the last scan
        if not self._last_scan_results:
            return {
                'success': False,
                'needs_scan': True,
                'summary': "No scan results available. Run scan_system first, then retry manage_startup_items."
            }

        if not item_ids:
            return {
                'data': {'action': action, 'items_modified': 0, 'results': []},
                'summary': "No item IDs provided."
            }

        metrics, _ = self._last_scan_results
        startup_data = metrics.startup or {}
        if hasattr(startup_data, 'model_dump'):
            startup_dict = startup_data.model_dump()
        elif isinstance(startup_data, dict):
            startup_dict = startup_data
        else:
            startup_dict = {}

        all_items = (
            startup_dict.get('login_items', []) +
            startup_dict.get('launch_agents', []) +
            startup_dict.get('launch_daemons', [])
        )

        # Build lookup: id -> item dict (deduplicate — login_items and launch_agents
        # may both contain the same user-level plist)
        item_map: Dict[str, Any] = {}
        for it in all_items:
            item_id = it.get('id') or it.get('name', '')
            if item_id and item_id not in item_map:
                item_map[item_id] = it

        import subprocess, os

        uid = os.getuid()
        results = []
        modified = 0

        for req_id in item_ids:
            item = item_map.get(req_id)
            entry: Dict[str, Any] = {
                'id': req_id,
                'action': action,
                'success': False,
                'error': None,
            }

            if not item:
                entry['error'] = f"Startup item '{req_id}' not found in last scan results"
                results.append(entry)
                continue

            item_type  = item.get('type', '')
            item_scope = item.get('scope', 'system')
            plist_path = item.get('path', '')
            label      = item.get('id') or item.get('name', req_id)

            # Determine launchctl domain target
            is_user = (item_type == 'login_item') or (item_type == 'launch_agent' and item_scope == 'user')
            domain_target = f"gui/{uid}/{label}" if is_user else f"system/{label}"

            try:
                if action == 'disable':
                    if is_user:
                        # Unload the agent from the current login session
                        cmd = ['launchctl', 'bootout', f'gui/{uid}', plist_path]
                    else:
                        # Mark permanently disabled (survives reboot); unload from system
                        cmd = ['launchctl', 'bootout', 'system', plist_path]

                    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

                    # launchctl exits non-zero if the service wasn't loaded — that's fine,
                    # it just means it was already stopped; persist the disabled state anyway.
                    if not is_user:
                        perm_error = (
                            proc.returncode != 0
                            and ('Operation not permitted' in proc.stderr or 'Permission denied' in proc.stderr)
                        )
                        if perm_error and use_sudo:
                            # Retry bootout via osascript sudo prompt
                            sudo_proc = self._run_with_sudo(
                                f"launchctl bootout system {plist_path}"
                            )
                            if sudo_proc.returncode == 0:
                                proc = sudo_proc  # treat as success
                            else:
                                entry['error'] = (
                                    f"Permission denied even with administrator privileges: "
                                    f"{sudo_proc.stderr.strip() or sudo_proc.stdout.strip()}"
                                )
                                results.append(entry)
                                continue
                        elif perm_error:
                            entry['error'] = (
                                f"Permission denied — system-level items require administrator privileges. "
                                f"Enable trust mode ('trust' command) or run manually: "
                                f"sudo launchctl bootout system {plist_path}"
                            )
                            results.append(entry)
                            continue

                        # Persist disabled state (suppress errors — best-effort)
                        disable_cmd = f"launchctl disable system/{label}"
                        if use_sudo:
                            self._run_with_sudo(disable_cmd)
                        else:
                            subprocess.run(
                                ['launchctl', 'disable', f'system/{label}'],
                                capture_output=True, text=True, timeout=10
                            )

                    if proc.returncode != 0 and 'No such process' not in proc.stderr and 'Could not find' not in proc.stderr:
                        entry['error'] = proc.stderr.strip() or f"launchctl returned exit code {proc.returncode}"
                        results.append(entry)
                        continue

                    entry['success'] = True
                    modified += 1

                elif action == 'enable':
                    if is_user:
                        cmd = ['launchctl', 'bootstrap', f'gui/{uid}', plist_path]
                    else:
                        enable_cmd = f"launchctl enable system/{label}"
                        if use_sudo:
                            self._run_with_sudo(enable_cmd)
                        else:
                            subprocess.run(
                                ['launchctl', 'enable', f'system/{label}'],
                                capture_output=True, text=True, timeout=10
                            )
                        cmd = ['launchctl', 'bootstrap', 'system', plist_path]

                    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

                    if proc.returncode != 0:
                        if 'Operation not permitted' in proc.stderr or 'Permission denied' in proc.stderr:
                            if use_sudo and not is_user:
                                sudo_proc = self._run_with_sudo(
                                    f"launchctl bootstrap system {plist_path}"
                                )
                                if sudo_proc.returncode == 0:
                                    proc = sudo_proc
                                else:
                                    entry['error'] = (
                                        f"Permission denied even with administrator privileges: "
                                        f"{sudo_proc.stderr.strip() or sudo_proc.stdout.strip()}"
                                    )
                                    results.append(entry)
                                    continue
                            else:
                                entry['error'] = (
                                    f"Permission denied — system-level items require administrator privileges. "
                                    f"Enable trust mode ('trust' command) or run manually: "
                                    f"sudo launchctl bootstrap system {plist_path}"
                                )
                                results.append(entry)
                                continue
                        # "Service already loaded" is acceptable for enable
                        if 'service already loaded' not in proc.stderr.lower() and 'already bootstrapped' not in proc.stderr.lower():
                            entry['error'] = proc.stderr.strip() or f"launchctl returned exit code {proc.returncode}"
                            results.append(entry)
                            continue

                    entry['success'] = True
                    modified += 1

            except subprocess.TimeoutExpired:
                entry['error'] = "launchctl timed out"
            except FileNotFoundError:
                entry['error'] = "launchctl not found — this feature requires macOS"
            except Exception as exc:
                entry['error'] = str(exc)

            results.append(entry)

        succeeded = [r for r in results if r['success']]
        failed    = [r for r in results if not r['success']]

        return {
            'data': {
                'action':         action,
                'items_modified': modified,
                'results':        results,
            },
            'summary': (
                f"{action.capitalize()}d {len(succeeded)} startup item(s)"
                + (f"; {len(failed)} failed" if failed else "")
            )
        }
    
    def _get_disk_analysis(self) -> Dict:
        """Get detailed disk space breakdown.
        
        Returns:
            Dict with 'data' and 'summary' keys
        """
        # Get disk metrics from last scan
        if not self._last_scan_results:
            return {
                'success': False,
                'needs_scan': True,
                'summary': "No scan results available. Run scan_system first, then retry get_disk_analysis."
            }
        
        metrics, _ = self._last_scan_results
        
        # Convert to dict if it's a Pydantic model
        metrics_dict = metrics.to_dict()
        disk_data = metrics_dict.get('disk', {}) or {}
        
        return {
            'data': {
                'total_gb':     disk_data.get('total_gb', 0),
                'used_gb':      disk_data.get('used_gb', 0),
                'free_gb':      disk_data.get('free_gb', 0),
                'usage_percent': disk_data.get('percent_used', 0),
                'breakdown':    disk_data.get('cache_breakdown', {}),
                'large_files':  disk_data.get('large_files', []),
                'log_size_gb':  disk_data.get('log_size_gb', 0),
                'log_files':    disk_data.get('log_files', {}),
                'temp_size_gb': disk_data.get('temp_size_gb', 0),
                'cache_size_gb': disk_data.get('cache_size_gb', 0),
            },
            'summary': f"Disk usage: {disk_data.get('used_gb', 0):.1f}GB / {disk_data.get('total_gb', 0):.1f}GB ({disk_data.get('percent_used', 0):.1f}%)"
        }
    
    def _get_system_status(self) -> Dict:
        """Quick health check.
        
        Returns:
            Dict with 'data' and 'summary' keys
        """
        # Use cached scan if available, otherwise do quick scan
        if self._last_scan_results:
            metrics, issues = self._last_scan_results
        else:
            metrics, issues = self.scanner.scan()
            self._last_scan_results = (metrics, issues)
            self._last_scan_time = datetime.now()
        
        # Convert to dict if it's a Pydantic model
        metrics_dict = metrics.to_dict()
        disk_data = metrics_dict.get('disk', {}) or {}
        memory_data = metrics_dict.get('memory', {}) or {}
        cpu_data = metrics_dict.get('cpu', {}) or {}
        battery_data = metrics_dict.get('battery', {}) or {}
        network_data = metrics_dict.get('network', {}) or {}
        startup_data = metrics_dict.get('startup', {}) or {}

        critical_issues = [i for i in issues if 'critical' in str(i.severity).lower()]

        disk_pct = disk_data.get('percent_used', 0)
        mem_pct = memory_data.get('percent_used', 0)
        cpu_pct = cpu_data.get('cpu_percent', 0)

        # Top processes (already sorted by memory_mb desc by the memory module)
        raw_processes = memory_data.get('top_processes', []) or []
        top_processes = [
            {
                'name':           p.get('name', 'unknown'),
                'memory_mb':      round(p.get('memory_mb', 0), 1),
                'memory_percent': round(p.get('memory_percent', 0), 1),
                'category':       p.get('category', 'background'),
            }
            for p in raw_processes[:8]
        ]

        # Memory breakdown (wired / active / inactive / compressed)
        raw_breakdown = memory_data.get('breakdown') or {}
        mem_breakdown = {}
        if raw_breakdown:
            mem_breakdown = {
                'wired_gb':      round(raw_breakdown.get('wired_gb', 0), 2),
                'active_gb':     round(raw_breakdown.get('active_gb', 0), 2),
                'inactive_gb':   round(raw_breakdown.get('inactive_gb', 0), 2),
                'compressed_gb': round(raw_breakdown.get('compressed_gb', 0), 2),
                'pressure':      raw_breakdown.get('pressure_level', 'normal'),
            }

        # CPU top processes
        cpu_top = [
            {
                'name':        p.get('name', 'unknown'),
                'cpu_percent': round(p.get('cpu_percent', 0), 1),
                'category':    p.get('category', 'background'),
            }
            for p in (cpu_data.get('top_processes', []) or [])[:5]
        ]

        # Battery summary (omit if not present)
        battery_summary: Dict = {}
        if battery_data.get('is_present'):
            battery_summary = {
                'percent':              battery_data.get('percent', 0),
                'charging_state':       battery_data.get('charging_state', 'Unknown'),
                'is_charging':          battery_data.get('is_charging', False),
                'health':               battery_data.get('health', 'Unknown'),
                'cycle_count':          battery_data.get('cycle_count', 0),
                'max_capacity_percent': battery_data.get('max_capacity_percent', 100),
                'time_remaining_min':   battery_data.get('time_remaining'),
                'temperature_c':        battery_data.get('temperature'),
                'temperature_status':   battery_data.get('temperature_status', 'unknown'),
                'current_power_draw_w': battery_data.get('current_power_draw_w'),
                'charger_connected':    battery_data.get('charger_connected', False),
                'charger_wattage':      battery_data.get('charger_wattage'),
                'charger_type':         battery_data.get('charger_type', 'Unknown'),
                'design_capacity_mah':  battery_data.get('design_capacity_mah', 0),
                'current_capacity_mah': battery_data.get('current_capacity_mah', 0),
                'battery_age_days':     battery_data.get('battery_age_days'),
            }

        # Network summary
        network_summary: Dict = {}
        if network_data:
            network_summary = {
                'bytes_sent_gb':   round(network_data.get('bytes_sent_gb', 0), 3),
                'bytes_recv_gb':   round(network_data.get('bytes_recv_gb', 0), 3),
                'connections':     network_data.get('connections_count', 0),
                'errors_in':       network_data.get('error_in', 0),
                'errors_out':      network_data.get('error_out', 0),
            }

        # Startup summary
        startup_summary: Dict = {}
        if startup_data:
            total_startup = (
                startup_data.get('login_items_count', 0) +
                startup_data.get('launch_agents_count', 0) +
                startup_data.get('launch_daemons_count', 0)
            )
            startup_summary = {
                'total_items':          total_startup,
                'login_items_count':    startup_data.get('login_items_count', 0),
                'launch_agents_count':  startup_data.get('launch_agents_count', 0),
                'launch_daemons_count': startup_data.get('launch_daemons_count', 0),
            }

        status = {
            'disk': {
                'free_gb':        disk_data.get('free_gb', 0),
                'usage_percent':  disk_pct,
                'status': 'critical' if disk_pct > 90 else 'warning' if disk_pct > 80 else 'ok',
            },
            'memory': {
                'total_gb':       memory_data.get('total_gb', 0),
                'used_gb':        memory_data.get('used_gb', 0),
                'available_gb':   memory_data.get('available_gb', 0),
                'usage_percent':  mem_pct,
                'status':         'critical' if mem_pct > 90 else 'warning' if mem_pct > 80 else 'ok',
                'top_processes':  top_processes,
                'breakdown':      mem_breakdown,
            },
            'cpu': {
                'usage_percent':  cpu_pct,
                'status':         'critical' if cpu_pct > 90 else 'warning' if cpu_pct > 80 else 'ok',
                'top_processes':  cpu_top,
                'load_average':   cpu_data.get('load_average', []),
            },
            'critical_issues':  len(critical_issues),
            'overall_status':   'critical' if critical_issues else 'ok',
        }

        if battery_summary:
            status['battery'] = battery_summary
        if network_summary:
            status['network'] = network_summary
        if startup_summary:
            status['startup'] = startup_summary
        
        return {
            'data': status,
            'summary': f"System status: {status['overall_status'].upper()} - {len(critical_issues)} critical issues"
        }
    
    def _show_trends(self, days: int = 7) -> Dict:
        """Show historical trends.
        
        Args:
            days: Number of days of history to show
        
        Returns:
            Dict with 'data' and 'summary' keys
        """
        # Limit to 30 days max
        days = min(days, 30)
        
        # Get historical snapshots
        snapshots = self.history_manager.get_snapshots(days)
        
        if not snapshots:
            return {
                'data': {'snapshots': [], 'trends': {}},
                'summary': f"No historical data available for the last {days} days"
            }
        
        # Calculate trends
        trends = {
            'disk_usage':   [s['metrics'].get('disk', {}).get('percent_used', 0) for s in snapshots],
            'memory_usage': [s['metrics'].get('memory', {}).get('percent_used', 0) for s in snapshots],
            'issue_count':  [s['metrics'].get('_issue_count', len(s.get('issues', []))) for s in snapshots],
        }
        
        return {
            'data': {
                'snapshots': snapshots,
                'trends': trends,
                'days': days
            },
            'summary': f"Found {len(snapshots)} snapshots over the last {days} days"
        }
    
    def _create_maintenance_plan(self) -> Dict:
        """Generate a data-driven maintenance schedule.

        Uses the most recent scan results (if available) to tailor the plan to
        actual system conditions, rather than returning a generic hardcoded list.

        Returns:
            Dict with 'data' and 'summary' keys
        """
        profile = self.profile_manager.load()
        usage_patterns = profile.usage_patterns

        # --- Build base task lists ---
        daily: List[str] = ['Check system status with get_system_status']
        weekly: List[str] = ['Run a quick scan (scan_system quick=true)']
        monthly: List[str] = ['Run a deep scan (scan_system quick=false)', 'Review and update software']

        personalized: List[str] = []

        # --- Tailor to live scan data when available ---
        if self._last_scan_results:
            metrics, issues = self._last_scan_results

            # Disk
            if metrics.disk:
                used_pct = metrics.disk.used_percentage or 0
                if used_pct >= 90:
                    daily.append('Monitor disk space — currently critical (≥90% full)')
                    weekly.append('Clean caches and review large files')
                elif used_pct >= 75:
                    weekly.append('Clean browser and system caches (disk >75% full)')
                else:
                    monthly.append('Review disk usage and clean caches')

            # Memory
            if metrics.memory:
                used_pct = metrics.memory.used_percentage or 0
                if used_pct >= 85:
                    daily.append('Monitor memory usage — currently elevated (≥85%)')
                    weekly.append('Review memory-heavy applications')
                else:
                    monthly.append('Review memory usage trends')

            # Startup items
            if metrics.startup:
                item_count = (
                    len(metrics.startup.login_items or []) +
                    len(metrics.startup.launch_agents or []) +
                    len(metrics.startup.launch_daemons or [])
                )
                if item_count > 12:
                    weekly.append(f'Review startup items — {item_count} items detected (high)')
                elif item_count > 6:
                    monthly.append(f'Review startup items — {item_count} items detected')

            # Issue-specific recommendations
            critical_issues = [i for i in issues if 'critical' in str(i.severity).lower()]
            warning_issues  = [i for i in issues if 'warning' in str(i.severity).lower()]

            if critical_issues:
                daily.append(
                    f'Address {len(critical_issues)} critical issue(s): '
                    + ', '.join(i.title for i in critical_issues[:3])
                )
            if warning_issues:
                weekly.append(
                    f'Review {len(warning_issues)} warning(s): '
                    + ', '.join(i.title for i in warning_issues[:3])
                )
        else:
            # Generic fallback when no scan data exists
            weekly.extend(['Clean browser caches', 'Review startup items'])
            monthly.extend(['Clean system caches', 'Review disk space usage'])

        # --- Profile-based personalisation ---
        if usage_patterns.cleanup_frequency > 0:
            personalized.append(
                f"You typically clean up every {usage_patterns.cleanup_frequency} days — "
                f"consider scheduling a recurring weekly scan."
            )
        if usage_patterns.most_common_issues:
            personalized.append(
                f"Your most frequent issues: {', '.join(usage_patterns.most_common_issues[:3])}. "
                "Pay extra attention to these areas."
            )

        plan = {
            'daily':   daily,
            'weekly':  weekly,
            'monthly': monthly,
            'personalized_recommendations': personalized,
        }

        return {
            'data': plan,
            'summary': (
                f"Created maintenance plan with {len(daily)} daily, "
                f"{len(weekly)} weekly, and {len(monthly)} monthly tasks"
                + (" based on your latest scan results" if self._last_scan_results else "")
            )
        }

    def _delete_files(self, paths: List[str]) -> Dict:
        """Permanently delete specific files by absolute path.

        Safety rules:
        - Only files (not directories) may be deleted.
        - All paths must be under the user's home directory.

        Args:
            paths: Absolute paths to delete.

        Returns:
            Dict with 'data' and 'summary' keys.
        """
        import os

        home = Path.home()
        results = []
        total_freed_bytes = 0

        for path_str in paths:
            path = Path(path_str)
            entry: Dict[str, Any] = {'path': path_str, 'success': False, 'bytes_freed': 0, 'error': None}

            # Safety: must be inside home directory
            try:
                path.resolve().relative_to(home)
            except ValueError:
                entry['error'] = "Refused: path is outside the user home directory"
                results.append(entry)
                continue

            # Safety: must exist
            if not path.exists():
                entry['error'] = "File not found"
                results.append(entry)
                continue

            # Safety: must be a file, not a directory
            if not path.is_file():
                entry['error'] = "Refused: path is a directory, not a file"
                results.append(entry)
                continue

            try:
                size = path.stat().st_size
                path.unlink()
                entry['success'] = True
                entry['bytes_freed'] = size
                total_freed_bytes += size
            except (OSError, PermissionError) as exc:
                entry['error'] = str(exc)

            results.append(entry)

        succeeded = [r for r in results if r['success']]
        failed = [r for r in results if not r['success']]
        freed_mb = round(total_freed_bytes / (1024 * 1024), 2)

        if succeeded:
            self.profile_manager.track_cleanup()

        return {
            'data': {
                'deleted': succeeded,
                'failed': failed,
                'files_deleted': len(succeeded),
                'space_freed_mb': freed_mb,
            },
            'summary': (
                f"Deleted {len(succeeded)} file(s), freed {freed_mb} MB"
                + (f"; {len(failed)} failed" if failed else "")
            )
        }

    def _find_duplicates(
        self,
        paths: Optional[List[str]] = None,
        min_size_mb: float = 1.0,
        deep_scan: bool = False,
        dry_run: bool = False,
    ) -> Dict:
        """Scan for duplicate files using SHA256 hash + size matching.

        Args:
            paths:       Directories to scan.  None = common user folders.
            min_size_mb: Minimum file size in MB to consider (default 1).
            deep_scan:   If True, scan entire home directory.
            dry_run:     If True, return results without recording history.

        Returns:
            Dict with 'data' and 'summary' keys.
        """
        from macmaint.modules.duplicates import DuplicateScanner

        dup_config = self.config.get_module_config("duplicates") if hasattr(self.config, 'get_module_config') else {}
        if not isinstance(dup_config, dict):
            dup_config = {}

        # Override min_size_mb from caller if provided
        dup_config = dict(dup_config)
        dup_config["min_size_mb"] = min_size_mb

        scanner = DuplicateScanner(dup_config)

        scan_paths = paths
        if deep_scan and not paths:
            scan_paths = [str(Path.home())]

        metrics, issues = scanner.scan(paths=scan_paths, dry_run=dry_run)

        # Cache for potential follow-up delete calls
        self._last_duplicate_scan = {"metrics": metrics, "issues": [i.model_dump() for i in issues]}

        groups = metrics.get("duplicate_groups", [])
        total_duplicates = metrics.get("total_duplicates", 0)
        wasted_mb = metrics.get("total_wasted_space_mb", 0.0)
        files_scanned = metrics.get("files_scanned", 0)
        group_count = metrics.get("duplicate_groups_count", 0)

        # Build concise per-group summary for the AI
        group_summaries = []
        for g in groups[:20]:  # cap at 20 groups to keep response size reasonable
            kept = next((f for f in g["files"] if f.get("keep_recommended")), g["files"][0])
            group_summaries.append({
                "name": Path(kept["path"]).name,
                "copies": g["count"],
                "size_mb": g["size_mb"],
                "wasted_mb": g["wasted_mb"],
                "keep": kept["path"],
                "delete": [f["path"] for f in g["files"] if not f.get("keep_recommended")],
            })

        if total_duplicates == 0:
            summary = f"No duplicates found. Scanned {files_scanned} file(s)."
        else:
            summary = (
                f"Found {group_count} duplicate group(s) with {total_duplicates} extra "
                f"cop{'y' if total_duplicates == 1 else 'ies'} wasting {wasted_mb:.1f} MB "
                f"(scanned {files_scanned} files)."
            )

        return {
            "data": {
                "duplicate_groups_count": group_count,
                "total_duplicates": total_duplicates,
                "total_wasted_space_mb": wasted_mb,
                "files_scanned": files_scanned,
                "scan_paths": metrics.get("scan_paths", []),
                "dry_run": dry_run,
                "groups": group_summaries,
            },
            "summary": summary,
        }

    def _check_for_updates(self, force: bool = False) -> Dict:
        """Check GitHub for a newer MacMaint release.

        Args:
            force: Bypass the 24-hour cache when True.

        Returns:
            Dict with 'data' and 'summary' keys.
        """
        from macmaint.utils.updater import check_for_updates

        info = check_for_updates(force=force)

        if info.get("error"):
            raise RuntimeError(info["error"])

        current = info["current_version"]
        latest  = info["latest_version"]

        if info["update_available"]:
            summary = (
                f"MacMaint {latest} is available (you have {current}). "
                f"Run 'macmaint update' in the terminal to upgrade."
            )
        else:
            summary = f"MacMaint is up to date (version {current})."

        return {
            "success": True,
            "data": {
                "current_version":  current,
                "latest_version":   latest,
                "update_available": info["update_available"],
                "release_url":      info["release_url"],
                "from_cache":       info["from_cache"],
            },
            "summary": summary,
        }
