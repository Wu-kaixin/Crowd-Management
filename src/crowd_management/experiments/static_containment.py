"""Static unknown-crowd containment experiment runner."""
from __future__ import annotations

import csv
import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from ..containment_metrics import containment_summary
from ..controllers import (
    ABCGController,
    ABCGv2Config,
    ABCGv2Controller,
    AssignmentConfig,
    AssignmentResult,
    CoveragePlan,
    EpisodeResult,
    LegacyCenterRadiusController,
    PeriodicArcCVTConfig,
    RandomDeploymentController,
    ResourceDecision,
    ResourcePolicy,
    ResourcePolicyConfig,
    StaticCircleController,
    VelocitySafetyConfig,
    assign_guides_to_targets,
    plan_periodic_arc_coverage,
)
from ..crowd import StaticCrowdConfig, StaticCrowdTruth, generate_static_crowd, generate_static_crowd_truth
from ..estimation import BoundaryEstimateFailure, BoundaryEstimateV2, BoundaryV2Config, estimate_boundary_v2
from ..estimation.boundary import estimate_radial_boundary
from ..types import Array, as_vec2


@dataclass(frozen=True)
class StaticContainmentConfig:
    seed: int
    room_size: Array
    crowd: StaticCrowdConfig
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

    @classmethod
    def from_yaml(cls, path: str | Path) -> "StaticContainmentConfig":
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        seed = int(raw.get("seed", 0))
        room_size = as_vec2(raw.get("room", {}).get("size", [20.0, 14.0]), "room.size")
        containment = raw.get("containment", {})
        coverage_radius = float(containment.get("coverage_radius", 1.2))
        resources = raw.get("resources", {})
        assignment = raw.get("assignment", {})
        motion = raw.get("motion", {})
        safety = raw.get("safety", {})
        boundary = raw.get("boundary", {})
        return cls(
            seed=seed,
            room_size=room_size,
            crowd=StaticCrowdConfig.from_dict(raw["crowd"], seed=seed),
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
                min_crowd_distance=float(
                    safety.get("min_crowd_distance", containment.get("safety_distance", 0.8))
                ),
                room_margin=float(safety.get("room_margin", 0.25)),
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
                    float(boundary["connectivity_radius"])
                    if boundary.get("connectivity_radius") is not None
                    else None
                ),
                connectivity_scale=float(boundary.get("connectivity_scale", 5.0)),
                min_component_fraction=float(boundary.get("min_component_fraction", 0.1)),
                min_observation_coverage=float(boundary.get("min_observation_coverage", 0.8)),
                room_size=tuple(float(value) for value in room_size),
                room_margin=float(boundary.get("room_margin", 0.0)),
                alpha_radius=(
                    float(boundary["alpha_radius"])
                    if boundary.get("alpha_radius") is not None
                    else None
                ),
                alpha_scale=float(boundary.get("alpha_scale", 2.5)),
                alpha_growth_factors=tuple(
                    float(value)
                    for value in boundary.get("alpha_growth_factors", [1.0, 1.25, 1.5, 2.0, 3.0, 4.0])
                ),
                alpha_smoothing_passes=int(boundary.get("alpha_smoothing_passes", 5)),
                bootstrap_samples=int(boundary.get("bootstrap_samples", 0)),
                bootstrap_min_success_fraction=float(
                    boundary.get("bootstrap_min_success_fraction", 0.7)
                ),
                bootstrap_confidence_floor=float(boundary.get("bootstrap_confidence_floor", 0.15)),
                bootstrap_confidence_scale=(
                    float(boundary["bootstrap_confidence_scale"])
                    if boundary.get("bootstrap_confidence_scale") is not None
                    else None
                ),
            ),
        )


def _controller_targets(method: str, cfg: StaticContainmentConfig, crowd_points: Array) -> tuple[Array, Any]:
    method = method.lower()
    if method == "random":
        controller = RandomDeploymentController(cfg.room_size, seed=cfg.seed)
        targets = controller.deploy(cfg.guide_count, crowd_points)
        boundary = estimate_radial_boundary(crowd_points, cfg.boundary_bins, cfg.safety_distance)
        return targets, boundary
    if method == "static_circle":
        radius = cfg.crowd.radius + cfg.safety_distance
        controller = StaticCircleController(radius=radius, center=cfg.crowd.center)
        targets = controller.deploy(cfg.guide_count, crowd_points)
        boundary = estimate_radial_boundary(crowd_points, cfg.boundary_bins, cfg.safety_distance)
        return targets, boundary
    if method == "legacy_center_radius":
        controller = LegacyCenterRadiusController(safety_distance=cfg.safety_distance)
        targets = controller.deploy(cfg.guide_count, crowd_points)
        boundary = estimate_radial_boundary(crowd_points, cfg.boundary_bins, cfg.safety_distance)
        return targets, boundary
    if method == "abcg":
        controller = ABCGController(
            num_bins=cfg.boundary_bins,
            safety_distance=cfg.safety_distance,
            min_guider_distance=cfg.min_guider_distance,
        )
        return controller.deploy(cfg.guide_count, crowd_points, room_size=cfg.room_size)
    raise ValueError(f"Unsupported containment method: {method}")


def _repository_state() -> dict[str, str | bool]:
    repo = Path(__file__).resolve().parents[3]

    def git_output(*args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"

    return {
        "commit": git_output("rev-parse", "HEAD"),
        "branch": git_output("branch", "--show-current"),
        "dirty": bool(git_output("status", "--porcelain")),
    }


def _package_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for distribution in ("crowd-management", "numpy", "pyyaml", "matplotlib"):
        try:
            versions[distribution] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            versions[distribution] = "not-installed"
    return versions


def _build_manifest(
    config_path: Path,
    cfg: StaticContainmentConfig,
    methods: list[str],
    truth: StaticCrowdTruth,
    boundary_v2: BoundaryEstimateV2 | BoundaryEstimateFailure,
    resource_decision: ResourceDecision | None,
    periodic_plan: CoveragePlan | None,
    assignments: dict[str, dict[str, Any]],
    episodes: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    config_bytes = config_path.read_bytes()
    geometry_valid = isinstance(boundary_v2, BoundaryEstimateV2)
    geometry_status = "VALID" if geometry_valid else boundary_v2.status
    plan_valid = periodic_plan is not None and periodic_plan.status == "VALID" and periodic_plan.converged
    plan_status = periodic_plan.status if periodic_plan is not None else "PLAN_SKIPPED_BOUNDARY_INVALID"
    resource_status = (
        resource_decision.status if resource_decision is not None else "RESOURCE_SKIPPED_BOUNDARY_INVALID"
    )
    assignment_failed = any(record["status"] == "ASSIGNMENT_INFEASIBLE" for record in assignments.values())
    episode_statuses = [record["status"] for record in episodes.values()]
    safety_infeasible = any(status == "SAFETY_INFEASIBLE" for status in episode_statuses)
    closed_loop_attempted = any(record["control_steps"] > 0 for record in episodes.values())
    all_converged = bool(episode_statuses) and all(status == "CONVERGED" for status in episode_statuses)
    if not truth.valid:
        run_status = "evaluation_scope_failure"
        stop_reason = truth.status
    elif not geometry_valid:
        run_status = "boundary_geometry_failure"
        stop_reason = geometry_status
    elif resource_status == "CAPACITY_SHORTFALL":
        run_status = "capacity_shortfall"
        stop_reason = resource_status
    elif not plan_valid:
        run_status = "periodic_plan_failure"
        stop_reason = plan_status
    elif assignment_failed:
        run_status = "assignment_failure"
        stop_reason = "ASSIGNMENT_INFEASIBLE"
    elif safety_infeasible:
        run_status = "safety_infeasible"
        stop_reason = "SAFETY_INFEASIBLE"
    elif "TIMEOUT" in episode_statuses:
        run_status = "timeout"
        stop_reason = "TIMEOUT"
    elif not all_converged:
        run_status = "episode_failure"
        stop_reason = next((status for status in episode_statuses if status != "CONVERGED"), "DEGRADED")
    else:
        run_status = "converged"
        stop_reason = "hold_window_satisfied"
    return {
        "schema_version": "step1-pr6-v1",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "run_scope": "alpha_bootstrap_safety_filtered_episode_with_pr6_evidence",
        "closed_loop": closed_loop_attempted,
        "converged": all_converged,
        "run_status": run_status,
        "stop_reason": stop_reason,
        "repository": _repository_state(),
        "config": {
            "source": str(config_path.resolve()),
            "sha256": hashlib.sha256(config_bytes).hexdigest(),
            "seed": cfg.seed,
        },
        "environment": {
            "python": sys.version.split()[0],
            "python_executable": sys.executable,
            "platform": platform.platform(),
            "packages": _package_versions(),
        },
        "methods": methods,
        "truth_boundary": {
            "shape": truth.shape,
            "status": truth.status,
            "valid_for_step1": truth.valid,
            "component_count": truth.component_count,
            "reference": truth.diagnostics["reference"],
        },
        "boundary_v2": {
            "status": geometry_status,
            "valid": geometry_valid,
            "component_count": boundary_v2.component_count,
            "method": boundary_v2.method,
            "version": boundary_v2.version,
            "length": boundary_v2.length if geometry_valid else None,
            "confidence_status": boundary_v2.diagnostics.get("confidence_status", "not_available"),
            "uncertainty_mean": boundary_v2.diagnostics.get("uncertainty_mean"),
            "confidence_mean": boundary_v2.diagnostics.get("confidence_mean"),
        },
        "resource_decision": _resource_record(resource_decision),
        "periodic_plan": {
            "status": plan_status,
            "valid": plan_valid,
            "converged": bool(periodic_plan.converged) if periodic_plan is not None else False,
            "active_count": periodic_plan.active_count if periodic_plan is not None else 0,
            "h_initial": float(periodic_plan.h_history[0]) if periodic_plan is not None else None,
            "h_final": float(periodic_plan.h_history[-1]) if periodic_plan is not None else None,
            "max_arc_gap": float(periodic_plan.max_arc_gap) if periodic_plan is not None else None,
            "density_model": periodic_plan.diagnostics.get("density_model") if periodic_plan is not None else None,
            "confidence_role": periodic_plan.diagnostics.get("confidence_role") if periodic_plan is not None else None,
            "confidence_source": periodic_plan.diagnostics.get("confidence_source") if periodic_plan is not None else None,
            "config": periodic_plan.diagnostics.get("config") if periodic_plan is not None else None,
        },
        "assignments": assignments,
        "episodes": episodes,
        "velocity_safety": {
            "status": "ENABLED_PR5" if cfg.safety.enabled else "DISABLED_PR5",
            "projection": "ordered_halfspaces_plus_speed_balls_dykstra",
            "config": {
                "enabled": cfg.safety.enabled,
                "min_guide_distance": cfg.safety.min_guide_distance,
                "min_crowd_distance": cfg.safety.min_crowd_distance,
                "room_margin": cfg.safety.room_margin,
                "residual_tolerance": cfg.safety.residual_tolerance,
                "max_projection_sweeps": cfg.safety.max_projection_sweeps,
            },
        },
        "limitations": [
            "PR5 uses fixed static targets and does not re-estimate or re-plan during an episode.",
            "max_boundary_gap is retained only as a deprecated serialized alias for an Euclidean distance.",
            "Existing endpoint baseline outputs seed PR4 guide initial positions; autonomous search/deployment is not modeled.",
            "PR5 applies sampled-data half-space projection and finite emergency stop; it is not ORCA or a CBF.",
            "No continuous-time forward-invariance claim is made from the discrete PR5 constraints.",
            "The hysteresis policy is sequence-tested, but this static one-shot runner has no prior active count.",
            "The confidence-gated Lloyd gain is implemented, but PR1 inputs remain neutral placeholders until PR6 bootstrap estimation.",
            "The single-run manifest is not a substitute for the separate paired PR6 evaluation.",
        ],
    }


def _resource_record(resource_decision: ResourceDecision | None) -> dict[str, Any]:
    if resource_decision is None:
        return {
            "status": "RESOURCE_SKIPPED_BOUNDARY_INVALID",
            "requested_count": 0,
            "desired_count": 0,
            "active_count": 0,
            "reserve_count": 0,
            "unmet_target_count": 0,
            "hysteresis_applied": False,
            "diagnostics": {"reason": "boundary_v2_invalid"},
        }
    return {
        "status": resource_decision.status,
        "requested_count": resource_decision.requested_count,
        "desired_count": resource_decision.desired_count,
        "active_count": resource_decision.active_count,
        "reserve_count": resource_decision.reserve_count,
        "unmet_target_count": resource_decision.unmet_target_count,
        "previous_active_count": resource_decision.previous_active_count,
        "hysteresis_applied": resource_decision.hysteresis_applied,
        "diagnostics": resource_decision.diagnostics,
    }


def _save_resource_decision(output: Path, resource_decision: ResourceDecision | None) -> None:
    with open(output / "resource_decision.json", "w", encoding="utf-8") as f:
        json.dump(_resource_record(resource_decision), f, indent=2)


def _assignment_record(assignment: AssignmentResult | None) -> dict[str, Any]:
    if assignment is None:
        return {
            "status": "ASSIGNMENT_SKIPPED_PLAN_INVALID",
            "reserve_count": 0,
            "unmet_target_count": 0,
            "switch_count": 0,
            "total_cost": None,
            "input_role": "pr4_initial_state_from_endpoint_baseline",
            "diagnostics": {"reason": "periodic_plan_invalid_or_skipped"},
        }
    return {
        "status": assignment.status,
        "reserve_count": int(len(assignment.reserve_guide_ids)),
        "unmet_target_count": int(len(assignment.unmet_target_ids)),
        "switch_count": assignment.switch_count,
        "total_cost": assignment.total_cost,
        "input_role": "pr4_initial_state_from_endpoint_baseline",
        "diagnostics": assignment.diagnostics,
    }


def _save_assignment_artifacts(method_dir: Path, assignment: AssignmentResult | None) -> dict[str, Any]:
    record = _assignment_record(assignment)
    with open(method_dir / "assignment_status.json", "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2)
    if assignment is None or assignment.status == "ASSIGNMENT_INFEASIBLE":
        return record
    np.savez_compressed(
        method_dir / "assignment.npz",
        guide_to_target=assignment.guide_to_target,
        target_to_guide=assignment.target_to_guide,
        reserve_guide_ids=assignment.reserve_guide_ids,
        unmet_target_ids=assignment.unmet_target_ids,
        cost_matrix=assignment.cost_matrix,
        total_cost=np.array(assignment.total_cost, dtype=float),
        switch_count=np.array(assignment.switch_count, dtype=int),
        status=np.array(assignment.status),
    )
    return record


def _episode_record(episode: EpisodeResult | None, skipped_status: str) -> dict[str, Any]:
    if episode is None:
        return {
            "status": skipped_status,
            "converged": False,
            "state_frames": 0,
            "control_steps": 0,
            "initial_tracking_rmse": None,
            "final_tracking_rmse": None,
            "max_applied_speed": None,
            "safety_filter_status": "not_available",
            "safety_projected_steps": 0,
            "safety_infeasible_steps": 0,
            "safety_max_residual_after": None,
            "stop_reason": "episode_precondition_unavailable",
            "trace_available": False,
            "diagnostics": {"reason": "valid_plan_and_assignment_required"},
        }
    return {
        "status": episode.status,
        "converged": episode.converged,
        "state_frames": int(len(episode.positions)),
        "control_steps": int(len(episode.applied_controls)),
        "initial_tracking_rmse": float(episode.tracking_rmse[0]),
        "final_tracking_rmse": float(episode.tracking_rmse[-1]),
        "max_applied_speed": float(np.max(episode.max_speed_history)),
        "safety_filter_status": episode.diagnostics.get("safety_filter_status", "not_available"),
        "safety_projected_steps": int(episode.diagnostics.get("safety_projected_steps", 0)),
        "safety_infeasible_steps": int(episode.diagnostics.get("safety_infeasible_steps", 0)),
        "safety_max_residual_after": float(
            episode.diagnostics.get("safety_max_residual_after", 0.0)
        ),
        "stop_reason": episode.stop_reason,
        "trace_available": True,
        "diagnostics": episode.diagnostics,
    }


def _save_episode_artifacts(
    method_dir: Path,
    episode: EpisodeResult | None,
    skipped_status: str,
) -> dict[str, Any]:
    record = _episode_record(episode, skipped_status)
    with open(method_dir / "episode_status.json", "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2)
    if episode is None:
        return record
    np.savez_compressed(
        method_dir / "episode.npz",
        times=episode.times,
        positions=episode.positions,
        velocities=episode.velocities,
        nominal_controls=episode.nominal_controls,
        applied_controls=episode.applied_controls,
        state_history=episode.state_history,
        tracking_rmse=episode.tracking_rmse,
        max_speed_history=episode.max_speed_history,
        hold_count_history=episode.hold_count_history,
        target_positions=episode.target_positions,
        guide_to_target=episode.guide_to_target,
        reserve_guide_ids=episode.reserve_guide_ids,
        safety_status_history=episode.safety_status_history,
        safety_constraint_count=episode.safety_constraint_count,
        safety_guide_pair_constraint_count=episode.safety_guide_pair_constraint_count,
        safety_crowd_constraint_count=episode.safety_crowd_constraint_count,
        safety_room_constraint_count=episode.safety_room_constraint_count,
        safety_violated_constraint_count=episode.safety_violated_constraint_count,
        safety_projection_sweeps=episode.safety_projection_sweeps,
        safety_max_residual_before=episode.safety_max_residual_before,
        safety_max_residual_after=episode.safety_max_residual_after,
        safety_max_guide_pair_residual_after=episode.safety_max_guide_pair_residual_after,
        safety_max_crowd_residual_after=episode.safety_max_crowd_residual_after,
        safety_max_room_residual_after=episode.safety_max_room_residual_after,
        safety_control_adjustment_norm=episode.safety_control_adjustment_norm,
        safety_emergency_stop_history=episode.safety_emergency_stop_history,
        status=np.array(episode.status),
        converged=np.array(episode.converged, dtype=bool),
        stop_reason=np.array(episode.stop_reason),
    )
    return record


def _save_boundary_v2_artifacts(
    output: Path,
    boundary_v2: BoundaryEstimateV2 | BoundaryEstimateFailure,
) -> None:
    valid = isinstance(boundary_v2, BoundaryEstimateV2)
    status = "VALID" if valid else boundary_v2.status
    status_record = {
        "status": status,
        "valid": valid,
        "component_count": boundary_v2.component_count,
        "method": boundary_v2.method,
        "version": boundary_v2.version,
        "diagnostics": boundary_v2.diagnostics,
    }
    with open(output / "boundary_v2_status.json", "w", encoding="utf-8") as f:
        json.dump(status_record, f, indent=2)
    if not valid:
        return
    np.savez_compressed(
        output / "boundary_v2.npz",
        curve_points=boundary_v2.curve_points,
        offset_points=boundary_v2.offset_points,
        arc_s=boundary_v2.arc_s,
        length=np.array(boundary_v2.length, dtype=float),
        tangents=boundary_v2.tangents,
        outward_normals=boundary_v2.outward_normals,
        uncertainty=boundary_v2.uncertainty,
        confidence=boundary_v2.confidence,
    )


def _save_periodic_plan_artifacts(output: Path, periodic_plan: CoveragePlan | None) -> None:
    valid = periodic_plan is not None and periodic_plan.status == "VALID" and periodic_plan.converged
    status = periodic_plan.status if periodic_plan is not None else "PLAN_SKIPPED_BOUNDARY_INVALID"
    status_record: dict[str, Any] = {
        "status": status,
        "valid": valid,
        "converged": bool(periodic_plan.converged) if periodic_plan is not None else False,
        "active_count": periodic_plan.active_count if periodic_plan is not None else 0,
        "diagnostics": periodic_plan.diagnostics if periodic_plan is not None else {
            "reason": "boundary_v2_invalid",
        },
    }
    if periodic_plan is not None:
        status_record.update(
            {
                "h_initial": float(periodic_plan.h_history[0]),
                "h_final": float(periodic_plan.h_history[-1]),
                "max_arc_gap": float(periodic_plan.max_arc_gap),
            }
        )
    with open(output / "periodic_plan_status.json", "w", encoding="utf-8") as f:
        json.dump(status_record, f, indent=2)
    if not valid or periodic_plan is None:
        return
    np.savez_compressed(
        output / "periodic_plan.npz",
        target_s=periodic_plan.target_s,
        target_xy=periodic_plan.target_xy,
        cell_bounds=periodic_plan.cell_bounds,
        cell_mass=periodic_plan.cell_mass,
        h_history=periodic_plan.h_history,
        gain_history=periodic_plan.gain_history,
        max_arc_gap=np.array(periodic_plan.max_arc_gap, dtype=float),
        active_count=np.array(periodic_plan.active_count, dtype=int),
        converged=np.array(periodic_plan.converged, dtype=bool),
        status=np.array(periodic_plan.status),
    )


def run_static_containment(
    config_path: str | Path,
    output_dir: str | Path,
    methods: list[str] | None = None,
    save_plots: bool = True,
) -> dict[str, dict[str, float | int | str]]:
    config_path = Path(config_path)
    cfg = StaticContainmentConfig.from_yaml(config_path)
    crowd_points = generate_static_crowd(cfg.crowd)
    truth = generate_static_crowd_truth(cfg.crowd, safety_distance=cfg.safety_distance)
    boundary_v2 = estimate_boundary_v2(crowd_points, cfg.boundary_v2, np.random.default_rng(cfg.seed))
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
    _save_boundary_v2_artifacts(output, boundary_v2)
    _save_resource_decision(output, resource_decision)
    _save_periodic_plan_artifacts(output, periodic_plan)

    methods = methods or ["random", "static_circle", "legacy_center_radius", "abcg"]
    resolved_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    with open(output / "config_resolved.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(resolved_config, f, sort_keys=False, allow_unicode=True)
    results: dict[str, dict[str, float | int | str]] = {}
    assignment_records: dict[str, dict[str, Any]] = {}
    episode_records: dict[str, dict[str, Any]] = {}
    for method in methods:
        targets, boundary = _controller_targets(method, cfg, crowd_points)
        initial_summary = containment_summary(
            targets,
            crowd_points,
            boundary,
            cfg.coverage_radius,
            cfg.safety_distance,
            truth_boundary=truth,
        )
        geometry_valid = isinstance(boundary_v2, BoundaryEstimateV2)
        plan_valid = periodic_plan is not None and periodic_plan.status == "VALID" and periodic_plan.converged
        resource_status = (
            resource_decision.status if resource_decision is not None else "RESOURCE_SKIPPED_BOUNDARY_INVALID"
        )
        assignment_result = (
            assign_guides_to_targets(targets, periodic_plan.target_xy, cfg.assignment)
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
        episode_result = (
            ABCGv2Controller(cfg.motion, cfg.safety).run_fixed_target_episode(
                targets,
                periodic_plan.target_xy,
                assignment_result,
                precondition_status=resource_status,
                crowd_points=crowd_points,
                room_size=cfg.room_size,
            )
            if periodic_plan is not None and assignment_result is not None
            else None
        )
        final_guide_points = episode_result.positions[-1] if episode_result is not None else targets
        summary = containment_summary(
            final_guide_points,
            crowd_points,
            boundary,
            cfg.coverage_radius,
            cfg.safety_distance,
            truth_boundary=truth,
        )
        summary["metrics_position_source"] = (
            "episode_final_frame" if episode_result is not None else "endpoint_baseline_no_episode"
        )
        summary["initial_endpoint_coverage_ratio"] = initial_summary["coverage_ratio"]
        summary["initial_endpoint_max_euclidean_boundary_distance"] = initial_summary[
            "max_euclidean_boundary_distance"
        ]
        summary["boundary_v2_status"] = "VALID" if geometry_valid else boundary_v2.status
        summary["boundary_v2_method"] = boundary_v2.method
        summary["boundary_confidence_status"] = boundary_v2.diagnostics.get(
            "confidence_status", "not_available"
        )
        summary["periodic_plan_status"] = (
            periodic_plan.status if periodic_plan is not None else "PLAN_SKIPPED_BOUNDARY_INVALID"
        )
        summary["periodic_max_arc_gap"] = (
            float(periodic_plan.max_arc_gap) if periodic_plan is not None else "not_available"
        )
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
        summary["safety_filter_status"] = (
            episode_result.diagnostics.get("safety_filter_status", "not_available")
            if episode_result is not None
            else "not_available"
        )
        summary["safety_projected_steps"] = (
            int(episode_result.diagnostics.get("safety_projected_steps", 0))
            if episode_result is not None
            else 0
        )
        summary["safety_infeasible_steps"] = (
            int(episode_result.diagnostics.get("safety_infeasible_steps", 0))
            if episode_result is not None
            else 0
        )
        summary["safety_max_residual_after"] = (
            float(episode_result.diagnostics.get("safety_max_residual_after", 0.0))
            if episode_result is not None
            else "not_available"
        )
        summary["method_status"] = (
            "converged_pr5_safety_filtered_episode"
            if truth.valid
            and geometry_valid
            and resource_status == "VALID"
            and plan_valid
            and assignment_result is not None
            and assignment_result.status == "VALID"
            and episode_result is not None
            and episode_result.status == "CONVERGED"
            else "diagnostic_only"
        )
        results[method] = summary
        method_dir = output / method
        method_dir.mkdir(parents=True, exist_ok=True)
        assignment_records[method] = _save_assignment_artifacts(method_dir, assignment_result)
        episode_records[method] = _save_episode_artifacts(method_dir, episode_result, episode_skipped_status)
        np.savez_compressed(
            method_dir / "containment_state.npz",
            crowd_points=crowd_points,
            guide_points=final_guide_points,
            guide_initial_points=targets,
            guide_final_points=final_guide_points,
            boundary_points=boundary.boundary_points,
            safety_points=boundary.safety_points,
            center=boundary.center,
        )
        with open(method_dir / "metrics.json", "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        if save_plots:
            from ..containment_visualization import plot_static_containment

            plot_static_containment(
                crowd_points,
                final_guide_points,
                boundary,
                method_dir / "containment.png",
                title=f"{method}: static containment",
            )

    with open(output / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(
            _build_manifest(
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
