"""Mobile guider model used by the crowd-guidance controller."""
from __future__ import annotations

import numpy as np

from .types import GuiderConfig, GuiderState, RoomConfig, limit_norm, unit


def initialize_guiders(config: GuiderConfig, room: RoomConfig) -> list[GuiderState]:
    """Place guiders near the left side before the controller updates targets."""
    if config.count <= 0:
        return []
    ys = np.linspace(room.height * 0.25, room.height * 0.75, config.count)
    guiders: list[GuiderState] = []
    for gid, y in enumerate(ys):
        pos = np.array([0.7, float(y)], dtype=float)
        guiders.append(
            GuiderState(
                gid=gid,
                position=pos.copy(),
                velocity=np.zeros(2, dtype=float),
                target_position=pos.copy(),
                desired_direction=np.array([1.0, 0.0], dtype=float),
                influence_radius=config.influence_radius,
            )
        )
    return guiders


class GuiderModel:
    """First-order mobile guider dynamics."""

    def __init__(self, config: GuiderConfig, room: RoomConfig) -> None:
        self.config = config
        self.room = room

    def step(self, guiders: list[GuiderState], dt: float) -> None:
        for guider in guiders:
            to_target = guider.target_position - guider.position
            desired_velocity = limit_norm(to_target / max(dt, 1e-9), self.config.max_speed)
            guider.velocity = desired_velocity
            guider.position = guider.position + dt * guider.velocity
            guider.position = self.room.clip_inside(guider.position, margin=0.15)
            guider.desired_direction = unit(guider.desired_direction, fallback=np.array([1.0, 0.0]))

    @staticmethod
    def arrays(guiders: list[GuiderState]) -> np.ndarray:
        if not guiders:
            return np.zeros((0, 2), dtype=float)
        return np.vstack([g.position for g in guiders])
