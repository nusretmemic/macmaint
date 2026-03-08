"""Network monitoring module."""
from typing import Dict, List
from datetime import datetime
import psutil

from macmaint.modules.base import BaseModule
from macmaint.models.issue import Issue, IssueSeverity, IssueCategory
from macmaint.models.metrics import NetworkMetrics
from macmaint.utils.system import bytes_to_gb


class NetworkModule(BaseModule):
    """Network usage monitoring and anomaly detection module."""
    
    def __init__(self, config: Dict):
        """Initialize network module with bandwidth tracking."""
        super().__init__(config)
        self.bandwidth_samples = []  # Store samples for 24 hours
        self.max_samples = 288  # 24 hours * 12 (5-minute intervals)
    
    def collect_metrics(self) -> Dict:
        """Collect network usage metrics."""
        net_io = psutil.net_io_counters()
        
        # Try to get connections, but handle permission errors gracefully
        connections = []
        try:
            connections = psutil.net_connections(kind='inet')
        except (psutil.AccessDenied, PermissionError, OSError):
            # Need elevated privileges for connection details
            # Continue without connection information
            pass
        
        metrics = NetworkMetrics(
            bytes_sent=net_io.bytes_sent,
            bytes_recv=net_io.bytes_recv,
            bytes_sent_gb=bytes_to_gb(net_io.bytes_sent),
            bytes_recv_gb=bytes_to_gb(net_io.bytes_recv),
            connections_count=len(connections),
            error_in=net_io.errin,
            error_out=net_io.errout,
            drop_in=net_io.dropin,
            drop_out=net_io.dropout
        )
        
        # Count connections by state (if we have access)
        connection_states = {}
        for conn in connections:
            state = conn.status
            connection_states[state] = connection_states.get(state, 0) + 1
        
        metrics.connections_by_state = connection_states
        
        # Store bandwidth sample for anomaly detection
        sample = {
            'timestamp': datetime.now().isoformat(),
            'bytes_sent': net_io.bytes_sent,
            'bytes_recv': net_io.bytes_recv
        }
        
        self.bandwidth_samples.append(sample)
        
        # Keep only last 24 hours of samples
        if len(self.bandwidth_samples) > self.max_samples:
            self.bandwidth_samples = self.bandwidth_samples[-self.max_samples:]
        
        metrics.bandwidth_samples = self.bandwidth_samples
        
        return metrics.model_dump()
    
    def analyze(self, metrics: Dict) -> List[Issue]:
        """Analyze network metrics and detect issues."""
        issues = []
        
        net_metrics = NetworkMetrics(**metrics)
        
        # Check for network errors
        total_errors = net_metrics.error_in + net_metrics.error_out
        if total_errors > 100:
            issue = Issue(
                id="network_errors",
                title=f"Network errors detected: {total_errors} errors",
                description=f"Input errors: {net_metrics.error_in}, Output errors: {net_metrics.error_out}",
                severity=IssueSeverity.WARNING if total_errors > 500 else IssueSeverity.INFO,
                category=IssueCategory.NETWORK,
                metrics={
                    "error_in": net_metrics.error_in,
                    "error_out": net_metrics.error_out
                }
            )
            issues.append(issue)
        
        # Check for packet drops
        total_drops = net_metrics.drop_in + net_metrics.drop_out
        if total_drops > 50:
            issue = Issue(
                id="network_drops",
                title=f"Network packet drops: {total_drops} packets",
                description=f"Incoming drops: {net_metrics.drop_in}, Outgoing drops: {net_metrics.drop_out}",
                severity=IssueSeverity.WARNING if total_drops > 200 else IssueSeverity.INFO,
                category=IssueCategory.NETWORK,
                metrics={
                    "drop_in": net_metrics.drop_in,
                    "drop_out": net_metrics.drop_out
                }
            )
            issues.append(issue)
        
        # Detect bandwidth anomalies
        if len(net_metrics.bandwidth_samples) >= 10:
            anomalies = self._detect_bandwidth_anomalies(net_metrics.bandwidth_samples)
            if anomalies:
                issue = Issue(
                    id="network_bandwidth_anomaly",
                    title=f"Unusual network activity detected",
                    description=f"Bandwidth usage is {anomalies['spike_ratio']:.1f}x higher than average",
                    severity=IssueSeverity.WARNING,
                    category=IssueCategory.NETWORK,
                    metrics=anomalies
                )
                issues.append(issue)
        
        # Check for too many connections
        if net_metrics.connections_count > 500:
            issue = Issue(
                id="network_high_connections",
                title=f"High number of network connections: {net_metrics.connections_count}",
                description="May indicate network-intensive applications or potential security issues",
                severity=IssueSeverity.WARNING if net_metrics.connections_count > 1000 else IssueSeverity.INFO,
                category=IssueCategory.NETWORK,
                metrics={
                    "connections_count": net_metrics.connections_count,
                    "connections_by_state": net_metrics.connections_by_state
                }
            )
            issues.append(issue)
        
        return issues
    
    def _detect_bandwidth_anomalies(self, samples: List[Dict]) -> Dict:
        """Detect bandwidth usage anomalies (spikes > 3x average)."""
        if len(samples) < 10:
            return {}
        
        # Calculate deltas between samples
        deltas_sent = []
        deltas_recv = []
        
        for i in range(1, len(samples)):
            prev = samples[i - 1]
            curr = samples[i]
            
            delta_sent = curr['bytes_sent'] - prev['bytes_sent']
            delta_recv = curr['bytes_recv'] - prev['bytes_recv']
            
            if delta_sent > 0:
                deltas_sent.append(delta_sent)
            if delta_recv > 0:
                deltas_recv.append(delta_recv)
        
        if not deltas_sent and not deltas_recv:
            return {}
        
        # Calculate averages
        avg_sent = sum(deltas_sent) / len(deltas_sent) if deltas_sent else 0
        avg_recv = sum(deltas_recv) / len(deltas_recv) if deltas_recv else 0
        
        # Check for recent spikes (last 3 samples)
        recent_samples = samples[-4:]
        for i in range(1, len(recent_samples)):
            prev = recent_samples[i - 1]
            curr = recent_samples[i]
            
            delta_sent = curr['bytes_sent'] - prev['bytes_sent']
            delta_recv = curr['bytes_recv'] - prev['bytes_recv']
            
            # Spike detection: 3x average
            if avg_sent > 0 and delta_sent > avg_sent * 3:
                return {
                    'spike_type': 'sent',
                    'spike_bytes': delta_sent,
                    'average_bytes': avg_sent,
                    'spike_ratio': delta_sent / avg_sent
                }
            
            if avg_recv > 0 and delta_recv > avg_recv * 3:
                return {
                    'spike_type': 'received',
                    'spike_bytes': delta_recv,
                    'average_bytes': avg_recv,
                    'spike_ratio': delta_recv / avg_recv
                }
        
        return {}
