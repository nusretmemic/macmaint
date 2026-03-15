"""Configuration management for MacMaint."""
import os
from pathlib import Path
from typing import Dict, List, Optional
import yaml
from dotenv import load_dotenv


class Config:
    """Application configuration manager."""
    
    CONFIG_DIR = Path.home() / ".macmaint"
    CONFIG_FILE = CONFIG_DIR / "config.yaml"
    
    DEFAULT_CONFIG = {
        "api": {
            "provider": "openai",
            "api_key_env": "OPENAI_API_KEY",
            "model": "gpt-4-turbo",
            "anonymize_data": True,
        },
        "modules": {
            "disk": {
                "enabled": True,
                "cache_age_days": 30,
                "large_file_threshold_mb": 500,
                "scan_paths": [
                    "~/Library/Caches",
                    "/Library/Caches",
                    "/tmp",
                    "~/Library/Logs",
                    "/var/log",
                ],
                "exclude_paths": [
                    "~/Documents",
                    "~/Desktop",
                    "~/Pictures",
                    "~/Music",
                    "~/Movies",
                ],
            },
            "memory": {
                "enabled": True,
                "alert_threshold_percent": 85,
                "track_memory_leaks": True,
                "min_process_memory_mb": 100,
            },
            "cpu": {
                "enabled": True,
                "alert_threshold_percent": 80,
                "sample_duration_seconds": 5,
                "min_process_cpu_percent": 10,
            },
            "duplicates": {
                "enabled": True,
                "min_size_mb": 1,
                "max_workers": 4,
                "scan_paths": None,  # None = use defaults (Downloads, Documents, etc.)
            },
        },
        "safety": {
            "require_confirmation": True,
            "dry_run_default": False,
            "max_file_delete_count": 1000,
            "max_space_to_free_gb": 50,
        },
        "ui": {
            "colors": True,
            "verbose": False,
        },
    }
    
    def __init__(self):
        """Initialize configuration."""
        # Load environment variables from ~/.macmaint/.env
        env_file = self.CONFIG_DIR / ".env"
        if env_file.exists():
            load_dotenv(env_file)
        self._config: Dict = {}
        self._load_config()
    
    def _load_config(self):
        """Load configuration from file or use defaults."""
        if self.CONFIG_FILE.exists():
            try:
                with open(self.CONFIG_FILE, "r") as f:
                    self._config = yaml.safe_load(f) or {}
                # Merge with defaults for any missing keys
                self._config = self._deep_merge(self.DEFAULT_CONFIG.copy(), self._config)
            except Exception as e:
                print(f"Warning: Could not load config file: {e}")
                self._config = self.DEFAULT_CONFIG.copy()
        else:
            self._config = self.DEFAULT_CONFIG.copy()
    
    def _deep_merge(self, base: Dict, override: Dict) -> Dict:
        """Deep merge two dictionaries."""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result
    
    def save(self):
        """Save configuration to file."""
        self.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(self.CONFIG_FILE, "w") as f:
            yaml.dump(self._config, f, default_flow_style=False, sort_keys=False)
    
    def get(self, key: str, default=None):
        """Get configuration value by dot-notation key."""
        keys = key.split(".")
        value = self._config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
                if value is None:
                    return default
            else:
                return default
        return value
    
    def set(self, key: str, value):
        """Set configuration value by dot-notation key."""
        keys = key.split(".")
        config = self._config
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        config[keys[-1]] = value
    
    @property
    def api_key(self) -> Optional[str]:
        """Get API key from environment."""
        api_key_env = self.get("api.api_key_env", "OPENAI_API_KEY")
        return os.getenv(api_key_env)
    
    @property
    def model(self) -> str:
        """Get AI model name."""
        return os.getenv("MACMAINT_MODEL", self.get("api.model", "gpt-4-turbo"))
    
    @property
    def anonymize_data(self) -> bool:
        """Check if data should be anonymized."""
        return self.get("api.anonymize_data", True)
    
    @property
    def require_confirmation(self) -> bool:
        """Check if actions require confirmation."""
        return self.get("safety.require_confirmation", True)
    
    @property
    def verbose(self) -> bool:
        """Check if verbose mode is enabled."""
        debug = os.getenv("MACMAINT_DEBUG", "false").lower() == "true"
        return debug or self.get("ui.verbose", False)
    
    def get_module_config(self, module_name: str) -> Dict:
        """Get configuration for a specific module."""
        return self.get(f"modules.{module_name}", {})
    
    def is_module_enabled(self, module_name: str) -> bool:
        """Check if a module is enabled."""
        return self.get(f"modules.{module_name}.enabled", True)


# Global configuration instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = Config()
    return _config


def reset_config():
    """Reset the global configuration instance."""
    global _config
    _config = None
