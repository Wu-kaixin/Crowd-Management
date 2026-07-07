"""Low-level pedestrian response to mobile guiders."""
from __future__ import annotations

import numpy as np

from ...types import GuiderState, PedestrianState, unit


class GuidanceController:
    """Convert guider influence into extra desired acceleration for pedestrians.

    The model is intentionally simple for the first sprint: a guider does not push a
    pedestrian physically. It changes the pedestrian's preferred direction within a
    finite influence radius, scaled by pedestrian compliance.
    """

    def __init__(self, guidance_strength: float) -> None:
        self.guidance_strength = float(guidance_strength)

    def force_on(self, pedestrian: PedestrianState, guiders: list[GuiderState]) -> np.ndarray:
        if pedestrian.evacuated or not guiders:
            return np.zeros(2, dtype=float)
        total = np.zeros(2, dtype=float)
        for guider in guiders:
            delta = pedestrian.position - guider.position
            dist = float(np.linalg.norm(delta))
            if dist >= guider.influence_radius:
                continue
            # Smooth weight: 1 near the guider, 0 at the boundary.
            weight = (1.0 - dist / guider.influence_radius) ** 2
            suggested = unit(guider.desired_direction, fallback=np.array([1.0, 0.0]))
            total += self.guidance_strength * pedestrian.compliance * weight * suggested
        return total
