"""Human-readable runtime configuration report."""
from __future__ import annotations

from .hardware import HardwareInfo, detect_hardware
from .parallel_config import ParallelPlan


def _format_bytes(value: int | None) -> str:
    if value is None:
        return "unknown"
    return f"{value / 2**30:.1f} GiB"


def format_parallel_report(plan: ParallelPlan, hardware: HardwareInfo | None = None) -> str:
    """Render the resolved hardware and parallel plan for startup logging."""
    info = hardware if hardware is not None else detect_hardware()
    lines = [
        f"Detected CPU: {info.cpu_model}",
        f"Physical cores: {info.physical_cores if info.physical_cores is not None else 'unknown'}",
        f"Logical CPUs: {info.logical_cpus if info.logical_cpus is not None else 'unknown'}",
        f"Affinity CPUs: {info.affinity_cpus if info.affinity_cpus is not None else 'unknown'}",
        f"Available memory: {_format_bytes(info.memory_available_bytes)} of {_format_bytes(info.memory_total_bytes)}",
        f"BLAS backend: {info.blas_backend or 'unknown'}",
        f"Selected workers: {plan.workers}",
        f"BLAS threads per worker: {plan.blas_threads_per_worker}",
        f"Estimated memory per worker: {plan.estimated_memory_per_worker_bytes / 2**20:.0f} MiB",
        f"Performance mode: {plan.mode}",
        f"Selection reason: {plan.reason}",
    ]
    if info.detection_warnings:
        lines.append(f"Detection warnings: {'; '.join(info.detection_warnings)}")
    return "\n".join(lines)
