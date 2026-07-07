"""Legacy center-radius deployment baseline.

This preserves the useful part of the previous DBACT-style prototype as a
baseline: estimate a crowd center and spread radius, then deploy a ring around
that simplified geometry. It is no longer treated as the main method.
"""
from __future__ import annotations

import numpy as np

from ..estimation.boundary import estimate_crowd_center
from ..types import Array


class LegacyCenterRadiusController:
    def __init__(self, safety_distance: float = 0.8, radius_percentile: float = 90.0) -> None:
        self.safety_distance = float(safety_distance)
        self.radius_percentile = float(radius_percentile)

    def deploy(self, count: int, crowd_points: Array) -> Array:
        points = np.asarray(crowd_points, dtype=float)
        center = estimate_crowd_center(points)
        radii = np.linalg.norm(points - center, axis=1)
        radius = float(np.percentile(radii, self.radius_percentile)) + self.safety_distance
        angles = np.linspace(0.0, 2.0 * np.pi, int(count), endpoint=False)
        dirs = np.column_stack((np.cos(angles), np.sin(angles)))
        return center + dirs * radius
