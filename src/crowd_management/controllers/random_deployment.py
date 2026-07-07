"""Random guide-agent deployment baseline."""
from __future__ import annotations

import numpy as np

from ..types import Array


class RandomDeploymentController:
    """Place guide agents randomly in the room with a reproducible seed."""

    def __init__(self, room_size: Array, margin: float = 0.5, seed: int = 0) -> None:
        self.room_size = np.asarray(room_size, dtype=float)
        self.margin = float(margin)
        self.rng = np.random.default_rng(seed)

    def deploy(self, count: int, crowd_points: Array | None = None) -> Array:
        low = np.array([self.margin, self.margin], dtype=float)
        high = self.room_size - self.margin
        return self.rng.uniform(low, high, size=(int(count), 2))
