"""Data anonymization for privacy protection."""
import re
import hashlib
from pathlib import Path
from typing import Any, Dict
import getpass


class DataAnonymizer:
    """Anonymizes sensitive data before sending to AI."""
    
    def __init__(self):
        """Initialize anonymizer."""
        self.username = getpass.getuser()
        self.home_dir = str(Path.home())
    
    def anonymize_metrics(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """Anonymize system metrics.
        
        Args:
            metrics: Raw system metrics
        
        Returns:
            Anonymized metrics dictionary
        """
        # Deep copy to avoid modifying original
        import copy
        anonymized = copy.deepcopy(metrics)
        
        # Recursively anonymize all string values
        anonymized = self._anonymize_recursive(anonymized)
        
        return anonymized
    
    def _anonymize_recursive(self, obj: Any) -> Any:
        """Recursively anonymize an object."""
        if isinstance(obj, dict):
            return {k: self._anonymize_recursive(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._anonymize_recursive(item) for item in obj]
        elif isinstance(obj, str):
            return self._anonymize_string(obj)
        else:
            return obj
    
    def _anonymize_string(self, text: str) -> str:
        """Anonymize sensitive information in a string."""
        # Replace username
        text = text.replace(self.username, "<USER>")
        
        # Replace home directory path
        text = text.replace(self.home_dir, "/Users/<USER>")
        
        # Replace /Users/anyname/ patterns
        text = re.sub(r'/Users/[^/]+/', '/Users/<USER>/', text)
        text = re.sub(r'~[^/]*/', '~/', text)
        
        # Remove UUIDs
        text = re.sub(
            r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
            '<UUID>',
            text,
            flags=re.IGNORECASE
        )
        
        # Remove MAC addresses
        text = re.sub(
            r'([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})',
            '<MAC>',
            text
        )
        
        # Remove IP addresses (keep for localhost)
        text = re.sub(
            r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b',
            '<IP>',
            text
        )
        # Restore localhost
        text = text.replace('<IP>', '127.0.0.1')
        
        # Remove serial numbers (common patterns)
        text = re.sub(r'\b[A-Z0-9]{10,}\b', '<SERIAL>', text)
        
        return text
    
    def _hash_identifier(self, identifier: str) -> str:
        """Create a consistent hash for an identifier."""
        return hashlib.md5(identifier.encode()).hexdigest()[:8]
