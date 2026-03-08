"""Battery health monitoring module."""
from typing import Dict, List, Optional
import subprocess
import psutil

from macmaint.modules.base import BaseModule
from macmaint.models.issue import Issue, IssueSeverity, IssueCategory
from macmaint.models.metrics import BatteryMetrics


class BatteryModule(BaseModule):
    """Battery health monitoring module (auto-hides on desktops)."""
    
    def collect_metrics(self) -> Optional[Dict]:
        """Collect battery metrics. Returns None if no battery present."""
        # Check if battery exists
        battery = psutil.sensors_battery()
        
        if battery is None:
            # No battery present (desktop, Mac Mini, etc.)
            return None
        
        metrics = BatteryMetrics(
            is_present=True,
            percent=battery.percent,
            is_charging=battery.power_plugged,
            time_remaining=battery.secsleft // 60 if battery.secsleft > 0 else None
        )
        
        # Try to get detailed battery info using system_profiler
        detailed_info = self._get_battery_details()
        if detailed_info:
            metrics.cycle_count = detailed_info.get('cycle_count', 0)
            metrics.max_capacity_percent = detailed_info.get('max_capacity_percent', 100.0)
            metrics.health = detailed_info.get('health', 'Unknown')
        
        return metrics.model_dump()
    
    def _get_battery_details(self) -> Optional[Dict]:
        """Get detailed battery information using system_profiler (macOS)."""
        try:
            result = subprocess.run(
                ['system_profiler', 'SPPowerDataType'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                return None
            
            output = result.stdout
            details = {}
            
            # Parse cycle count
            if 'Cycle Count:' in output:
                for line in output.split('\n'):
                    if 'Cycle Count:' in line:
                        try:
                            cycle_str = line.split(':')[1].strip()
                            details['cycle_count'] = int(cycle_str)
                        except (ValueError, IndexError):
                            pass
            
            # Parse condition/health
            if 'Condition:' in output:
                for line in output.split('\n'):
                    if 'Condition:' in line:
                        condition = line.split(':')[1].strip()
                        details['health'] = condition
            
            # Calculate max capacity percentage
            # Look for "Maximum Capacity" percentage
            if 'Maximum Capacity:' in output:
                for line in output.split('\n'):
                    if 'Maximum Capacity:' in line and '%' in line:
                        try:
                            capacity_str = line.split(':')[1].strip().replace('%', '')
                            details['max_capacity_percent'] = float(capacity_str)
                        except (ValueError, IndexError):
                            pass
            
            # If we couldn't find max capacity, estimate from health
            if 'max_capacity_percent' not in details:
                health = details.get('health', '').lower()
                if 'normal' in health or 'good' in health:
                    details['max_capacity_percent'] = 100.0
                elif 'replace soon' in health:
                    details['max_capacity_percent'] = 80.0
                elif 'replace' in health or 'service' in health:
                    details['max_capacity_percent'] = 70.0
            
            return details if details else None
            
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, Exception):
            return None
    
    def analyze(self, metrics: Dict) -> List[Issue]:
        """Analyze battery metrics and detect issues."""
        if metrics is None:
            # No battery present, return empty list
            return []
        
        issues = []
        battery_metrics = BatteryMetrics(**metrics)
        
        # Check battery health
        if battery_metrics.max_capacity_percent < 80:
            severity = IssueSeverity.WARNING if battery_metrics.max_capacity_percent < 70 else IssueSeverity.INFO
            issue = Issue(
                id="battery_health_degraded",
                title=f"Battery capacity degraded to {battery_metrics.max_capacity_percent:.1f}%",
                description=f"Original capacity: 100%, Current capacity: {battery_metrics.max_capacity_percent:.1f}%",
                severity=severity,
                category=IssueCategory.SYSTEM,
                metrics={
                    "max_capacity_percent": battery_metrics.max_capacity_percent,
                    "cycle_count": battery_metrics.cycle_count
                }
            )
            issues.append(issue)
        
        # Check cycle count
        # Most MacBook batteries are rated for 1000 cycles
        if battery_metrics.cycle_count > 800:
            severity = IssueSeverity.WARNING if battery_metrics.cycle_count > 1000 else IssueSeverity.INFO
            issue = Issue(
                id="battery_high_cycles",
                title=f"High battery cycle count: {battery_metrics.cycle_count} cycles",
                description=f"Battery may need replacement soon (typical limit: 1000 cycles)",
                severity=severity,
                category=IssueCategory.SYSTEM,
                metrics={
                    "cycle_count": battery_metrics.cycle_count,
                    "health": battery_metrics.health
                }
            )
            issues.append(issue)
        
        # Check battery health status
        if battery_metrics.health and 'replace' in battery_metrics.health.lower():
            issue = Issue(
                id="battery_needs_service",
                title=f"Battery needs service: {battery_metrics.health}",
                description="Apple recommends servicing or replacing the battery",
                severity=IssueSeverity.WARNING,
                category=IssueCategory.SYSTEM,
                metrics={
                    "health": battery_metrics.health,
                    "max_capacity_percent": battery_metrics.max_capacity_percent
                }
            )
            issues.append(issue)
        
        return issues
