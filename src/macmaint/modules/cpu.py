"""CPU monitoring module."""
import time
from typing import Dict, List
import psutil

from macmaint.modules.base import BaseModule
from macmaint.models.issue import Issue, IssueSeverity, IssueCategory, FixAction, ActionType
from macmaint.models.metrics import CPUMetrics, ProcessInfo


class CPUModule(BaseModule):
    """CPU usage monitoring module."""
    
    def collect_metrics(self) -> Dict:
        """Collect CPU usage metrics."""
        cpu_count = psutil.cpu_count()
        
        # Sample CPU usage over configured duration (use shorter default for speed)
        sample_duration = self.config.get("sample_duration_seconds", 1)
        cpu_percent = psutil.cpu_percent(interval=sample_duration)
        
        # Get load averages
        load_avg = psutil.getloadavg()
        
        metrics = CPUMetrics(
            cpu_count=cpu_count,
            cpu_percent=cpu_percent,
            load_average=list(load_avg)
        )
        
        # Get top CPU-consuming processes
        processes = []
        min_cpu_percent = self.config.get("min_process_cpu_percent", 10)
        
        # First pass: initialize CPU percent for all processes (non-blocking)
        all_procs = list(psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_info', 'status']))
        for proc in all_procs:
            try:
                proc.cpu_percent(interval=None)  # Non-blocking initialization
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        
        # Brief wait for CPU measurement
        time.sleep(0.1)
        
        # Second pass: collect CPU data (now available)
        for proc in all_procs:
            try:
                # Get CPU percent (non-blocking now)
                cpu = proc.cpu_percent(interval=None)
                
                if cpu >= min_cpu_percent:
                    mem_info = proc.info.get('memory_info')
                    if not mem_info:
                        continue
                        
                    mem_mb = mem_info.rss / (1024 * 1024)
                    
                    processes.append(ProcessInfo(
                        pid=proc.info['pid'],
                        name=proc.info['name'],
                        cpu_percent=cpu,
                        memory_mb=mem_mb,
                        status=proc.info.get('status', 'unknown')
                    ))
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        
        # Sort by CPU usage descending
        processes.sort(key=lambda p: p.cpu_percent, reverse=True)
        metrics.top_processes = processes[:10]
        
        return metrics.model_dump()
    
    def analyze(self, metrics: Dict) -> List[Issue]:
        """Analyze CPU metrics and detect issues."""
        issues = []
        
        cpu_metrics = CPUMetrics(**metrics)
        threshold = self.config.get("alert_threshold_percent", 80)
        
        # Check overall CPU usage
        if cpu_metrics.cpu_percent >= threshold:
            severity = IssueSeverity.WARNING if cpu_metrics.cpu_percent >= 90 else IssueSeverity.INFO
            issue = Issue(
                id="cpu_high_usage",
                title=f"High CPU usage: {cpu_metrics.cpu_percent:.1f}%",
                description=f"System CPU usage is elevated",
                severity=severity,
                category=IssueCategory.CPU,
                metrics={
                    "cpu_percent": cpu_metrics.cpu_percent,
                    "cpu_count": cpu_metrics.cpu_count
                }
            )
            issues.append(issue)
        
        # Check load average
        if cpu_metrics.load_average:
            load_1min = cpu_metrics.load_average[0]
            load_per_cpu = load_1min / cpu_metrics.cpu_count
            
            # Load average > 1.0 per CPU indicates system is busy
            if load_per_cpu > 1.5:
                issue = Issue(
                    id="cpu_high_load",
                    title=f"High system load: {load_1min:.2f} (1-min avg)",
                    description=f"Load per CPU: {load_per_cpu:.2f}",
                    severity=IssueSeverity.WARNING if load_per_cpu > 2.0 else IssueSeverity.INFO,
                    category=IssueCategory.CPU,
                    metrics={
                        "load_average": cpu_metrics.load_average,
                        "load_per_cpu": load_per_cpu
                    }
                )
                issues.append(issue)
        
        # Check for CPU-heavy processes
        if cpu_metrics.top_processes:
            for process in cpu_metrics.top_processes[:3]:  # Top 3 CPU hogs
                if process.cpu_percent > 50:
                    issue = Issue(
                        id=f"cpu_heavy_process_{process.pid}",
                        title=f"{process.name} using {process.cpu_percent:.1f}% CPU",
                        description=f"Process is consuming significant CPU resources",
                        severity=IssueSeverity.WARNING if process.cpu_percent > 80 else IssueSeverity.INFO,
                        category=IssueCategory.CPU,
                        metrics={
                            "process_name": process.name,
                            "pid": process.pid,
                            "cpu_percent": process.cpu_percent
                        },
                        fix_actions=[
                            FixAction(
                                action_type=ActionType.MANUAL,
                                description=f"Investigate {process.name} high CPU usage",
                                details={"pid": process.pid, "name": process.name},
                                estimated_impact="May reduce CPU load",
                                safe=False,
                                requires_confirmation=True
                            )
                        ]
                    )
                    issues.append(issue)
        
        return issues
