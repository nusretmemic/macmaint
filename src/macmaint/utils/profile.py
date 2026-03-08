"""User profile system for personalized recommendations and learning."""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field, asdict


@dataclass
class UsagePattern:
    """Track user behavior patterns."""
    most_common_issues: List[str] = field(default_factory=list)
    frequently_ignored_issues: List[str] = field(default_factory=list)
    preferred_fix_times: List[str] = field(default_factory=list)  # e.g., ["morning", "evening"]
    cleanup_frequency: int = 0  # days between cleanups
    last_cleanup: Optional[str] = None
    total_scans: int = 0
    total_fixes: int = 0


@dataclass
class UserPreferences:
    """User preferences for analysis and recommendations."""
    risk_tolerance: str = "conservative"  # conservative, moderate, aggressive
    preferred_ai_role: str = "general"  # general, performance, security, storage, maintenance, troubleshooter
    auto_fix_safe_issues: bool = False
    show_technical_details: bool = False
    notification_level: str = "important"  # all, important, critical
    language_style: str = "friendly"  # friendly, technical, concise


@dataclass
class UserProfile:
    """Complete user profile with preferences and history."""
    version: str = "1.0"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_updated: str = field(default_factory=lambda: datetime.now().isoformat())
    
    # User preferences
    preferences: UserPreferences = field(default_factory=UserPreferences)
    
    # Learning data
    usage_patterns: UsagePattern = field(default_factory=UsagePattern)
    
    # Issue tracking
    ignored_issues: Set[str] = field(default_factory=set)  # issue IDs user chose to ignore
    fixed_issues: List[Dict] = field(default_factory=list)  # history of fixed issues
    recurring_issues: Dict[str, int] = field(default_factory=dict)  # issue type -> count
    
    # System context
    system_info: Dict = field(default_factory=dict)  # basic system info for context


class ProfileManager:
    """Manages user profile loading, saving, and updates."""
    
    def __init__(self, profile_path: Optional[Path] = None):
        """Initialize profile manager.
        
        Args:
            profile_path: Path to profile file. Defaults to ~/.macmaint/profile.json
        """
        if profile_path is None:
            profile_path = Path.home() / ".macmaint" / "profile.json"
        
        self.profile_path = profile_path
        self.profile_path.parent.mkdir(parents=True, exist_ok=True)
        self._profile: Optional[UserProfile] = None
    
    def load(self) -> UserProfile:
        """Load user profile from disk, create default if doesn't exist.
        
        Returns:
            UserProfile instance
        """
        if self._profile is not None:
            return self._profile
        
        if self.profile_path.exists():
            try:
                with open(self.profile_path, 'r') as f:
                    data = json.load(f)
                
                # Convert dicts back to dataclasses
                preferences = UserPreferences(**data.get('preferences', {}))
                usage_patterns = UsagePattern(**data.get('usage_patterns', {}))
                
                # Convert ignored_issues list to set
                ignored_issues = set(data.get('ignored_issues', []))
                
                self._profile = UserProfile(
                    version=data.get('version', '1.0'),
                    created_at=data.get('created_at', datetime.now().isoformat()),
                    last_updated=data.get('last_updated', datetime.now().isoformat()),
                    preferences=preferences,
                    usage_patterns=usage_patterns,
                    ignored_issues=ignored_issues,
                    fixed_issues=data.get('fixed_issues', []),
                    recurring_issues=data.get('recurring_issues', {}),
                    system_info=data.get('system_info', {})
                )
            except Exception as e:
                print(f"Warning: Could not load profile, creating new one: {e}")
                self._profile = UserProfile()
        else:
            self._profile = UserProfile()
            self.save()  # Save default profile
        
        return self._profile
    
    def save(self) -> None:
        """Save user profile to disk."""
        if self._profile is None:
            return
        
        # Update timestamp
        self._profile.last_updated = datetime.now().isoformat()
        
        # Convert to dict
        data = asdict(self._profile)
        
        # Convert ignored_issues set to list for JSON serialization
        data['ignored_issues'] = list(self._profile.ignored_issues)
        
        # Save to file
        with open(self.profile_path, 'w') as f:
            json.dump(data, f, indent=2, default=str)
    
    def track_scan(self) -> None:
        """Track that a scan was performed."""
        profile = self.load()
        profile.usage_patterns.total_scans += 1
        self.save()
    
    def track_fix(self, issue_type: str, issue_details: Dict) -> None:
        """Track that an issue was fixed.
        
        Args:
            issue_type: Type of issue (e.g., "high_memory", "disk_space")
            issue_details: Details about the fix
        """
        profile = self.load()
        
        # Increment fix counter
        profile.usage_patterns.total_fixes += 1
        
        # Add to fixed issues history (keep last 100)
        profile.fixed_issues.append({
            'type': issue_type,
            'fixed_at': datetime.now().isoformat(),
            'details': issue_details
        })
        if len(profile.fixed_issues) > 100:
            profile.fixed_issues = profile.fixed_issues[-100:]
        
        # Track recurring issues
        if issue_type in profile.recurring_issues:
            profile.recurring_issues[issue_type] += 1
        else:
            profile.recurring_issues[issue_type] = 1
        
        # Update most common issues (top 5)
        sorted_issues = sorted(
            profile.recurring_issues.items(),
            key=lambda x: x[1],
            reverse=True
        )
        profile.usage_patterns.most_common_issues = [
            issue for issue, _ in sorted_issues[:5]
        ]
        
        self.save()
    
    def track_ignore(self, issue_id: str, issue_type: str) -> None:
        """Track that an issue was ignored by the user.
        
        Args:
            issue_id: Unique identifier for the issue
            issue_type: Type of issue
        """
        profile = self.load()
        
        # Add to ignored issues
        profile.ignored_issues.add(issue_id)
        
        # Track frequently ignored issue types (if ignored 3+ times)
        ignored_count = sum(1 for iid in profile.ignored_issues if issue_type in iid)
        if ignored_count >= 3 and issue_type not in profile.usage_patterns.frequently_ignored_issues:
            profile.usage_patterns.frequently_ignored_issues.append(issue_type)
        
        self.save()
    
    def track_cleanup(self) -> None:
        """Track that a cleanup was performed."""
        profile = self.load()
        
        # Update cleanup tracking
        if profile.usage_patterns.last_cleanup:
            last = datetime.fromisoformat(profile.usage_patterns.last_cleanup)
            now = datetime.now()
            days_since = (now - last).days
            
            # Update average cleanup frequency (moving average)
            if profile.usage_patterns.cleanup_frequency == 0:
                profile.usage_patterns.cleanup_frequency = days_since
            else:
                profile.usage_patterns.cleanup_frequency = int(
                    (profile.usage_patterns.cleanup_frequency + days_since) / 2
                )
        
        profile.usage_patterns.last_cleanup = datetime.now().isoformat()
        self.save()
    
    def is_ignored(self, issue_id: str) -> bool:
        """Check if an issue has been ignored by the user.
        
        Args:
            issue_id: Issue identifier
            
        Returns:
            True if issue should be ignored
        """
        profile = self.load()
        return issue_id in profile.ignored_issues
    
    def get_preferences(self) -> UserPreferences:
        """Get user preferences.
        
        Returns:
            UserPreferences instance
        """
        return self.load().preferences
    
    def update_preferences(self, **kwargs) -> None:
        """Update user preferences.
        
        Args:
            **kwargs: Preference key-value pairs to update
        """
        profile = self.load()
        for key, value in kwargs.items():
            if hasattr(profile.preferences, key):
                setattr(profile.preferences, key, value)
        self.save()
    
    def get_summary(self) -> Dict:
        """Get a summary of the user profile for AI context.
        
        Returns:
            Dictionary with profile summary
        """
        profile = self.load()
        
        return {
            'risk_tolerance': profile.preferences.risk_tolerance,
            'preferred_role': profile.preferences.preferred_ai_role,
            'total_scans': profile.usage_patterns.total_scans,
            'total_fixes': profile.usage_patterns.total_fixes,
            'most_common_issues': profile.usage_patterns.most_common_issues,
            'frequently_ignored_issues': profile.usage_patterns.frequently_ignored_issues,
            'cleanup_frequency_days': profile.usage_patterns.cleanup_frequency,
            'recurring_issues': profile.recurring_issues,
            'technical_level': 'technical' if profile.preferences.show_technical_details else 'general'
        }
