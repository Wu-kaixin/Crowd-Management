"""Deterministic case-level process-pool execution.

ROLE: ORCHESTRATION INFRA — process-pool task runner preserving submission order.
Wall-clock only; does not change scientific numerics.

Phase 1 profiling showed the workload is ~88% Python bytecode, so the GIL
makes thread pools useless here; case-level parallelism needs processes.
This module keeps scheduling concerns fully separate from science:

- results are returned in the submission order of ``tasks``, regardless of
  completion order, so downstream code sees exactly what a serial loop or
  ``executor.map`` would produce;
- every task is one pool item (dynamic scheduling, no chunking), so free
  workers immediately pick up remaining long-tail cases;
- worker processes inherit ``*_NUM_THREADS=1``-style environment variables
  set *before* the child imports NumPy, plus a threadpoolctl initializer as
  a second line of defense, preventing BLAS thread oversubscription;
- worker exceptions propagate to the caller unchanged;
- ``TaskPool`` reuses one ``ProcessPoolExecutor`` across multiple batches
  (primary → ablations → robustness) to avoid repeated Windows spawn cost.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Any

from .thread_limits import blas_env


def _worker_initializer(blas_threads: int) -> None:
    """Cap numerical thread pools inside a freshly spawned worker."""
    try:
        import threadpoolctl

        threadpoolctl.threadpool_limits(limits=blas_threads)
    except ImportError:
        pass


def _collect_ordered(
    executor: ProcessPoolExecutor,
    fn: Callable[..., Any],
    task_list: list[tuple[Any, ...]],
) -> list[Any]:
    future_to_index = {executor.submit(fn, *task): index for index, task in enumerate(task_list)}
    results: list[Any] = [None] * len(task_list)
    for future in as_completed(future_to_index):
        results[future_to_index[future]] = future.result()
    return results


class TaskPool:
    """Reusable case-level process pool (or serial fallback when workers <= 1)."""

    def __init__(self, workers: int, *, blas_threads_per_worker: int = 1) -> None:
        self.workers = max(1, int(workers))
        self.blas_threads_per_worker = max(1, int(blas_threads_per_worker))
        self._executor: ProcessPoolExecutor | None = None
        self._saved_env: dict[str, str | None] | None = None
        self._pool_workers = 1

    def __enter__(self) -> TaskPool:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def close(self) -> None:
        if self._executor is not None:
            self._executor.shutdown(wait=True, cancel_futures=False)
            self._executor = None
        if self._saved_env is not None:
            for name, value in self._saved_env.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
            self._saved_env = None

    def _ensure_executor(self, task_count: int) -> ProcessPoolExecutor | None:
        effective = max(1, min(self.workers, task_count))
        if effective <= 1:
            return None
        if self._executor is not None and self._pool_workers == effective:
            return self._executor
        # Worker count for this batch differs (or first parallel batch): rebuild pool.
        self.close()
        child_env = blas_env(self.blas_threads_per_worker)
        self._saved_env = {name: os.environ.get(name) for name in child_env}
        os.environ.update(child_env)
        self._pool_workers = effective
        self._executor = ProcessPoolExecutor(
            max_workers=effective,
            initializer=_worker_initializer,
            initargs=(self.blas_threads_per_worker,),
        )
        return self._executor

    def map(self, fn: Callable[..., Any], tasks: Sequence[tuple[Any, ...]]) -> list[Any]:
        """Run ``fn(*task)`` for every task; return results in submission order."""
        task_list = list(tasks)
        if not task_list:
            return []
        executor = self._ensure_executor(len(task_list))
        if executor is None:
            return [fn(*task) for task in task_list]
        return _collect_ordered(executor, fn, task_list)


def run_tasks(
    fn: Callable[..., Any],
    tasks: Sequence[tuple[Any, ...]],
    workers: int,
    *,
    blas_threads_per_worker: int = 1,
    pool: TaskPool | None = None,
) -> list[Any]:
    """Run ``fn(*task)`` for every task and return results in task order.

    ``workers <= 1`` executes serially in-process (no spawn overhead, exact
    legacy behavior). ``fn`` must be a module-level callable and every task
    must be picklable when ``workers > 1`` (Windows ``spawn``).

    When ``pool`` is provided, tasks reuse that pool (preferred for multi-stage
    G6). Otherwise a one-shot pool is created for this call only.
    """
    if pool is not None:
        return pool.map(fn, tasks)
    with TaskPool(workers, blas_threads_per_worker=blas_threads_per_worker) as owned:
        return owned.map(fn, tasks)
