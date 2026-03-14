"""OpenAI function tool definitions and execution for MacMaint operations.

Defines all MacMaint capabilities as OpenAI functions and provides execution wrappers.
"""

from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple

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
            "name": "optimize_memory",
            "description": "Optimize memory usage by killing high-memory processes (with user confirmation), clearing inactive memory, and suggesting adjustments.",
            "parameters": {
                "type": "object",
                "properties": {
                    "aggressive": {
                        "type": "boolean",
                        "description": "If true, be more aggressive with process termination. Default: false"
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
            (datetime.now() - self._last_scan_time).seconds < 300):
            metrics, issues = self._last_scan_results
        else:
            # Perform scan
            metrics, issues = self.scanner.scan()
            self._last_scan_results = (metrics, issues)
            self._last_scan_time = datetime.now()
        
        # Save to history
        self.history_manager.save_snapshot(metrics, issues)
        
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
            raise RuntimeError("No scan results available. Run scan_system first.")
        
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
        profile = self.profile_manager.load()
        for issue in to_fix:
            if stats['succeeded'] > 0:
                self.profile_manager.track_fixed_issue(issue.id, str(issue.category))
        
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
            raise RuntimeError("No scan results available. Run scan_system first.")
        
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
            categories: Cache categories to clean (browser, system, app, logs, temp)
            size_limit_mb: Maximum space to free in MB
        
        Returns:
            Dict with 'data' and 'summary' keys
        """
        # For Sprint 1, return placeholder
        # Full implementation will use existing disk module functionality
        return {
            'data': {
                'categories_cleaned': categories or ['browser', 'system', 'app'],
                'space_freed_mb': 0,
                'files_deleted': 0
            },
            'summary': "Cache cleaning will be fully implemented in Sprint 2"
        }
    
    def _optimize_memory(self, aggressive: bool = False) -> Dict:
        """Optimize memory usage.
        
        Args:
            aggressive: If True, be more aggressive with process termination
        
        Returns:
            Dict with 'data' and 'summary' keys
        """
        # For Sprint 1, return placeholder
        return {
            'data': {
                'processes_killed': 0,
                'memory_freed_mb': 0
            },
            'summary': "Memory optimization will be fully implemented in Sprint 2"
        }
    
    def _manage_startup_items(self, action: str, item_ids: List[str] = None) -> Dict:
        """Manage startup items.
        
        Args:
            action: Action to perform (list, disable, enable)
            item_ids: Startup item IDs
        
        Returns:
            Dict with 'data' and 'summary' keys
        """
        # Get startup items from last scan
        if action == "list":
            if self._last_scan_results:
                metrics, _ = self._last_scan_results
                startup_data = metrics.startup or {}
                items = startup_data.get('items', [])
                
                return {
                    'data': {
                        'items': items,
                        'count': len(items)
                    },
                    'summary': f"Found {len(items)} startup items"
                }
            else:
                return {
                    'data': {'items': [], 'count': 0},
                    'summary': "No scan data available. Run scan_system first."
                }
        
        # For disable/enable, placeholder for Sprint 1
        return {
            'data': {
                'action': action,
                'items_modified': 0
            },
            'summary': f"Startup item {action} will be fully implemented in Sprint 2"
        }
    
    def _get_disk_analysis(self) -> Dict:
        """Get detailed disk space breakdown.
        
        Returns:
            Dict with 'data' and 'summary' keys
        """
        # Get disk metrics from last scan
        if not self._last_scan_results:
            raise RuntimeError("No scan results available. Run scan_system first.")
        
        metrics, _ = self._last_scan_results
        
        # Convert to dict if it's a Pydantic model
        metrics_dict = metrics.to_dict()
        disk_data = metrics_dict.get('disk', {}) or {}
        
        return {
            'data': {
                'total_gb': disk_data.get('total_gb', 0),
                'used_gb': disk_data.get('used_gb', 0),
                'free_gb': disk_data.get('free_gb', 0),
                'usage_percent': disk_data.get('usage_percent', 0),
                'breakdown': disk_data.get('breakdown', {})
            },
            'summary': f"Disk usage: {disk_data.get('used_gb', 0):.1f}GB / {disk_data.get('total_gb', 0):.1f}GB ({disk_data.get('usage_percent', 0):.1f}%)"
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
        
        critical_issues = [i for i in issues if 'critical' in str(i.severity).lower()]
        
        status = {
            'disk': {
                'free_gb': disk_data.get('free_gb', 0),
                'usage_percent': disk_data.get('usage_percent', 0),
                'status': 'critical' if disk_data.get('usage_percent', 0) > 90 else 'warning' if disk_data.get('usage_percent', 0) > 80 else 'ok'
            },
            'memory': {
                'available_gb': memory_data.get('available_gb', 0),
                'usage_percent': memory_data.get('usage_percent', 0),
                'status': 'critical' if memory_data.get('usage_percent', 0) > 90 else 'warning' if memory_data.get('usage_percent', 0) > 80 else 'ok'
            },
            'cpu': {
                'usage_percent': cpu_data.get('usage_percent', 0),
                'status': 'critical' if cpu_data.get('usage_percent', 0) > 90 else 'warning' if cpu_data.get('usage_percent', 0) > 80 else 'ok'
            },
            'critical_issues': len(critical_issues),
            'overall_status': 'critical' if critical_issues else 'ok'
        }
        
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
            'disk_usage': [s['metrics'].get('disk', {}).get('usage_percent', 0) for s in snapshots],
            'memory_usage': [s['metrics'].get('memory', {}).get('usage_percent', 0) for s in snapshots],
            'issue_count': [len(s.get('issues', [])) for s in snapshots]
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
        """Generate personalized maintenance schedule.
        
        Returns:
            Dict with 'data' and 'summary' keys
        """
        # Load user profile for personalization
        profile = self.profile_manager.load()
        usage_patterns = profile.usage_patterns
        
        # Create basic maintenance plan
        plan = {
            'daily': [
                'Check system status',
                'Monitor memory usage'
            ],
            'weekly': [
                'Scan for issues',
                'Clean browser caches',
                'Review startup items'
            ],
            'monthly': [
                'Deep scan',
                'Clean system caches',
                'Review disk space usage',
                'Update software'
            ],
            'personalized_recommendations': []
        }
        
        # Add personalized recommendations based on profile
        if usage_patterns.cleanup_frequency > 0:
            plan['personalized_recommendations'].append(
                f"You typically clean up every {usage_patterns.cleanup_frequency} days"
            )
        
        if usage_patterns.most_common_issues:
            plan['personalized_recommendations'].append(
                f"Watch for: {', '.join(usage_patterns.most_common_issues[:3])}"
            )
        
        return {
            'data': plan,
            'summary': f"Created maintenance plan with {len(plan['daily'])} daily, {len(plan['weekly'])} weekly, and {len(plan['monthly'])} monthly tasks"
        }
