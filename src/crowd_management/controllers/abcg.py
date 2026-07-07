"""ABCG: Adaptive Boundary-Coverage Guidance for static containment."""
from __future__ import annotations

import numpy as np

from ..estimation.boundary import BoundaryEstimate, estimate_radial_boundary
from ..types import Array
from .coverage_cvt import BoundaryCVTController
from .safety import clip_to_room, enforce_distance_from_cloud, enforce_minimum_separation


class ABCGController:
    """Boundary-adapted coverage-control deployment.

    The controller transforms an unknown static crowd point cloud into a
    boundary coverage problem: estimate a safety boundary, compute optional
    boundary importance weights, then place guide agents with a CVT-style
    coverage step.
    """

    def __init__(
        self,
        num_bins: int = 72,
        safety_distance: float = 0.8,
        min_guider_distance: float = 0.55,
        cvt_iterations: int = 12,
    ) -> None:
        self.num_bins = int(num_bins)
        self.safety_distance = float(safety_distance)
        self.min_guider_distance = float(min_guider_distance)
        self.cvt = BoundaryCVTController(iterations=cvt_iterations)

    def estimate_boundary(self, crowd_points: Array) -> BoundaryEstimate:
        return estimate_radial_boundary(
            crowd_points,
            num_bins=self.num_bins,
            safety_distance=self.safety_distance,
            smoothing_passes=2,
        )

    def boundary_importance(self, boundary: BoundaryEstimate) -> Array:
        """Weight sparse or protruding regions slightly higher."""
        radii = np.asarray(boundary.radii, dtype=float)
        density_term = 1.0 / np.sqrt(np.maximum(boundary.bin_counts.astype(float), 1.0))
        protrusion_term = radii / max(float(radii.mean()), 1e-9)
        weights = 0.65 * protrusion_term + 0.35 * density_term / density_term.mean()
        return weights / max(float(weights.mean()), 1e-9)

    def deploy(
        self,
        count: int,
        crowd_points: Array,
        room_size: Array | None = None,
    ) -> tuple[Array, BoundaryEstimate]:
        boundary = self.estimate_boundary(crowd_points)
        weights = self.boundary_importance(boundary)
        targets = self.cvt.deploy(count, boundary, weights=weights)
        targets = enforce_distance_from_cloud(targets, crowd_points, boundary.center, self.safety_distance)
        targets = enforce_minimum_separation(targets, self.min_guider_distance)
        targets = enforce_distance_from_cloud(targets, crowd_points, boundary.center, self.safety_distance)
        if room_size is not None:
            targets = clip_to_room(targets, room_size)
        return targets, boundary
