r"""Closed square / rectangle environment for Step 1.

The environment boundary is known. It is never a substitute for the unknown
crowd boundary \(\partial\Omega_c\).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from shapely.geometry import Polygon

from ..types import Array


@dataclass(frozen=True)
class BoundaryOpening:
    """Reserved Step 2 wall opening. Step 1 requires this tuple to be empty."""

    wall: str
    start: float
    end: float


@dataclass(frozen=True)
class RectangularScenario:
    """Axis-aligned closed square or rectangle on [0, W] x [0, H]."""

    name: str
    width: float
    height: float
    openings: tuple[BoundaryOpening, ...] = ()
    origin: tuple[float, float] = (0.0, 0.0)

    def __post_init__(self) -> None:
        if not np.isfinite(self.width) or self.width <= 0.0:
            raise ValueError("width must be finite and positive.")
        if not np.isfinite(self.height) or self.height <= 0.0:
            raise ValueError("height must be finite and positive.")
        ox, oy = self.origin
        if not np.isfinite(ox) or not np.isfinite(oy):
            raise ValueError("origin must be finite.")
        if self.openings:
            raise ValueError("Step 1 RectangularScenario requires openings to be empty.")
        if self.name not in {"square", "rectangle"}:
            raise ValueError("name must be 'square' or 'rectangle'.")
        if self.name == "square" and not np.isclose(self.width, self.height):
            raise ValueError("square scenarios require width == height.")

    @classmethod
    def from_size(
        cls,
        room_size: Array,
        *,
        scene_type: str | None = None,
        name: str | None = None,
    ) -> RectangularScenario:
        size = np.asarray(room_size, dtype=float)
        if size.shape != (2,) or not np.all(np.isfinite(size)) or np.any(size <= 0.0):
            raise ValueError("room_size must contain two finite positive dimensions.")
        width = float(size[0])
        height = float(size[1])
        resolved = (scene_type or name or ("square" if np.isclose(width, height) else "rectangle")).strip().lower()
        if resolved not in {"square", "rectangle"}:
            raise ValueError("scene type must be 'square' or 'rectangle'.")
        return cls(name=resolved, width=width, height=height)

    @property
    def closed(self) -> bool:
        return len(self.openings) == 0

    @property
    def room_size(self) -> Array:
        return np.array([self.width, self.height], dtype=float)

    def boundary_vertices(self) -> Array:
        ox, oy = self.origin
        return np.array(
            [
                [ox, oy],
                [ox + self.width, oy],
                [ox + self.width, oy + self.height],
                [ox, oy + self.height],
            ],
            dtype=float,
        )

    def polygon(self) -> Polygon:
        return Polygon(self.boundary_vertices())

    def contains(self, points: Array, margin: float = 0.0) -> Array:
        if not np.isfinite(margin) or margin < 0.0:
            raise ValueError("margin must be finite and non-negative.")
        array = np.asarray(points, dtype=float)
        if array.ndim != 2 or array.shape[1:] != (2,):
            raise ValueError("points must have shape (N, 2).")
        lower, upper = self.feasible_workspace_bounds(margin)
        if np.any(upper < lower):
            return np.zeros(len(array), dtype=bool)
        return np.all((array >= lower) & (array <= upper), axis=1)

    def wall_clearance(self, points: Array) -> Array:
        array = np.asarray(points, dtype=float)
        if array.ndim != 2 or array.shape[1:] != (2,) or not np.all(np.isfinite(array)):
            raise ValueError("points must be a finite (N, 2) array.")
        ox, oy = self.origin
        left = array[:, 0] - ox
        right = (ox + self.width) - array[:, 0]
        bottom = array[:, 1] - oy
        top = (oy + self.height) - array[:, 1]
        return np.minimum(np.minimum(left, right), np.minimum(bottom, top))

    def feasible_workspace_bounds(self, margin: float) -> tuple[Array, Array]:
        if not np.isfinite(margin) or margin < 0.0:
            raise ValueError("margin must be finite and non-negative.")
        ox, oy = self.origin
        lower = np.array([ox + margin, oy + margin], dtype=float)
        upper = np.array([ox + self.width - margin, oy + self.height - margin], dtype=float)
        return lower, upper

    def feasible_workspace_polygon(self, margin: float) -> Polygon:
        lower, upper = self.feasible_workspace_bounds(margin)
        if np.any(upper <= lower):
            return Polygon()
        return Polygon(
            [
                (float(lower[0]), float(lower[1])),
                (float(upper[0]), float(lower[1])),
                (float(upper[0]), float(upper[1])),
                (float(lower[0]), float(upper[1])),
            ]
        )

    def step1_contract_valid(self) -> bool:
        return self.closed
