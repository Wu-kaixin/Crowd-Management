"""Static containment experiment configuration.

ROLE: INPUT BINDING — load configs/*.yaml into typed StaticContainmentConfig.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import yaml

from ...controllers import ABCGv2Config, AssignmentConfig, ResourcePolicyConfig, VelocitySafetyConfig
from ...crowd import (
    StaticCrowdConfig,
    StaticHeterogeneityConfig,
)
from ...estimation import BoundaryV2Config
from ...scenarios import RectangularScenario
from ...types import Array, as_vec2


@dataclass(frozen=True)
class VisualizationConfig:
    live: bool = True
    render_every: int = 1
    max_fps: float = 20.0
    show_trails: bool = True

    @classmethod
    def from_dict(cls, raw: dict[str, object] | None) -> VisualizationConfig:
        data = raw or {}
        render_every_raw = data.get("render_every", 1)
        max_fps_raw = data.get("max_fps", 20.0)
        if isinstance(render_every_raw, bool) or not isinstance(render_every_raw, (int, float)):
            raise TypeError("visualization.render_every must be numeric.")
        if isinstance(max_fps_raw, bool) or not isinstance(max_fps_raw, (int, float)):
            raise TypeError("visualization.max_fps must be numeric.")
        render_every = int(render_every_raw)
        max_fps = float(max_fps_raw)
        if render_every < 1:
            raise ValueError("visualization.render_every must be a positive integer.")
        if not np.isfinite(max_fps) or max_fps <= 0.0:
            raise ValueError("visualization.max_fps must be finite and positive.")
        return cls(
            live=bool(data.get("live", True)),
            render_every=render_every,
            max_fps=max_fps,
            show_trails=bool(data.get("show_trails", True)),
        )


@dataclass(frozen=True)
class StaticContainmentConfig:
    seed: int
    room_size: Array
    scene: RectangularScenario
    known_environment: bool
    crowd: StaticCrowdConfig
    heterogeneity: StaticHeterogeneityConfig
    guide_count: int
    safety_distance: float
    coverage_radius: float
    min_guider_distance: float
    boundary_bins: int
    boundary_sample_spacing: float
    resource_policy: ResourcePolicyConfig
    assignment: AssignmentConfig
    motion: ABCGv2Config
    safety: VelocitySafetyConfig
    boundary_v2: BoundaryV2Config
    visualization: VisualizationConfig = field(default_factory=VisualizationConfig)
    step: int = 1

    @classmethod
    def from_yaml(cls, path: str | Path) -> StaticContainmentConfig:
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        seed = int(raw.get("seed", 0))
        scene_raw = raw.get("scene") or {}
        room_raw = raw.get("room") or {}
        if scene_raw:
            width = float(scene_raw.get("width", (room_raw.get("size") or [20.0, 14.0])[0]))
            height = float(scene_raw.get("height", (room_raw.get("size") or [20.0, 14.0])[1]))
            scene_type = str(scene_raw.get("type", "square" if np.isclose(width, height) else "rectangle"))
            if scene_raw.get("closed", True) is False:
                raise ValueError("Step 1 requires a closed environment (scene.closed: true).")
            if scene_raw.get("openings"):
                raise ValueError("Step 1 does not implement environment openings.")
            scene = RectangularScenario(name=scene_type, width=width, height=height)
            room_size = scene.room_size
            known_environment = True
        else:
            room_size = as_vec2(room_raw.get("size", [20.0, 14.0]), "room.size")
            scene = RectangularScenario.from_size(room_size)
            known_environment = False
        containment = raw.get("containment", {})
        coverage_radius = float(containment.get("coverage_radius", 1.2))
        resources = raw.get("resources", {})
        assignment = raw.get("assignment", {})
        motion = raw.get("motion", {})
        safety = raw.get("safety", {})
        boundary = raw.get("boundary", {})
        wall_margin = float(safety.get("wall_margin", safety.get("room_margin", 0.25)))
        return cls(
            seed=seed,
            room_size=room_size,
            scene=scene,
            known_environment=known_environment,
            crowd=StaticCrowdConfig.from_dict(raw["crowd"], seed=seed),
            heterogeneity=StaticHeterogeneityConfig.from_dict(raw.get("heterogeneity", {})),
            guide_count=int(raw.get("guiders", {}).get("count", 8)),
            safety_distance=float(containment.get("safety_distance", 0.8)),
            coverage_radius=coverage_radius,
            min_guider_distance=float(containment.get("min_guider_distance", 0.55)),
            boundary_bins=int(containment.get("boundary_bins", 72)),
            boundary_sample_spacing=float(containment.get("boundary_sample_spacing", 0.08)),
            resource_policy=ResourcePolicyConfig(
                g_req=float(resources.get("required_arc_gap", 2.0 * coverage_radius)),
                m_min=int(resources.get("min_active_guides", 3)),
                increase_hysteresis=float(resources.get("increase_hysteresis", 0.1)),
                decrease_hysteresis=float(resources.get("decrease_hysteresis", 0.1)),
            ),
            assignment=AssignmentConfig(
                lambda_switch=float(assignment.get("switch_penalty", 0.25)),
                reserve_cost=float(assignment.get("reserve_cost", 0.0)),
                unmet_target_cost=float(assignment.get("unmet_target_cost", 1.0e6)),
            ),
            motion=ABCGv2Config(
                dt=float(motion.get("dt", 0.1)),
                k_p=float(motion.get("gain", 1.5)),
                v_max=float(motion.get("max_speed", 1.0)),
                tracking_rmse_tolerance=float(motion.get("tracking_rmse_tolerance", 0.03)),
                speed_tolerance=float(motion.get("speed_tolerance", 0.03)),
                hold_steps=int(motion.get("hold_steps", 10)),
                max_steps=int(motion.get("max_steps", 400)),
            ),
            safety=VelocitySafetyConfig(
                enabled=bool(safety.get("enabled", True)),
                min_guide_distance=float(
                    safety.get("min_guide_distance", containment.get("min_guider_distance", 0.55))
                ),
                min_crowd_distance=float(safety.get("min_crowd_distance", containment.get("safety_distance", 0.8))),
                room_margin=wall_margin,
                residual_tolerance=float(safety.get("residual_tolerance", 1.0e-9)),
                max_projection_sweeps=int(safety.get("max_projection_sweeps", 200)),
            ),
            boundary_v2=BoundaryV2Config(
                estimator=str(boundary.get("estimator", "radial")),
                safety_distance=float(containment.get("safety_distance", 0.8)),
                sample_spacing=float(containment.get("boundary_sample_spacing", 0.08)),
                radial_bins=int(boundary.get("radial_bins", 24)),
                radial_percentile=float(boundary.get("radial_percentile", 96.0)),
                radial_smoothing_passes=int(boundary.get("radial_smoothing_passes", 6)),
                min_observation_points=int(boundary.get("min_observation_points", 8)),
                connectivity_radius=(
                    float(boundary["connectivity_radius"]) if boundary.get("connectivity_radius") is not None else None
                ),
                connectivity_scale=float(boundary.get("connectivity_scale", 5.0)),
                min_component_fraction=float(boundary.get("min_component_fraction", 0.1)),
                min_observation_coverage=float(boundary.get("min_observation_coverage", 0.8)),
                room_size=(float(room_size[0]), float(room_size[1])),
                room_margin=float(boundary.get("room_margin", 0.0)),
                alpha_radius=(float(boundary["alpha_radius"]) if boundary.get("alpha_radius") is not None else None),
                alpha_scale=float(boundary.get("alpha_scale", 2.5)),
                alpha_growth_factors=tuple(
                    float(value) for value in boundary.get("alpha_growth_factors", [1.0, 1.25, 1.5, 2.0, 3.0, 4.0])
                ),
                alpha_smoothing_passes=int(boundary.get("alpha_smoothing_passes", 5)),
                bootstrap_samples=int(boundary.get("bootstrap_samples", 0)),
                bootstrap_min_success_fraction=float(boundary.get("bootstrap_min_success_fraction", 0.7)),
                bootstrap_confidence_floor=float(boundary.get("bootstrap_confidence_floor", 0.15)),
                bootstrap_confidence_scale=(
                    float(boundary["bootstrap_confidence_scale"])
                    if boundary.get("bootstrap_confidence_scale") is not None
                    else None
                ),
            ),
            visualization=VisualizationConfig.from_dict(raw.get("visualization")),
            step=int(raw.get("step", 1)),
        )
