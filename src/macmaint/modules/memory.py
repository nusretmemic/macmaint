"""Memory monitoring module."""
from typing import Dict, List
import psutil

from macmaint.modules.base import BaseModule
from macmaint.models.issue import Issue, IssueSeverity, IssueCategory, FixAction, ActionType
from macmaint.models.metrics import MemoryMetrics, ProcessInfo
from macmaint.utils.system import bytes_to_gb


class MemoryModule(BaseModule):
    """Memory usage monitoring module."""
    
    def collect_metrics(self) -> Dict:
        """Collect memory usage metrics."""
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        
        metrics = MemoryMetrics(
            total_gb=bytes_to_gb(mem.total),
            available_gb=bytes_to_gb(mem.available),
            used_gb=bytes_to_gb(mem.used),
            percent_used=mem.percent,
            swap_total_gb=bytes_to_gb(swap.total),
            swap_used_gb=bytes_to_gb(swap.used)
        )
        
        # Get top memory-consuming processes
        processes = []
        min_memory_mb = self.config.get("min_process_memory_mb", 100)
        
        for proc in psutil.process_iter(['pid', 'name', 'memory_info', 'memory_percent', 'status']):
            try:
                mem_info = proc.info.get('memory_info')
                if not mem_info:
                    continue
                    
                mem_mb = mem_info.rss / (1024 * 1024)
                
                if mem_mb >= min_memory_mb:
                    processes.append(ProcessInfo(
                        pid=proc.info['pid'],
                        name=proc.info['name'],
                        memory_mb=mem_mb,
                        memory_percent=proc.info.get('memory_percent', 0.0),
                        status=proc.info.get('status', 'unknown')
                    ))
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        
        # Sort by memory usage descending
        processes.sort(key=lambda p: p.memory_mb, reverse=True)
        metrics.top_processes = processes[:10]
        
        return metrics.model_dump()
    
    def analyze(self, metrics: Dict) -> List[Issue]:
        """Analyze memory metrics and detect issues."""
        issues = []
        
        mem_metrics = MemoryMetrics(**metrics)
        threshold = self.config.get("alert_threshold_percent", 85)
        
        # Check overall memory usage
        if mem_metrics.percent_used >= threshold:
            severity = IssueSeverity.CRITICAL if mem_metrics.percent_used >= 95 else IssueSeverity.WARNING
            issue = Issue(
                id="memory_high_usage",
                title=f"High memory usage: {mem_metrics.percent_used:.1f}%",
                description=f"Using {mem_metrics.used_gb:.1f} GB of {mem_metrics.total_gb:.1f} GB",
                severity=severity,
                category=IssueCategory.MEMORY,
                metrics={
                    "percent_used": mem_metrics.percent_used,
                    "available_gb": mem_metrics.available_gb
                }
            )
            issues.append(issue)
        
        # Check for memory-heavy processes
        if mem_metrics.top_processes:
            top_process = mem_metrics.top_processes[0]
            
            # If a single process is using > 2GB or > 25% of memory
            if top_process.memory_mb > 2048 or top_process.memory_percent > 25:
                issue = Issue(
                    id=f"memory_heavy_process_{top_process.pid}",
                    title=f"{top_process.name} using {top_process.memory_mb / 1024:.1f} GB memory",
                    description=f"Process may have a memory leak or is resource-intensive",
                    severity=IssueSeverity.WARNING if top_process.memory_mb > 4096 else IssueSeverity.INFO,
                    category=IssueCategory.MEMORY,
                    metrics={
                        "process_name": top_process.name,
                        "pid": top_process.pid,
                        "memory_mb": top_process.memory_mb,
                        "memory_percent": top_process.memory_percent
                    },
                    fix_actions=[
                        FixAction(
                            action_type=ActionType.MANUAL,
                            description=f"Consider restarting {top_process.name}",
                            details={"pid": top_process.pid, "name": top_process.name},
                            estimated_impact=f"Could free ~{top_process.memory_mb / 1024:.1f} GB",
                            safe=False,
                            requires_confirmation=True
                        )
                    ]
                )
                issues.append(issue)
        
        # Check swap usage
        if mem_metrics.swap_used_gb > 2.0:
            issue = Issue(
                id="memory_high_swap",
                title=f"High swap usage: {mem_metrics.swap_used_gb:.1f} GB",
                description="System is using significant swap memory, which can slow performance",
                severity=IssueSeverity.WARNING,
                category=IssueCategory.MEMORY,
                metrics={"swap_used_gb": mem_metrics.swap_used_gb}
            )
            issues.append(issue)
        
        return issues
