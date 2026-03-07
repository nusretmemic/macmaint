"""System utility functions."""
import os
import getpass
from pathlib import Path
from typing import List
from datetime import datetime
import psutil


def get_username() -> str:
    """Get the current username."""
    return getpass.getuser()


def get_home_dir() -> Path:
    """Get the user's home directory."""
    return Path.home()


def expand_path(path: str) -> Path:
    """Expand a path with ~ and environment variables."""
    return Path(os.path.expanduser(os.path.expandvars(path)))


def is_safe_path(path: Path, exclude_paths: List[str]) -> bool:
    """Check if a path is safe to modify (not in exclude list)."""
    path = path.resolve()
    
    # Check against exclude paths
    for exclude in exclude_paths:
        exclude_path = expand_path(exclude).resolve()
        try:
            # Check if path is under exclude_path
            path.relative_to(exclude_path)
            return False
        except ValueError:
            # Not under this exclude path, continue checking
            continue
    
    return True


def get_directory_size(path: Path) -> int:
    """Get total size of a directory in bytes."""
    total = 0
    try:
        for entry in path.rglob('*'):
            if entry.is_file():
                try:
                    total += entry.stat().st_size
                except (OSError, PermissionError):
                    pass
    except (OSError, PermissionError):
        pass
    return total


def get_file_age_days(path: Path) -> float:
    """Get age of file in days."""
    try:
        mtime = path.stat().st_mtime
        age_seconds = datetime.now().timestamp() - mtime
        return age_seconds / 86400  # Convert to days
    except (OSError, PermissionError):
        return 0


def bytes_to_gb(bytes: int) -> float:
    """Convert bytes to gigabytes."""
    return bytes / (1024 ** 3)


def get_boot_time() -> str:
    """Get system boot time."""
    boot_timestamp = psutil.boot_time()
    boot_time = datetime.fromtimestamp(boot_timestamp)
    return boot_time.strftime("%Y-%m-%d %H:%M:%S")


def get_uptime_hours() -> float:
    """Get system uptime in hours."""
    boot_timestamp = psutil.boot_time()
    uptime_seconds = datetime.now().timestamp() - boot_timestamp
    return uptime_seconds / 3600


def is_root() -> bool:
    """Check if running as root."""
    return os.geteuid() == 0


def safe_remove_file(path: Path, dry_run: bool = False) -> bool:
    """Safely remove a file."""
    try:
        if not path.exists():
            return False
        
        if dry_run:
            return True
        
        path.unlink()
        return True
    except (OSError, PermissionError) as e:
        return False


def safe_remove_directory(path: Path, dry_run: bool = False) -> bool:
    """Safely remove a directory and its contents."""
    try:
        if not path.exists():
            return False
        
        if dry_run:
            return True
        
        import shutil
        shutil.rmtree(path)
        return True
    except (OSError, PermissionError) as e:
        return False
