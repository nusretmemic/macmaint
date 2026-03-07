"""Disk space analysis module."""
import os
from pathlib import Path
from typing import Dict, List
import psutil

from macmaint.modules.base import BaseModule
from macmaint.models.issue import Issue, IssueSeverity, IssueCategory, FixAction, ActionType
from macmaint.models.metrics import DiskMetrics
from macmaint.utils.system import expand_path, get_file_age_days, bytes_to_gb


class DiskModule(BaseModule):
    """Disk space monitoring and cleanup module."""
    
    def collect_metrics(self) -> Dict:
        """Collect disk space metrics."""
        # Get disk usage
        disk = psutil.disk_usage('/')
        
        metrics = DiskMetrics(
            total_gb=bytes_to_gb(disk.total),
            used_gb=bytes_to_gb(disk.used),
            free_gb=bytes_to_gb(disk.free),
            percent_used=disk.percent
        )
        
        # Scan cache directories
        cache_info = self._scan_caches()
        metrics.cache_files = cache_info['counts']
        metrics.cache_size_gb = cache_info['size_gb']
        
        # Scan log files
        log_info = self._scan_logs()
        metrics.log_files = log_info['counts']
        metrics.log_size_gb = log_info['size_gb']
        
        # Scan temp directories
        metrics.temp_size_gb = self._scan_temp()
        
        # Find large files
        metrics.large_files = self._find_large_files()
        
        return metrics.model_dump()
    
    def _scan_caches(self) -> Dict:
        """Scan cache directories (optimized with depth limit)."""
        scan_paths = self.config.get("scan_paths", [])
        cache_paths = [p for p in scan_paths if "Cache" in p]
        
        total_size = 0
        total_count = 0
        counts_by_location = {}
        
        for cache_path_str in cache_paths:
            cache_path = expand_path(cache_path_str)
            if not cache_path.exists():
                continue
            
            count = 0
            size = 0
            
            try:
                # Use iterdir() for immediate children only - much faster
                for item in cache_path.iterdir():
                    if item.is_file():
                        try:
                            file_size = item.stat().st_size
                            size += file_size
                            count += 1
                        except (OSError, PermissionError):
                            pass
                    elif item.is_dir():
                        # Add subdirectory sizes (one level deep only)
                        try:
                            for subitem in item.iterdir():
                                if subitem.is_file():
                                    try:
                                        file_size = subitem.stat().st_size
                                        size += file_size
                                        count += 1
                                    except (OSError, PermissionError):
                                        pass
                        except (OSError, PermissionError):
                            pass
            except (OSError, PermissionError):
                pass
            
            if count > 0:
                counts_by_location[str(cache_path)] = count
                total_size += size
                total_count += count
        
        return {
            'counts': counts_by_location,
            'size_gb': bytes_to_gb(total_size),
            'total_count': total_count
        }
    
    def _scan_logs(self) -> Dict:
        """Scan log directories (optimized)."""
        scan_paths = self.config.get("scan_paths", [])
        log_paths = [p for p in scan_paths if "Log" in p or "log" in p]
        
        total_size = 0
        total_count = 0
        counts_by_location = {}
        
        for log_path_str in log_paths:
            log_path = expand_path(log_path_str)
            if not log_path.exists():
                continue
            
            count = 0
            size = 0
            
            try:
                # Scan only immediate files
                for item in log_path.iterdir():
                    if item.is_file() and ('.log' in item.name.lower()):
                        try:
                            file_size = item.stat().st_size
                            size += file_size
                            count += 1
                        except (OSError, PermissionError):
                            pass
            except (OSError, PermissionError):
                pass
            
            if count > 0:
                counts_by_location[str(log_path)] = count
                total_size += size
                total_count += count
        
        return {
            'counts': counts_by_location,
            'size_gb': bytes_to_gb(total_size),
            'total_count': total_count
        }
    
    def _scan_temp(self) -> float:
        """Scan temporary directories."""
        temp_paths = [Path("/tmp"), Path(os.getenv("TMPDIR", "/tmp"))]
        total_size = 0
        
        for temp_path in temp_paths:
            if not temp_path.exists():
                continue
            
            try:
                for item in temp_path.iterdir():
                    if item.is_file():
                        try:
                            total_size += item.stat().st_size
                        except (OSError, PermissionError):
                            pass
            except (OSError, PermissionError):
                pass
        
        return bytes_to_gb(total_size)
    
    def _find_large_files(self) -> List[Dict]:
        """Find large files that haven't been accessed recently (optimized)."""
        threshold_mb = self.config.get("large_file_threshold_mb", 500)
        threshold_bytes = threshold_mb * 1024 * 1024
        
        large_files = []
        scan_paths = [
            Path.home() / "Downloads",
        ]
        
        for scan_path in scan_paths:
            if not scan_path.exists():
                continue
            
            try:
                # Only scan immediate files in Downloads
                for item in scan_path.iterdir():
                    if item.is_file():
                        try:
                            size = item.stat().st_size
                            if size >= threshold_bytes:
                                age_days = get_file_age_days(item)
                                large_files.append({
                                    'path': str(item),
                                    'size_mb': size / (1024 * 1024),
                                    'age_days': int(age_days)
                                })
                        except (OSError, PermissionError):
                            pass
                    
                    # Limit to top 10 largest files
                    if len(large_files) >= 10:
                        break
            except (OSError, PermissionError):
                pass
        
        # Sort by size descending
        large_files.sort(key=lambda x: x['size_mb'], reverse=True)
        return large_files[:10]
    
    def analyze(self, metrics: Dict) -> List[Issue]:
        """Analyze disk metrics and detect issues."""
        issues = []
        
        disk_metrics = DiskMetrics(**metrics)
        
        # Check free space
        severity = None
        title = ""
        
        if disk_metrics.percent_used >= 95:
            severity = IssueSeverity.CRITICAL
            title = f"Disk space critically low: {disk_metrics.free_gb:.1f} GB free ({100 - disk_metrics.percent_used:.1f}%)"
        elif disk_metrics.percent_used >= 85:
            severity = IssueSeverity.WARNING
            title = f"Disk space running low: {disk_metrics.free_gb:.1f} GB free ({100 - disk_metrics.percent_used:.1f}%)"
        
        if severity:
            issue = Issue(
                id="disk_low_space",
                title=title,
                description=f"Total: {disk_metrics.total_gb:.1f} GB, Used: {disk_metrics.used_gb:.1f} GB",
                severity=severity,
                category=IssueCategory.DISK,
                metrics={"free_gb": disk_metrics.free_gb, "percent_used": disk_metrics.percent_used}
            )
            issues.append(issue)
        
        # Check cache files
        if disk_metrics.cache_size_gb > 1.0:
            issue = Issue(
                id="disk_cache_cleanup",
                title=f"Cache files consuming {disk_metrics.cache_size_gb:.1f} GB",
                description=f"Found cache files that can be safely cleaned",
                severity=IssueSeverity.WARNING if disk_metrics.cache_size_gb > 5 else IssueSeverity.INFO,
                category=IssueCategory.DISK,
                metrics={
                    "size_gb": disk_metrics.cache_size_gb,
                    "locations": disk_metrics.cache_files
                },
                fix_actions=[
                    FixAction(
                        action_type=ActionType.DELETE_FILES,
                        description=f"Clean cache files ({disk_metrics.cache_size_gb:.1f} GB)",
                        details={"paths": list(disk_metrics.cache_files.keys())},
                        estimated_impact=f"Free {disk_metrics.cache_size_gb:.1f} GB",
                        safe=True,
                        requires_confirmation=True
                    )
                ]
            )
            issues.append(issue)
        
        # Check log files
        if disk_metrics.log_size_gb > 0.5:
            issue = Issue(
                id="disk_log_cleanup",
                title=f"Log files consuming {disk_metrics.log_size_gb:.1f} GB",
                description="Old log files can be cleaned",
                severity=IssueSeverity.INFO,
                category=IssueCategory.DISK,
                metrics={
                    "size_gb": disk_metrics.log_size_gb,
                    "locations": disk_metrics.log_files
                },
                fix_actions=[
                    FixAction(
                        action_type=ActionType.DELETE_FILES,
                        description=f"Clean log files ({disk_metrics.log_size_gb:.1f} GB)",
                        details={"paths": list(disk_metrics.log_files.keys())},
                        estimated_impact=f"Free {disk_metrics.log_size_gb:.1f} GB",
                        safe=True,
                        requires_confirmation=True
                    )
                ]
            )
            issues.append(issue)
        
        # Check large files
        if disk_metrics.large_files:
            old_large_files = [f for f in disk_metrics.large_files if f['age_days'] > 90]
            if old_large_files:
                total_size_gb = sum(f['size_mb'] for f in old_large_files) / 1024
                issue = Issue(
                    id="disk_large_files",
                    title=f"{len(old_large_files)} large files not accessed in 90+ days ({total_size_gb:.1f} GB)",
                    description="Large files that may no longer be needed",
                    severity=IssueSeverity.INFO,
                    category=IssueCategory.DISK,
                    metrics={"files": old_large_files}
                )
                issues.append(issue)
        
        return issues
