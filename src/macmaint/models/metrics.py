"""System metrics data models."""
from typing import Any, Dict, List, Optional
from enum import Enum
from pydantic import BaseModel, Field


class MemoryPressure(str, Enum):
    """Memory pressure levels."""
    NORMAL = "normal"
    WARNING = "warning"
    CRITICAL = "critical"


class CacheCategory(BaseModel):
    """Information about a cache category."""
    name: str
    path: str
    size_gb: float
    file_count: int
    percentage: float = 0.0


class DiskMetrics(BaseModel):
    """Disk space metrics."""
    total_gb: float
    used_gb: float
    free_gb: float
    percent_used: float
    cache_files: Dict[str, int] = Field(default_factory=dict)
    cache_size_gb: float = 0.0
    cache_breakdown: Dict[str, CacheCategory] = Field(default_factory=dict)
    log_files: Dict[str, int] = Field(default_factory=dict)
    log_size_gb: float = 0.0
    large_files: List[Dict[str, Any]] = Field(default_factory=list)
    temp_size_gb: float = 0.0


class ProcessInfo(BaseModel):
    """Information about a running process."""
    pid: int
    name: str
    cpu_percent: float = 0.0
    memory_mb: float = 0.0
    memory_percent: float = 0.0
    status: str = "unknown"
    category: Optional[str] = None  # system, application, background


class MemoryBreakdown(BaseModel):
    """Detailed memory breakdown (macOS specific)."""
    wired_gb: float = 0.0
    active_gb: float = 0.0
    inactive_gb: float = 0.0
    compressed_gb: float = 0.0
    pressure_level: MemoryPressure = MemoryPressure.NORMAL


class MemoryMetrics(BaseModel):
    """Memory usage metrics."""
    total_gb: float
    available_gb: float
    used_gb: float
    percent_used: float
    swap_total_gb: float = 0.0
    swap_used_gb: float = 0.0
    top_processes: List[ProcessInfo] = Field(default_factory=list)
    breakdown: Optional[MemoryBreakdown] = None
    processes_by_category: Dict[str, List[ProcessInfo]] = Field(default_factory=dict)


class CPUMetrics(BaseModel):
    """CPU usage metrics."""
    cpu_count: int
    cpu_percent: float
    load_average: List[float] = Field(default_factory=list)
    top_processes: List[ProcessInfo] = Field(default_factory=list)


class NetworkMetrics(BaseModel):
    """Network usage metrics."""
    bytes_sent: float
    bytes_recv: float
    bytes_sent_gb: float = 0.0
    bytes_recv_gb: float = 0.0
    connections_count: int = 0
    connections_by_state: Dict[str, int] = Field(default_factory=dict)
    error_in: int = 0
    error_out: int = 0
    drop_in: int = 0
    drop_out: int = 0
    bandwidth_samples: List[Dict[str, Any]] = Field(default_factory=list)  # For anomaly detection


class BatteryMetrics(BaseModel):
    """Battery health metrics."""
    is_present: bool
    percent: float = 0.0
    is_charging: bool = False
    time_remaining: Optional[int] = None  # minutes
    cycle_count: int = 0
    max_capacity_percent: float = 100.0
    health: str = "Unknown"
    temperature: Optional[float] = None  # Celsius

    # Charging state detail
    charging_state: str = "Unknown"  # Charging|Discharging|Fully Charged|Not Charging

    # Power metrics (from ioreg)
    current_capacity_mah: int = 0     # actual mAh right now
    design_capacity_mah: int = 0      # factory spec mAh
    current_power_draw_w: Optional[float] = None  # watts (positive = charging in, negative = draining)
    voltage_mv: Optional[int] = None  # millivolts
    amperage_ma: Optional[int] = None  # milliamps (signed; negative = discharging)

    # Charger info
    charger_connected: bool = False
    charger_wattage: Optional[int] = None
    charger_type: str = "Unknown"     # e.g. "USB-C PD", "MagSafe", "Unknown"

    # Battery identity / age
    battery_serial: Optional[str] = None
    manufacture_date: Optional[str] = None  # ISO date (YYYY-MM-DD) when available
    battery_age_days: Optional[int] = None

    # Temperature status (derived)
    temperature_status: str = "unknown"  # normal|warm|hot|critical|unknown


class StartupMetrics(BaseModel):
    """Startup items metrics."""
    login_items_count: int = 0
    launch_agents_count: int = 0
    launch_daemons_count: int = 0
    login_items: List[Dict[str, Any]] = Field(default_factory=list)
    launch_agents: List[Dict[str, Any]] = Field(default_factory=list)
    launch_daemons: List[Dict[str, Any]] = Field(default_factory=list)


class SystemMetrics(BaseModel):
    """Combined system metrics."""
    disk: Optional[DiskMetrics] = None
    memory: Optional[MemoryMetrics] = None
    cpu: Optional[CPUMetrics] = None
    network: Optional[NetworkMetrics] = None
    battery: Optional[BatteryMetrics] = None
    startup: Optional[StartupMetrics] = None
    boot_time: Optional[str] = None
    uptime_hours: Optional[float] = None
    
    def to_dict(self) -> Dict:
        """Convert metrics to dictionary."""
        return self.model_dump(exclude_none=True)
