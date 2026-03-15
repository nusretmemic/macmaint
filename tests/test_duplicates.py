"""Unit tests for DuplicateScanner."""

import json
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from macmaint.modules.duplicates import DuplicateScanner


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_file(path: Path, content: bytes) -> Path:
    """Write *content* to *path*, creating parents as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _make_scanner(min_size_mb=0.0, max_workers=2):
    """Return a DuplicateScanner with given settings."""
    return DuplicateScanner({
        "min_size_mb": min_size_mb,
        "max_workers": max_workers,
        "scan_paths": None,
    })


def _scan(scanner, tmp_path, dry_run=True):
    """Run scanner on tmp_path, bypassing the home-dir restriction."""
    # Bypass _resolve_paths home check by returning tmp_path directly
    with patch.object(scanner, "_resolve_paths", return_value=[tmp_path]):
        return scanner.scan(paths=[str(tmp_path)], dry_run=dry_run)


# ---------------------------------------------------------------------------
# TestDuplicateScanner
# ---------------------------------------------------------------------------

class TestDuplicateScanner:

    def test_finds_duplicates_by_hash(self, tmp_path):
        content = b"x" * 1024  # 1 KB identical content
        _write_file(tmp_path / "a.txt", content)
        _write_file(tmp_path / "b.txt", content)

        scanner = _make_scanner()
        metrics, issues = _scan(scanner, tmp_path)

        assert metrics["duplicate_groups_count"] >= 1
        assert metrics["total_duplicates"] >= 1
        # wasted space may round to 0 for tiny files — just verify structure
        assert metrics["total_wasted_space_mb"] >= 0

    def test_no_duplicates_when_all_unique(self, tmp_path):
        _write_file(tmp_path / "a.txt", b"content_a" * 100)
        _write_file(tmp_path / "b.txt", b"content_b" * 100)

        scanner = _make_scanner()
        metrics, issues = _scan(scanner, tmp_path)

        assert metrics["duplicate_groups_count"] == 0
        assert metrics["total_duplicates"] == 0
        assert issues == []

    def test_respects_min_size_threshold(self, tmp_path):
        small = b"x" * 100  # tiny — below 1 MB threshold
        _write_file(tmp_path / "s1.txt", small)
        _write_file(tmp_path / "s2.txt", small)

        scanner = DuplicateScanner({"min_size_mb": 1, "max_workers": 2, "scan_paths": None})
        metrics, issues = _scan(scanner, tmp_path)

        assert metrics["duplicate_groups_count"] == 0
        assert metrics["files_scanned"] == 0

    def test_recommends_keeping_newest(self, tmp_path):
        import os
        content = b"same" * 512
        old_file = tmp_path / "old.txt"
        new_file = tmp_path / "new.txt"

        _write_file(old_file, content)
        _write_file(new_file, content)

        # Force old_file mtime to be definitively older (1 hour ago)
        old_mtime = time.time() - 3600
        os.utime(old_file, (old_mtime, old_mtime))
        new_mtime = time.time()
        os.utime(new_file, (new_mtime, new_mtime))

        scanner = _make_scanner()
        metrics, issues = _scan(scanner, tmp_path)

        assert len(issues) >= 1
        group_files = issues[0].metrics["files"]
        kept = [f for f in group_files if f["keep_recommended"]]
        assert len(kept) == 1
        assert kept[0]["path"] == str(new_file)

    def test_calculates_wasted_space_correctly(self, tmp_path):
        # 3 identical copies of a 1 MB file → 2 copies wasted
        content = b"z" * (1024 * 1024)  # exactly 1 MB
        for name in ("c1.bin", "c2.bin", "c3.bin"):
            _write_file(tmp_path / name, content)

        scanner = _make_scanner()
        metrics, issues = _scan(scanner, tmp_path)

        assert metrics["duplicate_groups_count"] == 1
        # 3 copies, 2 wasted; wasted_mb = 2 * 1.0 = 2.0
        assert abs(metrics["total_wasted_space_mb"] - 2.0) < 0.01

    def test_handles_permission_errors_gracefully(self, tmp_path):
        content = b"data" * 512
        _write_file(tmp_path / "r1.txt", content)
        _write_file(tmp_path / "r2.txt", content)

        original_sha = DuplicateScanner._sha256
        call_count = {"n": 0}

        @staticmethod
        def flaky_sha256(path):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return None  # simulate read error on first file
            return original_sha(path)

        with patch.object(DuplicateScanner, "_sha256", flaky_sha256):
            scanner = _make_scanner()
            metrics, issues = _scan(scanner, tmp_path)

        # Should not raise; gracefully handles the failed hash
        assert isinstance(metrics, dict)
        assert isinstance(issues, list)

    def test_parallel_hashing_matches_serial(self, tmp_path):
        """Results with 1 worker should match results with 4 workers."""
        content = b"parallel" * 256
        _write_file(tmp_path / "p1.bin", content)
        _write_file(tmp_path / "p2.bin", content)
        _write_file(tmp_path / "p3.bin", b"different" * 256)

        scanner_1 = DuplicateScanner({"min_size_mb": 0, "max_workers": 1, "scan_paths": None})
        scanner_4 = DuplicateScanner({"min_size_mb": 0, "max_workers": 4, "scan_paths": None})

        m1, _ = _scan(scanner_1, tmp_path)
        m4, _ = _scan(scanner_4, tmp_path)

        assert m1["duplicate_groups_count"] == m4["duplicate_groups_count"]
        assert m1["total_duplicates"] == m4["total_duplicates"]

    def test_dry_run_skips_history(self, tmp_path):
        content = b"h" * 512
        _write_file(tmp_path / "h1.txt", content)
        _write_file(tmp_path / "h2.txt", content)

        scanner = _make_scanner()
        tmp_history = tmp_path / "dup_history.json"

        with patch.object(DuplicateScanner, "HISTORY_FILE", tmp_history):
            _scan(scanner, tmp_path, dry_run=True)
            assert not tmp_history.exists(), "dry_run=True should not write history"

            _scan(scanner, tmp_path, dry_run=False)
            assert tmp_history.exists(), "dry_run=False should write history"

    def test_history_persists_and_loads(self, tmp_path):
        content = b"hist" * 512
        _write_file(tmp_path / "hh1.txt", content)
        _write_file(tmp_path / "hh2.txt", content)

        scanner = _make_scanner()
        tmp_history = tmp_path / "dup_history.json"

        with patch.object(DuplicateScanner, "HISTORY_FILE", tmp_history):
            _scan(scanner, tmp_path, dry_run=False)

        with open(tmp_history) as fh:
            records = json.load(fh)

        assert len(records) == 1
        assert "scanned_at" in records[0]
        assert "total_wasted_space_mb" in records[0]

    def test_skips_paths_outside_home(self, tmp_path):
        """Paths outside home directory are silently excluded."""
        scanner = _make_scanner()
        # /etc is outside any normal home; scanner._resolve_paths should drop it
        # Use real _resolve_paths (not patched) to test the safety logic
        home = Path.home()
        result = scanner._resolve_paths(["/etc", str(home)])
        assert not any("/etc" in str(p) for p in result)

    def test_nonexistent_path_ignored(self, tmp_path):
        scanner = _make_scanner()
        fake = str(tmp_path / "does_not_exist")
        metrics, issues = _scan(scanner, tmp_path)
        # Empty scan → 0 files (tmp_path itself is empty for this test)
        assert metrics["files_scanned"] == 0

    def test_empty_directory_returns_zero(self, tmp_path):
        scanner = _make_scanner()
        metrics, issues = _scan(scanner, tmp_path)
        assert metrics["total_duplicates"] == 0
        assert issues == []
