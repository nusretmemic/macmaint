"""Unit tests for the BatteryModule (v0.7.0 enhancements)."""
import pytest
from unittest.mock import MagicMock, patch
from typing import Dict, List, Optional

from macmaint.modules.battery import BatteryModule
from macmaint.models.metrics import BatteryMetrics


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def make_battery_dict(**kwargs) -> Dict:
    """Return a BatteryMetrics.model_dump() with sensible defaults."""
    defaults = dict(
        is_present=True,
        percent=60.0,
        is_charging=False,
        time_remaining=90,
        cycle_count=200,
        max_capacity_percent=92.0,
        health='Normal',
        temperature=28.0,
        charging_state='Discharging',
        current_capacity_mah=3000,
        design_capacity_mah=5103,
        current_power_draw_w=-10.0,
        voltage_mv=12000,
        amperage_ma=-833,
        charger_connected=False,
        charger_wattage=None,
        charger_type='Unknown',
        battery_serial=None,
        manufacture_date=None,
        battery_age_days=None,
        temperature_status='normal',
    )
    defaults.update(kwargs)
    return BatteryMetrics(**defaults).model_dump()


def make_history_manager(snapshots: List[Dict]):
    """Return a mock HistoryManager that returns given snapshots for any days."""
    hm = MagicMock()
    hm.get_snapshots.return_value = snapshots
    return hm


def _snap(is_charging: bool, cycle: int = 200, capacity: float = 92.0, date: str = '2025-01-01') -> Dict:
    """Construct a minimal snapshot dict."""
    return {
        'date': date,
        'metrics': {
            'battery': {
                'is_charging': is_charging,
                'cycle_count': cycle,
                'max_capacity_percent': capacity,
            }
        }
    }


# ---------------------------------------------------------------------------
# _classify_temperature
# ---------------------------------------------------------------------------

class TestClassifyTemperature:
    def test_normal(self):
        assert BatteryModule._classify_temperature(30.0) == 'normal'

    def test_boundary_normal_warm(self):
        assert BatteryModule._classify_temperature(34.9) == 'normal'
        assert BatteryModule._classify_temperature(35.0) == 'warm'

    def test_warm(self):
        assert BatteryModule._classify_temperature(37.5) == 'warm'

    def test_boundary_warm_hot(self):
        assert BatteryModule._classify_temperature(39.9) == 'warm'
        assert BatteryModule._classify_temperature(40.0) == 'hot'

    def test_hot(self):
        assert BatteryModule._classify_temperature(45.0) == 'hot'

    def test_boundary_hot_critical(self):
        assert BatteryModule._classify_temperature(49.9) == 'hot'
        assert BatteryModule._classify_temperature(50.0) == 'critical'

    def test_critical(self):
        assert BatteryModule._classify_temperature(60.0) == 'critical'


# ---------------------------------------------------------------------------
# _calculate_power_draw
# ---------------------------------------------------------------------------

class TestCalculatePowerDraw:
    def test_discharging(self):
        # Negative amperage = discharging
        result = BatteryModule._calculate_power_draw(12000, -1000)
        assert result == pytest.approx(-12.0, rel=1e-3)

    def test_charging(self):
        result = BatteryModule._calculate_power_draw(12000, 2500)
        assert result == pytest.approx(30.0, rel=1e-3)

    def test_zero_amperage(self):
        result = BatteryModule._calculate_power_draw(12000, 0)
        assert result == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# _derive_charging_state
# ---------------------------------------------------------------------------

class TestDeriveChargingState:
    def test_charging(self):
        assert BatteryModule._derive_charging_state(True, 80.0, True) == 'Charging'

    def test_fully_charged(self):
        assert BatteryModule._derive_charging_state(False, 100.0, True) == 'Fully Charged'

    def test_not_charging_plugged(self):
        assert BatteryModule._derive_charging_state(False, 80.0, True) == 'Not Charging'

    def test_discharging(self):
        assert BatteryModule._derive_charging_state(False, 80.0, False) == 'Discharging'


# ---------------------------------------------------------------------------
# _get_charging_time_stats
# ---------------------------------------------------------------------------

class TestGetChargingTimeStats:
    def test_no_data_returns_none(self):
        hm = make_history_manager([])
        assert BatteryModule._get_charging_time_stats(hm) is None

    def test_single_snapshot_returns_none(self):
        hm = make_history_manager([_snap(True)])
        assert BatteryModule._get_charging_time_stats(hm) is None

    def test_all_charging(self):
        snaps = [_snap(True, date=f'2025-01-0{i}') for i in range(1, 8)]
        hm = make_history_manager(snaps)
        result = BatteryModule._get_charging_time_stats(hm)
        assert result == pytest.approx(1.0)

    def test_half_charging(self):
        snaps = (
            [_snap(True, date=f'2025-01-0{i}') for i in range(1, 5)] +
            [_snap(False, date=f'2025-01-0{i}') for i in range(5, 9)]
        )
        hm = make_history_manager(snaps)
        result = BatteryModule._get_charging_time_stats(hm)
        assert result == pytest.approx(0.5)

    def test_no_charging(self):
        snaps = [_snap(False, date=f'2025-01-0{i}') for i in range(1, 8)]
        hm = make_history_manager(snaps)
        result = BatteryModule._get_charging_time_stats(hm)
        assert result == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# _calculate_degradation_rate
# ---------------------------------------------------------------------------

class TestCalculateDegradationRate:
    def test_no_data_returns_none(self):
        hm = make_history_manager([])
        assert BatteryModule._calculate_degradation_rate(hm) is None

    def test_single_snapshot_returns_none(self):
        hm = make_history_manager([_snap(False, cycle=100, capacity=95.0)])
        assert BatteryModule._calculate_degradation_rate(hm) is None

    def test_zero_cycle_delta_returns_none(self):
        snaps = [
            _snap(False, cycle=200, capacity=92.0, date='2025-01-01'),
            _snap(False, cycle=200, capacity=91.0, date='2025-06-01'),
        ]
        hm = make_history_manager(snaps)
        assert BatteryModule._calculate_degradation_rate(hm) is None

    def test_normal_degradation(self):
        # 2% capacity drop over 40 cycles → 0.05% per cycle
        snaps = [
            _snap(False, cycle=200, capacity=94.0, date='2025-01-01'),
            _snap(False, cycle=240, capacity=92.0, date='2025-12-01'),
        ]
        hm = make_history_manager(snaps)
        result = BatteryModule._calculate_degradation_rate(hm)
        assert result == pytest.approx(0.05, rel=1e-3)

    def test_rapid_degradation(self):
        # 10% drop over 100 cycles → 0.10% per cycle
        snaps = [
            _snap(False, cycle=100, capacity=100.0, date='2025-01-01'),
            _snap(False, cycle=200, capacity=90.0, date='2025-12-01'),
        ]
        hm = make_history_manager(snaps)
        result = BatteryModule._calculate_degradation_rate(hm)
        assert result == pytest.approx(0.10, rel=1e-3)


# ---------------------------------------------------------------------------
# analyze() — temperature issues
# ---------------------------------------------------------------------------

class TestAnalyzeTemperature:
    def setup_method(self):
        self.module = BatteryModule({})

    def test_no_temp_issue_when_normal(self):
        m = make_battery_dict(temperature=28.0, temperature_status='normal')
        issues = self.module.analyze(m)
        ids = [i.id for i in issues]
        assert 'battery_warm' not in ids
        assert 'battery_hot' not in ids
        assert 'battery_critical_temp' not in ids

    def test_warm_issue(self):
        m = make_battery_dict(temperature=37.0, temperature_status='warm')
        issues = self.module.analyze(m)
        ids = [i.id for i in issues]
        assert 'battery_warm' in ids

    def test_hot_issue(self):
        m = make_battery_dict(temperature=44.0, temperature_status='hot')
        issues = self.module.analyze(m)
        ids = [i.id for i in issues]
        assert 'battery_hot' in ids
        assert 'battery_warm' not in ids

    def test_critical_temp_issue(self):
        m = make_battery_dict(temperature=55.0, temperature_status='critical')
        issues = self.module.analyze(m)
        ids = [i.id for i in issues]
        assert 'battery_critical_temp' in ids
        assert 'battery_hot' not in ids

    def test_no_temp_issue_when_temperature_none(self):
        m = make_battery_dict(temperature=None, temperature_status='unknown')
        issues = self.module.analyze(m)
        ids = [i.id for i in issues]
        assert 'battery_warm' not in ids
        assert 'battery_hot' not in ids
        assert 'battery_critical_temp' not in ids

    def test_critical_temp_severity(self):
        m = make_battery_dict(temperature=52.0, temperature_status='critical')
        issues = self.module.analyze(m)
        temp_issue = next(i for i in issues if i.id == 'battery_critical_temp')
        assert temp_issue.severity.value == 'critical'

    def test_hot_temp_severity(self):
        m = make_battery_dict(temperature=42.0, temperature_status='hot')
        issues = self.module.analyze(m)
        temp_issue = next(i for i in issues if i.id == 'battery_hot')
        assert temp_issue.severity.value == 'warning'

    def test_warm_temp_severity(self):
        m = make_battery_dict(temperature=36.0, temperature_status='warm')
        issues = self.module.analyze(m)
        temp_issue = next(i for i in issues if i.id == 'battery_warm')
        assert temp_issue.severity.value == 'info'


# ---------------------------------------------------------------------------
# analyze() — capacity & cycle count
# ---------------------------------------------------------------------------

class TestAnalyzeCapacityAndCycles:
    def setup_method(self):
        self.module = BatteryModule({})

    def test_no_health_issue_when_capacity_ok(self):
        m = make_battery_dict(max_capacity_percent=85.0)
        issues = self.module.analyze(m)
        assert not any(i.id == 'battery_health_degraded' for i in issues)

    def test_health_degraded_info_at_74pct(self):
        m = make_battery_dict(max_capacity_percent=74.0)
        issues = self.module.analyze(m)
        issue = next(i for i in issues if i.id == 'battery_health_degraded')
        assert issue.severity.value == 'info'

    def test_health_degraded_info_at_79pct(self):
        m = make_battery_dict(max_capacity_percent=79.0)
        issues = self.module.analyze(m)
        issue = next(i for i in issues if i.id == 'battery_health_degraded')
        assert issue.severity.value == 'info'

    def test_no_cycle_issue_when_low(self):
        m = make_battery_dict(cycle_count=400)
        issues = self.module.analyze(m)
        assert not any(i.id == 'battery_high_cycles' for i in issues)

    def test_cycle_issue_info_at_900(self):
        m = make_battery_dict(cycle_count=900)
        issues = self.module.analyze(m)
        issue = next(i for i in issues if i.id == 'battery_high_cycles')
        assert issue.severity.value == 'info'

    def test_cycle_issue_warning_above_1000(self):
        m = make_battery_dict(cycle_count=1050)
        issues = self.module.analyze(m)
        issue = next(i for i in issues if i.id == 'battery_high_cycles')
        assert issue.severity.value == 'warning'

    def test_battery_needs_service_replace_now(self):
        m = make_battery_dict(health='Replace Now', max_capacity_percent=65.0)
        issues = self.module.analyze(m)
        assert any(i.id == 'battery_needs_service' for i in issues)

    def test_battery_needs_service_replace_soon(self):
        m = make_battery_dict(health='Replace Soon', max_capacity_percent=78.0)
        issues = self.module.analyze(m)
        assert any(i.id == 'battery_needs_service' for i in issues)

    def test_no_service_issue_for_normal_health(self):
        m = make_battery_dict(health='Normal')
        issues = self.module.analyze(m)
        assert not any(i.id == 'battery_needs_service' for i in issues)


# ---------------------------------------------------------------------------
# analyze() — old age
# ---------------------------------------------------------------------------

class TestAnalyzeOldAge:
    def setup_method(self):
        self.module = BatteryModule({})

    def test_no_age_issue_when_young(self):
        m = make_battery_dict(battery_age_days=365)
        issues = self.module.analyze(m)
        assert not any(i.id == 'battery_old_age' for i in issues)

    def test_age_issue_when_old(self):
        m = make_battery_dict(battery_age_days=1500)
        issues = self.module.analyze(m)
        assert any(i.id == 'battery_old_age' for i in issues)

    def test_no_age_issue_when_age_none(self):
        m = make_battery_dict(battery_age_days=None)
        issues = self.module.analyze(m)
        assert not any(i.id == 'battery_old_age' for i in issues)


# ---------------------------------------------------------------------------
# analyze() — low power mode suggestion
# ---------------------------------------------------------------------------

class TestAnalyzeLowPowerMode:
    def setup_method(self):
        self.module = BatteryModule({})

    def test_low_power_suggested_when_below_20_not_charging(self):
        m = make_battery_dict(percent=15.0, is_charging=False)
        issues = self.module.analyze(m)
        assert any(i.id == 'low_power_mode_suggested' for i in issues)

    def test_no_low_power_when_charging(self):
        m = make_battery_dict(percent=15.0, is_charging=True)
        issues = self.module.analyze(m)
        assert not any(i.id == 'low_power_mode_suggested' for i in issues)

    def test_no_low_power_when_above_20(self):
        m = make_battery_dict(percent=50.0, is_charging=False)
        issues = self.module.analyze(m)
        assert not any(i.id == 'low_power_mode_suggested' for i in issues)

    def test_low_power_boundary_exactly_20(self):
        m = make_battery_dict(percent=20.0, is_charging=False)
        issues = self.module.analyze(m)
        # 20 is not < 20, so no issue
        assert not any(i.id == 'low_power_mode_suggested' for i in issues)

    def test_low_power_boundary_19(self):
        m = make_battery_dict(percent=19.9, is_charging=False)
        issues = self.module.analyze(m)
        assert any(i.id == 'low_power_mode_suggested' for i in issues)


# ---------------------------------------------------------------------------
# analyze() — heavy power draw
# ---------------------------------------------------------------------------

class TestAnalyzeHeavyPowerDraw:
    def setup_method(self):
        self.module = BatteryModule({})

    def test_heavy_draw_when_draining_over_20w(self):
        # current_power_draw_w < -20 while not charging
        m = make_battery_dict(
            percent=70.0,
            is_charging=False,
            current_power_draw_w=-25.0,
        )
        issues = self.module.analyze(m)
        assert any(i.id == 'battery_heavy_power_draw' for i in issues)

    def test_no_heavy_draw_when_charging(self):
        m = make_battery_dict(
            percent=70.0,
            is_charging=True,
            current_power_draw_w=-25.0,
        )
        issues = self.module.analyze(m)
        assert not any(i.id == 'battery_heavy_power_draw' for i in issues)

    def test_no_heavy_draw_under_threshold(self):
        m = make_battery_dict(
            percent=70.0,
            is_charging=False,
            current_power_draw_w=-15.0,
        )
        issues = self.module.analyze(m)
        assert not any(i.id == 'battery_heavy_power_draw' for i in issues)

    def test_no_heavy_draw_when_draw_is_none(self):
        m = make_battery_dict(
            percent=70.0,
            is_charging=False,
            current_power_draw_w=None,
        )
        issues = self.module.analyze(m)
        assert not any(i.id == 'battery_heavy_power_draw' for i in issues)


# ---------------------------------------------------------------------------
# analyze() — history-based: always plugged in
# ---------------------------------------------------------------------------

class TestAnalyzeAlwaysPluggedIn:
    def setup_method(self):
        self.module = BatteryModule({})

    def test_always_plugged_in_detected(self):
        # 7 snapshots all charging
        snaps = [_snap(True, date=f'2025-01-0{i}') for i in range(1, 8)]
        hm = make_history_manager(snaps)
        m = make_battery_dict()
        issues = self.module.analyze(m, history_manager=hm)
        assert any(i.id == 'battery_always_plugged_in' for i in issues)

    def test_not_always_plugged_in_when_50pct(self):
        snaps = (
            [_snap(True, date=f'2025-01-0{i}') for i in range(1, 5)] +
            [_snap(False, date=f'2025-01-0{i}') for i in range(5, 9)]
        )
        hm = make_history_manager(snaps)
        m = make_battery_dict()
        issues = self.module.analyze(m, history_manager=hm)
        assert not any(i.id == 'battery_always_plugged_in' for i in issues)

    def test_no_always_plugged_in_without_history_manager(self):
        m = make_battery_dict()
        issues = self.module.analyze(m)  # no history_manager
        assert not any(i.id == 'battery_always_plugged_in' for i in issues)

    def test_no_always_plugged_in_with_insufficient_data(self):
        hm = make_history_manager([_snap(True)])  # only 1 snapshot
        m = make_battery_dict()
        issues = self.module.analyze(m, history_manager=hm)
        assert not any(i.id == 'battery_always_plugged_in' for i in issues)


# ---------------------------------------------------------------------------
# analyze() — history-based: rapid degradation
# ---------------------------------------------------------------------------

class TestAnalyzeRapidDegradation:
    def setup_method(self):
        self.module = BatteryModule({})

    def test_rapid_degradation_detected(self):
        # 10% capacity drop over 100 cycles = 0.10% / cycle > threshold 0.05
        snaps = [
            _snap(False, cycle=100, capacity=100.0, date='2025-01-01'),
            _snap(False, cycle=200, capacity=90.0, date='2025-12-01'),
        ]
        hm = make_history_manager(snaps)
        m = make_battery_dict()
        issues = self.module.analyze(m, history_manager=hm)
        assert any(i.id == 'battery_rapid_degradation' for i in issues)

    def test_normal_degradation_not_flagged(self):
        # 2% drop over 100 cycles = 0.02% / cycle < threshold 0.05
        snaps = [
            _snap(False, cycle=100, capacity=94.0, date='2025-01-01'),
            _snap(False, cycle=200, capacity=92.0, date='2025-12-01'),
        ]
        hm = make_history_manager(snaps)
        m = make_battery_dict()
        issues = self.module.analyze(m, history_manager=hm)
        assert not any(i.id == 'battery_rapid_degradation' for i in issues)

    def test_no_rapid_degradation_without_history_manager(self):
        m = make_battery_dict()
        issues = self.module.analyze(m)
        assert not any(i.id == 'battery_rapid_degradation' for i in issues)


# ---------------------------------------------------------------------------
# analyze() — returns empty list for None metrics (no battery)
# ---------------------------------------------------------------------------

class TestAnalyzeNoBattery:
    def test_returns_empty_for_none(self):
        module = BatteryModule({})
        assert module.analyze(None) == []


# ---------------------------------------------------------------------------
# _get_ioreg_battery_data — mocked subprocess
# ---------------------------------------------------------------------------

SAMPLE_IOREG_OUTPUT = """
+-o AppleSmartBattery  <class AppleSmartBattery, id 0x10000015b, registered, matched, active, busy 0, retain 11>
    {
      "Temperature" = 3015
      "Voltage" = 12600
      "InstantAmperage" = -500
      "CurrentCapacity" = 3200
      "DesignCapacity" = 5103
      "CycleCount" = 155
      "IsCharging" = No
      "FullyCharged" = No
      "ExternalConnected" = No
      "Serial" = "F1A2B3C4"
      "AdapterDetails" = {"Watts"=60,"Description"="pd charger","IsWireless"=No}
    }
"""

SAMPLE_IOREG_CHARGING = """
+-o AppleSmartBattery  <class AppleSmartBattery, id 0x10000015b>
    {
      "Temperature" = 3200
      "Voltage" = 12800
      "InstantAmperage" = 4000
      "CurrentCapacity" = 4000
      "DesignCapacity" = 5103
      "CycleCount" = 155
      "IsCharging" = Yes
      "FullyCharged" = No
      "ExternalConnected" = Yes
      "Serial" = "F1A2B3C4"
      "AdapterDetails" = {"Watts"=140,"Description"="pd charger","IsWireless"=No}
    }
"""


class TestGetIoregBatteryData:
    def setup_method(self):
        self.module = BatteryModule({})

    def _run_with_output(self, output: str):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = output
        with patch('subprocess.run', return_value=mock_result):
            return self.module._get_ioreg_battery_data()

    def test_parses_temperature(self):
        data = self._run_with_output(SAMPLE_IOREG_OUTPUT)
        assert data['temperature_raw'] == 3015

    def test_parses_voltage(self):
        data = self._run_with_output(SAMPLE_IOREG_OUTPUT)
        assert data['voltage_mv'] == 12600

    def test_parses_amperage(self):
        data = self._run_with_output(SAMPLE_IOREG_OUTPUT)
        assert data['amperage_ma'] == -500

    def test_parses_current_capacity(self):
        data = self._run_with_output(SAMPLE_IOREG_OUTPUT)
        assert data['current_capacity_mah'] == 3200

    def test_parses_design_capacity(self):
        data = self._run_with_output(SAMPLE_IOREG_OUTPUT)
        assert data['design_capacity_mah'] == 5103

    def test_parses_cycle_count(self):
        data = self._run_with_output(SAMPLE_IOREG_OUTPUT)
        assert data['cycle_count'] == 155

    def test_charger_not_connected(self):
        data = self._run_with_output(SAMPLE_IOREG_OUTPUT)
        assert data['charger_connected'] is False

    def test_charger_connected_when_charging(self):
        data = self._run_with_output(SAMPLE_IOREG_CHARGING)
        assert data['charger_connected'] is True

    def test_adapter_wattage(self):
        data = self._run_with_output(SAMPLE_IOREG_OUTPUT)
        assert data['charger_wattage'] == 60

    def test_adapter_type_usbc_pd(self):
        data = self._run_with_output(SAMPLE_IOREG_OUTPUT)
        assert data['charger_type'] == 'USB-C PD'

    def test_adapter_wattage_140w(self):
        data = self._run_with_output(SAMPLE_IOREG_CHARGING)
        assert data['charger_wattage'] == 140

    def test_battery_serial(self):
        data = self._run_with_output(SAMPLE_IOREG_OUTPUT)
        assert data['battery_serial'] == 'F1A2B3C4'

    def test_returns_none_on_subprocess_failure(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ''
        with patch('subprocess.run', return_value=mock_result):
            result = self.module._get_ioreg_battery_data()
        assert result is None

    def test_returns_none_on_exception(self):
        with patch('subprocess.run', side_effect=Exception('fail')):
            result = self.module._get_ioreg_battery_data()
        assert result is None


# ---------------------------------------------------------------------------
# collect_metrics — no battery case
# ---------------------------------------------------------------------------

class TestCollectMetricsNoBattery:
    def test_returns_none_when_no_battery(self):
        module = BatteryModule({})
        with patch('psutil.sensors_battery', return_value=None):
            result = module.collect_metrics()
        assert result is None
