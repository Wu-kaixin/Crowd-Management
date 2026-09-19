"""Pedestrian motion models for Step 2 gather-then-surround."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ...scenarios.rectangular import RectangularScenario
from ...types import Array


@dataclass(frozen=True)
class AttractiveRendezvousMotion:
    """Crowds walk toward a rendezvous disk; soft repulsion and wall clip.

    Guides outside the disk provide a mild inward bias (herding). This is a
    research kinematics model, not a calibrated social-force / JuPedSim dynamics
    replacement.
    """

    speed: float = 0.85
    soft_radius: float = 0.45
    soft_strength: float = 0.55
    guide_influence_radius: float = 2.5
    guide_influence_strength: float = 0.35
    wall_margin: float = 0.25

    def step(
        self,
        crowd_positions: Array,
        guide_positions: Array,
        dt: float,
        *,
        rendezvous: Array,
        scene: RectangularScenario | None = None,
        freeze: bool = False,
    ) -> Array:
        crowd = np.asarray(crowd_positions, dtype=float)
        if freeze or len(crowd) == 0:
            return crowd.copy()
        guides = np.asarray(guide_positions, dtype=float)
        center = np.asarray(rendezvous, dtype=float).reshape(2)
        dt = float(dt)
        if not np.isfinite(dt) or dt <= 0.0:
            raise ValueError("dt must be finite and positive.")

        to_center = center[None, :] - crowd
        dist = np.linalg.norm(to_center, axis=1, keepdims=True)
        desired = np.zeros_like(crowd)
        nonzero = dist[:, 0] > 1.0e-9
        desired[nonzero] = to_center[nonzero] / dist[nonzero] * self.speed

        # Soft pairwise repulsion among pedestrians.
        if len(crowd) > 1 and self.soft_strength > 0.0:
            delta = crowd[:, None, :] - crowd[None, :, :]
            sep = np.linalg.norm(delta, axis=2)
            np.fill_diagonal(sep, np.inf)
            mask = sep < self.soft_radius
            force = np.zeros_like(crowd)
            for i in range(len(crowd)):
                near = mask[i]
                if not np.any(near):
                    continue
                dirs = delta[i, near]
                norms = sep[i, near][:, None]
                force[i] = np.sum(
                    dirs / np.maximum(norms, 1.0e-9) * (self.soft_radius - norms) * self.soft_strength,
                    axis=0,
                )
            desired = desired + force

        # Mild herding: guides outside push people toward the rendezvous.
        if len(guides) and self.guide_influence_strength > 0.0:
            for i, person in enumerate(crowd):
                deltas = person[None, :] - guides
                dists = np.linalg.norm(deltas, axis=1)
                near = dists < self.guide_influence_radius
                if not np.any(near):
                    continue
                # Bias along person→center if a guide is farther from center than the person.
                person_r = float(np.linalg.norm(person - center))
                for g, d in zip(guides[near], dists[near], strict=False):
                    guide_r = float(np.linalg.norm(g - center))
                    if guide_r + 1.0e-9 < person_r:
                        continue
                    weight = self.guide_influence_strength * (1.0 - d / self.guide_influence_radius)
                    if person_r > 1.0e-9:
                        desired[i] = desired[i] + weight * (center - person) / person_r

        speed = np.linalg.norm(desired, axis=1, keepdims=True)
        too_fast = speed[:, 0] > self.speed
        desired[too_fast] = desired[too_fast] / speed[too_fast] * self.speed
        nxt = crowd + desired * dt

        if scene is not None:
            lower, upper = scene.feasible_workspace_bounds(self.wall_margin)
            nxt = np.clip(nxt, lower, upper)
        return nxt
