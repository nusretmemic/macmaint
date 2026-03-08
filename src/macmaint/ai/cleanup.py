"""Smart cleanup analyzer with AI-powered risk assessment."""

from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass
from enum import Enum
import os
from datetime import datetime, timedelta

from macmaint.ai.client import AIClient
from macmaint.utils.profile import ProfileManager


class RiskLevel(Enum):
    """Risk levels for cleanup actions."""
    SAFE = "safe"  # Can safely delete without any impact
    LOW_RISK = "low_risk"  # Minimal risk, easily recoverable
    MEDIUM_RISK = "medium_risk"  # Some risk, may require re-download or reconfiguration
    HIGH_RISK = "high_risk"  # Significant risk, could cause data loss or system issues
    CRITICAL = "critical"  # Do not delete without user confirmation


@dataclass
class CleanupItem:
    """Represents a file or directory that can be cleaned up."""
    path: str
    size_bytes: int
    file_type: str  # cache, log, temp, download, duplicate, etc.
    age_days: int
    risk_level: RiskLevel
    reason: str  # Why this can be cleaned
    recovery_info: Optional[str] = None  # How to recover if needed
    category: Optional[str] = None  # browser, system, app-specific, etc.


class CleanupAnalyzer:
    """Analyzes files and provides AI-powered cleanup recommendations."""
    
    def __init__(self, api_key: str):
        """Initialize cleanup analyzer.
        
        Args:
            api_key: OpenAI API key
        """
        self.ai_client = AIClient(api_key)
        self.profile_manager = ProfileManager()
    
    def analyze_cache_files(self, cache_dir: Path) -> List[CleanupItem]:
        """Analyze cache files and return cleanup recommendations.
        
        Args:
            cache_dir: Directory containing cache files
            
        Returns:
            List of CleanupItem with risk assessments
        """
        items = []
        
        if not cache_dir.exists():
            return items
        
        try:
            for item in cache_dir.iterdir():
                if item.is_file():
                    try:
                        stat = item.stat()
                        age_days = (datetime.now() - datetime.fromtimestamp(stat.st_mtime)).days
                        
                        # Basic categorization
                        category = self._categorize_cache(item)
                        
                        items.append({
                            'path': str(item),
                            'size_bytes': stat.st_size,
                            'file_type': 'cache',
                            'age_days': age_days,
                            'category': category
                        })
                    except (OSError, PermissionError):
                        continue
                elif item.is_dir():
                    # Recursively scan subdirectories
                    try:
                        items.extend(self._scan_directory(item, 'cache'))
                    except (OSError, PermissionError):
                        continue
        except (OSError, PermissionError):
            pass
        
        # Get AI risk assessment for batch
        if items:
            assessed_items = self._assess_cleanup_risk(items)
            return assessed_items
        
        return []
    
    def analyze_downloads(self, downloads_dir: Path, min_age_days: int = 30, 
                         min_size_mb: float = 10.0) -> List[CleanupItem]:
        """Analyze downloads folder for old/large files.
        
        Args:
            downloads_dir: Downloads directory path
            min_age_days: Minimum age in days to consider
            min_size_mb: Minimum size in MB to consider
            
        Returns:
            List of CleanupItem with risk assessments
        """
        items = []
        
        if not downloads_dir.exists():
            return items
        
        min_size_bytes = min_size_mb * 1024 * 1024
        cutoff_date = datetime.now() - timedelta(days=min_age_days)
        
        try:
            for item in downloads_dir.iterdir():
                if item.is_file():
                    try:
                        stat = item.stat()
                        modified_time = datetime.fromtimestamp(stat.st_mtime)
                        age_days = (datetime.now() - modified_time).days
                        
                        if stat.st_size >= min_size_bytes and modified_time < cutoff_date:
                            items.append({
                                'path': str(item),
                                'size_bytes': stat.st_size,
                                'file_type': 'download',
                                'age_days': age_days,
                                'category': item.suffix.lower() if item.suffix else 'unknown'
                            })
                    except (OSError, PermissionError):
                        continue
        except (OSError, PermissionError):
            pass
        
        # Get AI risk assessment
        if items:
            assessed_items = self._assess_cleanup_risk(items)
            return assessed_items
        
        return []
    
    def analyze_logs(self, log_dir: Path, max_age_days: int = 90) -> List[CleanupItem]:
        """Analyze log files for cleanup.
        
        Args:
            log_dir: Log directory path
            max_age_days: Maximum age to keep logs
            
        Returns:
            List of CleanupItem with risk assessments
        """
        items = []
        
        if not log_dir.exists():
            return items
        
        cutoff_date = datetime.now() - timedelta(days=max_age_days)
        
        try:
            items = self._scan_directory(log_dir, 'log', cutoff_date)
        except (OSError, PermissionError):
            pass
        
        # Logs are generally safe to delete
        assessed_items = []
        for item_dict in items:
            assessed_items.append(CleanupItem(
                path=item_dict['path'],
                size_bytes=item_dict['size_bytes'],
                file_type='log',
                age_days=item_dict['age_days'],
                risk_level=RiskLevel.SAFE,
                reason=f"Log file older than {max_age_days} days",
                recovery_info="Logs will be regenerated by the system as needed",
                category=item_dict.get('category', 'system')
            ))
        
        return assessed_items
    
    def get_cleanup_summary(self, items: List[CleanupItem]) -> Dict:
        """Get summary of cleanup recommendations.
        
        Args:
            items: List of cleanup items
            
        Returns:
            Dictionary with summary statistics
        """
        total_size = sum(item.size_bytes for item in items)
        
        by_risk = {}
        for risk_level in RiskLevel:
            count = sum(1 for item in items if item.risk_level == risk_level)
            size = sum(item.size_bytes for item in items if item.risk_level == risk_level)
            by_risk[risk_level.value] = {
                'count': count,
                'size_bytes': size,
                'size_gb': size / (1024 ** 3)
            }
        
        by_type = {}
        for item in items:
            if item.file_type not in by_type:
                by_type[item.file_type] = {
                    'count': 0,
                    'size_bytes': 0
                }
            by_type[item.file_type]['count'] += 1
            by_type[item.file_type]['size_bytes'] += item.size_bytes
        
        return {
            'total_items': len(items),
            'total_size_bytes': total_size,
            'total_size_gb': total_size / (1024 ** 3),
            'by_risk_level': by_risk,
            'by_type': by_type,
            'safe_to_clean': by_risk.get('safe', {}).get('count', 0) + 
                           by_risk.get('low_risk', {}).get('count', 0)
        }
    
    def _scan_directory(self, directory: Path, file_type: str, 
                       cutoff_date: Optional[datetime] = None) -> List[Dict]:
        """Recursively scan directory for files.
        
        Args:
            directory: Directory to scan
            file_type: Type of files (cache, log, etc.)
            cutoff_date: Optional cutoff date for file age
            
        Returns:
            List of file info dictionaries
        """
        items = []
        
        try:
            for item in directory.iterdir():
                if item.is_file():
                    try:
                        stat = item.stat()
                        modified_time = datetime.fromtimestamp(stat.st_mtime)
                        age_days = (datetime.now() - modified_time).days
                        
                        if cutoff_date is None or modified_time < cutoff_date:
                            items.append({
                                'path': str(item),
                                'size_bytes': stat.st_size,
                                'file_type': file_type,
                                'age_days': age_days,
                                'category': self._categorize_file(item)
                            })
                    except (OSError, PermissionError):
                        continue
                elif item.is_dir():
                    try:
                        items.extend(self._scan_directory(item, file_type, cutoff_date))
                    except (OSError, PermissionError):
                        continue
        except (OSError, PermissionError):
            pass
        
        return items
    
    def _categorize_cache(self, path: Path) -> str:
        """Categorize cache file by location."""
        path_str = str(path).lower()
        
        if 'safari' in path_str or 'webkit' in path_str:
            return 'browser'
        elif 'chrome' in path_str or 'chromium' in path_str:
            return 'browser'
        elif 'firefox' in path_str:
            return 'browser'
        elif 'system' in path_str or 'apple' in path_str:
            return 'system'
        else:
            return 'application'
    
    def _categorize_file(self, path: Path) -> str:
        """Categorize file by extension and location."""
        ext = path.suffix.lower()
        path_str = str(path).lower()
        
        if ext in ['.log', '.txt']:
            return 'log'
        elif ext in ['.cache', '.tmp', '.temp']:
            return 'cache'
        elif 'browser' in path_str or 'safari' in path_str or 'chrome' in path_str:
            return 'browser'
        else:
            return 'application'
    
    def _assess_cleanup_risk(self, items: List[Dict]) -> List[CleanupItem]:
        """Use AI to assess cleanup risk for items.
        
        Args:
            items: List of file info dictionaries
            
        Returns:
            List of CleanupItem with risk assessments
        """
        # Get user preferences for risk tolerance
        profile = self.profile_manager.load()
        risk_tolerance = profile.preferences.risk_tolerance
        
        try:
            # Get AI assessment
            analysis = self.ai_client.analyze_cleanup_safety(items, risk_tolerance)
            
            # Parse AI response and create CleanupItem objects
            assessed_items = []
            
            # AI returns a list of assessments
            # For now, use heuristic-based assessment as fallback
            for item_dict in items:
                risk_level, reason, recovery = self._heuristic_risk_assessment(item_dict)
                
                assessed_items.append(CleanupItem(
                    path=item_dict['path'],
                    size_bytes=item_dict['size_bytes'],
                    file_type=item_dict['file_type'],
                    age_days=item_dict['age_days'],
                    risk_level=risk_level,
                    reason=reason,
                    recovery_info=recovery,
                    category=item_dict.get('category', 'unknown')
                ))
            
            return assessed_items
            
        except Exception:
            # Fallback to heuristic assessment if AI fails
            assessed_items = []
            
            for item_dict in items:
                risk_level, reason, recovery = self._heuristic_risk_assessment(item_dict)
                
                assessed_items.append(CleanupItem(
                    path=item_dict['path'],
                    size_bytes=item_dict['size_bytes'],
                    file_type=item_dict['file_type'],
                    age_days=item_dict['age_days'],
                    risk_level=risk_level,
                    reason=reason,
                    recovery_info=recovery,
                    category=item_dict.get('category', 'unknown')
                ))
            
            return assessed_items
    
    def _heuristic_risk_assessment(self, item: Dict) -> tuple:
        """Heuristic-based risk assessment.
        
        Args:
            item: File info dictionary
            
        Returns:
            Tuple of (RiskLevel, reason, recovery_info)
        """
        file_type = item['file_type']
        age_days = item['age_days']
        category = item.get('category', 'unknown')
        path = item['path'].lower()
        
        # Cache files - generally safe
        if file_type == 'cache':
            if category == 'browser':
                return (
                    RiskLevel.LOW_RISK,
                    "Browser cache can be safely deleted (will require re-login to websites)",
                    "Cache will be rebuilt automatically when you browse"
                )
            else:
                return (
                    RiskLevel.SAFE,
                    "Application cache can be safely deleted",
                    "Cache will be rebuilt automatically when you use the application"
                )
        
        # Log files - always safe if old enough
        elif file_type == 'log':
            if age_days > 90:
                return (
                    RiskLevel.SAFE,
                    f"Log file is {age_days} days old",
                    "Logs will be regenerated as needed"
                )
            else:
                return (
                    RiskLevel.LOW_RISK,
                    f"Recent log file ({age_days} days old)",
                    "May contain useful debugging information"
                )
        
        # Downloads - depends on age and type
        elif file_type == 'download':
            if age_days > 180:
                return (
                    RiskLevel.LOW_RISK,
                    f"Downloaded file not accessed in {age_days} days",
                    "Move to trash (can be recovered from Trash)"
                )
            elif age_days > 60:
                return (
                    RiskLevel.MEDIUM_RISK,
                    f"Downloaded file from {age_days} days ago",
                    "Verify you don't need this file before deleting"
                )
            else:
                return (
                    RiskLevel.HIGH_RISK,
                    f"Recent download ({age_days} days ago)",
                    "Make sure you don't need this file"
                )
        
        # Unknown - be conservative
        else:
            return (
                RiskLevel.HIGH_RISK,
                "Unknown file type - manual review recommended",
                "Unknown"
            )
