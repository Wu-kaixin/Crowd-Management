"""Bootstrap summary helpers for formal evaluation aggregates."""
from __future__ import annotations

from typing import Any

import numpy as np


def bootstrap_metric_summary(
    values: list[float],
    rng: np.random.Generator,
    resamples: int,
    direction: str,
) -> dict[str, Any]:
    """Summarize a metric list with mean/median/CI/p95/worst-5% statistics."""
    array = np.asarray(values, dtype=float)
    if len(array) == 0:
        return {
            "n": 0,
            "mean": None,
            "median": None,
            "ci95_low": None,
            "ci95_high": None,
            "p95": None,
            "worst_5_percent_mean": None,
        }
    indices = rng.integers(0, len(array), size=(resamples, len(array)))
    means = np.mean(array[indices], axis=1)
    worst_count = max(1, int(np.ceil(0.05 * len(array))))
    ordered = np.sort(array)
    worst = ordered[-worst_count:] if direction == "lower" else ordered[:worst_count]
    return {
        "n": int(len(array)),
        "mean": float(np.mean(array)),
        "median": float(np.median(array)),
        "ci95_low": float(np.percentile(means, 2.5)),
        "ci95_high": float(np.percentile(means, 97.5)),
        "p95": float(np.percentile(array, 95.0)),
        "worst_5_percent_mean": float(np.mean(worst)),
        "direction": direction,
    }


def percentile_interval(
    values: np.ndarray,
    rng: np.random.Generator,
    resamples: int,
) -> dict[str, float | int | None]:
    """Bootstrap mean percentile interval used by PR6 aggregates."""
    array = np.asarray(values, dtype=float)
    if len(array) == 0:
        return {"n": 0, "mean": None, "ci95_low": None, "ci95_high": None}
    indices = rng.integers(0, len(array), size=(resamples, len(array)))
    means = np.mean(array[indices], axis=1)
    return {
        "n": int(len(array)),
        "mean": float(np.mean(array)),
        "ci95_low": float(np.percentile(means, 2.5)),
        "ci95_high": float(np.percentile(means, 97.5)),
    }
