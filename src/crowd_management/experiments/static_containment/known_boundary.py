"""Known-environment Step 1 helpers used by the static containment runner."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np
from shapely.geometry import MultiPoint

from ...controllers.periodic_arc_cvt import CoveragePlan, PeriodicArcCVTConfig, plan_periodic_arc_coverage
from ...controllers.resources import ResourceDecision, ResourcePolicyConfig
from ...crowd.observation import CrowdObservation, crowd_observation_from_points
from ...estimation import BoundaryEstimateFailure, BoundaryEstimateV2, estimate_boundary_v2
from ...geometry.arclength import resample_closed_curve_by_arclength
from ...geometry.deployment_curve import DeploymentCurve, DeploymentCurveFailure, build_deployment_curve
from ...types import Array
from .config import StaticContainmentConfig


def _boundary_diagnostics(data: dict[str, object]) -> dict[str, float | int | str]:
    """Coerce planner diagnostics to the estimator's scalar/string map."""
    out: dict[str, float | int | str] = {}
    for key, value in data.items():
        if isinstance(value, bool):
            out[str(key)] = int(value)
        elif isinstance(value, (int, float, str)):
            out[str(key)] = value
        else:
            out[str(key)] = str(value)
    return out


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


def _deploy_from_crowd_estimate(
    crowd_estimate: BoundaryEstimateV2,
    observation: CrowdObservation,
    cfg: StaticContainmentConfig,
) -> tuple[BoundaryEstimateV2 | BoundaryEstimateFailure, DeploymentCurve | DeploymentCurveFailure | None]:
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
    return _deploy_from_crowd_estimate(crowd_estimate, observation, cfg)


def _crowd_estimate_from_closed_curve(
    vertices: Array,
    *,
    sample_spacing: float,
    method: str,
    diagnostics: dict[str, object],
) -> BoundaryEstimateV2 | BoundaryEstimateFailure:
    try:
        curve, arc_s, length, tangents, normals = resample_closed_curve_by_arclength(
            np.asarray(vertices, dtype=float),
            spacing=float(sample_spacing),
        )
    except ValueError as error:
        return BoundaryEstimateFailure(
            status="BOUNDARY_INVALID",
            component_count=1,
            method=method,
            version=2,
            diagnostics=_boundary_diagnostics({"reason": str(error), **diagnostics}),
        )
    count = len(curve)
    return BoundaryEstimateV2(
        curve_points=curve,
        offset_points=curve.copy(),
        arc_s=arc_s,
        length=float(length),
        tangents=tangents,
        outward_normals=normals,
        uncertainty=np.zeros(count, dtype=float),
        confidence=np.ones(count, dtype=float),
        component_count=1,
        topology_valid=True,
        method=method,
        version=2,
        diagnostics=_boundary_diagnostics({"status": "VALID", **diagnostics}),
    )


def _convex_hull_crowd_estimate(
    points: Array,
    *,
    sample_spacing: float,
) -> BoundaryEstimateV2 | BoundaryEstimateFailure:
    hull = MultiPoint([tuple(map(float, row)) for row in np.asarray(points, dtype=float)]).convex_hull
    if hull.geom_type != "Polygon" or hull.is_empty:
        return BoundaryEstimateFailure(
            status="BOUNDARY_INVALID",
            component_count=1,
            method="convex_hull",
            version=2,
            diagnostics={"reason": "convex_hull_not_a_polygon"},
        )
    coords = np.asarray(hull.exterior.coords[:-1], dtype=float)
    return _crowd_estimate_from_closed_curve(
        coords,
        sample_spacing=sample_spacing,
        method="convex_hull",
        diagnostics={"fallback": "convex_hull", "observation_count": int(len(points))},
    )


def estimate_group_boundary_pipeline(
    observation: CrowdObservation,
    cfg: StaticContainmentConfig,
    *,
    seed_offset: int = 0,
) -> tuple[BoundaryEstimateV2 | BoundaryEstimateFailure, DeploymentCurve | DeploymentCurveFailure | None]:
    """Robust single-group ring for multi-crowd surround.

    Cascade (no bootstrap — placement must not flake across groups):
    1. alpha with relaxed connectivity/coverage
    2. radial
    3. convex hull of the group points
    """
    points = observation.controller_points()
    spacing = float(cfg.boundary_v2.sample_spacing)
    attempts: list[tuple[str, object]] = []

    alpha_cfg = replace(
        cfg.boundary_v2,
        safety_distance=0.0,
        room_size=None,
        estimator="alpha",
        bootstrap_samples=0,
        connectivity_radius=max(float(cfg.boundary_v2.connectivity_radius or 1.5), 1.5),
        min_observation_coverage=min(float(cfg.boundary_v2.min_observation_coverage), 0.55),
        min_component_fraction=min(float(cfg.boundary_v2.min_component_fraction), 0.05),
        alpha_growth_factors=tuple(
            sorted(set(list(cfg.boundary_v2.alpha_growth_factors) + [6.0, 8.0, 10.0]))
        ),
    )
    alpha = estimate_boundary_v2(points, alpha_cfg, np.random.default_rng(cfg.seed + seed_offset))
    if isinstance(alpha, BoundaryEstimateV2):
        planned, deployment = _deploy_from_crowd_estimate(alpha, observation, cfg)
        if isinstance(planned, BoundaryEstimateV2):
            return planned, deployment
        attempts.append(("alpha_deploy", getattr(deployment, "reason", "deploy_failed")))
    else:
        attempts.append(("alpha", alpha.diagnostics.get("reason", alpha.status)))

    radial_cfg = replace(
        cfg.boundary_v2,
        safety_distance=0.0,
        room_size=None,
        estimator="radial",
        bootstrap_samples=0,
        connectivity_radius=max(float(cfg.boundary_v2.connectivity_radius or 2.0), 2.0),
        min_component_fraction=min(float(cfg.boundary_v2.min_component_fraction), 0.05),
    )
    radial = estimate_boundary_v2(points, radial_cfg, np.random.default_rng(cfg.seed + seed_offset + 1))
    if isinstance(radial, BoundaryEstimateV2):
        planned, deployment = _deploy_from_crowd_estimate(radial, observation, cfg)
        if isinstance(planned, BoundaryEstimateV2):
            return planned, deployment
        attempts.append(("radial_deploy", getattr(deployment, "reason", "deploy_failed")))
    else:
        attempts.append(("radial", radial.diagnostics.get("reason", radial.status)))

    hull = _convex_hull_crowd_estimate(points, sample_spacing=spacing)
    if isinstance(hull, BoundaryEstimateV2):
        planned, deployment = _deploy_from_crowd_estimate(hull, observation, cfg)
        if isinstance(planned, BoundaryEstimateV2):
            planned = BoundaryEstimateV2(
                curve_points=planned.curve_points,
                offset_points=planned.offset_points,
                arc_s=planned.arc_s,
                length=planned.length,
                tangents=planned.tangents,
                outward_normals=planned.outward_normals,
                uncertainty=planned.uncertainty,
                confidence=planned.confidence,
                component_count=1,
                topology_valid=True,
                method="convex_hull",
                version=2,
                diagnostics=_boundary_diagnostics(
                    {
                        **planned.diagnostics,
                        "group_estimate_cascade": attempts,
                        "fallback": "convex_hull",
                    }
                ),
            )
            return planned, deployment
        attempts.append(("hull_deploy", getattr(deployment, "reason", "deploy_failed")))
    else:
        attempts.append(("hull", hull.diagnostics.get("reason", hull.status)))

    return (
        BoundaryEstimateFailure(
            status="BOUNDARY_INVALID",
            component_count=1,
            method="multi_group_cascade",
            version=2,
            diagnostics={
                "reason": "group_estimate_cascade_exhausted",
                "attempts": str(attempts),
            },
        ),
        None,
    )

@dataclass(frozen=True)
class MultiGroupSurroundResult:
    """Per-group estimate → deploy → plan, then one merged surround episode."""

    boundary_v2: BoundaryEstimateV2 | BoundaryEstimateFailure
    deployment: DeploymentCurve | DeploymentCurveFailure | None
    resource_decision: ResourceDecision | None
    periodic_plan: CoveragePlan | None
    crowd_curve_display: Array | None
    deployment_curve_display: Array | None
    group_allocations: tuple[int, ...] = ()
    observed_component_ids: Array | None = None
    diagnostics: dict[str, object] = field(default_factory=dict)


def _slice_observation(observation: CrowdObservation, mask: Array) -> CrowdObservation:
    attributes: dict[str, Array] = {}
    if observation.radii is not None:
        attributes["radius"] = observation.radii[mask]
    if observation.demand is not None:
        attributes["demand"] = observation.demand[mask]
    if observation.desired_speed is not None:
        attributes["desired_speed"] = observation.desired_speed[mask]
    if observation.time_gap is not None:
        attributes["time_gap"] = observation.time_gap[mask]
    return crowd_observation_from_points(observation.positions[mask], attributes or None)


def _join_curves_with_nan(curves: list[Array]) -> Array:
    pieces: list[Array] = []
    for index, curve in enumerate(curves):
        if index:
            pieces.append(np.array([[np.nan, np.nan]], dtype=float))
        pieces.append(np.asarray(curve, dtype=float))
    return np.vstack(pieces)


def partition_observed_components(
    points: Array,
    *,
    connectivity_radius: float,
    min_component_fraction: float,
    min_observation_points: int = 3,
) -> Array:
    """Label significant connected components from the observed point cloud only.

    This is the unknown-crowd partition: no generator group IDs, spawn polygons,
    or truth membership. Small fragments are assigned to the nearest significant
    component so every observed person keeps a planning label.
    """
    cloud = np.asarray(points, dtype=float)
    if cloud.ndim != 2 or cloud.shape[1] != 2 or not np.all(np.isfinite(cloud)):
        raise ValueError("points must be a finite (N, 2) array.")
    count = len(cloud)
    if count == 0:
        return np.zeros(0, dtype=int)
    radius = float(connectivity_radius)
    if not np.isfinite(radius) or radius <= 0.0:
        raise ValueError("connectivity_radius must be finite and positive.")
    pairwise = np.linalg.norm(cloud[:, None, :] - cloud[None, :, :], axis=2)
    np.fill_diagonal(pairwise, np.inf)
    adjacency = pairwise <= radius
    visited = np.zeros(count, dtype=bool)
    raw_labels = np.full(count, -1, dtype=int)
    component_id = 0
    sizes: list[int] = []
    for start in range(count):
        if visited[start]:
            continue
        stack = [start]
        visited[start] = True
        members: list[int] = []
        while stack:
            current = stack.pop()
            members.append(current)
            neighbors = np.flatnonzero(adjacency[current] & ~visited)
            if len(neighbors):
                visited[neighbors] = True
                stack.extend(int(item) for item in neighbors)
        for index in members:
            raw_labels[index] = component_id
        sizes.append(len(members))
        component_id += 1

    minimum_size = max(int(min_observation_points), int(np.ceil(float(min_component_fraction) * count)))
    significant = [cid for cid, size in enumerate(sizes) if size >= minimum_size]
    if not significant:
        return np.zeros(count, dtype=int)

    remap = {old: new for new, old in enumerate(significant)}
    labels = np.full(count, -1, dtype=int)
    for index, raw in enumerate(raw_labels):
        if int(raw) in remap:
            labels[index] = remap[int(raw)]

    # Attach fragments to nearest significant component (observation-only).
    significant_points = cloud[labels >= 0]
    significant_labels = labels[labels >= 0]
    for index in range(count):
        if labels[index] >= 0:
            continue
        distances = np.linalg.norm(significant_points - cloud[index], axis=1)
        labels[index] = int(significant_labels[int(np.argmin(distances))])
    return labels


def estimate_multi_group_surround_pipeline(
    observation: CrowdObservation,
    cfg: StaticContainmentConfig,
    *,
    component_ids: Array | None = None,
) -> MultiGroupSurroundResult:
    """Surround each observed crowd component with its own deployment ring.

    Partition comes from the observation point cloud (connectivity components).
    Optional ``component_ids`` are rejected: generator/oracle labels must not
    drive planning under the unknown-crowd contract.
    """
    if component_ids is not None:
        raise ValueError(
            "component_ids must not be passed into multi-group planning; "
            "use partition_observed_components on the observation only."
        )
    # Multi-group separation needs a radius that does not glue distant clusters,
    # but is large enough for JuPedSim within-cluster spacing.
    partition_radius = min(max(float(cfg.boundary_v2.connectivity_radius or 1.25), 1.0), 2.5)
    labels = partition_observed_components(
        observation.positions,
        connectivity_radius=partition_radius,
        min_component_fraction=min(float(cfg.boundary_v2.min_component_fraction), 0.08),
        min_observation_points=int(cfg.boundary_v2.min_observation_points),
    )
    unique = sorted(int(v) for v in np.unique(labels))
    if len(unique) < 2:
        failure = BoundaryEstimateFailure(
            status="BOUNDARY_INVALID",
            component_count=len(unique),
            method="multi_group",
            version=2,
            diagnostics={
                "reason": "observation_has_fewer_than_two_significant_components",
                "partition_radius": partition_radius,
                "component_count": len(unique),
            },
        )
        return MultiGroupSurroundResult(
            boundary_v2=failure,
            deployment=None,
            resource_decision=None,
            periodic_plan=None,
            crowd_curve_display=None,
            deployment_curve_display=None,
            diagnostics=dict(failure.diagnostics),
        )

    group_boundaries: list[BoundaryEstimateV2] = []
    group_deployments: list[DeploymentCurve] = []
    crowd_curves: list[Array] = []
    deploy_curves: list[Array] = []
    for group_id in unique:
        mask = labels == group_id
        if int(np.count_nonzero(mask)) < int(cfg.boundary_v2.min_observation_points):
            failure = BoundaryEstimateFailure(
                status="OBSERVATION_INVALID",
                component_count=len(unique),
                method="multi_group",
                version=2,
                diagnostics={
                    "reason": "group_observation_too_small",
                    "group_id": int(group_id),
                    "group_count": int(np.count_nonzero(mask)),
                },
            )
            return MultiGroupSurroundResult(
                boundary_v2=failure,
                deployment=None,
                resource_decision=None,
                periodic_plan=None,
                crowd_curve_display=_join_curves_with_nan(crowd_curves) if crowd_curves else None,
                deployment_curve_display=_join_curves_with_nan(deploy_curves) if deploy_curves else None,
                diagnostics=dict(failure.diagnostics),
            )
        subset = _slice_observation(observation, mask)
        boundary, deployment = estimate_group_boundary_pipeline(
            subset,
            cfg,
            seed_offset=17 * int(group_id) + 3,
        )
        if isinstance(boundary, BoundaryEstimateFailure) or not isinstance(deployment, DeploymentCurve):
            status = boundary.status if isinstance(boundary, BoundaryEstimateFailure) else "OFFSET_INVALID"
            failure = BoundaryEstimateFailure(
                status=status,
                component_count=len(unique),
                method="multi_group",
                version=2,
                diagnostics={
                    "reason": "group_boundary_or_deployment_failed",
                    "group_id": int(group_id),
                    "group_status": status,
                    "group_reason": str(
                        boundary.diagnostics.get("reason", status)
                        if isinstance(boundary, BoundaryEstimateFailure)
                        else status
                    ),
                },
            )
            return MultiGroupSurroundResult(
                boundary_v2=failure,
                deployment=deployment if isinstance(deployment, DeploymentCurveFailure) else None,
                resource_decision=None,
                periodic_plan=None,
                crowd_curve_display=_join_curves_with_nan(crowd_curves) if crowd_curves else None,
                deployment_curve_display=_join_curves_with_nan(deploy_curves) if deploy_curves else None,
                diagnostics=dict(failure.diagnostics),
            )
        group_boundaries.append(boundary)
        group_deployments.append(deployment)
        crowd_curves.append(boundary.curve_points)
        deploy_curves.append(deployment.curve_points)

    lengths = [float(item.length) for item in group_deployments]
    resource_decision, allocations = _multi_resource_decision(
        lengths,
        int(cfg.guide_count),
        cfg.resource_policy,
    )
    if any(count < 1 for count in allocations):
        failure = BoundaryEstimateFailure(
            status="CAPACITY_SHORTFALL",
            component_count=len(unique),
            method="multi_group",
            version=2,
            diagnostics=_boundary_diagnostics(
                {
                    "reason": "zero_guides_allocated_to_a_group",
                    "group_allocations": list(allocations),
                }
            ),
        )
        return MultiGroupSurroundResult(
            boundary_v2=failure,
            deployment=None,
            resource_decision=resource_decision,
            periodic_plan=None,
            crowd_curve_display=_join_curves_with_nan(crowd_curves),
            deployment_curve_display=_join_curves_with_nan(deploy_curves),
            group_allocations=tuple(allocations),
            diagnostics=dict(failure.diagnostics),
        )

    group_plans: list[CoveragePlan] = []
    for boundary, count in zip(group_boundaries, allocations, strict=True):
        plan = plan_periodic_arc_coverage(boundary, int(count), PeriodicArcCVTConfig())
        if plan.status != "VALID" or not plan.converged:
            failure = BoundaryEstimateFailure(
                status="DEGRADED",
                component_count=len(unique),
                method="multi_group",
                version=2,
                diagnostics=_boundary_diagnostics(
                    {
                        "reason": "group_periodic_plan_invalid",
                        "plan_status": plan.status,
                        "group_allocations": list(allocations),
                    }
                ),
            )
            return MultiGroupSurroundResult(
                boundary_v2=failure,
                deployment=None,
                resource_decision=resource_decision,
                periodic_plan=plan,
                crowd_curve_display=_join_curves_with_nan(crowd_curves),
                deployment_curve_display=_join_curves_with_nan(deploy_curves),
                group_allocations=tuple(allocations),
                diagnostics=dict(failure.diagnostics),
            )
        group_plans.append(plan)

    merged_plan = _merge_coverage_plans(group_plans, allocations)
    display_crowd = _join_curves_with_nan(crowd_curves)
    display_deploy = _join_curves_with_nan(deploy_curves)
    total_length = float(sum(lengths))
    joined = BoundaryEstimateV2(
        curve_points=display_crowd,
        offset_points=display_deploy,
        arc_s=np.linspace(0.0, total_length, len(display_deploy), endpoint=False),
        length=total_length,
        tangents=np.zeros_like(display_deploy),
        outward_normals=np.zeros_like(display_deploy),
        uncertainty=np.zeros(len(display_deploy), dtype=float),
        confidence=np.ones(len(display_deploy), dtype=float),
        component_count=len(unique),
        topology_valid=True,
        method="multi_group_known_boundary",
        version=2,
        diagnostics=_boundary_diagnostics(
            {
                "mode": "multi_group_surround",
                "partition": "observed_connectivity",
                "partition_radius": partition_radius,
                "group_count": len(unique),
                "group_lengths": lengths,
                "group_allocations": list(allocations),
                "deployment_status": "VALID",
                "used_environment_as_crowd_boundary": False,
                "used_generator_component_ids": False,
            }
        ),
    )
    return MultiGroupSurroundResult(
        boundary_v2=joined,
        deployment=None,
        resource_decision=resource_decision,
        periodic_plan=merged_plan,
        crowd_curve_display=display_crowd,
        deployment_curve_display=display_deploy,
        group_allocations=tuple(allocations),
        observed_component_ids=labels.copy(),
        diagnostics={
            "mode": "multi_group_surround",
            "partition": "observed_connectivity",
            "group_count": len(unique),
            "group_allocations": list(allocations),
        },
    )


def _allocate_guides_by_length(lengths: list[float], total: int, *, floor_each: int) -> list[int]:
    count = len(lengths)
    if count == 0:
        return []
    if total <= 0:
        return [0] * count
    if total < count:
        alloc = [0] * count
        order = np.argsort([-float(length) for length in lengths])
        for index in order[:total]:
            alloc[int(index)] = 1
        return alloc
    floor = max(0, min(int(floor_each), total // count))
    counts = np.full(count, floor, dtype=int)
    remaining = int(total) - int(counts.sum())
    weights = np.asarray(lengths, dtype=float)
    weights = np.maximum(weights, 1.0e-9)
    weights = weights / float(weights.sum())
    raw = remaining * weights
    add = np.floor(raw).astype(int)
    leftover = remaining - int(add.sum())
    frac_order = np.argsort(-(raw - add))
    for index in range(leftover):
        add[int(frac_order[index])] += 1
    return (counts + add).tolist()


def _multi_resource_decision(
    lengths: list[float],
    available: int,
    config: ResourcePolicyConfig,
) -> tuple[ResourceDecision, list[int]]:
    requests = [max(int(config.m_min), int(np.ceil(float(length) / config.g_req))) for length in lengths]
    desired = int(sum(requests))
    total_length = float(sum(lengths))
    if desired <= available:
        decision = ResourceDecision(
            requested_count=desired,
            desired_count=desired,
            active_count=desired,
            reserve_count=max(available - desired, 0),
            unmet_target_count=0,
            previous_active_count=None,
            hysteresis_applied=False,
            status="VALID",
            diagnostics={
                "reason": "multi_group_resource_requirement_satisfied",
                "formula": "sum_max_m_min_ceil_Lg_over_g_req",
                "group_lengths": [float(v) for v in lengths],
                "group_requests": list(requests),
                "total_length": total_length,
                "config": {
                    "g_req": float(config.g_req),
                    "m_min": int(config.m_min),
                },
            },
        )
        return decision, requests
    alloc = _allocate_guides_by_length(lengths, available, floor_each=1)
    decision = ResourceDecision(
        requested_count=desired,
        desired_count=desired,
        active_count=int(sum(alloc)),
        reserve_count=max(available - int(sum(alloc)), 0),
        unmet_target_count=max(desired - available, 0),
        previous_active_count=None,
        hysteresis_applied=False,
        status="CAPACITY_SHORTFALL",
        diagnostics={
            "reason": "insufficient_available_guides_for_multi_group",
            "formula": "sum_max_m_min_ceil_Lg_over_g_req",
            "group_lengths": [float(v) for v in lengths],
            "group_requests": list(requests),
            "group_allocations": list(alloc),
            "total_length": total_length,
            "config": {
                "g_req": float(config.g_req),
                "m_min": int(config.m_min),
            },
        },
    )
    return decision, alloc


def _merge_coverage_plans(plans: list[CoveragePlan], allocations: list[int]) -> CoveragePlan:
    target_xy = np.vstack([plan.target_xy for plan in plans])
    target_s = np.concatenate([plan.target_s + float(index) * 1.0e6 for index, plan in enumerate(plans)])
    cell_bounds = np.vstack([plan.cell_bounds for plan in plans])
    cell_mass = np.concatenate([plan.cell_mass for plan in plans])
    h_values = [float(plan.h_history[-1]) if len(plan.h_history) else 0.0 for plan in plans]
    return CoveragePlan(
        target_s=target_s,
        target_xy=target_xy,
        cell_bounds=cell_bounds,
        cell_mass=cell_mass,
        h_history=np.asarray([float(np.mean(h_values)), float(np.mean(h_values))], dtype=float),
        max_arc_gap=float(max(plan.max_arc_gap for plan in plans)),
        active_count=int(sum(allocations)),
        converged=all(plan.converged for plan in plans),
        status="VALID" if all(plan.status == "VALID" for plan in plans) else "PLAN_INVALID",
        gain_history=np.empty((0, 0), dtype=float),
        diagnostics={
            "mode": "multi_group_merged",
            "group_count": len(plans),
            "group_allocations": list(allocations),
            "group_statuses": [plan.status for plan in plans],
            "group_max_arc_gaps": [float(plan.max_arc_gap) for plan in plans],
        },
    )


__all__ = [
    "MultiGroupSurroundResult",
    "build_step1_observation",
    "estimate_group_boundary_pipeline",
    "estimate_known_boundary_pipeline",
    "estimate_multi_group_surround_pipeline",
    "partition_observed_components",
    "planning_boundary_from_deployment",
]
