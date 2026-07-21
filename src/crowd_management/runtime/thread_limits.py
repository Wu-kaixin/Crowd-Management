"""BLAS/OpenMP thread governance.

Two mechanisms, both no-ops when unavailable:

- ``limit_blas_threads``: runtime limiting via threadpoolctl for pools that
  already exist in this process (works after NumPy import).
- ``blas_env`` / ``apply_blas_env``: environment variables that must be set
  *before* NumPy/SciPy initialise their thread pools; use for subprocesses
  (pass into the child environment) or at interpreter startup.
"""
from __future__ import annotations

import contextlib
import os
import sys
from typing import Any, Iterator

from .hardware import BLAS_ENV_VARS


def blas_env(threads: int) -> dict[str, str]:
    """Environment variables limiting numerical libraries to ``threads``."""
    if threads < 1:
        raise ValueError("threads must be a positive integer.")
    return {name: str(threads) for name in BLAS_ENV_VARS}


def apply_blas_env(threads: int) -> bool:
    """Set BLAS env vars in this process; only effective before NumPy import.

    Returns False (without setting anything) when NumPy is already imported,
    because the variables would silently have no effect on existing pools.
    """
    if "numpy" in sys.modules:
        return False
    os.environ.update(blas_env(threads))
    return True


@contextlib.contextmanager
def limit_blas_threads(threads: int | None) -> Iterator[dict[str, Any] | None]:
    """Limit existing BLAS/OpenMP pools within the block via threadpoolctl.

    ``threads=None`` leaves the configuration untouched. Missing
    threadpoolctl degrades to a no-op so simulations never fail.
    Yields the effective threadpool info (or None when unavailable).
    """
    if threads is None:
        yield None
        return
    if threads < 1:
        raise ValueError("threads must be a positive integer.")
    try:
        from threadpoolctl import threadpool_info, threadpool_limits
    except ImportError:
        yield None
        return
    with threadpool_limits(limits=threads):
        yield {"requested": threads, "pools": threadpool_info()}


def effective_blas_threads() -> list[dict[str, Any]]:
    """Report the currently effective threadpool configuration (read-only)."""
    try:
        from threadpoolctl import threadpool_info

        return [
            {
                "user_api": pool.get("user_api"),
                "internal_api": pool.get("internal_api"),
                "num_threads": pool.get("num_threads"),
            }
            for pool in threadpool_info()
        ]
    except ImportError:
        return []
