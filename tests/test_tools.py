"""Unit tests for ToolExecutor."""

from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock
import tempfile
import os

import pytest

from macmaint.assistant.tools import ToolExecutor, TOOLS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tool_executor(mock_config, mock_profile_manager):
    with (
        patch("macmaint.assistant.tools.Scanner") as MockScanner,
        patch("macmaint.assistant.tools.Fixer") as MockFixer,
        patch("macmaint.assistant.tools.HistoryManager") as MockHistory,
    ):
        scanner_instance = MockScanner.return_value
        fixer_instance = MockFixer.return_value
        history_instance = MockHistory.return_value

        # Default scan returns empty metrics + issues
        mock_metrics = MagicMock()
        mock_metrics.to_dict.return_value = {
            "disk": {"total_gb": 500, "used_gb": 200, "free_gb": 300, "percent_used": 40, "cache_breakdown": {}},
            "memory": {"available_gb": 8, "percent_used": 50},
            "cpu": {"cpu_percent": 20},
            "startup": {"items": []},
        }
        scanner_instance.scan.return_value = (mock_metrics, [])
        history_instance.get_snapshots.return_value = []
        history_instance.save_snapshot.return_value = None
        fixer_instance.fix_issues.return_value = {"succeeded": 0, "failed": 0, "skipped": 0}

        executor = ToolExecutor(mock_config, mock_profile_manager)
        # Expose the mocks for tests that need them
        executor._scanner_mock = scanner_instance
        executor._fixer_mock = fixer_instance
        executor._history_mock = history_instance
        executor._mock_metrics = mock_metrics
        yield executor


# ---------------------------------------------------------------------------
# TOOLS schema
# ---------------------------------------------------------------------------

class TestToolSchemas:
    def test_tool_count(self):
        assert len(TOOLS) == 12

    def test_all_have_function_name(self):
        names = {t["function"]["name"] for t in TOOLS}
        expected = {
            "scan_system", "fix_issues", "explain_issue", "clean_caches",
            "manage_startup_items", "get_disk_analysis",
            "get_system_status", "show_trends", "create_maintenance_plan",
            "delegate_to_sub_agent", "delete_files", "find_duplicates",
        }
        assert names == expected

    def test_each_tool_has_description(self):
        for tool in TOOLS:
            assert tool["function"]["description"]


# ---------------------------------------------------------------------------
# ToolExecutor.execute dispatch
# ---------------------------------------------------------------------------

class TestToolExecutorDispatch:
    def test_unknown_tool_returns_error(self, tool_executor):
        result = tool_executor.execute("nonexistent_tool", {})
        assert result["success"] is False
        assert "Unknown tool" in result["error"]

    def test_execute_wraps_exceptions(self, tool_executor):
        # Force _scan_system to raise
        tool_executor._scanner_mock.scan.side_effect = RuntimeError("boom")
        tool_executor._last_scan_results = None
        result = tool_executor.execute("scan_system", {})
        assert result["success"] is False
        assert "boom" in result["error"]


# ---------------------------------------------------------------------------
# Individual tools
# ---------------------------------------------------------------------------

class TestScanSystem:
    def test_returns_success(self, tool_executor):
        result = tool_executor.execute("scan_system", {})
        assert result["success"] is True
        assert "issues" in result["data"]
        assert "metrics" in result["data"]

    def test_caches_results_within_5_minutes(self, tool_executor):
        tool_executor.execute("scan_system", {})
        tool_executor.execute("scan_system", {})
        # Scanner.scan should only be called once due to caching
        assert tool_executor._scanner_mock.scan.call_count == 1

    def test_quick_flag_accepted(self, tool_executor):
        result = tool_executor.execute("scan_system", {"quick": True})
        assert result["success"] is True


class TestGetSystemStatus:
    def test_returns_status_dict(self, tool_executor):
        result = tool_executor.execute("get_system_status", {})
        assert result["success"] is True
        data = result["data"]
        assert "disk" in data
        assert "memory" in data
        assert "cpu" in data
        assert "overall_status" in data

    def test_critical_disk_flagged(self, tool_executor):
        tool_executor._mock_metrics.to_dict.return_value = {
            "disk": {"total_gb": 500, "used_gb": 470, "free_gb": 30, "percent_used": 95, "cache_breakdown": {}},
            "memory": {"available_gb": 8, "percent_used": 50},
            "cpu": {"cpu_percent": 20},
            "startup": {"items": []},
        }
        tool_executor._scanner_mock.scan.return_value = (tool_executor._mock_metrics, [])
        tool_executor._last_scan_results = None
        result = tool_executor.execute("get_system_status", {})
        assert result["data"]["disk"]["status"] == "critical"


class TestGetDiskAnalysis:
    def test_requires_prior_scan(self, tool_executor):
        tool_executor._last_scan_results = None
        result = tool_executor.execute("get_disk_analysis", {})
        assert result["success"] is False

    def test_returns_disk_breakdown_after_scan(self, tool_executor):
        tool_executor.execute("scan_system", {})
        result = tool_executor.execute("get_disk_analysis", {})
        assert result["success"] is True
        assert "total_gb" in result["data"]


class TestFixIssues:
    def test_requires_prior_scan(self, tool_executor):
        tool_executor._last_scan_results = None
        result = tool_executor.execute("fix_issues", {"issue_ids": ["some_id"]})
        assert result["success"] is False

    def test_no_matching_issues(self, tool_executor):
        tool_executor.execute("scan_system", {})
        result = tool_executor.execute("fix_issues", {"issue_ids": ["nonexistent"]})
        assert result["success"] is True
        assert "No matching" in result["summary"]


class TestShowTrends:
    def test_no_history_returns_gracefully(self, tool_executor):
        result = tool_executor.execute("show_trends", {"days": 7})
        assert result["success"] is True
        assert "No historical data" in result["summary"]

    def test_days_capped_at_30(self, tool_executor):
        tool_executor.execute("show_trends", {"days": 999})
        call_args = tool_executor._history_mock.get_snapshots.call_args
        assert call_args[0][0] <= 30


class TestCleanCaches:
    def test_returns_success(self, tool_executor):
        result = tool_executor.execute("clean_caches", {})
        assert result["success"] is True

    def test_accepts_categories(self, tool_executor):
        result = tool_executor.execute("clean_caches", {"categories": ["browser", "logs"]})
        assert result["success"] is True


class TestManageStartupItems:
    def test_list_without_scan(self, tool_executor):
        tool_executor._last_scan_results = None
        result = tool_executor.execute("manage_startup_items", {"action": "list"})
        # No scan → needs_scan signal returned (no success key at root)
        assert result.get("needs_scan") is True

    def test_list_after_scan(self, tool_executor):
        tool_executor.execute("scan_system", {})
        result = tool_executor.execute("manage_startup_items", {"action": "list"})
        assert result["success"] is True

    def test_disable_action(self, tool_executor):
        # Requires a prior scan; without one the tool returns needs_scan, not success
        tool_executor.execute("scan_system", {})
        result = tool_executor.execute(
            "manage_startup_items", {"action": "disable", "item_ids": ["nonexistent_item"]}
        )
        # Top-level response has 'data' key; success flag is per-item
        assert "data" in result
        assert result["data"]["action"] == "disable"


class TestCreateMaintenancePlan:
    def test_returns_plan_structure(self, tool_executor):
        result = tool_executor.execute("create_maintenance_plan", {})
        assert result["success"] is True
        data = result["data"]
        assert "daily" in data
        assert "weekly" in data
        assert "monthly" in data


class TestDeleteFiles:
    def test_deletes_file_in_home(self, tool_executor):
        with tempfile.NamedTemporaryFile(dir=Path.home(), delete=False, suffix=".dmg") as f:
            f.write(b"x" * 1024 * 1024)  # 1 MB so space_freed_mb rounds > 0
            tmp_path = f.name
        try:
            result = tool_executor.execute("delete_files", {"paths": [tmp_path]})
            assert result["success"] is True
            assert result["data"]["files_deleted"] == 1
            assert result["data"]["space_freed_mb"] > 0
            assert not Path(tmp_path).exists()
        finally:
            # Cleanup if test failed mid-way
            if Path(tmp_path).exists():
                os.unlink(tmp_path)

    def test_file_not_found_graceful(self, tool_executor):
        path = str(Path.home() / "nonexistent_macmaint_test_file_xyz.dmg")
        result = tool_executor.execute("delete_files", {"paths": [path]})
        assert result["success"] is True
        assert result["data"]["files_deleted"] == 0
        assert len(result["data"]["failed"]) == 1
        assert "not found" in result["data"]["failed"][0]["error"].lower()

    def test_refuses_path_outside_home(self, tool_executor):
        result = tool_executor.execute("delete_files", {"paths": ["/etc/hosts"]})
        assert result["success"] is True
        assert result["data"]["files_deleted"] == 0
        failed = result["data"]["failed"]
        assert len(failed) == 1
        assert "outside" in failed[0]["error"].lower()

    def test_refuses_directory(self, tool_executor):
        with tempfile.TemporaryDirectory(dir=Path.home()) as tmpdir:
            result = tool_executor.execute("delete_files", {"paths": [tmpdir]})
            assert result["success"] is True
            assert result["data"]["files_deleted"] == 0
            failed = result["data"]["failed"]
            assert len(failed) == 1
            assert "directory" in failed[0]["error"].lower()

    def test_partial_success(self, tool_executor):
        """One valid file + one nonexistent → 1 deleted, 1 failed."""
        with tempfile.NamedTemporaryFile(dir=Path.home(), delete=False, suffix=".tmp") as f:
            f.write(b"data")
            tmp_path = f.name
        try:
            missing = str(Path.home() / "does_not_exist_macmaint.tmp")
            result = tool_executor.execute("delete_files", {"paths": [tmp_path, missing]})
            assert result["success"] is True
            assert result["data"]["files_deleted"] == 1
            assert len(result["data"]["failed"]) == 1
        finally:
            if Path(tmp_path).exists():
                os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# TestFindDuplicates
# ---------------------------------------------------------------------------

class TestFindDuplicates:
    """Tests for the find_duplicates tool via ToolExecutor."""

    def test_no_duplicates_found(self, tool_executor, tmp_path):
        """Scanning an empty dir returns success with zero duplicates."""
        with patch("macmaint.modules.duplicates.DuplicateScanner") as MockDS:
            instance = MockDS.return_value
            instance.scan.return_value = (
                {
                    "total_duplicates": 0,
                    "duplicate_groups": [],
                    "duplicate_groups_count": 0,
                    "total_wasted_space_mb": 0.0,
                    "scan_duration_seconds": 0.1,
                    "files_scanned": 5,
                    "scan_paths": [str(tmp_path)],
                    "dry_run": True,
                },
                [],
            )
            result = tool_executor.execute(
                "find_duplicates",
                {"paths": [str(tmp_path)], "dry_run": True},
            )

        assert result["success"] is True
        assert result["data"]["total_duplicates"] == 0
        assert result["data"]["duplicate_groups_count"] == 0
        assert "No duplicates" in result["summary"]

    def test_finds_duplicate_files(self, tool_executor, tmp_path):
        """Returns correct counts and group summaries when duplicates exist."""
        fake_groups = [
            {
                "hash": "abcd1234abcd1234",
                "size_mb": 2.0,
                "count": 2,
                "wasted_mb": 2.0,
                "files": [
                    {"path": str(tmp_path / "new.bin"), "size_mb": 2.0,
                     "modified_date": "2026-03-15 10:00", "age_days": 0,
                     "keep_recommended": True},
                    {"path": str(tmp_path / "old.bin"), "size_mb": 2.0,
                     "modified_date": "2026-01-01 10:00", "age_days": 73,
                     "keep_recommended": False},
                ],
            }
        ]
        with patch("macmaint.modules.duplicates.DuplicateScanner") as MockDS:
            instance = MockDS.return_value
            instance.scan.return_value = (
                {
                    "total_duplicates": 1,
                    "duplicate_groups": fake_groups,
                    "duplicate_groups_count": 1,
                    "total_wasted_space_mb": 2.0,
                    "scan_duration_seconds": 0.5,
                    "files_scanned": 2,
                    "scan_paths": [str(tmp_path)],
                    "dry_run": False,
                },
                [],
            )
            result = tool_executor.execute("find_duplicates", {"paths": [str(tmp_path)]})

        assert result["success"] is True
        assert result["data"]["total_duplicates"] == 1
        assert result["data"]["total_wasted_space_mb"] == 2.0
        assert len(result["data"]["groups"]) == 1
        assert result["data"]["groups"][0]["copies"] == 2

    def test_dry_run_flag_passed_through(self, tool_executor, tmp_path):
        """dry_run=True is forwarded to DuplicateScanner.scan."""
        with patch("macmaint.modules.duplicates.DuplicateScanner") as MockDS:
            instance = MockDS.return_value
            instance.scan.return_value = (
                {
                    "total_duplicates": 0,
                    "duplicate_groups": [],
                    "duplicate_groups_count": 0,
                    "total_wasted_space_mb": 0.0,
                    "scan_duration_seconds": 0.0,
                    "files_scanned": 0,
                    "scan_paths": [],
                    "dry_run": True,
                },
                [],
            )
            tool_executor.execute("find_duplicates", {"dry_run": True})
            instance.scan.assert_called_once()
            _, call_kwargs = instance.scan.call_args
            assert call_kwargs.get("dry_run") is True

    def test_deep_scan_sets_home_path(self, tool_executor):
        """deep_scan=True passes the home directory as scan path."""
        with patch("macmaint.modules.duplicates.DuplicateScanner") as MockDS:
            instance = MockDS.return_value
            instance.scan.return_value = (
                {
                    "total_duplicates": 0,
                    "duplicate_groups": [],
                    "duplicate_groups_count": 0,
                    "total_wasted_space_mb": 0.0,
                    "scan_duration_seconds": 0.0,
                    "files_scanned": 0,
                    "scan_paths": [],
                    "dry_run": False,
                },
                [],
            )
            tool_executor.execute("find_duplicates", {"deep_scan": True})
            instance.scan.assert_called_once()
            _, call_kwargs = instance.scan.call_args
            passed_paths = call_kwargs.get("paths")
            assert passed_paths is not None
            assert str(Path.home()) in passed_paths
