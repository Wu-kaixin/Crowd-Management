"""Target generation for static containment methods.

ROLE: ORCHESTRATION helper — map method name → baseline endpoint targets.
Uses controllers/* baselines; not the ABCG-v2 closed loop itself.
"""

from __future__ import annotations

from typing import Any

from ...controllers import (
    ABCGController,
    LegacyCenterRadiusController,
    RandomDeploymentController,
    StaticCircleController,
)
from ...estimation.boundary import estimate_radial_boundary
from ...types import Array
from .config import StaticContainmentConfig


def _controller_targets(method: str, cfg: StaticContainmentConfig, crowd_points: Array) -> tuple[Array, Any]:
    method = method.lower()
    if method == "random":
        controller = RandomDeploymentController(cfg.room_size, seed=cfg.seed)
        targets = controller.deploy(cfg.guide_count, crowd_points)
        boundary = estimate_radial_boundary(crowd_points, cfg.boundary_bins, cfg.safety_distance)
        return targets, boundary
    if method == "static_circle":
        radius = cfg.crowd.radius + cfg.safety_distance
        circle = StaticCircleController(radius=radius, center=cfg.crowd.center)
        targets = circle.deploy(cfg.guide_count, crowd_points)
        boundary = estimate_radial_boundary(crowd_points, cfg.boundary_bins, cfg.safety_distance)
        return targets, boundary
    if method == "legacy_center_radius":
        legacy = LegacyCenterRadiusController(safety_distance=cfg.safety_distance)
        targets = legacy.deploy(cfg.guide_count, crowd_points)
        boundary = estimate_radial_boundary(crowd_points, cfg.boundary_bins, cfg.safety_distance)
        return targets, boundary
    if method == "abcg":
        abcg = ABCGController(
            num_bins=cfg.boundary_bins,
            safety_distance=cfg.safety_distance,
            min_guider_distance=cfg.min_guider_distance,
        )
        return abcg.deploy(cfg.guide_count, crowd_points, room_size=cfg.room_size)
    raise ValueError(f"Unsupported containment method: {method}")
