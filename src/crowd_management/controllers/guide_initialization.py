r"""Guide initial-state sampling for Step 1 closed-loop episodes.

KNOWN-BOUNDARY DEFAULT: guides spawn at random unknown positions inside the
feasible workspace, then track deployment-curve targets (surround motion).

``endpoint`` mode keeps legacy PR4 semantics: initial positions equal the
method endpoint plan.
"""

from __future__ import annotations

import numpy as np

from ..scenarios.rectangular import RectangularScenario
from ..types import Array


def sample_random_guide_positions(
    scene: RectangularScenario,
    count: int,
    *,
    seed: int,
    wall_margin: float,
    min_guide_distance: float = 0.0,
    crowd_points: Array | None = None,
    min_crowd_distance: float = 0.0,
    max_attempts_per_guide: int = 200,
) -> Array:
    """Sample reproducible random guide positions in the inset workspace."""
    if count < 0:
        raise ValueError("count must be non-negative.")
    if not np.isfinite(wall_margin) or wall_margin < 0.0:
        raise ValueError("wall_margin must be finite and non-negative.")
    if not np.isfinite(min_guide_distance) or min_guide_distance < 0.0:
        raise ValueError("min_guide_distance must be finite and non-negative.")
    if not np.isfinite(min_crowd_distance) or min_crowd_distance < 0.0:
        raise ValueError("min_crowd_distance must be finite and non-negative.")
    if max_attempts_per_guide < 1:
        raise ValueError("max_attempts_per_guide must be a positive integer.")

    lower, upper = scene.feasible_workspace_bounds(wall_margin)
    if np.any(upper <= lower):
        raise ValueError("wall_margin leaves an empty feasible workspace for guide spawn.")

    rng = np.random.default_rng(int(seed))
    crowd = None if crowd_points is None else np.asarray(crowd_points, dtype=float)
    if crowd is not None and (crowd.ndim != 2 or crowd.shape[1:] != (2,)):
        raise ValueError("crowd_points must have shape (N, 2).")

    positions = np.zeros((int(count), 2), dtype=float)
    for index in range(int(count)):
        placed = False
        for _ in range(int(max_attempts_per_guide)):
            candidate = rng.uniform(lower, upper)
            if min_guide_distance > 0.0 and index > 0:
                deltas = positions[:index] - candidate
                if np.any(np.linalg.norm(deltas, axis=1) < min_guide_distance):
                    continue
            if crowd is not None and min_crowd_distance > 0.0 and len(crowd) > 0:
                if np.any(np.linalg.norm(crowd - candidate, axis=1) < min_crowd_distance):
                    continue
            positions[index] = candidate
            placed = True
            break
        if not placed:
            # Feasibility fallback: ignore separation and keep workspace bounds.
            positions[index] = rng.uniform(lower, upper)
    return positions
