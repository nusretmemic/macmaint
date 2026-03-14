"""Unit tests for ToolExecutor."""

from unittest.mock import MagicMock, patch, PropertyMock

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
        assert len(TOOLS) == 11

    def test_all_have_function_name(self):
        names = {t["function"]["name"] for t in TOOLS}
        expected = {
            "scan_system", "fix_issues", "explain_issue", "clean_caches",
            "optimize_memory", "manage_startup_items", "get_disk_analysis",
            "get_system_status", "show_trends", "create_maintenance_plan",
            "delegate_to_sub_agent",
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
        assert result["success"] is True
        assert result["data"]["count"] == 0

    def test_list_after_scan(self, tool_executor):
        tool_executor.execute("scan_system", {})
        result = tool_executor.execute("manage_startup_items", {"action": "list"})
        assert result["success"] is True

    def test_disable_action(self, tool_executor):
        result = tool_executor.execute(
            "manage_startup_items", {"action": "disable", "item_ids": ["item1"]}
        )
        assert result["success"] is True


class TestCreateMaintenancePlan:
    def test_returns_plan_structure(self, tool_executor):
        result = tool_executor.execute("create_maintenance_plan", {})
        assert result["success"] is True
        data = result["data"]
        assert "daily" in data
        assert "weekly" in data
        assert "monthly" in data
