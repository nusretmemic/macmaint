"""Scanner orchestration - coordinates all monitoring modules."""
from typing import Dict, List, Optional
from macmaint.config import get_config
from macmaint.modules.disk import DiskModule
from macmaint.modules.memory import MemoryModule
from macmaint.modules.cpu import CPUModule
from macmaint.modules.network import NetworkModule
from macmaint.modules.battery import BatteryModule
from macmaint.modules.startup import StartupModule
from macmaint.models.issue import Issue
from macmaint.models.metrics import SystemMetrics
from macmaint.ai.client import AIClient
from macmaint.ai.prompts import AIRole
from macmaint.utils.system import get_boot_time, get_uptime_hours
from macmaint.utils.history import HistoryManager
from macmaint.utils.profile import ProfileManager


class Scanner:
    """Orchestrates system scanning across all modules."""
    
    def __init__(self, use_ai: bool = True):
        """Initialize scanner.
        
        Args:
            use_ai: Whether to use AI analysis
        """
        self.config = get_config()
        self.use_ai = use_ai
        
        # Initialize history manager
        self.history_manager = HistoryManager(retention_days=30)
        
        # Initialize profile manager
        self.profile_manager = ProfileManager()
        
        # Initialize modules
        self.modules = {}
        if self.config.is_module_enabled("disk"):
            self.modules["disk"] = DiskModule(self.config.get_module_config("disk"))
        if self.config.is_module_enabled("memory"):
            self.modules["memory"] = MemoryModule(self.config.get_module_config("memory"))
        if self.config.is_module_enabled("cpu"):
            self.modules["cpu"] = CPUModule(self.config.get_module_config("cpu"))
        if self.config.is_module_enabled("network"):
            self.modules["network"] = NetworkModule(self.config.get_module_config("network"))
        if self.config.is_module_enabled("battery"):
            self.modules["battery"] = BatteryModule(self.config.get_module_config("battery"))
        if self.config.is_module_enabled("startup"):
            self.modules["startup"] = StartupModule(self.config.get_module_config("startup"))
        
        # Initialize AI client if enabled
        self.ai_client = None
        if use_ai and self.config.api_key:
            try:
                self.ai_client = AIClient(
                    api_key=self.config.api_key,
                    model=self.config.model,
                    anonymize=self.config.anonymize_data
                )
            except Exception as e:
                if self.config.verbose:
                    print(f"Warning: Could not initialize AI client: {e}")
    
    def scan(self) -> tuple[SystemMetrics, List[Issue]]:
        """Run full system scan.
        
        Returns:
            Tuple of (metrics, issues)
        """
        all_metrics = {}
        all_issues = []
        
        # Collect metrics from all modules
        for module_name, module in self.modules.items():
            metrics, issues = module.scan()
            
            # Battery module returns None if no battery present
            if metrics is not None:
                all_metrics[module_name] = metrics
                all_issues.extend(issues)
            # For battery, if None is returned, skip it entirely
        
        # Add system-level metrics
        all_metrics["system"] = {
            "boot_time": get_boot_time(),
            "uptime_hours": get_uptime_hours()
        }
        
        # Create SystemMetrics object
        system_metrics = SystemMetrics(
            disk=all_metrics.get("disk"),
            memory=all_metrics.get("memory"),
            cpu=all_metrics.get("cpu"),
            network=all_metrics.get("network"),
            battery=all_metrics.get("battery"),
            startup=all_metrics.get("startup"),
            boot_time=all_metrics["system"]["boot_time"],
            uptime_hours=all_metrics["system"]["uptime_hours"]
        )
        
        # Use AI to enrich issues if available
        if self.ai_client:
            try:
                # Load user profile for personalized analysis
                profile = self.profile_manager.load()
                
                # Determine which AI role to use based on user preference
                role_map = {
                    'general': AIRole.GENERAL,
                    'performance': AIRole.PERFORMANCE,
                    'security': AIRole.SECURITY,
                    'storage': AIRole.STORAGE,
                    'maintenance': AIRole.MAINTENANCE,
                    'troubleshooter': AIRole.TROUBLESHOOTER
                }
                preferred_role = role_map.get(
                    profile.preferences.preferred_ai_role,
                    AIRole.GENERAL
                )
                
                # Get AI analysis with personalized role
                ai_issues, summary = self.ai_client.analyze_system(
                    all_metrics,
                    role=preferred_role
                )
                all_issues = self.ai_client.enrich_issues(all_issues, ai_issues)
                
                # Filter out issues user has chosen to ignore
                all_issues = [
                    issue for issue in all_issues
                    if not self.profile_manager.is_ignored(issue.id)
                ]
                
            except Exception as e:
                if self.config.verbose:
                    print(f"Warning: AI analysis failed: {e}")
        
        # Save snapshot to history
        try:
            self.history_manager.save_snapshot(all_metrics)
        except Exception:
            # Don't fail scan if history save fails
            pass
        
        # Track scan in user profile
        try:
            self.profile_manager.track_scan()
        except Exception:
            # Don't fail scan if profile tracking fails
            pass
        
        return system_metrics, all_issues
    
    def quick_status(self) -> Dict:
        """Get quick system status without full scan.
        
        Returns:
            Dictionary with basic status info
        """
        import psutil
        from macmaint.utils.system import bytes_to_gb
        
        disk = psutil.disk_usage('/')
        mem = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=1)
        
        return {
            "disk": {
                "percent_used": disk.percent,
                "free_gb": bytes_to_gb(disk.free)
            },
            "memory": {
                "percent_used": mem.percent,
                "available_gb": bytes_to_gb(mem.available)
            },
            "cpu": {
                "percent": cpu
            },
            "uptime_hours": get_uptime_hours()
        }
