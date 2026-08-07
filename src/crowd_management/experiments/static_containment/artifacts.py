"""Artifact writers for static containment experiments.

ROLE: OUTPUT — serialize boundary/plan/assignment/episode under the run dir.
Manifest assembly lives in manifest.py. Public writers have no leading underscore.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from ...controllers import AssignmentResult, CoveragePlan, EpisodeResult, ResourceDecision
from ...estimation import BoundaryEstimateFailure, BoundaryEstimateV2
from .manifest import build_manifest, resource_record


def diag_int(diagnostics: dict[str, object], key: str, default: int = 0) -> int:
    value = diagnostics.get(key, default)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        return int(value)
    return default


def diag_float(diagnostics: dict[str, object], key: str, default: float = 0.0) -> float:
    value = diagnostics.get(key, default)
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        return float(value)
    return default


def save_resource_decision(output: Path, resource_decision: ResourceDecision | None) -> None:
    with open(output / "resource_decision.json", "w", encoding="utf-8") as f:
        json.dump(resource_record(resource_decision), f, indent=2)


def assignment_record(assignment: AssignmentResult | None) -> dict[str, Any]:
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


def save_assignment_artifacts(method_dir: Path, assignment: AssignmentResult | None) -> dict[str, Any]:
    record = assignment_record(assignment)
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


def episode_record(episode: EpisodeResult | None, skipped_status: str) -> dict[str, Any]:
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
        "safety_filter_status": str(episode.diagnostics.get("safety_filter_status", "not_available")),
        "safety_projected_steps": diag_int(episode.diagnostics, "safety_projected_steps", 0),
        "safety_infeasible_steps": diag_int(episode.diagnostics, "safety_infeasible_steps", 0),
        "safety_max_residual_after": diag_float(episode.diagnostics, "safety_max_residual_after", 0.0),
        "stop_reason": episode.stop_reason,
        "trace_available": True,
        "diagnostics": episode.diagnostics,
    }


def save_episode_artifacts(
    method_dir: Path,
    episode: EpisodeResult | None,
    skipped_status: str,
) -> dict[str, Any]:
    record = episode_record(episode, skipped_status)
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


def save_boundary_v2_artifacts(
    output: Path,
    boundary_v2: BoundaryEstimateV2 | BoundaryEstimateFailure,
) -> None:
    if isinstance(boundary_v2, BoundaryEstimateV2):
        status_record = {
            "status": "VALID",
            "valid": True,
            "component_count": boundary_v2.component_count,
            "method": boundary_v2.method,
            "version": boundary_v2.version,
            "diagnostics": boundary_v2.diagnostics,
        }
        with open(output / "boundary_v2_status.json", "w", encoding="utf-8") as f:
            json.dump(status_record, f, indent=2)
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
        return
    status_record = {
        "status": boundary_v2.status,
        "valid": False,
        "component_count": boundary_v2.component_count,
        "method": boundary_v2.method,
        "version": boundary_v2.version,
        "diagnostics": boundary_v2.diagnostics,
    }
    with open(output / "boundary_v2_status.json", "w", encoding="utf-8") as f:
        json.dump(status_record, f, indent=2)


def save_periodic_plan_artifacts(output: Path, periodic_plan: CoveragePlan | None) -> None:
    valid = periodic_plan is not None and periodic_plan.status == "VALID" and periodic_plan.converged
    status = periodic_plan.status if periodic_plan is not None else "PLAN_SKIPPED_BOUNDARY_INVALID"
    status_record: dict[str, Any] = {
        "status": status,
        "valid": valid,
        "converged": bool(periodic_plan.converged) if periodic_plan is not None else False,
        "active_count": periodic_plan.active_count if periodic_plan is not None else 0,
        "diagnostics": periodic_plan.diagnostics
        if periodic_plan is not None
        else {
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


__all__ = [
    "assignment_record",
    "build_manifest",
    "diag_float",
    "diag_int",
    "episode_record",
    "save_assignment_artifacts",
    "save_boundary_v2_artifacts",
    "save_episode_artifacts",
    "save_periodic_plan_artifacts",
    "save_resource_decision",
]
