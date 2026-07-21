"""Artifact writers for static containment experiments."""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from ...controllers import AssignmentResult, CoveragePlan, EpisodeResult, ResourceDecision
from ...crowd import StaticCrowdTruth
from ...estimation import BoundaryEstimateFailure, BoundaryEstimateV2
from ...reporting import python_environment, repository_state
from .config import StaticContainmentConfig


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
        "repository": repository_state(),
        "config": {
            "source": str(config_path.resolve()),
            "sha256": hashlib.sha256(config_bytes).hexdigest(),
            "seed": cfg.seed,
        },
        "environment": python_environment(),
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
