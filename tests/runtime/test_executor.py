from __future__ import annotations

import os

import pytest

from crowd_management.runtime import run_tasks
from crowd_management.runtime.hardware import BLAS_ENV_VARS


def _square(value: int) -> int:
    return value * value


def _fail(value: int) -> int:
    raise ValueError(f"boom {value}")


def _report_env(name: str) -> str | None:
    return os.environ.get(name)


def test_serial_path_preserves_order() -> None:
    assert run_tasks(_square, [(3,), (1,), (2,)], workers=1) == [9, 1, 4]


def test_empty_tasks() -> None:
    assert run_tasks(_square, [], workers=4) == []


def test_process_pool_preserves_order() -> None:
    tasks = [(value,) for value in range(10)]
    assert run_tasks(_square, tasks, workers=2) == [value * value for value in range(10)]


def test_workers_clamped_to_task_count() -> None:
    assert run_tasks(_square, [(5,)], workers=8) == [25]


def test_worker_exception_propagates() -> None:
    with pytest.raises(ValueError, match="boom"):
        run_tasks(_fail, [(1,), (2,)], workers=2)


def test_children_inherit_blas_env_and_parent_env_is_restored() -> None:
    saved = {name: os.environ.get(name) for name in BLAS_ENV_VARS}
    results = run_tasks(_report_env, [("OMP_NUM_THREADS",), ("OPENBLAS_NUM_THREADS",)], workers=2)
    assert results == ["1", "1"]
    assert {name: os.environ.get(name) for name in BLAS_ENV_VARS} == saved
