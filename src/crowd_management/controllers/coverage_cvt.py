"""Boundary CVT-style deployment for static containment."""
from __future__ import annotations

import numpy as np

from ..estimation.boundary import BoundaryEstimate
from ..types import Array


class BoundaryCVTController:
    """Approximate a weighted 1D CVT over boundary samples."""

    def __init__(self, iterations: int = 12) -> None:
        self.iterations = int(iterations)

    def deploy(self, count: int, boundary: BoundaryEstimate, weights: Array | None = None) -> Array:
        samples = np.asarray(boundary.safety_points, dtype=float)
        n = len(samples)
        count = int(count)
        if count <= 0:
            return np.zeros((0, 2), dtype=float)
        if weights is None:
            weights_arr = np.ones(n, dtype=float)
        else:
            weights_arr = np.maximum(np.asarray(weights, dtype=float), 1e-9)
            if weights_arr.shape != (n,):
                raise ValueError("weights must match the number of boundary samples.")

        indices = np.linspace(0, n, count, endpoint=False, dtype=int)
        centers = samples[indices].copy()
        for _ in range(max(1, self.iterations)):
            dist = np.linalg.norm(samples[:, None, :] - centers[None, :, :], axis=2)
            assignment = np.argmin(dist, axis=1)
            next_centers = centers.copy()
            for gid in range(count):
                mask = assignment == gid
                if not np.any(mask):
                    continue
                w = weights_arr[mask]
                next_centers[gid] = np.average(samples[mask], axis=0, weights=w)
            centers = _project_to_boundary_order(next_centers, boundary)
        return centers


def _project_to_boundary_order(points: Array, boundary: BoundaryEstimate) -> Array:
    """Project centroid updates back to the nearest safety boundary samples."""
    samples = boundary.safety_points
    chosen = []
    for point in points:
        idx = int(np.argmin(np.linalg.norm(samples - point, axis=1)))
        chosen.append(samples[idx])
    return np.asarray(chosen, dtype=float)
