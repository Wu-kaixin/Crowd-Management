"""Primary G6 case execution and per-run artifact writing."""
from __future__ import annotations

import json
import time
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import numpy as np
from shapely.geometry import LineString

from ...containment_metrics import coverage_ratio_to_points, max_euclidean_boundary_distance_to_points
from ...controllers import (
    ABCGController,
    ABCGv2Config,
    ABCGv2Controller,
    AssignmentConfig,
    PeriodicArcCVTConfig,
    ResourcePolicyConfig,
    VelocitySafetyConfig,
    allocate_guide_resources,
    assign_guides_to_targets,
    integrate_guide_positions,
    plan_equal_arc_coverage,
    plan_periodic_arc_coverage,
    periodic_uniform_coverage_cost,
)
from ...estimation import BoundaryEstimateFailure, BoundaryEstimateV2, estimate_boundary_v2
from ...geometry import max_consecutive_arc_gap
from ...reporting import jsonable as _jsonable
from ...reporting import write_json as _write_json
from ...types import Array
from ..shared import curve_errors_with_p95 as _curve_errors
from .cases import _boundary_config, _initial_guides, _neutralize_confidence, _observed_case
from .config import G6EvaluationConfig, PRIMARY_SCENARIOS


def _nearest_arc_coordinates(targets: Array, boundary: BoundaryEstimateV2) -> Array:
    distances = np.linalg.norm(targets[:, None, :] - boundary.offset_points[None, :, :], axis=2)
    indices = np.unique(np.argmin(distances, axis=1))
    return np.sort(boundary.arc_s[indices])


def _plan_metrics(targets: Array, boundary: BoundaryEstimateV2) -> tuple[Array, float, float]:
    target_s = _nearest_arc_coordinates(targets, boundary)
    return (
        target_s,
        periodic_uniform_coverage_cost(target_s, boundary.length),
        max_consecutive_arc_gap(target_s, boundary.length),
    )


def _make_targets(
    method: str,
    observation: Array,
    boundary: BoundaryEstimateV2,
    config: G6EvaluationConfig,
) -> tuple[Array, Array, Array, dict[str, Any]]:
    fixed = min(config.fixed_guide_count, config.available_guides)
    h_history = np.empty(0, dtype=float)
    if method == "endpoint_abcg":
        targets, _ = ABCGController(safety_distance=config.safety_distance).deploy(
            fixed, observation, np.asarray(config.room_size)
        )
        target_s, h_final, gap = _plan_metrics(targets, boundary)
        h_history = np.array([h_final])
        details = {"planner": "current_endpoint_radial_cvt", "active_count": len(targets)}
    elif method == "uniform_angular":
        center = np.mean(observation, axis=0)
        radius = float(np.percentile(np.linalg.norm(observation - center, axis=1), 96.0) + config.safety_distance)
        angles = np.linspace(0.0, 2.0 * np.pi, fixed, endpoint=False)
        targets = center + radius * np.column_stack((np.cos(angles), np.sin(angles)))
        targets = np.clip(targets, 0.2, np.asarray(config.room_size) - 0.2)
        target_s, h_final, gap = _plan_metrics(targets, boundary)
        h_history = np.array([h_final])
        details = {"planner": "uniform_angular", "active_count": len(targets)}
    elif method == "uniform_arc":
        plan = plan_equal_arc_coverage(boundary, fixed)
        targets, target_s, h_history, gap = plan.target_xy, plan.target_s, plan.h_history, plan.max_arc_gap
        details = {"planner": "uniform_arc", "active_count": plan.active_count, "plan_status": plan.status}
    elif method == "fixed_m_periodic":
        plan = plan_periodic_arc_coverage(
            _neutralize_confidence(boundary), fixed, PeriodicArcCVTConfig(max_iterations=200)
        )
        targets, target_s, h_history, gap = plan.target_xy, plan.target_s, plan.h_history, plan.max_arc_gap
        details = {
            "planner": "fixed_m_periodic_cvt",
            "active_count": plan.active_count,
            "plan_status": plan.status,
            "confidence_role": "ablated",
        }
    elif method == "abcg_v2":
        resource = allocate_guide_resources(
            boundary.length,
            config.available_guides,
            ResourcePolicyConfig(g_req=config.required_arc_gap, m_min=4),
        )
        if resource.status != "VALID":
            raise RuntimeError(f"{resource.status}: {resource.diagnostics['reason']}")
        plan = plan_periodic_arc_coverage(
            boundary, resource.active_count, PeriodicArcCVTConfig(max_iterations=200)
        )
        targets, target_s, h_history, gap = plan.target_xy, plan.target_s, plan.h_history, plan.max_arc_gap
        details = {
            "planner": "abcg_v2_periodic_confidence_gated",
            "active_count": plan.active_count,
            "reserve_count": resource.reserve_count,
            "resource": asdict(resource),
            "plan_status": plan.status,
            "confidence_role": "lloyd_gain_only",
        }
    else:
        raise ValueError(f"unsupported method: {method}")
    if len(targets) == 0 or not np.all(np.isfinite(targets)):
        raise RuntimeError("PLAN_INVALID: no finite targets")
    return targets, target_s, h_history, {**details, "plan_h_final": float(h_history[-1]), "plan_max_arc_gap": float(gap)}


def _minimum_pair_distance(points: Array) -> float:
    if len(points) < 2:
        return float("inf")
    distance = np.linalg.norm(points[:, None, :] - points[None, :, :], axis=2)
    distance[np.diag_indices(len(points))] = np.inf
    return float(np.min(distance))


def _trajectory_crossings(positions: Array, active_ids: Array) -> int:
    lines: list[LineString] = []
    for guide_id in active_ids:
        path = positions[:, int(guide_id), :]
        if len(path) >= 2 and np.any(np.linalg.norm(np.diff(path, axis=0), axis=1) > 1.0e-12):
            lines.append(LineString(path))
    return int(sum(lines[i].crosses(lines[j]) for i in range(len(lines)) for j in range(i + 1, len(lines))))


def _run_feedback_episode(
    observation: Array,
    initial: Array,
    targets: Array,
    assignment: Any,
    config: G6EvaluationConfig,
) -> tuple[dict[str, Array], list[dict[str, Any]], dict[str, Any]]:
    controller = ABCGv2Controller(
        ABCGv2Config(
            dt=config.dt,
            k_p=1.2,
            v_max=0.8,
            tracking_rmse_tolerance=0.05,
            speed_tolerance=0.05,
            hold_steps=4,
            max_steps=config.max_steps,
        ),
        VelocitySafetyConfig(
            enabled=True,
            min_guide_distance=0.35,
            min_crowd_distance=0.60,
            room_margin=0.20,
            max_projection_sweeps=120,
        ),
    )
    controller.reset(targets, assignment, initial, room_size=np.asarray(config.room_size))
    positions = [initial.copy()]
    preferred: list[Array] = []
    applied: list[Array] = []
    states: list[str] = ["INIT"]
    tracking = []
    safety_status: list[str] = []
    events: list[dict[str, Any]] = []
    current = initial.copy()
    control_started = time.perf_counter()
    for step_index in range(config.max_steps + 1):
        output = controller.step(observation, current, config.dt)
        preferred.append(output.preferred_velocity.copy())
        applied.append(output.safe_velocity.copy())
        states.append(output.state)
        tracking.append(float(output.diagnostics["tracking_rmse"]))
        safety_status.append(str(output.diagnostics["safety_status"]))
        for event in output.events:
            events.append({"step": step_index, "time": step_index * config.dt, "event": event})
        if output.state in {
            "CONVERGED",
            "DEGRADED",
            "BOUNDARY_INVALID",
            "OFFSET_INVALID",
            "CAPACITY_SHORTFALL",
            "ASSIGNMENT_INFEASIBLE",
            "SAFETY_INFEASIBLE",
            "TIMEOUT",
        }:
            break
        current = integrate_guide_positions(current, output.safe_velocity, config.dt)
        positions.append(current.copy())
    control_runtime_ms = 1000.0 * (time.perf_counter() - control_started)
    position_array = np.asarray(positions, dtype=float)
    preferred_array = np.asarray(preferred, dtype=float)
    applied_array = np.asarray(applied, dtype=float)
    trace = {
        "time": np.arange(len(position_array), dtype=float) * config.dt,
        "positions": position_array,
        "preferred_velocity": preferred_array,
        "safe_velocity": applied_array,
        "states": np.asarray(states),
        "tracking_rmse": np.asarray(tracking, dtype=float),
        "safety_status": np.asarray(safety_status),
    }
    active_ids = np.flatnonzero(np.asarray(assignment.guide_to_target) >= 0)
    step_distance = np.linalg.norm(np.diff(position_array, axis=0), axis=2) if len(position_array) > 1 else np.empty((0, len(initial)))
    control_energy = float(config.dt * np.sum(np.sum(applied_array**2, axis=2))) if len(applied_array) else 0.0
    trace_memory = int(sum(array.nbytes for array in trace.values() if isinstance(array, np.ndarray)))
    final_tracking = float(tracking[-1]) if tracking else None
    convergence_time = float((len(position_array) - 1) * config.dt) if states[-1] == "CONVERGED" else None
    metrics = {
        "episode_status": states[-1],
        "success": states[-1] == "CONVERGED",
        "tracking_rmse_initial": float(tracking[0]) if tracking else None,
        "tracking_rmse_final": final_tracking,
        "convergence_time_s": convergence_time,
        "path_length_m": float(np.sum(step_distance)),
        "control_energy_m2_per_s": control_energy,
        "trajectory_crossing_count": _trajectory_crossings(position_array, active_ids),
        "min_guide_guide_clearance_m": float(min(_minimum_pair_distance(frame) for frame in position_array)),
        "min_guide_crowd_clearance_m": float(
            min(np.min(np.linalg.norm(frame[:, None, :] - observation[None, :, :], axis=2)) for frame in position_array)
        ),
        "safety_projection_count": int(sum(item == "PROJECTED" for item in safety_status)),
        "safety_infeasible_count": int(sum(item == "SAFETY_INFEASIBLE" for item in safety_status)),
        "control_runtime_ms": control_runtime_ms,
        "trace_memory_bytes": trace_memory,
    }
    return trace, events, metrics


def _empty_trace(initial: Array) -> dict[str, Array]:
    count = len(initial)
    return {
        "time": np.array([0.0]),
        "positions": initial[None, :, :],
        "preferred_velocity": np.empty((0, count, 2)),
        "safe_velocity": np.empty((0, count, 2)),
        "states": np.array(["INIT"]),
        "tracking_rmse": np.empty(0),
        "safety_status": np.empty(0, dtype="U24"),
    }


def _save_run_artifacts(
    run_dir: Path,
    resolved: dict[str, Any],
    observation: Array,
    truth: Array,
    boundary: BoundaryEstimateV2 | BoundaryEstimateFailure,
    targets: Array,
    target_s: Array,
    h_history: Array,
    assignment: Any | None,
    trace: dict[str, Array],
    events: list[dict[str, Any]],
    metrics: dict[str, Any],
    manifest: dict[str, Any],
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_json(run_dir / "config_resolved.json", resolved)
    _write_json(run_dir / "manifest.json", manifest)
    np.savez_compressed(run_dir / "observations.npz", observation=observation, truth_boundary=truth)
    if isinstance(boundary, BoundaryEstimateV2):
        np.savez_compressed(
            run_dir / "boundary_versions.npz",
            curve_points=boundary.curve_points,
            offset_points=boundary.offset_points,
            arc_s=boundary.arc_s,
            confidence=boundary.confidence,
            uncertainty=boundary.uncertainty,
        )
    else:
        np.savez_compressed(
            run_dir / "boundary_versions.npz",
            curve_points=np.empty((0, 2)),
            offset_points=np.empty((0, 2)),
            arc_s=np.empty(0),
            confidence=np.empty(0),
            uncertainty=np.empty(0),
        )
    mapping = np.asarray(assignment.guide_to_target, dtype=int) if assignment is not None else np.empty(0, dtype=int)
    np.savez_compressed(
        run_dir / "plan_trace.npz",
        targets=targets,
        target_s=target_s,
        h_history=h_history,
        guide_to_target=mapping,
    )
    np.savez_compressed(run_dir / "trajectory.npz", **trace)
    with open(run_dir / "events.jsonl", "w", encoding="utf-8") as file:
        for event in events:
            file.write(json.dumps(_jsonable(event), ensure_ascii=False) + "\n")
    _write_json(run_dir / "metrics.json", metrics)


def _run_method(
    scenario: str,
    seed: int,
    method: str,
    observation: Array,
    truth: Array,
    boundary: BoundaryEstimateV2 | BoundaryEstimateFailure,
    initial: Array,
    layout: str,
    config: G6EvaluationConfig,
    run_root: Path,
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    started = time.perf_counter()
    targets = np.empty((0, 2))
    target_s = np.empty(0)
    h_history = np.empty(0)
    assignment = None
    trace = _empty_trace(initial)
    events: list[dict[str, Any]] = []
    planning_details: dict[str, Any] = {}
    status = "BOUNDARY_INVALID" if isinstance(boundary, BoundaryEstimateFailure) else "VALID"
    failure_reason = str(boundary.diagnostics.get("reason", "boundary_invalid")) if isinstance(boundary, BoundaryEstimateFailure) else ""
    boundary_runtime_ms = float(boundary.diagnostics.get("runtime_ms", 0.0)) if isinstance(boundary, BoundaryEstimateV2) else 0.0
    planning_started = time.perf_counter()
    planning_runtime_ms = 0.0
    if isinstance(boundary, BoundaryEstimateV2):
        try:
            targets, target_s, h_history, planning_details = _make_targets(method, observation, boundary, config)
            assignment = assign_guides_to_targets(initial, targets, AssignmentConfig(lambda_switch=0.25))
            planning_runtime_ms = 1000.0 * (time.perf_counter() - planning_started)
            if assignment.status != "VALID":
                status = assignment.status
                failure_reason = str(assignment.diagnostics.get("reason", "assignment_failed"))
            else:
                trace, events, episode_metrics = _run_feedback_episode(observation, initial, targets, assignment, config)
                status = str(episode_metrics["episode_status"])
        except (RuntimeError, ValueError) as error:
            message = str(error)
            status = message.split(":", 1)[0] if ":" in message else "DEGRADED"
            if status not in {
                "DEGRADED",
                "BOUNDARY_INVALID",
                "OFFSET_INVALID",
                "CAPACITY_SHORTFALL",
                "ASSIGNMENT_INFEASIBLE",
                "SAFETY_INFEASIBLE",
                "TIMEOUT",
            }:
                status = "DEGRADED"
            failure_reason = message
            planning_runtime_ms = 1000.0 * (time.perf_counter() - planning_started)
    if "episode_metrics" not in locals():
        episode_metrics = {
            "episode_status": status,
            "success": False,
            "tracking_rmse_initial": None,
            "tracking_rmse_final": None,
            "convergence_time_s": None,
            "path_length_m": 0.0,
            "control_energy_m2_per_s": 0.0,
            "trajectory_crossing_count": 0,
            "min_guide_guide_clearance_m": _minimum_pair_distance(initial),
            "min_guide_crowd_clearance_m": float(np.min(np.linalg.norm(initial[:, None, :] - observation[None, :, :], axis=2))),
            "safety_projection_count": 0,
            "safety_infeasible_count": int(status == "SAFETY_INFEASIBLE"),
            "control_runtime_ms": 0.0,
            "trace_memory_bytes": int(sum(item.nbytes for item in trace.values())),
        }
    if isinstance(boundary, BoundaryEstimateV2):
        chamfer, hausdorff, hausdorff95 = _curve_errors(boundary.curve_points, truth)
        truth_length = float(np.sum(np.linalg.norm(np.roll(truth, -1, axis=0) - truth, axis=1)))
        boundary_values = {
            "boundary_status": "VALID",
            "curve_chamfer_m": chamfer,
            "curve_hausdorff_m": hausdorff,
            "curve_hausdorff95_m": hausdorff95,
            "boundary_length_relative_error": abs(boundary.length - truth_length) / truth_length,
            "confidence_mean": float(np.mean(boundary.confidence)),
            "uncertainty_mean": float(np.mean(boundary.uncertainty)),
        }
    else:
        boundary_values = {
            "boundary_status": boundary.status,
            "curve_chamfer_m": None,
            "curve_hausdorff_m": None,
            "curve_hausdorff95_m": None,
            "boundary_length_relative_error": None,
            "confidence_mean": None,
            "uncertainty_mean": None,
        }
    final = trace["positions"][-1]
    active_mapping = np.asarray(assignment.guide_to_target) >= 0 if assignment is not None else np.zeros(len(initial), dtype=bool)
    active_final = final[active_mapping]
    containment = {
        "coverage_ratio": coverage_ratio_to_points(active_final, truth, config.coverage_radius) if len(active_final) else 0.0,
        "max_truth_boundary_distance_m": max_euclidean_boundary_distance_to_points(active_final, truth) if len(active_final) else None,
    }
    method_runtime_ms = 1000.0 * (time.perf_counter() - started)
    estimator_runtime_ms = boundary_runtime_ms if method in {"uniform_arc", "fixed_m_periodic", "abcg_v2"} else 0.0
    total_runtime_ms = method_runtime_ms + estimator_runtime_ms
    record = {
        "scenario": scenario,
        "seed": int(seed),
        "method": method,
        "initial_layout": layout,
        "status": status,
        "success": status == "CONVERGED",
        "failure_reason": failure_reason,
        "active_count": int(np.count_nonzero(active_mapping)),
        "reserve_count": int(len(initial) - np.count_nonzero(active_mapping)),
        "assignment_switch_count": int(assignment.switch_count) if assignment is not None else 0,
        "plan_h_final": float(h_history[-1]) if len(h_history) else None,
        "plan_max_arc_gap_m": float(planning_details.get("plan_max_arc_gap")) if "plan_max_arc_gap" in planning_details else None,
        "boundary_runtime_ms": boundary_runtime_ms,
        "planning_runtime_ms": planning_runtime_ms,
        "method_runtime_excluding_shared_estimator_ms": method_runtime_ms,
        "total_runtime_ms": total_runtime_ms,
        **boundary_values,
        **containment,
        **episode_metrics,
    }
    run_dir = run_root / scenario / method / f"seed_{seed:03d}"
    resolved = {**asdict(config), "scenario": scenario, "seed": seed, "method": method, "initial_layout": layout}
    manifest = {
        "schema": "abcg-v2-step1-g6-run-v1",
        "source_commit": snapshot["commit"],
        "source_sha256": snapshot["source_sha256"],
        "truth_access": "evaluator_only",
        "planner_inputs": ["observation", "estimated_boundary", "guide_state"],
        "artifacts": [
            "config_resolved.json",
            "manifest.json",
            "observations.npz",
            "boundary_versions.npz",
            "plan_trace.npz",
            "trajectory.npz",
            "events.jsonl",
            "metrics.json",
        ],
    }
    _save_run_artifacts(
        run_dir, resolved, observation, truth, boundary, targets, target_s, h_history, assignment, trace, events, record, manifest
    )
    return record


def _run_primary_case(
    scenario: str,
    seed: int,
    config: G6EvaluationConfig,
    run_root: Path,
    snapshot: dict[str, Any],
) -> list[dict[str, Any]]:
    observation, truth = _observed_case(scenario, seed, config)
    boundary_started = time.perf_counter()
    boundary = estimate_boundary_v2(
        observation,
        _boundary_config(config),
        np.random.default_rng(42_000_019 + 4099 * seed + PRIMARY_SCENARIOS.index(scenario)),
    )
    elapsed = 1000.0 * (time.perf_counter() - boundary_started)
    if isinstance(boundary, BoundaryEstimateV2):
        boundary = replace(boundary, diagnostics={**boundary.diagnostics, "runtime_ms": elapsed})
    initial, layout = _initial_guides(seed, config.available_guides)
    return [
        _run_method(scenario, seed, method, observation, truth, boundary, initial, layout, config, run_root, snapshot)
        for method in config.methods
    ]
