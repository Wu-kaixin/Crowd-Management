from __future__ import annotations

import pytest

from crowd_management.runtime import ParallelPlan, format_parallel_report, select_parallel_plan
from crowd_management.runtime.hardware import HardwareInfo


def _hardware(
    physical: int | None = 16,
    logical: int | None = 16,
    affinity: int | None = 16,
    available_bytes: int | None = 16 * 2**30,
) -> HardwareInfo:
    return HardwareInfo(
        cpu_model="TestCPU",
        physical_cores=physical,
        logical_cpus=logical,
        affinity_cpus=affinity,
        memory_total_bytes=32 * 2**30,
        memory_available_bytes=available_bytes,
        os_name="TestOS",
        os_version="1",
        python_version="3.12.0",
        numpy_version="2.0.0",
        scipy_version="1.13.0",
        blas_backend="test-blas",
        blas_thread_env={},
        threadpools=[],
        multiprocessing_start_method="spawn",
        cuda_gpu_detected=False,
    )


def test_balanced_mode_uses_physical_minus_one() -> None:
    plan = select_parallel_plan(case_count=120, mode="balanced", hardware=_hardware())
    assert plan.workers == 15
    assert plan.blas_threads_per_worker == 1


def test_workers_never_exceed_case_count() -> None:
    plan = select_parallel_plan(case_count=3, mode="maximum", hardware=_hardware())
    assert plan.workers == 3


def test_workers_never_exceed_affinity() -> None:
    plan = select_parallel_plan(case_count=100, mode="maximum", hardware=_hardware(affinity=8))
    assert plan.workers == 8


def test_memory_cap_limits_workers() -> None:
    plan = select_parallel_plan(
        case_count=100,
        mode="maximum",
        hardware=_hardware(available_bytes=2 * 2**30),
        estimated_memory_per_worker_bytes=512 * 2**20,
    )
    assert plan.workers <= 3
    assert "memory cap" in plan.reason


def test_manual_mode_respects_request_but_clamps_to_cases() -> None:
    plan = select_parallel_plan(case_count=4, requested_workers=32, hardware=_hardware())
    assert plan.mode == "manual"
    assert plan.workers == 4


def test_single_worker_also_gets_single_blas_thread() -> None:
    """Tiny-array workload: multi-threaded BLAS is measured slower even serially."""
    plan = select_parallel_plan(case_count=1, mode="balanced", hardware=_hardware())
    assert plan.workers == 1
    assert plan.blas_threads_per_worker == 1


def test_degraded_detection_still_returns_valid_plan() -> None:
    plan = select_parallel_plan(
        case_count=10,
        mode="balanced",
        hardware=_hardware(physical=None, logical=None, affinity=None, available_bytes=None),
    )
    assert plan.workers >= 1


def test_invalid_mode_rejected() -> None:
    with pytest.raises(ValueError):
        select_parallel_plan(case_count=1, mode="turbo", hardware=_hardware())


def test_report_contains_required_fields() -> None:
    hardware = _hardware()
    plan = select_parallel_plan(case_count=120, mode="balanced", hardware=hardware)
    report = format_parallel_report(plan, hardware)
    for fragment in (
        "Detected CPU:",
        "Physical cores:",
        "Logical CPUs:",
        "Affinity CPUs:",
        "Selected workers:",
        "BLAS threads per worker:",
        "Performance mode:",
        "Selection reason:",
    ):
        assert fragment in report


def test_plan_metadata_is_serializable() -> None:
    plan = select_parallel_plan(case_count=8, mode="conservative", hardware=_hardware())
    metadata = plan.as_metadata()
    assert metadata["performance_mode"] == "conservative"
    assert isinstance(metadata["selection_reason"], str)
    assert isinstance(plan, ParallelPlan)
