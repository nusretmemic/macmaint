"""Startup items monitoring module."""
from typing import Dict, List
from pathlib import Path
import plistlib

from macmaint.modules.base import BaseModule
from macmaint.models.issue import Issue, IssueSeverity, IssueCategory
from macmaint.models.metrics import StartupMetrics


class StartupModule(BaseModule):
    """Startup items monitoring module (display only)."""
    
    def collect_metrics(self) -> Dict:
        """Collect startup items metrics."""
        metrics = StartupMetrics()
        
        # Scan login items (user-specific)
        login_items = self._scan_login_items()
        metrics.login_items = login_items
        metrics.login_items_count = len(login_items)
        
        # Scan launch agents (user and system)
        launch_agents = self._scan_launch_agents()
        metrics.launch_agents = launch_agents
        metrics.launch_agents_count = len(launch_agents)
        
        # Scan launch daemons (system-wide)
        launch_daemons = self._scan_launch_daemons()
        metrics.launch_daemons = launch_daemons
        metrics.launch_daemons_count = len(launch_daemons)
        
        return metrics.model_dump()
    
    def _scan_login_items(self) -> List[Dict[str, str]]:
        """Scan user login items."""
        items = []
        
        # Login items are in ~/Library/LaunchAgents
        user_launch_agents = Path.home() / 'Library/LaunchAgents'
        
        if user_launch_agents.exists():
            try:
                for plist_file in user_launch_agents.glob('*.plist'):
                    try:
                        with open(plist_file, 'rb') as f:
                            plist_data = plistlib.load(f)
                            
                            label = plist_data.get('Label', plist_file.stem)
                            disabled = plist_data.get('Disabled', False)
                            
                            items.append({
                                'name': label,
                                'path': str(plist_file),
                                'enabled': not disabled,
                                'type': 'login_item'
                            })
                    except (plistlib.InvalidFileException, Exception):
                        # Skip invalid plists
                        pass
            except (OSError, PermissionError):
                pass
        
        return items
    
    def _scan_launch_agents(self) -> List[Dict[str, str]]:
        """Scan launch agents (user and system)."""
        items = []
        
        # Paths to check for launch agents
        agent_paths = [
            Path.home() / 'Library/LaunchAgents',
            Path('/Library/LaunchAgents')
        ]
        
        for agent_path in agent_paths:
            if not agent_path.exists():
                continue
            
            try:
                for plist_file in agent_path.glob('*.plist'):
                    try:
                        with open(plist_file, 'rb') as f:
                            plist_data = plistlib.load(f)
                            
                            label = plist_data.get('Label', plist_file.stem)
                            disabled = plist_data.get('Disabled', False)
                            run_at_load = plist_data.get('RunAtLoad', False)
                            
                            scope = 'user' if str(agent_path).startswith(str(Path.home())) else 'system'
                            
                            items.append({
                                'name': label,
                                'path': str(plist_file),
                                'enabled': not disabled,
                                'run_at_load': run_at_load,
                                'scope': scope,
                                'type': 'launch_agent'
                            })
                    except (plistlib.InvalidFileException, Exception):
                        pass
            except (OSError, PermissionError):
                pass
        
        return items
    
    def _scan_launch_daemons(self) -> List[Dict[str, str]]:
        """Scan launch daemons (system-wide background services)."""
        items = []
        
        daemon_path = Path('/Library/LaunchDaemons')
        
        if not daemon_path.exists():
            return items
        
        try:
            for plist_file in daemon_path.glob('*.plist'):
                try:
                    with open(plist_file, 'rb') as f:
                        plist_data = plistlib.load(f)
                        
                        label = plist_data.get('Label', plist_file.stem)
                        disabled = plist_data.get('Disabled', False)
                        run_at_load = plist_data.get('RunAtLoad', False)
                        
                        items.append({
                            'name': label,
                            'path': str(plist_file),
                            'enabled': not disabled,
                            'run_at_load': run_at_load,
                            'type': 'launch_daemon'
                        })
                except (plistlib.InvalidFileException, Exception):
                    pass
        except (OSError, PermissionError):
            pass
        
        return items
    
    def analyze(self, metrics: Dict) -> List[Issue]:
        """Analyze startup items and provide information."""
        issues = []
        
        startup_metrics = StartupMetrics(**metrics)
        
        # Total startup items count
        total_items = (
            startup_metrics.login_items_count +
            startup_metrics.launch_agents_count +
            startup_metrics.launch_daemons_count
        )
        
        if total_items > 50:
            severity = IssueSeverity.WARNING if total_items > 100 else IssueSeverity.INFO
            issue = Issue(
                id="startup_many_items",
                title=f"High number of startup items: {total_items} total",
                description=f"Login items: {startup_metrics.login_items_count}, Launch agents: {startup_metrics.launch_agents_count}, Launch daemons: {startup_metrics.launch_daemons_count}",
                severity=severity,
                category=IssueCategory.SYSTEM,
                metrics={
                    "total_items": total_items,
                    "login_items_count": startup_metrics.login_items_count,
                    "launch_agents_count": startup_metrics.launch_agents_count,
                    "launch_daemons_count": startup_metrics.launch_daemons_count
                }
            )
            issues.append(issue)
        
        # Informational issue listing startup items
        if total_items > 0:
            issue = Issue(
                id="startup_items_list",
                title=f"System has {total_items} startup items",
                description="These items run automatically at login or system startup",
                severity=IssueSeverity.INFO,
                category=IssueCategory.SYSTEM,
                metrics={
                    "login_items": startup_metrics.login_items[:10],  # Show first 10
                    "launch_agents": startup_metrics.launch_agents[:10],
                    "launch_daemons": startup_metrics.launch_daemons[:10]
                }
            )
            issues.append(issue)
        
        return issues
