"""Hardware-aware worker selection for case-level parallelism.

Selection never changes scientific semantics: seeds, case ordering of the
official outputs, and statistical inputs are independent of worker count.
Only wall-clock scheduling is affected.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .hardware import HardwareInfo, detect_hardware

PERFORMANCE_MODES = ("conservative", "balanced", "maximum", "manual")

# Fallbacks when psutil is unavailable and estimates are not provided.
_DEFAULT_MEMORY_PER_WORKER_BYTES = 256 * 2**20
_MEMORY_SAFETY_FRACTION = 0.75


@dataclass(frozen=True)
class ParallelPlan:
    """Resolved parallel execution plan with its selection rationale."""

    workers: int
    blas_threads_per_worker: int
    mode: str
    case_count: int
    estimated_memory_per_worker_bytes: int
    reason: str

    def as_metadata(self) -> dict[str, Any]:
        return {
            "workers": self.workers,
            "blas_threads_per_worker": self.blas_threads_per_worker,
            "performance_mode": self.mode,
            "case_count": self.case_count,
            "estimated_memory_per_worker_bytes": self.estimated_memory_per_worker_bytes,
            "selection_reason": self.reason,
        }


def _memory_cap(hardware: HardwareInfo, per_worker_bytes: int) -> int | None:
    if hardware.memory_available_bytes is None or per_worker_bytes <= 0:
        return None
    budget = int(hardware.memory_available_bytes * _MEMORY_SAFETY_FRACTION)
    return max(1, budget // per_worker_bytes)


def select_parallel_plan(
    case_count: int,
    mode: str = "balanced",
    requested_workers: int | None = None,
    hardware: HardwareInfo | None = None,
    estimated_memory_per_worker_bytes: int | None = None,
) -> ParallelPlan:
    """Choose worker count and per-worker BLAS threads for a case batch.

    ``requested_workers`` implies manual mode. Guarantees:
    ``1 <= workers <= min(case_count, affinity CPUs)`` (manual mode is
    clamped to case_count but may exceed affinity if explicitly requested).
    """
    if case_count < 1:
        raise ValueError("case_count must be a positive integer.")
    if mode not in PERFORMANCE_MODES:
        raise ValueError(f"mode must be one of {PERFORMANCE_MODES}.")
    if requested_workers is not None:
        mode = "manual"

    info = hardware if hardware is not None else detect_hardware()
    logical = info.logical_cpus or 1
    physical = info.physical_cores or logical
    affinity = info.affinity_cpus or logical
    available = max(1, min(affinity, logical))
    per_worker_bytes = (
        estimated_memory_per_worker_bytes
        if estimated_memory_per_worker_bytes is not None
        else _DEFAULT_MEMORY_PER_WORKER_BYTES
    )

    reasons: list[str] = []
    if mode == "manual":
        if requested_workers is None or requested_workers < 1:
            raise ValueError("manual mode requires requested_workers >= 1.")
        workers = min(requested_workers, case_count)
        reasons.append(f"manual override requested_workers={requested_workers}")
        if workers != requested_workers:
            reasons.append(f"clamped to case_count={case_count}")
    else:
        if mode == "conservative":
            candidate = max(1, physical // 2)
            reasons.append(f"conservative: physical_cores({physical})//2")
        elif mode == "balanced":
            candidate = max(1, physical - 1)
            reasons.append(f"balanced: physical_cores({physical})-1 keeps one core for OS/IO")
        else:  # maximum
            candidate = available
            reasons.append(f"maximum: all affinity CPUs ({available})")
        workers = min(candidate, available, case_count)
        if workers < candidate:
            reasons.append(f"capped by min(affinity={available}, case_count={case_count})")

    memory_cap = _memory_cap(info, per_worker_bytes)
    if memory_cap is not None and workers > memory_cap:
        workers = memory_cap
        reasons.append(
            f"memory cap: {memory_cap} workers at ~{per_worker_bytes // 2**20} MiB each within "
            f"{_MEMORY_SAFETY_FRACTION:.0%} of available memory"
        )

    workers = max(1, workers)
    # BLAS threads stay at 1 in every mode: the simulator operates on tiny
    # arrays (2-vectors, K-by-2 curves) where multi-threaded OpenBLAS pools
    # only add synchronization cost. Phase 1 measured a 1.57x serial speedup
    # from capping BLAS at 1 thread (docs/performance/profile_report.md).
    blas_threads = 1
    reasons.append("blas_threads_per_worker=1 (tiny-array workload; measured faster and avoids oversubscription)")

    return ParallelPlan(
        workers=workers,
        blas_threads_per_worker=blas_threads,
        mode=mode,
        case_count=case_count,
        estimated_memory_per_worker_bytes=per_worker_bytes,
        reason="; ".join(reasons),
    )
