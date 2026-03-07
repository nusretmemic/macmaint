"""Base module class for all monitoring modules."""
from abc import ABC, abstractmethod
from typing import Dict, List
from macmaint.models.issue import Issue
from macmaint.models.metrics import SystemMetrics


class BaseModule(ABC):
    """Base class for all system monitoring modules."""
    
    def __init__(self, config: Dict):
        """Initialize the module with configuration."""
        self.config = config
        self.enabled = config.get("enabled", True)
    
    @abstractmethod
    def collect_metrics(self) -> Dict:
        """Collect metrics for this module.
        
        Returns:
            Dictionary of metrics specific to this module.
        """
        pass
    
    @abstractmethod
    def analyze(self, metrics: Dict) -> List[Issue]:
        """Analyze metrics and detect issues.
        
        Args:
            metrics: Metrics collected by collect_metrics()
        
        Returns:
            List of detected issues.
        """
        pass
    
    def scan(self) -> tuple[Dict, List[Issue]]:
        """Run full scan: collect metrics and analyze.
        
        Returns:
            Tuple of (metrics, issues).
        """
        if not self.enabled:
            return {}, []
        
        metrics = self.collect_metrics()
        issues = self.analyze(metrics)
        return metrics, issues
