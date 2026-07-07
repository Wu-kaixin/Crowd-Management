"""Static circular deployment baseline."""
from __future__ import annotations

import numpy as np

from ..estimation.boundary import estimate_crowd_center
from ..types import Array


class StaticCircleController:
    """Deploy guide agents uniformly around a fixed circle."""

    def __init__(self, radius: float, center: Array | None = None) -> None:
        self.radius = float(radius)
        self.center = None if center is None else np.asarray(center, dtype=float)

    def deploy(self, count: int, crowd_points: Array) -> Array:
        center = estimate_crowd_center(crowd_points) if self.center is None else self.center
        angles = np.linspace(0.0, 2.0 * np.pi, int(count), endpoint=False)
        dirs = np.column_stack((np.cos(angles), np.sin(angles)))
        return center + dirs * self.radius
