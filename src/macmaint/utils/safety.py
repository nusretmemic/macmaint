"""Safety checks and validation."""
from pathlib import Path
from typing import List
from macmaint.utils.system import expand_path


class SafetyChecker:
    """Safety checks for system modifications."""
    
    # System-critical paths that should never be modified
    PROTECTED_PATHS = [
        "/System",
        "/Library/Apple",
        "/bin",
        "/sbin",
        "/usr/bin",
        "/usr/sbin",
        "/private/var/db",
    ]
    
    # User paths that require explicit confirmation
    SENSITIVE_PATHS = [
        "~/Documents",
        "~/Desktop",
        "~/Pictures",
        "~/Music",
        "~/Movies",
        "~/Downloads",
    ]
    
    def __init__(self, exclude_paths: List[str] = None):
        """Initialize safety checker."""
        self.exclude_paths = exclude_paths or []
        self.exclude_paths.extend(self.SENSITIVE_PATHS)
    
    def is_safe_to_delete(self, path: Path) -> bool:
        """Check if a path is safe to delete."""
        path = path.resolve()
        
        # Check if it's a protected system path
        for protected in self.PROTECTED_PATHS:
            protected_path = Path(protected).resolve()
            try:
                path.relative_to(protected_path)
                return False  # Path is under protected directory
            except ValueError:
                continue
        
        return True
    
    def requires_confirmation(self, path: Path) -> bool:
        """Check if deleting this path requires user confirmation."""
        path = path.resolve()
        
        # Check if it's under a sensitive path
        for sensitive in self.SENSITIVE_PATHS:
            sensitive_path = expand_path(sensitive).resolve()
            try:
                path.relative_to(sensitive_path)
                return True  # Path is under sensitive directory
            except ValueError:
                continue
        
        return False
    
    def validate_file_list(self, files: List[Path], max_count: int = 1000) -> tuple[bool, str]:
        """Validate a list of files before deletion."""
        if len(files) > max_count:
            return False, f"Too many files to delete ({len(files)} > {max_count})"
        
        unsafe_files = []
        for file in files:
            if not self.is_safe_to_delete(file):
                unsafe_files.append(str(file))
        
        if unsafe_files:
            return False, f"Cannot delete protected files: {', '.join(unsafe_files[:5])}"
        
        return True, "OK"
    
    def validate_space_to_free(self, size_gb: float, max_size_gb: float = 50) -> tuple[bool, str]:
        """Validate the amount of space to free."""
        if size_gb > max_size_gb:
            return False, f"Attempting to free too much space ({size_gb:.1f} GB > {max_size_gb} GB)"
        
        return True, "OK"
