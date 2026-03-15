"""Unit tests for macmaint.utils.updater."""

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from macmaint.utils.updater import (
    _parse_version,
    _load_cache,
    _save_cache,
    _fetch_latest_release,
    check_for_updates,
    run_brew_upgrade,
)


# ---------------------------------------------------------------------------
# _parse_version
# ---------------------------------------------------------------------------

class TestParseVersion:
    def test_plain(self):
        assert _parse_version("1.2.3") == (1, 2, 3)

    def test_with_v_prefix(self):
        assert _parse_version("v0.9.4") == (0, 9, 4)

    def test_comparison(self):
        assert _parse_version("0.9.4") > _parse_version("0.9.3")
        assert _parse_version("1.0.0") > _parse_version("0.9.99")
        assert _parse_version("0.9.4") == _parse_version("0.9.4")


# ---------------------------------------------------------------------------
# _load_cache / _save_cache
# ---------------------------------------------------------------------------

class TestCache:
    def test_save_and_load_fresh(self, tmp_path):
        cache_file = tmp_path / "update_cache.json"
        with patch("macmaint.utils.updater.CACHE_FILE", cache_file):
            _save_cache("1.0.0", "https://example.com/releases/1.0.0")
            result = _load_cache()

        assert result is not None
        assert result["latest_version"] == "1.0.0"
        assert result["release_url"] == "https://example.com/releases/1.0.0"

    def test_stale_cache_returns_none(self, tmp_path):
        cache_file = tmp_path / "update_cache.json"
        stale_time = (datetime.now() - timedelta(hours=25)).isoformat()
        cache_file.write_text(json.dumps({
            "checked_at":    stale_time,
            "latest_version": "0.1.0",
            "release_url":    "https://example.com",
        }))
        with patch("macmaint.utils.updater.CACHE_FILE", cache_file):
            result = _load_cache()
        assert result is None

    def test_missing_cache_returns_none(self, tmp_path):
        cache_file = tmp_path / "no_such_file.json"
        with patch("macmaint.utils.updater.CACHE_FILE", cache_file):
            result = _load_cache()
        assert result is None

    def test_corrupt_cache_returns_none(self, tmp_path):
        cache_file = tmp_path / "update_cache.json"
        cache_file.write_text("not json {{")
        with patch("macmaint.utils.updater.CACHE_FILE", cache_file):
            result = _load_cache()
        assert result is None


# ---------------------------------------------------------------------------
# _fetch_latest_release
# ---------------------------------------------------------------------------

class TestFetchLatestRelease:
    def test_successful_fetch(self):
        mock_payload = json.dumps({
            "tag_name": "v1.2.3",
            "html_url": "https://github.com/nusretmemic/macmaint/releases/tag/v1.2.3",
        }).encode()

        mock_resp = MagicMock()
        mock_resp.read.return_value = mock_payload
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = _fetch_latest_release()

        assert result is not None
        assert result["latest_version"] == "1.2.3"
        assert "releases" in result["release_url"]

    def test_network_error_returns_none(self):
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("timeout")):
            result = _fetch_latest_release()
        assert result is None

    def test_missing_tag_returns_none(self):
        mock_payload = json.dumps({"html_url": "https://example.com"}).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = mock_payload
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = _fetch_latest_release()
        assert result is None


# ---------------------------------------------------------------------------
# check_for_updates
# ---------------------------------------------------------------------------

class TestCheckForUpdates:
    def test_update_available(self, tmp_path):
        cache_file = tmp_path / "update_cache.json"
        with patch("macmaint.utils.updater.CACHE_FILE", cache_file), \
             patch("macmaint.utils.updater.__version__", "0.9.0"), \
             patch("macmaint.utils.updater._fetch_latest_release", return_value={
                 "latest_version": "0.9.4",
                 "release_url": "https://example.com",
             }):
            result = check_for_updates(force=True)

        assert result["update_available"] is True
        assert result["current_version"] == "0.9.0"
        assert result["latest_version"] == "0.9.4"

    def test_already_up_to_date(self, tmp_path):
        cache_file = tmp_path / "update_cache.json"
        with patch("macmaint.utils.updater.CACHE_FILE", cache_file), \
             patch("macmaint.utils.updater.__version__", "0.9.4"), \
             patch("macmaint.utils.updater._fetch_latest_release", return_value={
                 "latest_version": "0.9.4",
                 "release_url": "https://example.com",
             }):
            result = check_for_updates(force=True)

        assert result["update_available"] is False

    def test_uses_cache_when_fresh(self, tmp_path):
        cache_file = tmp_path / "update_cache.json"
        cache_file.write_text(json.dumps({
            "checked_at":    datetime.now().isoformat(),
            "latest_version": "9.9.9",
            "release_url":    "https://example.com",
        }))
        with patch("macmaint.utils.updater.CACHE_FILE", cache_file), \
             patch("macmaint.utils.updater._fetch_latest_release") as mock_fetch:
            result = check_for_updates(force=False)

        mock_fetch.assert_not_called()
        assert result["from_cache"] is True
        assert result["latest_version"] == "9.9.9"

    def test_network_failure_sets_error(self, tmp_path):
        cache_file = tmp_path / "update_cache.json"
        with patch("macmaint.utils.updater.CACHE_FILE", cache_file), \
             patch("macmaint.utils.updater._fetch_latest_release", return_value=None):
            result = check_for_updates(force=True)

        assert result["error"] is not None
        assert result["latest_version"] is None


# ---------------------------------------------------------------------------
# run_brew_upgrade
# ---------------------------------------------------------------------------

class TestRunBrewUpgrade:
    def test_success(self):
        mock_proc = MagicMock(returncode=0, stdout="macmaint upgraded", stderr="")
        with patch("subprocess.run", return_value=mock_proc):
            result = run_brew_upgrade()
        assert result["success"] is True

    def test_already_up_to_date(self):
        mock_proc = MagicMock(returncode=1, stdout="", stderr="macmaint 0.9.4 already installed")
        with patch("subprocess.run", return_value=mock_proc):
            result = run_brew_upgrade()
        assert result["success"] is True

    def test_brew_not_found(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = run_brew_upgrade()
        assert result["success"] is False
        assert "brew not found" in result["error"]

    def test_timeout(self):
        import subprocess
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("brew", 120)):
            result = run_brew_upgrade()
        assert result["success"] is False
        assert "timed out" in result["error"]

    def test_brew_error(self):
        mock_proc = MagicMock(returncode=1, stdout="", stderr="Error: some brew failure")
        with patch("subprocess.run", return_value=mock_proc):
            result = run_brew_upgrade()
        assert result["success"] is False
        assert result["error"] is not None
