"""Read-only hardware and numerical-backend detection.

All probes degrade gracefully when optional dependencies (psutil,
threadpoolctl) are missing; detection must never fail a simulation.
The exported metadata intentionally excludes privacy-sensitive fields
(username, hostname, IP/MAC addresses, filesystem paths, serial numbers).
"""
from __future__ import annotations

import multiprocessing
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from typing import Any

BLAS_ENV_VARS = (
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
)


@dataclass(frozen=True)
class HardwareInfo:
    """Snapshot of machine, OS, and numerical-backend configuration."""

    cpu_model: str
    physical_cores: int | None
    logical_cpus: int | None
    affinity_cpus: int | None
    memory_total_bytes: int | None
    memory_available_bytes: int | None
    os_name: str
    os_version: str
    python_version: str
    numpy_version: str | None
    scipy_version: str | None
    blas_backend: str | None
    blas_thread_env: dict[str, str | None]
    threadpools: list[dict[str, Any]]
    multiprocessing_start_method: str
    cuda_gpu_detected: bool
    detection_warnings: tuple[str, ...] = field(default=())


def _detect_cpu_counts(warnings: list[str]) -> tuple[int | None, int | None, int | None]:
    logical = os.cpu_count()
    affinity: int | None = None
    if hasattr(os, "process_cpu_count"):
        affinity = os.process_cpu_count()
    physical: int | None = None
    try:
        import psutil

        physical = psutil.cpu_count(logical=False)
        logical = psutil.cpu_count(logical=True) or logical
    except Exception as exc:  # noqa: BLE001 - detection must never fail the run
        warnings.append(f"psutil unavailable for core detection: {type(exc).__name__}")
    return physical, logical, affinity if affinity is not None else logical


def _detect_memory(warnings: list[str]) -> tuple[int | None, int | None]:
    try:
        import psutil

        memory = psutil.virtual_memory()
        return int(memory.total), int(memory.available)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"psutil unavailable for memory detection: {type(exc).__name__}")
        return None, None


def _detect_numpy_backend(warnings: list[str]) -> tuple[str | None, str | None, str | None]:
    numpy_version: str | None = None
    scipy_version: str | None = None
    blas_backend: str | None = None
    try:
        import numpy as np

        numpy_version = np.__version__
        try:
            config = np.__config__.show(mode="dicts")
            blas_backend = config.get("Build Dependencies", {}).get("blas", {}).get("name")
        except Exception:  # noqa: BLE001 - older numpy without dict mode
            blas_backend = None
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"numpy probe failed: {type(exc).__name__}")
    try:
        import scipy

        scipy_version = scipy.__version__
    except Exception:  # noqa: BLE001
        pass
    return numpy_version, scipy_version, blas_backend


def _detect_threadpools(warnings: list[str]) -> list[dict[str, Any]]:
    try:
        import threadpoolctl

        pools = []
        for pool in threadpoolctl.threadpool_info():
            pools.append(
                {
                    "user_api": pool.get("user_api"),
                    "internal_api": pool.get("internal_api"),
                    "num_threads": pool.get("num_threads"),
                    "version": pool.get("version"),
                }
            )
        return pools
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"threadpoolctl unavailable: {type(exc).__name__}")
        return []


def _detect_cuda() -> bool:
    if shutil.which("nvidia-smi") is None:
        return False
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=count", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return result.returncode == 0 and bool(result.stdout.strip())
    except Exception:  # noqa: BLE001
        return False


def detect_hardware() -> HardwareInfo:
    """Detect hardware and numerical-backend configuration (read-only)."""
    warnings: list[str] = []
    physical, logical, affinity = _detect_cpu_counts(warnings)
    memory_total, memory_available = _detect_memory(warnings)
    numpy_version, scipy_version, blas_backend = _detect_numpy_backend(warnings)
    try:
        start_method = multiprocessing.get_start_method(allow_none=True) or (
            "spawn" if sys.platform == "win32" else "fork"
        )
    except Exception:  # noqa: BLE001
        start_method = "unknown"
    return HardwareInfo(
        cpu_model=platform.processor() or platform.machine(),
        physical_cores=physical,
        logical_cpus=logical,
        affinity_cpus=affinity,
        memory_total_bytes=memory_total,
        memory_available_bytes=memory_available,
        os_name=platform.system(),
        os_version=platform.version(),
        python_version=platform.python_version(),
        numpy_version=numpy_version,
        scipy_version=scipy_version,
        blas_backend=blas_backend,
        blas_thread_env={name: os.environ.get(name) for name in BLAS_ENV_VARS},
        threadpools=_detect_threadpools(warnings),
        multiprocessing_start_method=start_method,
        cuda_gpu_detected=_detect_cuda(),
        detection_warnings=tuple(warnings),
    )


def hardware_metadata(info: HardwareInfo | None = None) -> dict[str, Any]:
    """Return hardware info as a JSON-serializable, privacy-safe dict."""
    return asdict(info if info is not None else detect_hardware())
