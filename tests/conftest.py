"""Shared fixtures for MacMaint test suite."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from macmaint.config import Config
from macmaint.utils.profile import ProfileManager, UserProfile, UsagePattern


# ---------------------------------------------------------------------------
# Config fixture — uses a temp dir so tests never touch ~/.macmaint
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_macmaint_dir(tmp_path):
    """Isolated ~/.macmaint-equivalent directory."""
    return tmp_path


@pytest.fixture
def mock_config(tmp_macmaint_dir):
    """Minimal Config with an API key and temp directories."""
    cfg = MagicMock(spec=Config)
    cfg.api_key = "sk-test-key"
    cfg.verbose = False
    cfg.macmaint_dir = tmp_macmaint_dir
    return cfg


@pytest.fixture
def mock_profile_manager():
    """ProfileManager that returns a default UserProfile without disk I/O."""
    pm = MagicMock()
    profile = UserProfile()
    pm.load.return_value = profile
    pm.track_fixed_issue.return_value = None
    return pm
