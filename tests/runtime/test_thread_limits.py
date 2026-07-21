from __future__ import annotations

import pytest

from crowd_management.runtime import blas_env, effective_blas_threads, limit_blas_threads
from crowd_management.runtime.hardware import BLAS_ENV_VARS


def test_blas_env_covers_all_libraries() -> None:
    env = blas_env(1)
    assert set(env) == set(BLAS_ENV_VARS)
    assert all(value == "1" for value in env.values())


def test_blas_env_rejects_nonpositive() -> None:
    with pytest.raises(ValueError):
        blas_env(0)


def test_limit_blas_threads_none_is_noop() -> None:
    with limit_blas_threads(None) as info:
        assert info is None


def test_limit_blas_threads_applies_within_block() -> None:
    pytest.importorskip("threadpoolctl")
    import numpy as np

    with limit_blas_threads(1) as info:
        assert info is not None
        blas_pools = [pool for pool in info["pools"] if pool.get("user_api") == "blas"]
        assert all(pool["num_threads"] == 1 for pool in blas_pools)
        # Exercise BLAS inside the limited region.
        matrix = np.random.default_rng(0).normal(size=(64, 64))
        assert np.isfinite(matrix @ matrix).all()


def test_effective_blas_threads_reports_pools() -> None:
    pytest.importorskip("threadpoolctl")
    pools = effective_blas_threads()
    assert isinstance(pools, list)
    assert all("num_threads" in pool for pool in pools)
