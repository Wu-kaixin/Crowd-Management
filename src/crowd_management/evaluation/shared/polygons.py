"""Shared polygon point-in-polygon and rejection sampling primitives."""
from __future__ import annotations

import numpy as np

from ...types import Array


def points_inside_polygon(points: Array, polygon: Array) -> Array:
    """Return a boolean mask for points inside a simple closed polygon."""
    x, y = points[:, 0], points[:, 1]
    inside = np.zeros(len(points), dtype=bool)
    previous = polygon[-1]
    for current in polygon:
        crosses = (current[1] > y) != (previous[1] > y)
        denominator = previous[1] - current[1]
        if abs(denominator) > 1.0e-15:
            crossing_x = (previous[0] - current[0]) * (y - current[1]) / denominator + current[0]
            inside ^= crosses & (x < crossing_x)
        previous = current
    return inside


def sample_polygon(polygon: Array, count: int, rng: np.random.Generator, *, batch_size: int | None = None) -> Array:
    """Rejection-sample ``count`` points uniformly inside ``polygon``."""
    accepted: list[Array] = []
    total = 0
    size = max(count, 64) if batch_size is None else batch_size
    while total < count:
        candidates = rng.uniform(np.min(polygon, axis=0), np.max(polygon, axis=0), size=(size, 2))
        batch = candidates[points_inside_polygon(candidates, polygon)]
        accepted.append(batch)
        total += len(batch)
    return np.vstack(accepted)[:count]
