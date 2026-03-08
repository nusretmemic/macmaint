"""Memory monitoring module."""
from typing import Dict, List, Optional
import psutil
import subprocess
import re

from macmaint.modules.base import BaseModule
from macmaint.models.issue import Issue, IssueSeverity, IssueCategory, FixAction, ActionType
from macmaint.models.metrics import MemoryMetrics, ProcessInfo, MemoryBreakdown, MemoryPressure
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
        
        # Get memory breakdown (macOS specific)
        breakdown = self._get_memory_breakdown()
        if breakdown:
            metrics.breakdown = breakdown
        
        # Get top memory-consuming processes
        processes = []
        min_memory_mb = self.config.get("min_process_memory_mb", 100)
        
        for proc in psutil.process_iter(['pid', 'name', 'memory_info', 'memory_percent', 'status', 'exe']):
            try:
                mem_info = proc.info.get('memory_info')
                if not mem_info:
                    continue
                    
                mem_mb = mem_info.rss / (1024 * 1024)
                
                if mem_mb >= min_memory_mb:
                    # Categorize process
                    category = self._categorize_process(proc.info.get('name', ''), proc.info.get('exe', ''))
                    
                    processes.append(ProcessInfo(
                        pid=proc.info['pid'],
                        name=proc.info['name'],
                        memory_mb=mem_mb,
                        memory_percent=proc.info.get('memory_percent', 0.0),
                        status=proc.info.get('status', 'unknown'),
                        category=category
                    ))
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        
        # Sort by memory usage descending
        processes.sort(key=lambda p: p.memory_mb, reverse=True)
        metrics.top_processes = processes[:10]
        
        # Group processes by category
        metrics.processes_by_category = self._group_processes_by_category(processes)
        
        return metrics.model_dump()
    
    def _get_memory_breakdown(self) -> Optional[MemoryBreakdown]:
        """Get detailed memory breakdown using vm_stat (macOS specific)."""
        try:
            result = subprocess.run(['vm_stat'], capture_output=True, text=True, timeout=5)
            if result.returncode != 0:
                return None
            
            output = result.stdout
            
            # Parse vm_stat output
            # Example line: "Pages wired down:                12345."
            def extract_pages(pattern: str) -> float:
                match = re.search(rf'{pattern}:\s+(\d+)\.?', output)
                if match:
                    pages = int(match.group(1))
                    # Page size is typically 4096 bytes on macOS
                    bytes_value = pages * 4096
                    return bytes_to_gb(bytes_value)
                return 0.0
            
            wired = extract_pages('Pages wired down')
            active = extract_pages('Pages active')
            inactive = extract_pages('Pages inactive')
            compressed = extract_pages('Pages occupied by compressor')
            
            # Determine memory pressure
            mem = psutil.virtual_memory()
            pressure = MemoryPressure.NORMAL
            if mem.percent >= 95:
                pressure = MemoryPressure.CRITICAL
            elif mem.percent >= 85:
                pressure = MemoryPressure.WARNING
            
            return MemoryBreakdown(
                wired_gb=wired,
                active_gb=active,
                inactive_gb=inactive,
                compressed_gb=compressed,
                pressure_level=pressure
            )
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, Exception):
            return None
    
    def _categorize_process(self, name: str, exe_path: str) -> str:
        """Categorize a process as system, application, or background."""
        name_lower = name.lower()
        exe_lower = exe_path.lower() if exe_path else ''
        
        # System processes
        system_names = [
            'kernel_task', 'launchd', 'windowserver', 'systemmigrationd',
            'loginwindow', 'systemuiserver', 'dock', 'finder', 'spotlight',
            'coreaudiod', 'bluetoothd', 'wirelessproxd', 'notifyd',
            'distnoted', 'cfprefsd', 'powerd', 'syslogd', 'coreservicesd'
        ]
        
        for sys_name in system_names:
            if sys_name in name_lower:
                return 'system'
        
        # Applications (in /Applications or have .app)
        if '/applications/' in exe_lower or '.app/' in exe_lower:
            return 'application'
        
        # Helper processes (typically end with 'Helper' or contain 'helper')
        if 'helper' in name_lower or 'agent' in name_lower:
            return 'background'
        
        # Default to background for anything else
        return 'background'
    
    def _group_processes_by_category(self, processes: List[ProcessInfo]) -> Dict[str, List[ProcessInfo]]:
        """Group processes by their category."""
        grouped = {
            'system': [],
            'application': [],
            'background': []
        }
        
        for proc in processes:
            category = proc.category or 'background'
            if category in grouped:
                grouped[category].append(proc)
        
        return grouped
    
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
