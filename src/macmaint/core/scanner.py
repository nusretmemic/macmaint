"""Scanner orchestration - coordinates all monitoring modules."""
from typing import Dict, List, Optional
from macmaint.config import get_config
from macmaint.modules.disk import DiskModule
from macmaint.modules.memory import MemoryModule
from macmaint.modules.cpu import CPUModule
from macmaint.models.issue import Issue
from macmaint.models.metrics import SystemMetrics
from macmaint.ai.client import AIClient
from macmaint.utils.system import get_boot_time, get_uptime_hours


class Scanner:
    """Orchestrates system scanning across all modules."""
    
    def __init__(self, use_ai: bool = True):
        """Initialize scanner.
        
        Args:
            use_ai: Whether to use AI analysis
        """
        self.config = get_config()
        self.use_ai = use_ai
        
        # Initialize modules
        self.modules = {}
        if self.config.is_module_enabled("disk"):
            self.modules["disk"] = DiskModule(self.config.get_module_config("disk"))
        if self.config.is_module_enabled("memory"):
            self.modules["memory"] = MemoryModule(self.config.get_module_config("memory"))
        if self.config.is_module_enabled("cpu"):
            self.modules["cpu"] = CPUModule(self.config.get_module_config("cpu"))
        
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
            all_metrics[module_name] = metrics
            all_issues.extend(issues)
        
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
            boot_time=all_metrics["system"]["boot_time"],
            uptime_hours=all_metrics["system"]["uptime_hours"]
        )
        
        # Use AI to enrich issues if available
        if self.ai_client:
            try:
                ai_issues, summary = self.ai_client.analyze_system(all_metrics)
                all_issues = self.ai_client.enrich_issues(all_issues, ai_issues)
            except Exception as e:
                if self.config.verbose:
                    print(f"Warning: AI analysis failed: {e}")
        
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
