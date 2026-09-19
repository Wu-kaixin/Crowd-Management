"""Top-level static containment runner.

ROLE: ORCHESTRATION — crowd → estimate → plan → assign → episode → metrics → disk.
Core math lives in controllers/ and estimation/; this file only sequences them.
Typical OUTPUT root: runs/<name>/ (see docs/CODEMAP.zh.md §5).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from ...containment_metrics import containment_summary
from ...controllers import (
    ABCGv2Controller,
    AssignmentResult,
    CoveragePlan,
    EpisodeResult,
    PeriodicArcCVTConfig,
    ResourceDecision,
    ResourcePolicy,
    assign_guides_to_targets,
    plan_periodic_arc_coverage,
)
from ...controllers.guide_initialization import sample_random_guide_positions
from ...crowd import (
    StaticCrowdTruth,
    build_crowd_source,
    generate_static_agent_attributes,
)
from ...crowd.observation import CrowdObservation
from ...estimation import BoundaryEstimateFailure, BoundaryEstimateV2, estimate_boundary_v2
from ...geometry.deployment_curve import DeploymentCurve
from ...types import Array
from ...visualization.live_step1 import (
    NullStep1Renderer,
    Step1Frame,
    build_renderer,
    display_is_unattended,
)
from ...visualization.static_step1 import save_final_scene
from .artifacts import (
    diag_float,
    diag_int,
    save_assignment_artifacts,
    save_boundary_v2_artifacts,
    save_episode_artifacts,
    save_periodic_plan_artifacts,
    save_resource_decision,
)
from .config import StaticContainmentConfig
from .known_boundary import (
    build_step1_observation,
    estimate_known_boundary_pipeline,
    estimate_multi_group_surround_pipeline,
)
from .manifest import build_manifest
from .methods import _controller_targets
from .records import MethodSummary


def _assemble_method_summary(
    *,
    final_summary: dict[str, Any],
    initial_summary: dict[str, Any],
    truth: StaticCrowdTruth,
    boundary_v2: BoundaryEstimateV2 | BoundaryEstimateFailure,
    resource_decision: ResourceDecision | None,
    periodic_plan: CoveragePlan | None,
    assignment_result: AssignmentResult | None,
    episode_result: EpisodeResult | None,
    episode_skipped_status: str,
    geometry_valid: bool,
    plan_valid: bool,
    resource_status: str,
) -> MethodSummary:
    summary: MethodSummary = dict(final_summary)  # type: ignore[assignment]
    summary["metrics_position_source"] = (
        "episode_final_frame" if episode_result is not None else "endpoint_baseline_no_episode"
    )
    summary["initial_endpoint_coverage_ratio"] = float(initial_summary["coverage_ratio"])
    summary["initial_endpoint_max_euclidean_boundary_distance"] = float(
        initial_summary["max_euclidean_boundary_distance"]
    )
    if isinstance(boundary_v2, BoundaryEstimateFailure):
        summary["boundary_v2_status"] = boundary_v2.status
    else:
        summary["boundary_v2_status"] = "VALID"
    summary["boundary_v2_method"] = boundary_v2.method
    summary["boundary_confidence_status"] = str(boundary_v2.diagnostics.get("confidence_status", "not_available"))
    summary["periodic_plan_status"] = (
        periodic_plan.status if periodic_plan is not None else "PLAN_SKIPPED_BOUNDARY_INVALID"
    )
    summary["periodic_max_arc_gap"] = float(periodic_plan.max_arc_gap) if periodic_plan is not None else "not_available"
    summary["resource_status"] = resource_status
    summary["active_guide_count"] = resource_decision.active_count if resource_decision is not None else 0
    summary["reserve_guide_count"] = resource_decision.reserve_count if resource_decision is not None else 0
    summary["resource_unmet_target_count"] = (
        resource_decision.unmet_target_count if resource_decision is not None else 0
    )
    summary["assignment_status"] = (
        assignment_result.status if assignment_result is not None else "ASSIGNMENT_SKIPPED_PLAN_INVALID"
    )
    summary["assignment_switch_count"] = assignment_result.switch_count if assignment_result is not None else 0
    summary["episode_status"] = episode_result.status if episode_result is not None else episode_skipped_status
    summary["episode_control_steps"] = len(episode_result.applied_controls) if episode_result is not None else 0
    summary["episode_final_tracking_rmse"] = (
        float(episode_result.tracking_rmse[-1]) if episode_result is not None else "not_available"
    )
    if episode_result is not None:
        summary["safety_filter_status"] = str(episode_result.diagnostics.get("safety_filter_status", "not_available"))
        summary["safety_projected_steps"] = diag_int(episode_result.diagnostics, "safety_projected_steps", 0)
        summary["safety_infeasible_steps"] = diag_int(episode_result.diagnostics, "safety_infeasible_steps", 0)
        summary["safety_max_residual_after"] = diag_float(episode_result.diagnostics, "safety_max_residual_after", 0.0)
    else:
        summary["safety_filter_status"] = "not_available"
        summary["safety_projected_steps"] = 0
        summary["safety_infeasible_steps"] = 0
        summary["safety_max_residual_after"] = "not_available"
    boundary_valid = isinstance(boundary_v2, BoundaryEstimateV2) or (
        isinstance(boundary_v2, BoundaryEstimateFailure)
        and int(boundary_v2.diagnostics.get("crowd_boundary_valid", 0)) == 1
    )
    deployment_valid = isinstance(boundary_v2, BoundaryEstimateV2)
    assignment_valid = assignment_result is not None and assignment_result.status == "VALID"
    episode_converged = episode_result is not None and episode_result.status == "CONVERGED"
    sampled_safety_valid = (
        episode_result is not None
        and diag_int(episode_result.diagnostics, "safety_infeasible_steps", 0) == 0
        and episode_result.status != "SAFETY_INFEASIBLE"
    )
    execution_success = episode_result is not None or episode_skipped_status not in {
        "BOUNDARY_INVALID",
        "OBSERVATION_INVALID",
    }
    scientific_success = (
        truth.valid
        and deployment_valid
        and resource_status == "VALID"
        and plan_valid
        and assignment_valid
        and episode_converged
        and sampled_safety_valid
    )
    summary["execution_success"] = bool(execution_success)
    summary["boundary_valid"] = bool(boundary_valid)
    summary["deployment_valid"] = bool(deployment_valid)
    summary["resource_valid"] = resource_status == "VALID"
    summary["plan_valid"] = bool(plan_valid)
    summary["assignment_valid"] = bool(assignment_valid)
    summary["episode_converged"] = bool(episode_converged)
    summary["sampled_safety_valid"] = bool(sampled_safety_valid)
    summary["scientific_success"] = bool(scientific_success)
    summary["failure_reason"] = (
        "none"
        if scientific_success
        else str(
            episode_result.status
            if episode_result is not None
            else episode_skipped_status
        )
    )
    if episode_result is not None:
        summary["minimum_guide_guide_distance"] = _finite_or_unavailable(
            diag_float(episode_result.diagnostics, "minimum_guide_guide_distance", float("nan"))
        )
        summary["minimum_guide_crowd_distance"] = _finite_or_unavailable(
            diag_float(episode_result.diagnostics, "minimum_guide_crowd_distance", float("nan"))
        )
        summary["minimum_guide_wall_distance"] = _finite_or_unavailable(
            diag_float(episode_result.diagnostics, "minimum_guide_wall_distance", float("nan"))
        )
    else:
        summary["minimum_guide_guide_distance"] = "not_available"
        summary["minimum_guide_crowd_distance"] = "not_available"
        summary["minimum_guide_wall_distance"] = "not_available"
    summary["method_status"] = (
        "converged_pr5_safety_filtered_episode"
        if scientific_success
        else "diagnostic_only"
    )
    return summary


def _finite_or_unavailable(value: object) -> float | str:
    number = _finite_or_none(value)
    return number if number is not None else "not_available"


def _finite_or_none(value: object) -> float | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not np.isfinite(number):
        return None
    return number


def _build_frame(
    *,
    cfg: StaticContainmentConfig,
    crowd_observation: CrowdObservation,
    guides: Array,
    initial_guides: Array,
    active_ids: tuple[int, ...],
    reserve_ids: tuple[int, ...],
    crowd_curve: Array | None,
    deployment_curve: Array | None,
    targets: Array | None,
    trails: Array | None,
    state: str,
    step: int,
    time: float,
    tracking_rmse: float | None,
    max_arc_gap: float | None,
    safety_status: str,
    min_gg: float | None,
    min_gc: float | None,
    min_gw: float | None,
    failed: bool,
    failure_reason: str | None,
    guide_to_target: Array | None = None,
    crowd_component_ids: Array | None = None,
) -> Step1Frame:
    halo = max(float(cfg.safety.min_guide_distance) * 0.5, 0.2)
    body = max(min(halo * 0.4, 0.18), 0.08)
    group_count = len(cfg.crowd.groups) if cfg.crowd.is_multi else 1
    labels = crowd_component_ids
    return Step1Frame(
        scenario_name=cfg.scene.name,
        seed=cfg.seed,
        time=time,
        step=step,
        environment_vertices=cfg.scene.boundary_vertices(),
        crowd_points=crowd_observation.positions,
        crowd_radii=crowd_observation.radii,
        crowd_demand=crowd_observation.demand,
        estimated_crowd_boundary=crowd_curve,
        deployment_curve=deployment_curve,
        target_positions=targets,
        initial_guides=initial_guides,
        current_guides=guides,
        active_ids=active_ids,
        reserve_ids=reserve_ids,
        trails=trails,
        controller_state=state,
        tracking_rmse=tracking_rmse,
        active_guide_count=len(active_ids),
        max_arc_gap=max_arc_gap,
        min_guide_guide_distance=min_gg,
        min_guide_crowd_distance=min_gc,
        min_guide_wall_distance=min_gw,
        safety_status=safety_status,
        failed=failed,
        failure_reason=failure_reason,
        max_steps=int(cfg.motion.max_steps),
        guide_body_radius=body,
        guide_halo_radius=halo,
        min_guide_distance_req=float(cfg.safety.min_guide_distance),
        min_crowd_distance_req=float(cfg.safety.min_crowd_distance),
        min_wall_distance_req=float(cfg.safety.room_margin),
        guide_to_target=None if guide_to_target is None else np.asarray(guide_to_target, dtype=int),
        crowd_component_ids=None if labels is None else np.asarray(labels, dtype=int),
        crowd_group_count=group_count,
    )


def _run_method(
    method: str,
    *,
    cfg: StaticContainmentConfig,
    crowd_points: Array,
    crowd_observation: CrowdObservation,
    truth: StaticCrowdTruth,
    boundary_v2: BoundaryEstimateV2 | BoundaryEstimateFailure,
    crowd_curve: Array | None,
    deployment_curve: Array | None,
    resource_decision: ResourceDecision | None,
    periodic_plan: CoveragePlan | None,
    output: Path,
    save_plots: bool,
    renderer: Any,
    live: bool,
    planning_labels: Array | None = None,
) -> tuple[MethodSummary, dict[str, Any], dict[str, Any]]:
    method_targets, boundary = _controller_targets(method, cfg, crowd_points)
    if cfg.guide_init == "random":
        initial_guides = sample_random_guide_positions(
            cfg.scene,
            cfg.guide_count,
            seed=cfg.seed + 17,
            wall_margin=cfg.safety.room_margin,
            min_guide_distance=cfg.safety.min_guide_distance,
            crowd_points=crowd_points,
            min_crowd_distance=cfg.safety.min_crowd_distance,
        )
    else:
        initial_guides = np.asarray(method_targets, dtype=float)
    initial_summary = containment_summary(
        method_targets,
        crowd_points,
        boundary,
        cfg.coverage_radius,
        cfg.safety_distance,
        truth_boundary=truth,
    )
    geometry_valid = isinstance(boundary_v2, BoundaryEstimateV2)
    plan_valid = periodic_plan is not None and periodic_plan.status == "VALID" and periodic_plan.converged
    resource_status = resource_decision.status if resource_decision is not None else "RESOURCE_SKIPPED_BOUNDARY_INVALID"
    assignment_result = (
        assign_guides_to_targets(initial_guides, periodic_plan.target_xy, cfg.assignment)
        if plan_valid and periodic_plan is not None
        else None
    )
    if isinstance(boundary_v2, BoundaryEstimateFailure):
        episode_skipped_status = boundary_v2.status
    elif periodic_plan is None or not plan_valid:
        episode_skipped_status = "DEGRADED"
    elif assignment_result is None:
        episode_skipped_status = "ASSIGNMENT_INFEASIBLE"
    else:
        episode_skipped_status = "DEGRADED"
    trail_frames: list[Array] = []

    def on_frame(frame: dict[str, Any]) -> None:
        positions = np.asarray(frame["positions"], dtype=float)
        trail_frames.append(positions.copy())
        output_obj = frame.get("output")
        active_ids = output_obj.active_ids if output_obj is not None else tuple(range(len(positions)))
        reserve_ids = output_obj.reserve_ids if output_obj is not None else ()
        diagnostics = output_obj.diagnostics if output_obj is not None else {}
        renderer.update(
            _build_frame(
                cfg=cfg,
                crowd_observation=crowd_observation,
                guides=positions,
                initial_guides=initial_guides,
                active_ids=active_ids,
                reserve_ids=reserve_ids,
                crowd_curve=crowd_curve,
                deployment_curve=deployment_curve if deployment_curve is not None else (
                    boundary_v2.offset_points if isinstance(boundary_v2, BoundaryEstimateV2) else None
                ),
                targets=periodic_plan.target_xy if periodic_plan is not None else None,
                trails=np.stack(trail_frames, axis=0) if trail_frames else None,
                state=str(frame["state"]),
                step=int(frame["step_index"]),
                time=float(frame["time"]),
                tracking_rmse=_finite_or_none(diagnostics.get("tracking_rmse")) if diagnostics else None,
                max_arc_gap=float(periodic_plan.max_arc_gap) if periodic_plan is not None else None,
                safety_status=(
                    str(diagnostics.get("safety_status", "not_available"))
                    if diagnostics
                    else "not_available"
                ),
                min_gg=_finite_or_none(diagnostics.get("minimum_guide_guide_distance")) if diagnostics else None,
                min_gc=_finite_or_none(diagnostics.get("minimum_guide_crowd_distance")) if diagnostics else None,
                min_gw=_finite_or_none(diagnostics.get("minimum_guide_wall_distance")) if diagnostics else None,
                failed=bool(frame.get("failed")),
                failure_reason=str(frame["state"]) if frame.get("failed") else None,
                guide_to_target=(
                    assignment_result.guide_to_target if assignment_result is not None else None
                ),
                crowd_component_ids=planning_labels,
            )
        )

    start_failed = not (
        plan_valid
        and assignment_result is not None
        and resource_status == "VALID"
        and geometry_valid
    )
    start_state = "INIT" if not start_failed else episode_skipped_status
    renderer.start(
        _build_frame(
            cfg=cfg,
            crowd_observation=crowd_observation,
            guides=initial_guides,
            initial_guides=initial_guides,
            active_ids=tuple(range(len(initial_guides))),
            reserve_ids=(),
            crowd_curve=crowd_curve,
            deployment_curve=deployment_curve,
            targets=periodic_plan.target_xy if periodic_plan is not None else None,
            trails=None,
            state=start_state,
            step=0,
            time=0.0,
            tracking_rmse=None,
            max_arc_gap=float(periodic_plan.max_arc_gap) if periodic_plan is not None else None,
            safety_status="not_available",
            min_gg=None,
            min_gc=None,
            min_gw=None,
            failed=start_failed,
            failure_reason=episode_skipped_status if start_failed else None,
            guide_to_target=(
                assignment_result.guide_to_target if assignment_result is not None else None
            ),
            crowd_component_ids=planning_labels,
        )
    )
    episode_result = (
        ABCGv2Controller(cfg.motion, cfg.safety).run_fixed_target_episode(
            initial_guides,
            periodic_plan.target_xy,
            assignment_result,
            precondition_status=resource_status,
            crowd_points=crowd_observation,
            room_size=cfg.room_size,
            on_frame=on_frame if live else None,
        )
        if periodic_plan is not None and assignment_result is not None
        else None
    )
    final_guide_points = episode_result.positions[-1] if episode_result is not None else initial_guides
    final_summary = containment_summary(
        final_guide_points,
        crowd_points,
        boundary,
        cfg.coverage_radius,
        cfg.safety_distance,
        truth_boundary=truth,
    )
    summary = _assemble_method_summary(
        final_summary=final_summary,
        initial_summary=initial_summary,
        truth=truth,
        boundary_v2=boundary_v2,
        resource_decision=resource_decision,
        periodic_plan=periodic_plan,
        assignment_result=assignment_result,
        episode_result=episode_result,
        episode_skipped_status=episode_skipped_status,
        geometry_valid=geometry_valid,
        plan_valid=plan_valid,
        resource_status=resource_status,
    )
    method_dir = output / method
    method_dir.mkdir(parents=True, exist_ok=True)
    assignment_rec = save_assignment_artifacts(method_dir, assignment_result)
    episode_rec = save_episode_artifacts(method_dir, episode_result, episode_skipped_status)
    np.savez_compressed(
        method_dir / "containment_state.npz",
        crowd_points=crowd_points,
        guide_points=final_guide_points,
        guide_initial_points=initial_guides,
        guide_final_points=final_guide_points,
        guide_method_endpoints=method_targets,
        guide_init_mode=np.array(cfg.guide_init),
        boundary_points=boundary.boundary_points,
        safety_points=boundary.safety_points,
        center=boundary.center,
    )
    with open(method_dir / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    if save_plots:
        from ...containment_visualization import plot_static_containment

        plot_static_containment(
            crowd_points,
            final_guide_points,
            boundary,
            method_dir / "containment.png",
            title=f"{method}: static containment",
        )
        final_frame = _build_frame(
            cfg=cfg,
            crowd_observation=crowd_observation,
            guides=final_guide_points,
            initial_guides=initial_guides,
            active_ids=tuple(int(i) for i in range(len(final_guide_points)))
            if episode_result is None
            else tuple(int(i) for i in np.flatnonzero(episode_result.guide_to_target >= 0)),
            reserve_ids=()
            if episode_result is None
            else tuple(int(i) for i in episode_result.reserve_guide_ids),
            crowd_curve=crowd_curve,
            deployment_curve=deployment_curve
            if deployment_curve is not None
            else (boundary_v2.offset_points if isinstance(boundary_v2, BoundaryEstimateV2) else None),
            targets=periodic_plan.target_xy if periodic_plan is not None else None,
            trails=episode_result.positions if episode_result is not None else None,
            state=summary["episode_status"],
            step=int(summary["episode_control_steps"]),
            time=float(summary["episode_control_steps"]) * cfg.motion.dt,
            tracking_rmse=_finite_or_none(summary["episode_final_tracking_rmse"]),
            max_arc_gap=_finite_or_none(summary["periodic_max_arc_gap"]),
            safety_status=str(summary["safety_filter_status"]),
            min_gg=_finite_or_none(summary["minimum_guide_guide_distance"]),
            min_gc=_finite_or_none(summary["minimum_guide_crowd_distance"]),
            min_gw=_finite_or_none(summary["minimum_guide_wall_distance"]),
            failed=not bool(summary["scientific_success"]),
            failure_reason=None if summary["scientific_success"] else str(summary["failure_reason"]),
            guide_to_target=(
                None
                if episode_result is None
                else np.asarray(episode_result.guide_to_target, dtype=int)
            ),
            crowd_component_ids=planning_labels,
        )
        save_final_scene(final_frame, method_dir / "final_scene.png")
        renderer.save_final(method_dir / "final_scene.png", final_frame)
    return summary, assignment_rec, episode_rec


def run_static_containment(
    config_path: str | Path,
    output_dir: str | Path,
    methods: list[str] | None = None,
    save_plots: bool = True,
    live: bool | None = None,
    headless: bool = False,
    renderer: Any | None = None,
    hold_window: bool | None = None,
) -> dict[str, MethodSummary]:
    config_path = Path(config_path)
    cfg = StaticContainmentConfig.from_yaml(config_path)
    if headless:
        live_enabled = False
    elif live is None:
        live_enabled = bool(cfg.known_environment and cfg.visualization.live)
    else:
        live_enabled = bool(live)
    if live_enabled and renderer is None and display_is_unattended():
        live_enabled = False
    hold_enabled = bool(cfg.visualization.hold_window if hold_window is None else hold_window)
    crowd_source = build_crowd_source(cfg.crowd)
    crowd_points = crowd_source.observe()
    crowd_attributes = generate_static_agent_attributes(
        count=len(crowd_points),
        config=cfg.heterogeneity,
        seed=cfg.seed + 100003,
        positions=crowd_points,
    )
    crowd_observation = build_step1_observation(crowd_points, crowd_attributes)
    from ...crowd import crowd_component_ids as _crowd_component_ids

    # Generator labels are evaluator/viz only — never fed into planning.
    evaluator_labels = _crowd_component_ids(cfg.crowd)
    truth = crowd_source.truth(
        safety_distance=(
            cfg.safety_distance
        )
    )
    deployment_result = None
    crowd_curve: Array | None = None
    deployment_curve: Array | None = None
    resource_decision: ResourceDecision | None = None
    periodic_plan = None
    planning_labels = evaluator_labels
    multi_group_mode = bool(
        cfg.known_environment and cfg.crowd.is_multi and not cfg.crowd.is_dispersed
    )
    if multi_group_mode:
        multi = estimate_multi_group_surround_pipeline(crowd_observation, cfg)
        boundary_v2 = multi.boundary_v2
        deployment_result = multi.deployment
        resource_decision = multi.resource_decision
        periodic_plan = multi.periodic_plan
        crowd_curve = multi.crowd_curve_display
        deployment_curve = multi.deployment_curve_display
        if multi.observed_component_ids is not None:
            planning_labels = np.asarray(multi.observed_component_ids, dtype=int)
        if isinstance(boundary_v2, BoundaryEstimateV2):
            crowd_curve = boundary_v2.curve_points if crowd_curve is None else crowd_curve
            deployment_curve = boundary_v2.offset_points if deployment_curve is None else deployment_curve
    elif cfg.known_environment:
        boundary_v2, deployment_result = estimate_known_boundary_pipeline(crowd_observation, cfg)
        if isinstance(boundary_v2, BoundaryEstimateV2):
            crowd_curve = boundary_v2.curve_points
            deployment_curve = boundary_v2.offset_points
        elif isinstance(deployment_result, DeploymentCurve):
            crowd_curve = None
            deployment_curve = deployment_result.curve_points
    else:
        boundary_v2 = estimate_boundary_v2(crowd_points, cfg.boundary_v2, np.random.default_rng(cfg.seed))
        if isinstance(boundary_v2, BoundaryEstimateV2):
            crowd_curve = boundary_v2.curve_points
            deployment_curve = boundary_v2.offset_points
    if not multi_group_mode:
        resource_decision = (
            ResourcePolicy(cfg.resource_policy).decide(boundary_v2.length, cfg.guide_count)
            if isinstance(boundary_v2, BoundaryEstimateV2)
            else None
        )
        periodic_plan = (
            plan_periodic_arc_coverage(boundary_v2, resource_decision.active_count, PeriodicArcCVTConfig())
            if isinstance(boundary_v2, BoundaryEstimateV2)
            and resource_decision is not None
            and resource_decision.active_count > 0
            else None
        )
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    np.savez_compressed(
        output / "crowd_observation.npz",
        positions=crowd_observation.positions,
        radii=crowd_observation.radii if crowd_observation.radii is not None else np.empty(0),
        demand=crowd_observation.demand if crowd_observation.demand is not None else np.empty(0),
    )
    np.savez_compressed(
        output / "crowd_component_ids.npz",
        evaluator_component_ids=evaluator_labels,
        planning_component_ids=planning_labels,
        group_count=np.array(len(cfg.crowd.groups) if cfg.crowd.is_multi else 1, dtype=int),
        note=np.array(
            "evaluator_ids_from_generator; planning_ids_from_observation_only"
        ),
    )
    if cfg.heterogeneity.enabled:
        np.savez_compressed(
            output / "crowd_attributes.npz",
            agent_id=crowd_attributes["agent_id"],
            radius=crowd_attributes["radius"],
            desired_speed=crowd_attributes["desired_speed"],
            time_gap=crowd_attributes["time_gap"],
            demand=crowd_attributes["demand"],
            heterogeneity_enabled=crowd_attributes["heterogeneity_enabled"],
        )
    np.savez_compressed(output / "crowd_points.npz", positions=crowd_points)
    np.savez_compressed(
        output / "crowd_truth.npz",
        crowd_points=crowd_points,
        boundary_points=truth.boundary_points,
        safety_points=truth.safety_points,
        component_ids=truth.component_ids,
        component_count=np.array(truth.component_count, dtype=int),
        truth_valid=np.array(truth.valid, dtype=bool),
        truth_status=np.array(truth.status),
        shape=np.array(truth.shape),
    )
    np.savez_compressed(
        output / "evaluator_truth.npz",
        boundary_points=truth.boundary_points,
        safety_points=truth.safety_points,
        component_ids=truth.component_ids,
        valid=np.array(truth.valid, dtype=bool),
        status=np.array(truth.status),
        spawn_vertices=np.asarray(cfg.crowd.region_vertices, dtype=float)
        if cfg.crowd.region_vertices is not None
        else np.empty((0, 2)),
        environment_vertices=cfg.scene.boundary_vertices(),
        note=np.array("evaluator_only_not_for_controller"),
    )
    save_boundary_v2_artifacts(output, boundary_v2)
    if isinstance(boundary_v2, BoundaryEstimateV2):
        np.savez_compressed(
            output / "boundary_estimate.npz",
            curve_points=boundary_v2.curve_points,
            offset_points=boundary_v2.offset_points,
            arc_s=boundary_v2.arc_s,
            length=np.array(boundary_v2.length),
        )
        np.savez_compressed(
            output / "deployment_geometry.npz",
            curve_points=boundary_v2.offset_points,
            length=np.array(boundary_v2.length),
        )
    save_resource_decision(output, resource_decision)
    save_periodic_plan_artifacts(output, periodic_plan)

    methods = methods or ["random", "static_circle", "legacy_center_radius", "abcg"]
    resolved_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    with open(output / "config_resolved.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(resolved_config, f, sort_keys=False, allow_unicode=True)

    viewer = renderer if renderer is not None else build_renderer(
        live=live_enabled,
        render_every=cfg.visualization.render_every,
        max_fps=cfg.visualization.max_fps,
        show_trails=cfg.visualization.show_trails,
        block=bool(hold_enabled and live_enabled),
    )
    if live_enabled and isinstance(viewer, NullStep1Renderer):
        print("[live] warning: NullStep1Renderer injected; no GUI window will open.", flush=True)
    elif live_enabled:
        print(
            "[live] visualization enabled "
            f"(hold_window={hold_enabled}).",
            flush=True,
        )
    results: dict[str, MethodSummary] = {}
    assignment_records: dict[str, dict[str, object]] = {}
    episode_records: dict[str, dict[str, object]] = {}
    for method in methods:
        summary, assignment_rec, episode_rec = _run_method(
            method,
            cfg=cfg,
            crowd_points=crowd_points,
            crowd_observation=crowd_observation,
            truth=truth,
            boundary_v2=boundary_v2,
            crowd_curve=crowd_curve,
            deployment_curve=deployment_curve,
            resource_decision=resource_decision,
            periodic_plan=periodic_plan,
            output=output,
            save_plots=save_plots,
            renderer=viewer,
            live=live_enabled,
            planning_labels=planning_labels,
        )
        results[method] = summary
        assignment_records[method] = assignment_rec
        episode_records[method] = episode_rec

    viewer.close()

    with open(output / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(
            build_manifest(
                config_path,
                cfg,
                methods,
                truth,
                boundary_v2,
                resource_decision,
                periodic_plan,
                assignment_records,
                episode_records,
            ),
            f,
            indent=2,
        )

    with open(output / "summary.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    with open(output / "summary.csv", "w", encoding="utf-8", newline="") as f:
        fieldnames = ["method", *next(iter(results.values())).keys()]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for method, row in results.items():
            writer.writerow({"method": method, **row})
    return results
