"""Battery health monitoring module."""
from typing import Dict, List, Optional
import subprocess
import re
import psutil

from macmaint.modules.base import BaseModule
from macmaint.models.issue import Issue, IssueSeverity, IssueCategory, FixAction, ActionType
from macmaint.models.metrics import BatteryMetrics


class BatteryModule(BaseModule):
    """Battery health monitoring module (auto-hides on desktops)."""

    # Temperature thresholds (°C) — conservative / longevity-focused
    TEMP_WARM_C = 35.0
    TEMP_HOT_C = 40.0
    TEMP_CRITICAL_C = 50.0

    # Cycle / capacity thresholds
    CYCLE_HIGH = 800
    CYCLE_LIMIT = 1000           # typical Apple rated limit
    CAPACITY_DEGRADED_PCT = 80   # below this → battery_health_degraded
    DEGRADATION_RATE_THRESHOLD = 0.05  # % capacity loss per cycle → rapid_degradation

    # Time / age thresholds
    AGE_OLD_DAYS = 1460          # 4 years
    CHARGING_TIME_THRESHOLD = 0.90   # >90% of snapshots in last 7 days = always plugged in

    # Power draw
    HEAVY_DRAW_W = 20.0          # watts while discharging

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def collect_metrics(self) -> Optional[Dict]:
        """Collect battery metrics. Returns None if no battery present."""
        battery = psutil.sensors_battery()
        if battery is None:
            return None

        metrics = BatteryMetrics(
            is_present=True,
            percent=battery.percent,
            is_charging=battery.power_plugged,
            time_remaining=battery.secsleft // 60 if battery.secsleft and battery.secsleft > 0 else None,
        )

        # Layer 1: system_profiler (cycle count, health condition, max capacity %)
        sp_info = self._get_battery_details()
        if sp_info:
            metrics.cycle_count = sp_info.get('cycle_count', 0)
            metrics.max_capacity_percent = sp_info.get('max_capacity_percent', 100.0)
            metrics.health = sp_info.get('health', 'Unknown')

        # Layer 2: ioreg (temperature, voltage, amperage, mAh, charger details)
        ioreg_info = self._get_ioreg_battery_data()
        if ioreg_info:
            # Temperature
            raw_temp = ioreg_info.get('temperature_raw')
            if raw_temp is not None:
                metrics.temperature = raw_temp / 10.0

            # Electrical
            metrics.voltage_mv = ioreg_info.get('voltage_mv')
            metrics.amperage_ma = ioreg_info.get('amperage_ma')
            metrics.current_capacity_mah = ioreg_info.get('current_capacity_mah', 0)
            metrics.design_capacity_mah = ioreg_info.get('design_capacity_mah', 0)

            # Charger
            metrics.charger_connected = ioreg_info.get('charger_connected', battery.power_plugged)
            metrics.charger_wattage = ioreg_info.get('charger_wattage')
            metrics.charger_type = ioreg_info.get('charger_type', 'Unknown')

            # Identity
            metrics.battery_serial = ioreg_info.get('battery_serial')

            # Override cycle_count if ioreg has it and system_profiler didn't
            if not metrics.cycle_count and ioreg_info.get('cycle_count'):
                metrics.cycle_count = ioreg_info['cycle_count']

        # Derived fields
        metrics.charging_state = self._derive_charging_state(
            is_charging=battery.power_plugged,
            percent=battery.percent,
            charger_connected=metrics.charger_connected,
        )

        if metrics.temperature is not None:
            metrics.temperature_status = self._classify_temperature(metrics.temperature)
        else:
            metrics.temperature_status = 'unknown'

        if metrics.voltage_mv and metrics.amperage_ma is not None:
            metrics.current_power_draw_w = self._calculate_power_draw(
                metrics.voltage_mv, metrics.amperage_ma
            )

        return metrics.model_dump()

    def analyze(self, metrics: Dict, history_manager=None) -> List[Issue]:
        """Analyze battery metrics and detect issues.

        Args:
            metrics: Battery metrics dict (from collect_metrics)
            history_manager: Optional HistoryManager instance for history-based checks
        """
        if metrics is None:
            return []

        issues = []
        bm = BatteryMetrics(**metrics)

        # ------------------------------------------------------------------ #
        # 1. Temperature issues
        # ------------------------------------------------------------------ #
        if bm.temperature is not None:
            if bm.temperature >= self.TEMP_CRITICAL_C:
                issues.append(Issue(
                    id="battery_critical_temp",
                    title=f"Battery temperature critically high: {bm.temperature:.1f}°C",
                    description=(
                        f"Your battery is at {bm.temperature:.1f}°C — well above the safe operating "
                        f"range. Sustained heat above {self.TEMP_CRITICAL_C}°C accelerates chemical "
                        "degradation inside lithium-ion cells, permanently reducing capacity and "
                        "shortening battery lifespan. Stop charging immediately, move to a cool "
                        "environment, and let the device cool before resuming use."
                    ),
                    severity=IssueSeverity.CRITICAL,
                    category=IssueCategory.SYSTEM,
                    metrics={"temperature_c": bm.temperature, "temperature_status": bm.temperature_status},
                    fix_actions=[FixAction(
                        action_type=ActionType.MANUAL,
                        description="Disconnect charger and move device to a cooler location",
                        estimated_impact="Prevents further heat-induced capacity degradation",
                        safe=True,
                        requires_confirmation=False,
                    )],
                ))
            elif bm.temperature >= self.TEMP_HOT_C:
                issues.append(Issue(
                    id="battery_hot",
                    title=f"Battery temperature elevated: {bm.temperature:.1f}°C",
                    description=(
                        f"Your battery is running warm at {bm.temperature:.1f}°C "
                        f"(warning threshold: {self.TEMP_HOT_C}°C). "
                        "Prolonged operation above 40°C measurably accelerates lithium-ion degradation. "
                        "Common causes: charging while doing heavy work, direct sunlight, or blocked vents. "
                        "Consider pausing the charger or reducing workload."
                    ),
                    severity=IssueSeverity.WARNING,
                    category=IssueCategory.SYSTEM,
                    metrics={"temperature_c": bm.temperature, "temperature_status": bm.temperature_status},
                    fix_actions=[FixAction(
                        action_type=ActionType.MANUAL,
                        description="Reduce workload or disconnect charger to lower battery temperature",
                        estimated_impact="Reduces heat-induced degradation rate",
                        safe=True,
                        requires_confirmation=False,
                    )],
                ))
            elif bm.temperature >= self.TEMP_WARM_C:
                issues.append(Issue(
                    id="battery_warm",
                    title=f"Battery temperature slightly warm: {bm.temperature:.1f}°C",
                    description=(
                        f"Battery temperature is {bm.temperature:.1f}°C — within acceptable range but "
                        f"warmer than ideal (optimal: below {self.TEMP_WARM_C}°C). "
                        "No immediate action required, but monitoring is recommended if it keeps rising."
                    ),
                    severity=IssueSeverity.INFO,
                    category=IssueCategory.SYSTEM,
                    metrics={"temperature_c": bm.temperature, "temperature_status": bm.temperature_status},
                    fix_actions=[FixAction(
                        action_type=ActionType.MANUAL,
                        description="Monitor battery temperature and ensure adequate ventilation",
                        estimated_impact="Maintains battery health over time",
                        safe=True,
                        requires_confirmation=False,
                    )],
                ))

        # ------------------------------------------------------------------ #
        # 2. Battery health degraded (enhanced with education)
        # ------------------------------------------------------------------ #
        if bm.max_capacity_percent < self.CAPACITY_DEGRADED_PCT:
            severity = IssueSeverity.WARNING if bm.max_capacity_percent < 70 else IssueSeverity.INFO
            issues.append(Issue(
                id="battery_health_degraded",
                title=f"Battery capacity degraded to {bm.max_capacity_percent:.1f}%",
                description=(
                    f"Your battery now holds {bm.max_capacity_percent:.1f}% of its original capacity. "
                    "Lithium-ion batteries degrade naturally with each charge cycle — the more cycles "
                    "completed and the more heat experienced, the faster capacity drops. "
                    f"Apple considers batteries below 80% capacity eligible for service replacement. "
                    f"Current cycle count: {bm.cycle_count}."
                ),
                severity=severity,
                category=IssueCategory.SYSTEM,
                metrics={
                    "max_capacity_percent": bm.max_capacity_percent,
                    "cycle_count": bm.cycle_count,
                    "design_capacity_mah": bm.design_capacity_mah,
                    "current_capacity_mah": bm.current_capacity_mah,
                },
                fix_actions=[FixAction(
                    action_type=ActionType.MANUAL,
                    description="Consider scheduling a battery replacement with Apple or an authorised service provider",
                    estimated_impact="Restores full-day battery life",
                    safe=True,
                    requires_confirmation=False,
                )],
            ))

        # ------------------------------------------------------------------ #
        # 3. Battery needs service (health string check)
        # ------------------------------------------------------------------ #
        if bm.health and 'replace' in bm.health.lower():
            issues.append(Issue(
                id="battery_needs_service",
                title=f"Battery needs service: {bm.health}",
                description=(
                    f"Apple's diagnostics report your battery condition as '{bm.health}'. "
                    "This means the battery cannot reliably deliver the power your Mac needs "
                    "and should be serviced or replaced to restore normal performance and runtime."
                ),
                severity=IssueSeverity.WARNING,
                category=IssueCategory.SYSTEM,
                metrics={"health": bm.health, "max_capacity_percent": bm.max_capacity_percent},
                fix_actions=[FixAction(
                    action_type=ActionType.MANUAL,
                    description="Book a battery service appointment via Apple Support or System Information > Battery",
                    estimated_impact="Restores expected battery runtime and reliability",
                    safe=True,
                    requires_confirmation=False,
                )],
            ))

        # ------------------------------------------------------------------ #
        # 4. High cycle count (enhanced with education)
        # ------------------------------------------------------------------ #
        if bm.cycle_count > self.CYCLE_HIGH:
            severity = IssueSeverity.WARNING if bm.cycle_count > self.CYCLE_LIMIT else IssueSeverity.INFO
            issues.append(Issue(
                id="battery_high_cycles",
                title=f"High battery cycle count: {bm.cycle_count} cycles",
                description=(
                    f"Your battery has completed {bm.cycle_count} charge cycles "
                    f"(Apple rates this model for ~{self.CYCLE_LIMIT} cycles). "
                    "A charge cycle counts as consuming 100% of capacity, even across multiple partial "
                    "charges (e.g., two 50% charges = one cycle). Above 800 cycles you will typically "
                    "notice shorter runtimes; above 1000 cycles capacity can drop sharply. "
                    "Keeping charge between 20–80% significantly extends cycle life."
                ),
                severity=severity,
                category=IssueCategory.SYSTEM,
                metrics={"cycle_count": bm.cycle_count, "rated_limit": self.CYCLE_LIMIT, "health": bm.health},
                fix_actions=[FixAction(
                    action_type=ActionType.MANUAL,
                    description=(
                        "Enable Optimised Battery Charging in System Settings > Battery to slow future degradation. "
                        "Plan for a battery replacement if runtime has become noticeably shorter."
                    ),
                    estimated_impact="Slows future cycle accumulation; replacement restores full runtime",
                    safe=True,
                    requires_confirmation=False,
                )],
            ))

        # ------------------------------------------------------------------ #
        # 5. Battery old age
        # ------------------------------------------------------------------ #
        if bm.battery_age_days is not None and bm.battery_age_days > self.AGE_OLD_DAYS:
            years = bm.battery_age_days / 365
            issues.append(Issue(
                id="battery_old_age",
                title=f"Battery is over {years:.1f} years old",
                description=(
                    f"Your battery is approximately {years:.1f} years old ({bm.battery_age_days} days). "
                    "Lithium-ion batteries degrade over time regardless of cycle count — electrolyte "
                    "breakdown and electrode corrosion occur even during storage. "
                    "Batteries older than 4 years often show unpredictable behaviour such as sudden "
                    "shutdowns even at moderate charge levels."
                ),
                severity=IssueSeverity.INFO,
                category=IssueCategory.SYSTEM,
                metrics={"battery_age_days": bm.battery_age_days},
                fix_actions=[FixAction(
                    action_type=ActionType.MANUAL,
                    description="Consider a proactive battery replacement to avoid unexpected shutdowns",
                    estimated_impact="Prevents unpredictable battery behaviour",
                    safe=True,
                    requires_confirmation=False,
                )],
            ))

        # ------------------------------------------------------------------ #
        # 6. Heavy power draw while discharging
        # ------------------------------------------------------------------ #
        if (bm.current_power_draw_w is not None
                and bm.current_power_draw_w < -self.HEAVY_DRAW_W
                and not bm.is_charging):
            draw = abs(bm.current_power_draw_w)
            issues.append(Issue(
                id="battery_heavy_power_draw",
                title=f"Heavy battery power draw: {draw:.1f} W",
                description=(
                    f"Your Mac is consuming {draw:.1f} W from the battery "
                    f"(threshold: {self.HEAVY_DRAW_W} W). "
                    "High sustained draw reduces the effective runtime per charge and "
                    "can generate extra heat, both of which accelerate battery wear. "
                    "Common causes: GPU-intensive tasks, high screen brightness, or background processes."
                ),
                severity=IssueSeverity.WARNING,
                category=IssueCategory.SYSTEM,
                metrics={"power_draw_w": draw, "voltage_mv": bm.voltage_mv, "amperage_ma": bm.amperage_ma},
                fix_actions=[FixAction(
                    action_type=ActionType.MANUAL,
                    description=(
                        "Reduce screen brightness, close GPU-intensive apps, "
                        "or enable Low Power Mode in System Settings > Battery"
                    ),
                    estimated_impact="Extends battery runtime and reduces heat",
                    safe=True,
                    requires_confirmation=False,
                )],
            ))

        # ------------------------------------------------------------------ #
        # 7. Low power mode suggestion
        # ------------------------------------------------------------------ #
        if bm.percent < 20 and not bm.is_charging:
            issues.append(Issue(
                id="low_power_mode_suggested",
                title=f"Battery low ({bm.percent:.0f}%) — Low Power Mode recommended",
                description=(
                    f"Battery is at {bm.percent:.0f}% and not charging. "
                    "Low Power Mode reduces background activity, screen brightness, and CPU/GPU "
                    "performance to extend the remaining runtime. "
                    "Enable it in System Settings > Battery, or via Control Centre."
                ),
                severity=IssueSeverity.INFO,
                category=IssueCategory.SYSTEM,
                metrics={"percent": bm.percent},
                fix_actions=[FixAction(
                    action_type=ActionType.MANUAL,
                    description="Enable Low Power Mode via System Settings > Battery",
                    estimated_impact="Can extend remaining runtime by 20–40%",
                    safe=True,
                    requires_confirmation=False,
                )],
            ))

        # ------------------------------------------------------------------ #
        # 8 & 9. History-based checks (require history_manager)
        # ------------------------------------------------------------------ #
        if history_manager is not None:
            # Always-plugged-in check
            charging_pct = self._get_charging_time_stats(history_manager, days=7)
            if charging_pct is not None and charging_pct > self.CHARGING_TIME_THRESHOLD:
                issues.append(Issue(
                    id="battery_always_plugged_in",
                    title=f"Battery almost always plugged in ({charging_pct * 100:.0f}% of the time)",
                    description=(
                        f"Over the past 7 days your Mac was charging {charging_pct * 100:.0f}% of the time. "
                        "Keeping a lithium-ion battery at 100% charge for prolonged periods causes "
                        "'calendar ageing' — the high voltage stress permanently reduces capacity over months. "
                        "Aim to keep charge between 20–80% for maximum longevity. "
                        "Enable Optimised Battery Charging in System Settings > Battery to let macOS manage this automatically."
                    ),
                    severity=IssueSeverity.INFO,
                    category=IssueCategory.SYSTEM,
                    metrics={"charging_time_percent": round(charging_pct * 100, 1)},
                    fix_actions=[FixAction(
                        action_type=ActionType.MANUAL,
                        description="Enable Optimised Battery Charging in System Settings > Battery",
                        estimated_impact="Reduces high-voltage stress and extends battery lifespan",
                        safe=True,
                        requires_confirmation=False,
                    )],
                ))

            # Rapid degradation check
            degrad_rate = self._calculate_degradation_rate(history_manager)
            if degrad_rate is not None and degrad_rate > self.DEGRADATION_RATE_THRESHOLD:
                issues.append(Issue(
                    id="battery_rapid_degradation",
                    title=f"Battery degrading faster than expected ({degrad_rate:.3f}%/cycle)",
                    description=(
                        f"Your battery is losing approximately {degrad_rate:.3f}% of capacity per charge cycle "
                        f"(threshold: {self.DEGRADATION_RATE_THRESHOLD}%). "
                        "Rapid degradation is often caused by frequent charging in hot conditions, "
                        "charging to 100% routinely, or deep discharges to 0%. "
                        "At this rate your battery health may reach 80% sooner than expected."
                    ),
                    severity=IssueSeverity.WARNING,
                    category=IssueCategory.SYSTEM,
                    metrics={
                        "degradation_rate_per_cycle": round(degrad_rate, 4),
                        "threshold": self.DEGRADATION_RATE_THRESHOLD,
                    },
                    fix_actions=[FixAction(
                        action_type=ActionType.MANUAL,
                        description=(
                            "Avoid charging in warm environments, enable Optimised Battery Charging, "
                            "and keep charge between 20–80% where possible"
                        ),
                        estimated_impact="Slows capacity loss, extending useful battery life",
                        safe=True,
                        requires_confirmation=False,
                    )],
                ))

        return issues

    # ------------------------------------------------------------------
    # Private helpers — data collection
    # ------------------------------------------------------------------

    def _get_battery_details(self) -> Optional[Dict]:
        """Get detailed battery information using system_profiler (macOS)."""
        try:
            result = subprocess.run(
                ['system_profiler', 'SPPowerDataType'],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return None

            output = result.stdout
            details = {}

            for line in output.split('\n'):
                stripped = line.strip()
                if stripped.startswith('Cycle Count:'):
                    try:
                        details['cycle_count'] = int(stripped.split(':')[1].strip())
                    except (ValueError, IndexError):
                        pass
                elif stripped.startswith('Condition:'):
                    details['health'] = stripped.split(':', 1)[1].strip()
                elif stripped.startswith('Maximum Capacity:') and '%' in stripped:
                    try:
                        cap_str = stripped.split(':')[1].strip().replace('%', '')
                        details['max_capacity_percent'] = float(cap_str)
                    except (ValueError, IndexError):
                        pass

            # Estimate max_capacity_percent from health condition if not explicitly found
            if 'max_capacity_percent' not in details:
                health = details.get('health', '').lower()
                if 'normal' in health or 'good' in health:
                    details['max_capacity_percent'] = 100.0
                elif 'replace soon' in health:
                    details['max_capacity_percent'] = 80.0
                elif 'replace' in health or 'service' in health:
                    details['max_capacity_percent'] = 70.0

            return details if details else None

        except (subprocess.TimeoutExpired, subprocess.SubprocessError, Exception):
            return None

    def _get_ioreg_battery_data(self) -> Optional[Dict]:
        """Parse ioreg -rn AppleSmartBattery for rich battery telemetry."""
        try:
            result = subprocess.run(
                ['ioreg', '-rn', 'AppleSmartBattery'],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0 or not result.stdout:
                return None

            output = result.stdout
            data = {}

            def _parse_int(key: str) -> Optional[int]:
                m = re.search(rf'"{re.escape(key)}"\s*=\s*(-?\d+)', output)
                return int(m.group(1)) if m else None

            def _parse_str(key: str) -> Optional[str]:
                m = re.search(rf'"{re.escape(key)}"\s*=\s*"([^"]*)"', output)
                return m.group(1) if m else None

            def _parse_bool(key: str) -> Optional[bool]:
                m = re.search(rf'"{re.escape(key)}"\s*=\s*(Yes|No|True|False)', output, re.IGNORECASE)
                if m:
                    return m.group(1).lower() in ('yes', 'true')
                return None

            # Temperature (raw value, divide by 10 for °C)
            temp_raw = _parse_int('Temperature')
            if temp_raw is not None:
                data['temperature_raw'] = temp_raw

            # Electrical
            data['voltage_mv'] = _parse_int('Voltage') or _parse_int('AppleRawBatteryVoltage')
            data['amperage_ma'] = _parse_int('InstantAmperage') or _parse_int('Amperage')

            # Capacity
            data['current_capacity_mah'] = _parse_int('CurrentCapacity') or _parse_int('AppleRawCurrentCapacity') or 0
            design_cap = _parse_int('DesignCapacity')
            if design_cap:
                data['design_capacity_mah'] = design_cap

            # Cycle count
            cycle = _parse_int('CycleCount')
            if cycle is not None:
                data['cycle_count'] = cycle

            # Charging states
            is_charging = _parse_bool('IsCharging')
            external = _parse_bool('ExternalConnected')
            data['charger_connected'] = bool(external)

            # Adapter / charger details — lives inside an AdapterDetails dict block
            adapter_block_m = re.search(r'"AdapterDetails"\s*=\s*\{([^}]*)\}', output, re.DOTALL)
            if adapter_block_m:
                adapter_block = adapter_block_m.group(1)
                watts_m = re.search(r'"Watts"\s*=\s*(\d+)', adapter_block)
                if watts_m:
                    data['charger_wattage'] = int(watts_m.group(1))
                desc_m = re.search(r'"Description"\s*=\s*"([^"]*)"', adapter_block)
                if desc_m:
                    desc_lower = desc_m.group(1).lower()
                    if 'pd' in desc_lower or 'usb-c' in desc_lower or 'usbc' in desc_lower:
                        data['charger_type'] = 'USB-C PD'
                    elif data.get('charger_wattage') in (45, 60, 85, 87, 96, 140):
                        data['charger_type'] = 'MagSafe'
                    else:
                        data['charger_type'] = desc_m.group(1)
                else:
                    # Infer from wattage alone
                    watt = data.get('charger_wattage')
                    if watt in (45, 60, 85, 87, 96, 140):
                        data['charger_type'] = 'MagSafe'
                    elif watt:
                        data['charger_type'] = f'{watt}W'
                    else:
                        data['charger_type'] = 'Unknown'
            elif data.get('charger_connected'):
                data['charger_type'] = 'Unknown'

            # Battery serial
            serial = _parse_str('Serial')
            if serial:
                data['battery_serial'] = serial

            return data if data else None

        except (subprocess.TimeoutExpired, subprocess.SubprocessError, Exception):
            return None

    # ------------------------------------------------------------------
    # Private helpers — derived values
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_temperature(temp_c: float) -> str:
        """Return a human-readable temperature status string."""
        if temp_c >= BatteryModule.TEMP_CRITICAL_C:
            return 'critical'
        if temp_c >= BatteryModule.TEMP_HOT_C:
            return 'hot'
        if temp_c >= BatteryModule.TEMP_WARM_C:
            return 'warm'
        return 'normal'

    @staticmethod
    def _calculate_power_draw(voltage_mv: int, amperage_ma: int) -> float:
        """Calculate power draw in watts.

        Positive = charging in; negative = draining.
        """
        return (voltage_mv / 1000.0) * (amperage_ma / 1000.0)

    @staticmethod
    def _derive_charging_state(
        is_charging: bool,
        percent: float,
        charger_connected: bool,
    ) -> str:
        """Derive a human-readable charging state string."""
        if is_charging:
            return 'Charging'
        if charger_connected and percent >= 99:
            return 'Fully Charged'
        if charger_connected and not is_charging:
            return 'Not Charging'
        return 'Discharging'

    @staticmethod
    def _get_charging_time_stats(history_manager, days: int = 7) -> Optional[float]:
        """Return fraction of snapshots in the last *days* where battery was charging.

        Returns None if there are fewer than 2 snapshots (not enough data).
        """
        try:
            snapshots = history_manager.get_snapshots(days=days)
            if len(snapshots) < 2:
                return None
            charging_count = sum(
                1 for s in snapshots
                if s.get('metrics', {}).get('battery', {}).get('is_charging', False)
            )
            return charging_count / len(snapshots)
        except Exception:
            return None

    @staticmethod
    def _calculate_degradation_rate(history_manager) -> Optional[float]:
        """Return estimated capacity loss in % per cycle, computed from 365-day history.

        Returns None when there is insufficient data.
        """
        try:
            snapshots = history_manager.get_snapshots(days=365)
            # Filter to snapshots that have both cycle_count and max_capacity_percent
            valid = [
                s for s in snapshots
                if s.get('metrics', {}).get('battery', {}).get('cycle_count')
                and s['metrics']['battery'].get('max_capacity_percent') is not None
            ]
            if len(valid) < 2:
                return None

            # Sort chronologically
            valid.sort(key=lambda s: s.get('date', ''))

            oldest = valid[0]['metrics']['battery']
            newest = valid[-1]['metrics']['battery']

            cycle_delta = newest['cycle_count'] - oldest['cycle_count']
            if cycle_delta <= 0:
                return None

            capacity_drop = oldest['max_capacity_percent'] - newest['max_capacity_percent']
            return capacity_drop / cycle_delta
        except Exception:
            return None
