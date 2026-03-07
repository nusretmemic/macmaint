"""System metrics data models."""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class DiskMetrics(BaseModel):
    """Disk space metrics."""
    total_gb: float
    used_gb: float
    free_gb: float
    percent_used: float
    cache_files: Dict[str, int] = Field(default_factory=dict)
    cache_size_gb: float = 0.0
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


class MemoryMetrics(BaseModel):
    """Memory usage metrics."""
    total_gb: float
    available_gb: float
    used_gb: float
    percent_used: float
    swap_total_gb: float = 0.0
    swap_used_gb: float = 0.0
    top_processes: List[ProcessInfo] = Field(default_factory=list)


class CPUMetrics(BaseModel):
    """CPU usage metrics."""
    cpu_count: int
    cpu_percent: float
    load_average: List[float] = Field(default_factory=list)
    top_processes: List[ProcessInfo] = Field(default_factory=list)


class SystemMetrics(BaseModel):
    """Combined system metrics."""
    disk: Optional[DiskMetrics] = None
    memory: Optional[MemoryMetrics] = None
    cpu: Optional[CPUMetrics] = None
    boot_time: Optional[str] = None
    uptime_hours: Optional[float] = None
    
    def to_dict(self) -> Dict:
        """Convert metrics to dictionary."""
        return self.model_dump(exclude_none=True)
