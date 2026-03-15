"""Version check and update utilities for MacMaint.

Checks GitHub releases for a newer version and can trigger a Homebrew upgrade.
Results are cached for 24 hours so the network is not hit on every launch.
"""

from __future__ import annotations

import json
import subprocess
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple

from macmaint import __version__

# ── Constants ─────────────────────────────────────────────────────────────────

GITHUB_API_URL = "https://api.github.com/repos/nusretmemic/macmaint/releases/latest"
CACHE_FILE     = Path.home() / ".macmaint" / "update_cache.json"
CACHE_TTL_H    = 24   # hours


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_version(v: str) -> Tuple[int, ...]:
    """Return a tuple of ints from a version string, stripping any leading 'v'."""
    return tuple(int(x) for x in v.lstrip("v").split(".") if x.isdigit())


def _load_cache() -> Optional[dict]:
    """Return cached release data if it exists and is fresh, else None."""
    try:
        if not CACHE_FILE.exists():
            return None
        data = json.loads(CACHE_FILE.read_text())
        checked_at = datetime.fromisoformat(data["checked_at"])
        if datetime.now() - checked_at < timedelta(hours=CACHE_TTL_H):
            return data
    except Exception:
        pass
    return None


def _save_cache(latest_version: str, release_url: str) -> None:
    """Persist the latest release info to disk."""
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps({
            "checked_at":    datetime.now().isoformat(),
            "latest_version": latest_version,
            "release_url":    release_url,
        }))
    except Exception:
        pass


def _fetch_latest_release(timeout: int = 8) -> Optional[dict]:
    """Hit the GitHub API and return {'latest_version': str, 'release_url': str} or None."""
    try:
        req = urllib.request.Request(
            GITHUB_API_URL,
            headers={"Accept": "application/vnd.github+json", "User-Agent": f"macmaint/{__version__}"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode())
        tag = payload.get("tag_name", "").lstrip("v")
        url = payload.get("html_url", "")
        if tag:
            return {"latest_version": tag, "release_url": url}
    except urllib.error.HTTPError as e:
        if e.code == 404:
            # No GitHub Release published yet for this repo
            return None
        raise
    except Exception:
        pass
    return None


# ── Public API ────────────────────────────────────────────────────────────────

def check_for_updates(force: bool = False) -> dict:
    """Return version info dict.

    Keys:
        current_version  str   – installed version
        latest_version   str   – latest GitHub release (or None on failure)
        update_available bool  – True if latest > current
        release_url      str   – GitHub release page URL
        from_cache       bool  – True if data came from disk cache
        error            str   – set if the check failed

    Args:
        force: If True, bypass cache and always hit GitHub.
    """
    result: dict = {
        "current_version":  __version__,
        "latest_version":   None,
        "update_available": False,
        "release_url":      "",
        "from_cache":       False,
        "error":            None,
    }

    # Try cache first (unless forced)
    cached = None if force else _load_cache()
    if cached:
        result["latest_version"] = cached["latest_version"]
        result["release_url"]    = cached["release_url"]
        result["from_cache"]     = True
    else:
        fetched = _fetch_latest_release()
        if fetched is None:
            result["error"] = "Could not reach GitHub — check your internet connection."
            return result
        result["latest_version"] = fetched["latest_version"]
        result["release_url"]    = fetched["release_url"]
        _save_cache(fetched["latest_version"], fetched["release_url"])

    try:
        result["update_available"] = (
            _parse_version(result["latest_version"]) > _parse_version(result["current_version"])
        )
    except Exception:
        pass

    return result


def run_brew_upgrade() -> dict:
    """Run `brew upgrade macmaint` and return a result dict.

    Keys:
        success  bool
        output   str   – combined stdout/stderr
        error    str   – set on failure
    """
    try:
        proc = subprocess.run(
            ["brew", "upgrade", "macmaint"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = (proc.stdout + proc.stderr).strip()
        if proc.returncode == 0:
            return {"success": True, "output": output, "error": None}
        # returncode 1 with "already installed" means up-to-date
        if "already installed" in output.lower() or "already up-to-date" in output.lower():
            return {"success": True, "output": output, "error": None}
        return {"success": False, "output": output, "error": f"brew exited {proc.returncode}"}
    except FileNotFoundError:
        return {"success": False, "output": "", "error": "brew not found — is Homebrew installed?"}
    except subprocess.TimeoutExpired:
        return {"success": False, "output": "", "error": "brew upgrade timed out after 120 s"}
    except Exception as exc:
        return {"success": False, "output": "", "error": str(exc)}
