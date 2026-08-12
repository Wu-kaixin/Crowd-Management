"""Hardware-aware runtime utilities (read-only detection and configuration).

ROLE: ORCHESTRATION INFRA — worker count, BLAS thread limits, parallel executor.
Must not change scientific numerics (only wall-clock).
"""

from .diagnostics import format_parallel_report
from .executor import TaskPool, run_tasks
from .hardware import HardwareInfo, detect_hardware, hardware_metadata
from .parallel_config import PERFORMANCE_MODES, ParallelPlan, select_parallel_plan
from .thread_limits import apply_blas_env, blas_env, effective_blas_threads, limit_blas_threads

__all__ = [
    "HardwareInfo",
    "ParallelPlan",
    "PERFORMANCE_MODES",
    "TaskPool",
    "apply_blas_env",
    "blas_env",
    "detect_hardware",
    "effective_blas_threads",
    "format_parallel_report",
    "hardware_metadata",
    "limit_blas_threads",
    "run_tasks",
    "select_parallel_plan",
]
