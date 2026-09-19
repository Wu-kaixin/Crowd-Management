"""Known-environment Step 1 helpers used by the static containment runner."""

from __future__ import annotations

from dataclasses import replace

import numpy as np

from ...crowd.observation import CrowdObservation, crowd_observation_from_points
from ...estimation import BoundaryEstimateFailure, BoundaryEstimateV2, estimate_boundary_v2
from ...geometry.deployment_curve import DeploymentCurve, DeploymentCurveFailure, build_deployment_curve
from ...types import Array
from .config import StaticContainmentConfig


def build_step1_observation(
    crowd_points: Array,
    attributes: dict[str, Array] | None,
) -> CrowdObservation:
    return crowd_observation_from_points(crowd_points, attributes)


def planning_boundary_from_deployment(
    crowd: BoundaryEstimateV2,
    deployment: DeploymentCurve,
) -> BoundaryEstimateV2:
    count = len(deployment.curve_points)
    return BoundaryEstimateV2(
        curve_points=crowd.curve_points,
        offset_points=deployment.curve_points,
        arc_s=deployment.arc_s,
        length=deployment.length,
        tangents=deployment.tangents,
        outward_normals=deployment.outward_normals,
        uncertainty=np.zeros(count, dtype=float),
        confidence=np.ones(count, dtype=float),
        component_count=1,
        topology_valid=True,
        method=crowd.method,
        version=crowd.version,
        diagnostics={
            **crowd.diagnostics,
            "deployment_status": "VALID",
            "deployment_construction": "shapely_minkowski_buffer",
            "deployment_length": float(deployment.length),
            "used_environment_as_crowd_boundary": False,
        },
    )


def estimate_known_boundary_pipeline(
    observation: CrowdObservation,
    cfg: StaticContainmentConfig,
) -> tuple[BoundaryEstimateV2 | BoundaryEstimateFailure, DeploymentCurve | DeploymentCurveFailure | None]:
    """Estimate unknown crowd boundary, then buffer a deployment curve.

    The controller-facing observation has no spawn polygon. Environment is
    used only as the guide workspace.
    """
    crowd_config = replace(cfg.boundary_v2, safety_distance=0.0, room_size=None)
    crowd_estimate = estimate_boundary_v2(
        observation.controller_points(),
        crowd_config,
        np.random.default_rng(cfg.seed),
    )
    if isinstance(crowd_estimate, BoundaryEstimateFailure):
        return crowd_estimate, None

    deployment = build_deployment_curve(
        crowd_estimate.curve_points,
        cfg.safety_distance,
        crowd_points=observation.positions,
        workspace=cfg.scene,
        wall_margin=cfg.safety.room_margin,
        sample_spacing=cfg.boundary_v2.sample_spacing,
        min_crowd_clearance=None,
    )
    if isinstance(deployment, DeploymentCurveFailure):
        failure = BoundaryEstimateFailure(
            status=deployment.status,
            component_count=1,
            method=crowd_estimate.method,
            version=2,
            diagnostics={
                "status": deployment.status,
                "reason": deployment.reason,
                **{key: value for key, value in deployment.diagnostics.items() if isinstance(value, (int, float, str))},
                "crowd_boundary_valid": 1,
                "used_environment_as_crowd_boundary": 0,
            },
        )
        return failure, deployment
    return planning_boundary_from_deployment(crowd_estimate, deployment), deployment
