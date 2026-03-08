"""Historical data tracking and management."""
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional


class HistoryManager:
    """Manages historical system metrics snapshots."""
    
    def __init__(self, history_dir: Optional[Path] = None, retention_days: int = 30):
        """Initialize history manager.
        
        Args:
            history_dir: Directory to store history files (default: ~/.macmaint/history)
            retention_days: Number of days to retain snapshots (default: 30)
        """
        self.history_dir = history_dir or (Path.home() / ".macmaint" / "history")
        self.retention_days = retention_days
        self.history_dir.mkdir(parents=True, exist_ok=True)
    
    def save_snapshot(self, metrics: Dict) -> bool:
        """Save a metrics snapshot.
        
        Args:
            metrics: System metrics dictionary
        
        Returns:
            True if successful
        """
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            snapshot_file = self.history_dir / f"{today}.json"
            
            # Add timestamp
            snapshot_data = {
                "timestamp": datetime.now().isoformat(),
                "date": today,
                "metrics": metrics
            }
            
            with open(snapshot_file, 'w') as f:
                json.dump(snapshot_data, f, indent=2)
            
            # Cleanup old snapshots
            self._cleanup_old_snapshots()
            
            return True
        except Exception:
            return False
    
    def get_snapshots(self, days: int = 7) -> List[Dict]:
        """Get recent snapshots.
        
        Args:
            days: Number of days to retrieve
        
        Returns:
            List of snapshot dictionaries
        """
        snapshots = []
        cutoff_date = datetime.now() - timedelta(days=days)
        
        try:
            for snapshot_file in sorted(self.history_dir.glob("*.json")):
                # Parse date from filename
                try:
                    file_date = datetime.strptime(snapshot_file.stem, "%Y-%m-%d")
                    
                    if file_date >= cutoff_date:
                        with open(snapshot_file, 'r') as f:
                            snapshot_data = json.load(f)
                            snapshots.append(snapshot_data)
                except (ValueError, json.JSONDecodeError):
                    # Skip invalid files
                    continue
        except Exception:
            pass
        
        return snapshots
    
    def _cleanup_old_snapshots(self):
        """Remove snapshots older than retention_days."""
        try:
            cutoff_date = datetime.now() - timedelta(days=self.retention_days)
            
            for snapshot_file in self.history_dir.glob("*.json"):
                try:
                    file_date = datetime.strptime(snapshot_file.stem, "%Y-%m-%d")
                    
                    if file_date < cutoff_date:
                        snapshot_file.unlink()
                except (ValueError, OSError):
                    # Skip files we can't process
                    continue
        except Exception:
            pass
    
    def get_trend_data(self, metric_path: str, days: int = 7) -> List[tuple]:
        """Get trend data for a specific metric.
        
        Args:
            metric_path: Dot-notation path to metric (e.g., "disk.percent_used")
            days: Number of days to retrieve
        
        Returns:
            List of (date, value) tuples
        """
        snapshots = self.get_snapshots(days)
        trend_data = []
        
        for snapshot in snapshots:
            try:
                # Navigate the metric path
                value = snapshot['metrics']
                for key in metric_path.split('.'):
                    value = value.get(key)
                    if value is None:
                        break
                
                if value is not None:
                    date = snapshot['date']
                    trend_data.append((date, value))
            except (KeyError, TypeError):
                continue
        
        return trend_data


def create_sparkline(values: List[float], width: int = 20) -> str:
    """Create ASCII sparkline from values.
    
    Args:
        values: List of numeric values
        width: Width of sparkline in characters
    
    Returns:
        String representation of sparkline
    """
    if not values or len(values) < 2:
        return "─" * width
    
    # Normalize values to 0-7 range for Unicode block characters
    min_val = min(values)
    max_val = max(values)
    
    if max_val == min_val:
        # All values are the same
        return "▄" * width
    
    # Resize values to fit width
    step = len(values) / width if len(values) > width else 1
    sampled_values = []
    
    for i in range(width):
        idx = int(i * step)
        if idx < len(values):
            sampled_values.append(values[idx])
    
    # Create sparkline
    blocks = ['▁', '▂', '▃', '▄', '▅', '▆', '▇', '█']
    sparkline = ""
    
    for value in sampled_values:
        normalized = (value - min_val) / (max_val - min_val)
        block_idx = min(int(normalized * 8), 7)
        sparkline += blocks[block_idx]
    
    return sparkline


def calculate_trend_direction(values: List[float]) -> tuple:
    """Calculate trend direction and change percentage.
    
    Args:
        values: List of numeric values (chronological order)
    
    Returns:
        Tuple of (direction_symbol, change_percent)
    """
    if len(values) < 2:
        return "→", 0.0
    
    first_val = values[0]
    last_val = values[-1]
    
    if first_val == 0:
        return "→", 0.0
    
    change_pct = ((last_val - first_val) / first_val) * 100
    
    if abs(change_pct) < 1:
        direction = "→"
    elif change_pct > 0:
        direction = "↑"
    else:
        direction = "↓"
    
    return direction, abs(change_pct)
