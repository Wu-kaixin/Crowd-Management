"""Manifest status machine for static containment runs.

ROLE: ORCHESTRATION — decide run_status/stop_reason; assemble manifest dict.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ...controllers import CoveragePlan, ResourceDecision
from ...crowd import StaticCrowdTruth
from ...estimation import BoundaryEstimateFailure, BoundaryEstimateV2
from ...evaluation.schemas import STATIC_MANIFEST_SCHEMA
from ...reporting import python_environment, repository_state
from .config import StaticContainmentConfig
from .records import RunStatusDecision, StaticManifest


def resolve_run_status(
    truth: StaticCrowdTruth,
    boundary_v2: BoundaryEstimateV2 | BoundaryEstimateFailure,
    resource_decision: ResourceDecision | None,
    periodic_plan: CoveragePlan | None,
    assignments: dict[str, dict[str, Any]],
    episodes: dict[str, dict[str, Any]],
) -> RunStatusDecision:
    """Map upstream/artifact statuses onto a single run_status / stop_reason."""
    if isinstance(boundary_v2, BoundaryEstimateV2):
        geometry_valid = True
        geometry_status = "VALID"
        boundary_length: float | None = boundary_v2.length
    else:
        geometry_valid = False
        geometry_status = boundary_v2.status
        boundary_length = None
    plan_valid = periodic_plan is not None and periodic_plan.status == "VALID" and periodic_plan.converged
    plan_status = periodic_plan.status if periodic_plan is not None else "PLAN_SKIPPED_BOUNDARY_INVALID"
    resource_status = resource_decision.status if resource_decision is not None else "RESOURCE_SKIPPED_BOUNDARY_INVALID"
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
        "run_status": run_status,
        "stop_reason": stop_reason,
        "closed_loop": closed_loop_attempted,
        "converged": all_converged,
        "geometry_valid": geometry_valid,
        "geometry_status": geometry_status,
        "plan_valid": plan_valid,
        "plan_status": plan_status,
        "resource_status": resource_status,
        "boundary_length": boundary_length,
    }


def resource_record(resource_decision: ResourceDecision | None) -> dict[str, Any]:
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


def build_manifest(
    config_path: Path,
    cfg: StaticContainmentConfig,
    methods: list[str],
    truth: StaticCrowdTruth,
    boundary_v2: BoundaryEstimateV2 | BoundaryEstimateFailure,
    resource_decision: ResourceDecision | None,
    periodic_plan: CoveragePlan | None,
    assignments: dict[str, dict[str, Any]],
    episodes: dict[str, dict[str, Any]],
) -> StaticManifest:
    config_bytes = config_path.read_bytes()
    decision = resolve_run_status(truth, boundary_v2, resource_decision, periodic_plan, assignments, episodes)
    return {
        "schema_version": STATIC_MANIFEST_SCHEMA,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "run_scope": "alpha_bootstrap_safety_filtered_episode_with_pr6_evidence",
        "closed_loop": decision["closed_loop"],
        "converged": decision["converged"],
        "run_status": decision["run_status"],
        "stop_reason": decision["stop_reason"],
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
            "status": decision["geometry_status"],
            "valid": decision["geometry_valid"],
            "component_count": boundary_v2.component_count,
            "method": boundary_v2.method,
            "version": boundary_v2.version,
            "length": decision.get("boundary_length"),
            "confidence_status": boundary_v2.diagnostics.get("confidence_status", "not_available"),
            "uncertainty_mean": boundary_v2.diagnostics.get("uncertainty_mean"),
            "confidence_mean": boundary_v2.diagnostics.get("confidence_mean"),
        },
        "resource_decision": resource_record(resource_decision),
        "periodic_plan": {
            "status": decision["plan_status"],
            "valid": decision["plan_valid"],
            "converged": bool(periodic_plan.converged) if periodic_plan is not None else False,
            "active_count": periodic_plan.active_count if periodic_plan is not None else 0,
            "h_initial": float(periodic_plan.h_history[0]) if periodic_plan is not None else None,
            "h_final": float(periodic_plan.h_history[-1]) if periodic_plan is not None else None,
            "max_arc_gap": float(periodic_plan.max_arc_gap) if periodic_plan is not None else None,
            "density_model": periodic_plan.diagnostics.get("density_model") if periodic_plan is not None else None,
            "confidence_role": periodic_plan.diagnostics.get("confidence_role") if periodic_plan is not None else None,
            "confidence_source": (
                periodic_plan.diagnostics.get("confidence_source") if periodic_plan is not None else None
            ),
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
            (
                "Existing endpoint baseline outputs seed PR4 guide initial positions; "
                "autonomous search/deployment is not modeled."
            ),
            "PR5 applies sampled-data half-space projection and finite emergency stop; it is not ORCA or a CBF.",
            "No continuous-time forward-invariance claim is made from the discrete PR5 constraints.",
            "The hysteresis policy is sequence-tested, but this static one-shot runner has no prior active count.",
            (
                "The confidence-gated Lloyd gain is implemented, but PR1 inputs remain "
                "neutral placeholders until PR6 bootstrap estimation."
            ),
            "The single-run manifest is not a substitute for the separate paired PR6 evaluation.",
        ],
    }
