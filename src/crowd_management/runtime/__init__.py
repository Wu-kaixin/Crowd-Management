"""Hardware-aware runtime utilities (read-only detection and configuration)."""

from .diagnostics import format_parallel_report
from .hardware import HardwareInfo, detect_hardware, hardware_metadata
from .parallel_config import PERFORMANCE_MODES, ParallelPlan, select_parallel_plan
from .thread_limits import apply_blas_env, blas_env, effective_blas_threads, limit_blas_threads

__all__ = [
    "HardwareInfo",
    "ParallelPlan",
    "PERFORMANCE_MODES",
    "apply_blas_env",
    "blas_env",
    "detect_hardware",
    "effective_blas_threads",
    "format_parallel_report",
    "hardware_metadata",
    "limit_blas_threads",
    "select_parallel_plan",
]
