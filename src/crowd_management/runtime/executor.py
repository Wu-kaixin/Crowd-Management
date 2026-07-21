"""Deterministic case-level process-pool execution.

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
- worker exceptions propagate to the caller unchanged.
"""
from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Any, Callable, Sequence

from .thread_limits import blas_env


def _worker_initializer(blas_threads: int) -> None:
    """Cap numerical thread pools inside a freshly spawned worker."""
    try:
        import threadpoolctl

        threadpoolctl.threadpool_limits(limits=blas_threads)
    except ImportError:
        pass


def run_tasks(
    fn: Callable[..., Any],
    tasks: Sequence[tuple[Any, ...]],
    workers: int,
    *,
    blas_threads_per_worker: int = 1,
) -> list[Any]:
    """Run ``fn(*task)`` for every task and return results in task order.

    ``workers <= 1`` executes serially in-process (no spawn overhead, exact
    legacy behavior). ``fn`` must be a module-level callable and every task
    must be picklable when ``workers > 1`` (Windows ``spawn``).
    """
    task_list = list(tasks)
    if not task_list:
        return []
    effective_workers = max(1, min(int(workers), len(task_list)))
    if effective_workers == 1:
        return [fn(*task) for task in task_list]

    child_env = blas_env(blas_threads_per_worker)
    saved_env = {name: os.environ.get(name) for name in child_env}
    os.environ.update(child_env)
    try:
        with ProcessPoolExecutor(
            max_workers=effective_workers,
            initializer=_worker_initializer,
            initargs=(blas_threads_per_worker,),
        ) as executor:
            future_to_index = {
                executor.submit(fn, *task): index for index, task in enumerate(task_list)
            }
            results: list[Any] = [None] * len(task_list)
            for future in as_completed(future_to_index):
                results[future_to_index[future]] = future.result()
    finally:
        for name, value in saved_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
    return results
