"""Formal G6 evaluation for ABCG-v2 Step 1 static containment.

The estimator and all planners receive observations only.  Analytic boundary
truth is retained by the evaluator for scoring, and every failed run remains
in the run-count and failure-rate denominator.
"""
from __future__ import annotations

import csv
import ctypes
import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np
from shapely.geometry import LineString

from ..containment_metrics import coverage_ratio_to_points, max_euclidean_boundary_distance_to_points
from ..controllers import (
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
from ..estimation import BoundaryEstimateFailure, BoundaryEstimateV2, BoundaryV2Config, estimate_boundary_v2
from ..geometry import max_consecutive_arc_gap, resample_closed_curve_by_arclength
from ..runtime import run_tasks
from ..types import Array


PRIMARY_METHODS = (
    "endpoint_abcg",
    "uniform_angular",
    "uniform_arc",
    "fixed_m_periodic",
    "abcg_v2",
)
PRIMARY_SCENARIOS = ("circle", "ellipse", "u_shape", "c_shape")
NONCONVEX_SCENARIOS = ("u_shape", "c_shape")
ABLATION_VARIANTS = ("radial_no_bootstrap", "alpha_no_bootstrap", "alpha_bootstrap_no_gain", "abcg_v2_full")


@dataclass(frozen=True)
class G6EvaluationConfig:
    """Resolved formal-G6 configuration; distances are metres and time seconds."""

    seeds: tuple[int, ...] = tuple(range(30))
    scenarios: tuple[str, ...] = PRIMARY_SCENARIOS
    methods: tuple[str, ...] = PRIMARY_METHODS
    observation_count: int = 120
    bootstrap_samples: int = 30
    confidence_interval_resamples: int = 2000
    robustness_noise_levels: tuple[float, ...] = (0.0, 0.04, 0.08)
    robustness_dropout_levels: tuple[float, ...] = (0.0, 0.15, 0.30)
    robustness_scales: tuple[float, ...] = (0.75, 1.0, 1.25)
    available_guides: int = 16
    fixed_guide_count: int = 8
    required_arc_gap: float = 2.2
    safety_distance: float = 0.8
    coverage_radius: float = 1.25
    room_size: tuple[float, float] = (10.0, 10.0)
    dt: float = 0.1
    max_steps: int = 160
    workers: int = 4
    alpha_scale: float = 2.5
    sample_spacing: float = 0.08

    def __post_init__(self) -> None:
        if not self.seeds or len(set(self.seeds)) != len(self.seeds):
            raise ValueError("seeds must be a non-empty unique tuple.")
        if any(isinstance(seed, bool) or int(seed) != seed for seed in self.seeds):
            raise ValueError("seeds must contain integers.")
        if not self.scenarios or not set(self.scenarios).issubset(PRIMARY_SCENARIOS):
            raise ValueError(f"scenarios must select from {PRIMARY_SCENARIOS}.")
        if not self.methods or not set(self.methods).issubset(PRIMARY_METHODS):
            raise ValueError(f"methods must select from {PRIMARY_METHODS}.")
        for name in (
            "observation_count",
            "bootstrap_samples",
            "confidence_interval_resamples",
            "available_guides",
            "fixed_guide_count",
            "max_steps",
            "workers",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or value < 1:
                raise ValueError(f"{name} must be a positive integer.")
        if self.fixed_guide_count > self.available_guides:
            raise ValueError("fixed_guide_count must not exceed available_guides.")
        for name in (
            "required_arc_gap",
            "safety_distance",
            "coverage_radius",
            "dt",
            "alpha_scale",
            "sample_spacing",
        ):
            value = float(getattr(self, name))
            if not np.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and positive.")
        room = np.asarray(self.room_size, dtype=float)
        if room.shape != (2,) or not np.all(np.isfinite(room)) or np.any(room <= 0.0):
            raise ValueError("room_size must contain two finite positive dimensions.")
        for name in ("robustness_noise_levels", "robustness_dropout_levels", "robustness_scales"):
            values = np.asarray(getattr(self, name), dtype=float)
            if values.ndim != 1 or len(values) < 3 or not np.all(np.isfinite(values)):
                raise ValueError(f"{name} must contain at least three finite levels.")
        if np.any(np.asarray(self.robustness_noise_levels) < 0.0):
            raise ValueError("robustness noise levels must be non-negative.")
        dropout = np.asarray(self.robustness_dropout_levels)
        if np.any((dropout < 0.0) | (dropout >= 1.0)):
            raise ValueError("robustness dropout levels must be in [0, 1).")
        if np.any(np.asarray(self.robustness_scales) <= 0.0):
            raise ValueError("robustness scales must be positive.")


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_jsonable(value), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _polygon_for_shape(shape: str) -> Array:
    if shape == "u_shape":
        return np.array(
            [[2.0, 2.0], [8.0, 2.0], [8.0, 7.5], [6.6, 7.5], [6.6, 3.7], [3.4, 3.7], [3.4, 7.5], [2.0, 7.5]],
            dtype=float,
        )
    if shape == "c_shape":
        return np.array(
            [[2.0, 2.0], [8.0, 2.0], [8.0, 3.4], [4.0, 3.4], [4.0, 6.1], [8.0, 6.1], [8.0, 7.5], [2.0, 7.5]],
            dtype=float,
        )
    raise ValueError(f"unsupported polygon shape: {shape}")


def _inside_polygon(points: Array, polygon: Array) -> Array:
    x, y = points[:, 0], points[:, 1]
    inside = np.zeros(len(points), dtype=bool)
    previous = polygon[-1]
    for current in polygon:
        crosses = (current[1] > y) != (previous[1] > y)
        denominator = previous[1] - current[1]
        if abs(denominator) > 1.0e-15:
            crossing_x = (previous[0] - current[0]) * (y - current[1]) / denominator + current[0]
            inside ^= crosses & (x < crossing_x)
        previous = current
    return inside


def _sample_polygon(polygon: Array, count: int, rng: np.random.Generator) -> Array:
    accepted: list[Array] = []
    total = 0
    while total < count:
        candidates = rng.uniform(np.min(polygon, axis=0), np.max(polygon, axis=0), size=(max(count, 64), 2))
        batch = candidates[_inside_polygon(candidates, polygon)]
        accepted.append(batch)
        total += len(batch)
    return np.vstack(accepted)[:count]


def _base_case(scenario: str, seed: int, count: int, spacing: float) -> tuple[Array, Array]:
    rng = np.random.default_rng(1_000_003 + 1009 * int(seed) + 65_537 * PRIMARY_SCENARIOS.index(scenario))
    if scenario == "circle":
        angles = rng.uniform(0.0, 2.0 * np.pi, count)
        radii = 2.0 * np.sqrt(rng.uniform(0.0, 1.0, count))
        observation = np.column_stack((5.0 + radii * np.cos(angles), 5.0 + radii * np.sin(angles)))
        truth_angles = np.linspace(0.0, 2.0 * np.pi, max(96, int(np.ceil(4.0 * np.pi / spacing))), endpoint=False)
        truth = np.column_stack((5.0 + 2.0 * np.cos(truth_angles), 5.0 + 2.0 * np.sin(truth_angles)))
    elif scenario == "ellipse":
        angles = rng.uniform(0.0, 2.0 * np.pi, count)
        radii = np.sqrt(rng.uniform(0.0, 1.0, count))
        observation = np.column_stack((5.0 + 2.5 * radii * np.cos(angles), 5.0 + 1.35 * radii * np.sin(angles)))
        dense = np.linspace(0.0, 2.0 * np.pi, 720, endpoint=False)
        polygon = np.column_stack((5.0 + 2.5 * np.cos(dense), 5.0 + 1.35 * np.sin(dense)))
        truth, _, _, _, _ = resample_closed_curve_by_arclength(polygon, spacing=spacing)
    else:
        polygon = _polygon_for_shape(scenario)
        observation = _sample_polygon(polygon, count, rng)
        truth, _, _, _, _ = resample_closed_curve_by_arclength(polygon, spacing=spacing)
    return observation, truth


def _observed_case(
    scenario: str,
    seed: int,
    config: G6EvaluationConfig,
    *,
    noise_std: float = 0.03,
    dropout_rate: float = 0.05,
    scale: float = 1.0,
) -> tuple[Array, Array]:
    observation, truth = _base_case(scenario, seed, config.observation_count, config.sample_spacing / 2.0)
    center = np.array([5.0, 5.0])
    observation = center + float(scale) * (observation - center)
    truth = center + float(scale) * (truth - center)
    rng = np.random.default_rng(8_000_021 + 8191 * int(seed) + 131_071 * PRIMARY_SCENARIOS.index(scenario))
    if dropout_rate > 0.0:
        keep = rng.random(len(observation)) >= float(dropout_rate)
        if np.count_nonzero(keep) >= 8:
            observation = observation[keep]
    if noise_std > 0.0:
        observation = observation + rng.normal(0.0, float(noise_std), observation.shape)
    return observation, truth


def _boundary_config(config: G6EvaluationConfig, bootstrap_samples: int | None = None) -> BoundaryV2Config:
    return BoundaryV2Config(
        estimator="alpha",
        safety_distance=config.safety_distance,
        sample_spacing=config.sample_spacing,
        min_observation_coverage=0.72,
        room_size=config.room_size,
        room_margin=0.2,
        alpha_scale=config.alpha_scale,
        alpha_smoothing_passes=5,
        bootstrap_samples=config.bootstrap_samples if bootstrap_samples is None else bootstrap_samples,
        bootstrap_min_success_fraction=0.5,
        bootstrap_confidence_floor=0.15,
    )


def _neutralize_confidence(boundary: BoundaryEstimateV2) -> BoundaryEstimateV2:
    return replace(
        boundary,
        confidence=np.ones_like(boundary.confidence),
        diagnostics={**boundary.diagnostics, "confidence_status": "confidence_gain_ablated_g6"},
    )


def _initial_guides(seed: int, count: int) -> tuple[Array, str]:
    layout = ("balanced_perimeter", "one_sided", "opposed_sides")[int(seed) % 3]
    if layout == "one_sided":
        y = np.linspace(0.55, 9.45, count)
        guides = np.column_stack((np.full(count, 0.55), y))
    elif layout == "opposed_sides":
        left_count = (count + 1) // 2
        right_count = count - left_count
        left = np.column_stack((np.full(left_count, 0.55), np.linspace(0.65, 9.35, left_count)))
        right = np.column_stack((np.full(right_count, 9.45), np.linspace(9.35, 0.65, right_count)))
        guides = np.vstack((left, right))
    else:
        perimeter = np.mod(np.linspace(0.0, 4.0, count, endpoint=False) + 0.013 * seed, 4.0)
        guides = np.empty((count, 2), dtype=float)
        for index, value in enumerate(perimeter):
            side = int(value)
            fraction = value - side
            if side == 0:
                guides[index] = [0.55 + 8.9 * fraction, 0.55]
            elif side == 1:
                guides[index] = [9.45, 0.55 + 8.9 * fraction]
            elif side == 2:
                guides[index] = [9.45 - 8.9 * fraction, 9.45]
            else:
                guides[index] = [0.55, 9.45 - 8.9 * fraction]
    return guides, layout


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


def _curve_errors(estimate: Array, truth: Array) -> tuple[float, float, float]:
    distances = np.linalg.norm(estimate[:, None, :] - truth[None, :, :], axis=2)
    a = np.min(distances, axis=1)
    b = np.min(distances, axis=0)
    chamfer = 0.5 * (float(np.mean(a)) + float(np.mean(b)))
    hausdorff = max(float(np.max(a)), float(np.max(b)))
    hausdorff95 = max(float(np.percentile(a, 95.0)), float(np.percentile(b, 95.0)))
    return chamfer, hausdorff, hausdorff95


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


def _summary(values: list[float], rng: np.random.Generator, resamples: int, direction: str) -> dict[str, Any]:
    array = np.asarray(values, dtype=float)
    if len(array) == 0:
        return {"n": 0, "mean": None, "median": None, "ci95_low": None, "ci95_high": None, "p95": None, "worst_5_percent_mean": None}
    indices = rng.integers(0, len(array), size=(resamples, len(array)))
    means = np.mean(array[indices], axis=1)
    worst_count = max(1, int(np.ceil(0.05 * len(array))))
    ordered = np.sort(array)
    worst = ordered[-worst_count:] if direction == "lower" else ordered[:worst_count]
    return {
        "n": int(len(array)),
        "mean": float(np.mean(array)),
        "median": float(np.median(array)),
        "ci95_low": float(np.percentile(means, 2.5)),
        "ci95_high": float(np.percentile(means, 97.5)),
        "p95": float(np.percentile(array, 95.0)),
        "worst_5_percent_mean": float(np.mean(worst)),
        "direction": direction,
    }


METRIC_DIRECTIONS = {
    "curve_chamfer_m": "lower",
    "curve_hausdorff95_m": "lower",
    "plan_h_final": "lower",
    "plan_max_arc_gap_m": "lower",
    "tracking_rmse_final": "lower",
    "convergence_time_s": "lower",
    "path_length_m": "lower",
    "assignment_switch_count": "lower",
    "trajectory_crossing_count": "lower",
    "coverage_ratio": "higher",
    "max_truth_boundary_distance_m": "lower",
    "min_guide_guide_clearance_m": "higher",
    "min_guide_crowd_clearance_m": "higher",
    "active_count": "lower",
    "total_runtime_ms": "lower",
    "trace_memory_bytes": "lower",
}


def _aggregate(records: list[dict[str, Any]], config: G6EvaluationConfig) -> dict[str, Any]:
    rng = np.random.default_rng(700_001)
    aggregate: dict[str, Any] = {}
    for scenario in config.scenarios:
        aggregate[scenario] = {}
        for method in config.methods:
            subset = [record for record in records if record["scenario"] == scenario and record["method"] == method]
            aggregate[scenario][method] = {
                "run_count": len(subset),
                "success_count": int(sum(bool(record["success"]) for record in subset)),
                "failure_count": int(sum(not bool(record["success"]) for record in subset)),
                "failure_rate": float(np.mean([not bool(record["success"]) for record in subset])) if subset else None,
                "status_counts": {
                    status: sum(record["status"] == status for record in subset)
                    for status in sorted({str(record["status"]) for record in subset})
                },
                "metrics": {
                    metric: _summary(
                        [float(record[metric]) for record in subset if record.get(metric) is not None],
                        rng,
                        config.confidence_interval_resamples,
                        direction,
                    )
                    for metric, direction in METRIC_DIRECTIONS.items()
                },
            }
    return aggregate


def _paired_comparisons(records: list[dict[str, Any]], config: G6EvaluationConfig) -> dict[str, Any]:
    rng = np.random.default_rng(700_003)
    by_key = {(record["scenario"], record["seed"], record["method"]): record for record in records}
    comparisons: dict[str, Any] = {}
    for scenario in config.scenarios:
        comparisons[scenario] = {}
        for baseline in config.methods:
            if baseline == "abcg_v2" or "abcg_v2" not in config.methods:
                continue
            comparison: dict[str, Any] = {}
            for metric in ("plan_max_arc_gap_m", "tracking_rmse_final", "path_length_m", "coverage_ratio", "total_runtime_ms"):
                differences = []
                paired_count = 0
                for seed in config.seeds:
                    full = by_key[(scenario, seed, "abcg_v2")]
                    other = by_key[(scenario, seed, baseline)]
                    if full.get(metric) is None or other.get(metric) is None:
                        continue
                    paired_count += 1
                    differences.append(float(full[metric]) - float(other[metric]))
                if differences:
                    array = np.asarray(differences)
                    indices = rng.integers(0, len(array), size=(config.confidence_interval_resamples, len(array)))
                    bootstrap = np.mean(array[indices], axis=1)
                    std = float(np.std(array, ddof=1)) if len(array) > 1 else 0.0
                    direction = METRIC_DIRECTIONS[metric]
                    wins = array < 0.0 if direction == "lower" else array > 0.0
                    comparison[metric] = {
                        "paired_count": paired_count,
                        "missing_pair_count": len(config.seeds) - paired_count,
                        "mean_difference_abcg_v2_minus_baseline": float(np.mean(array)),
                        "median_difference": float(np.median(array)),
                        "ci95_low": float(np.percentile(bootstrap, 2.5)),
                        "ci95_high": float(np.percentile(bootstrap, 97.5)),
                        "cohen_dz": float(np.mean(array) / std) if std > 0.0 else None,
                        "win_rate": float(np.mean(wins)),
                        "direction": direction,
                    }
                else:
                    comparison[metric] = {"paired_count": 0, "missing_pair_count": len(config.seeds)}
            comparisons[scenario][f"abcg_v2_minus_{baseline}"] = comparison
    return comparisons


def _run_ablation_case(
    scenario: str,
    seed: int,
    config: G6EvaluationConfig,
    primary_by_key: dict[tuple[str, int, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    observation, truth = _observed_case(scenario, seed, config)
    estimates: dict[str, BoundaryEstimateV2 | BoundaryEstimateFailure] = {
        "radial_no_bootstrap": estimate_boundary_v2(
            observation,
            BoundaryV2Config(
                estimator="radial",
                safety_distance=config.safety_distance,
                sample_spacing=config.sample_spacing,
                radial_bins=72,
                min_observation_coverage=0.60,
                room_size=config.room_size,
            ),
            np.random.default_rng(90_000 + seed),
        ),
        "alpha_no_bootstrap": estimate_boundary_v2(
            observation, _boundary_config(config, bootstrap_samples=0), np.random.default_rng(91_000 + seed)
        ),
    }
    for variant, boundary in estimates.items():
        if isinstance(boundary, BoundaryEstimateFailure):
            records.append({"scenario": scenario, "seed": seed, "variant": variant, "valid": False, "status": boundary.status})
            continue
        plan = plan_periodic_arc_coverage(
            boundary,
            min(config.fixed_guide_count, config.available_guides),
            PeriodicArcCVTConfig(max_iterations=200),
        )
        chamfer, hausdorff, hausdorff95 = _curve_errors(boundary.curve_points, truth)
        records.append(
            {
                "scenario": scenario,
                "seed": seed,
                "variant": variant,
                "valid": True,
                "status": plan.status,
                "curve_chamfer_m": chamfer,
                "curve_hausdorff_m": hausdorff,
                "curve_hausdorff95_m": hausdorff95,
                "plan_h_initial": float(plan.h_history[0]),
                "plan_h_final": float(plan.h_history[-1]),
                "plan_iterations": int(len(plan.gain_history)),
                "plan_max_arc_gap_m": float(plan.max_arc_gap),
            }
        )
    for variant, method in (
        ("alpha_bootstrap_no_gain", "fixed_m_periodic"),
        ("abcg_v2_full", "abcg_v2"),
    ):
        source = primary_by_key[(scenario, seed, method)]
        records.append(
            {
                "scenario": scenario,
                "seed": seed,
                "variant": variant,
                "valid": source["boundary_status"] == "VALID",
                "status": source["status"],
                "curve_chamfer_m": source["curve_chamfer_m"],
                "curve_hausdorff95_m": source["curve_hausdorff95_m"],
                "plan_h_initial": None,
                "plan_h_final": source["plan_h_final"],
                "plan_iterations": None,
                "plan_max_arc_gap_m": source["plan_max_arc_gap_m"],
                "source": "paired_primary_boundary_and_plan",
            }
        )
    return records


def _run_ablations(config: G6EvaluationConfig, primary: list[dict[str, Any]]) -> list[dict[str, Any]]:
    primary_by_key = {
        (str(record["scenario"]), int(record["seed"]), str(record["method"])): record
        for record in primary
    }
    cases = [
        (scenario, seed)
        for scenario in NONCONVEX_SCENARIOS
        if scenario in config.scenarios
        for seed in config.seeds
    ]
    # Ship only the case's own primary records to each worker instead of
    # pickling the full primary map once per task.
    tasks = [
        (
            scenario,
            seed,
            config,
            {key: value for key, value in primary_by_key.items() if key[0] == scenario and key[1] == seed},
        )
        for scenario, seed in cases
    ]
    groups = run_tasks(_run_ablation_case, tasks, config.workers)
    records = [record for group in groups for record in group]
    records.sort(key=lambda record: (str(record["scenario"]), int(record["seed"]), str(record["variant"])))
    return records


def _ablation_summary(records: list[dict[str, Any]], config: G6EvaluationConfig) -> dict[str, Any]:
    rng = np.random.default_rng(700_004)
    summary: dict[str, Any] = {}
    for scenario in (item for item in NONCONVEX_SCENARIOS if item in config.scenarios):
        summary[scenario] = {}
        for variant in ABLATION_VARIANTS:
            subset = [
                record for record in records if record["scenario"] == scenario and record["variant"] == variant
            ]
            summary[scenario][variant] = {
                "run_count": len(subset),
                "valid_count": int(sum(bool(record["valid"]) for record in subset)),
                "status_counts": {
                    status: int(sum(record["status"] == status for record in subset))
                    for status in sorted({str(record["status"]) for record in subset})
                },
                "metrics": {
                    metric: _summary(
                        [float(record[metric]) for record in subset if record.get(metric) is not None],
                        rng,
                        config.confidence_interval_resamples,
                        "lower",
                    )
                    for metric in ("curve_chamfer_m", "curve_hausdorff95_m", "plan_h_final", "plan_max_arc_gap_m")
                },
            }
    return summary


def _run_robustness_case(
    task: tuple[str, int, str, int, float],
    config: G6EvaluationConfig,
) -> dict[str, Any]:
    scenario, seed, dimension, level_index, level = task
    kwargs = {"noise_std": 0.03, "dropout_rate": 0.05, "scale": 1.0}
    if dimension == "noise":
        kwargs["noise_std"] = float(level)
    elif dimension == "dropout":
        kwargs["dropout_rate"] = float(level)
    else:
        kwargs["scale"] = float(level)
    observation, truth = _observed_case(scenario, seed, config, **kwargs)
    rng_seed = 301_000 + 10_007 * seed + 101 * ("noise", "dropout", "scale").index(dimension) + level_index
    boundary = estimate_boundary_v2(
        observation,
        _boundary_config(config, bootstrap_samples=0),
        np.random.default_rng(rng_seed),
    )
    if isinstance(boundary, BoundaryEstimateFailure):
        return {
            "scenario": scenario,
            "seed": seed,
            "dimension": dimension,
            "level": float(level),
            "valid": False,
            "status": boundary.status,
            "curve_chamfer_m": None,
            "curve_hausdorff95_m": None,
        }
    chamfer, _, hausdorff95 = _curve_errors(boundary.curve_points, truth)
    return {
        "scenario": scenario,
        "seed": seed,
        "dimension": dimension,
        "level": float(level),
        "valid": True,
        "status": "VALID",
        "curve_chamfer_m": chamfer,
        "curve_hausdorff95_m": hausdorff95,
    }


def _run_robustness(config: G6EvaluationConfig) -> list[dict[str, Any]]:
    dimensions = (
        ("noise", config.robustness_noise_levels),
        ("dropout", config.robustness_dropout_levels),
        ("scale", config.robustness_scales),
    )
    tasks = [
        (scenario, seed, dimension, level_index, float(level))
        for scenario in NONCONVEX_SCENARIOS
        if scenario in config.scenarios
        for seed in config.seeds
        for dimension, levels in dimensions
        for level_index, level in enumerate(levels)
    ]
    records = run_tasks(_run_robustness_case, [(task, config) for task in tasks], config.workers)
    records.sort(key=lambda record: (str(record["scenario"]), int(record["seed"]), str(record["dimension"]), float(record["level"])))
    return records


def _robustness_summary(records: list[dict[str, Any]], config: G6EvaluationConfig) -> dict[str, Any]:
    rng = np.random.default_rng(700_005)
    summary: dict[str, Any] = {}
    for scenario in (item for item in NONCONVEX_SCENARIOS if item in config.scenarios):
        summary[scenario] = {}
        for dimension in ("noise", "dropout", "scale"):
            summary[scenario][dimension] = {}
            levels = sorted({float(record["level"]) for record in records if record["scenario"] == scenario and record["dimension"] == dimension})
            for level in levels:
                subset = [record for record in records if record["scenario"] == scenario and record["dimension"] == dimension and record["level"] == level]
                summary[scenario][dimension][str(level)] = {
                    "run_count": len(subset),
                    "failure_rate": float(np.mean([not record["valid"] for record in subset])),
                    "curve_chamfer_m": _summary(
                        [float(record["curve_chamfer_m"]) for record in subset if record["curve_chamfer_m"] is not None],
                        rng,
                        config.confidence_interval_resamples,
                        "lower",
                    ),
                    "curve_hausdorff95_m": _summary(
                        [float(record["curve_hausdorff95_m"]) for record in subset if record["curve_hausdorff95_m"] is not None],
                        rng,
                        config.confidence_interval_resamples,
                        "lower",
                    ),
                }
    return summary


def _failure_fixtures(config: G6EvaluationConfig) -> list[dict[str, Any]]:
    fixtures: list[dict[str, Any]] = []
    rng = np.random.default_rng(880_001)
    first = rng.normal([3.0, 5.0], [0.25, 0.45], size=(60, 2))
    second = rng.normal([7.0, 5.0], [0.25, 0.45], size=(60, 2))
    observation = np.vstack((first, second))
    boundary = estimate_boundary_v2(observation, _boundary_config(config, bootstrap_samples=0), rng)
    fixtures.append(
        {
            "fixture": "double_cluster",
            "status": boundary.status if isinstance(boundary, BoundaryEstimateFailure) else "UNEXPECTED_VALID",
            "reason": str(boundary.diagnostics.get("reason", "")),
            "observation": observation,
            "truth": np.empty((0, 2)),
            "estimate": boundary.curve_points if isinstance(boundary, BoundaryEstimateV2) else np.empty((0, 2)),
        }
    )
    observation, truth = _observed_case("u_shape", 0, config, noise_std=0.0, dropout_rate=0.0)
    valid = estimate_boundary_v2(observation, _boundary_config(config, bootstrap_samples=0), rng)
    if isinstance(valid, BoundaryEstimateV2):
        decision = allocate_guide_resources(valid.length, 2, ResourcePolicyConfig(g_req=config.required_arc_gap, m_min=4))
        fixtures.append(
            {
                "fixture": "capacity_shortfall",
                "status": decision.status,
                "reason": str(decision.diagnostics.get("reason", "")),
                "observation": observation,
                "truth": truth,
                "estimate": valid.curve_points,
            }
        )
    narrow_polygon = np.array(
        [[2.0, 2.0], [8.0, 2.0], [8.0, 8.0], [5.6, 8.0], [5.6, 3.2], [4.4, 3.2], [4.4, 8.0], [2.0, 8.0]],
        dtype=float,
    )
    narrow_observation = _sample_polygon(narrow_polygon, config.observation_count, np.random.default_rng(880_003))
    narrow_truth, _, _, _, _ = resample_closed_curve_by_arclength(
        narrow_polygon,
        spacing=config.sample_spacing / 2.0,
    )
    narrow = estimate_boundary_v2(
        narrow_observation,
        _boundary_config(config, bootstrap_samples=0),
        np.random.default_rng(880_005),
    )
    fixtures.append(
        {
            "fixture": "narrow_neck",
            "status": narrow.status if isinstance(narrow, BoundaryEstimateFailure) else "VALID",
            "reason": str(narrow.diagnostics.get("reason", "valid_stress_case")),
            "observation": narrow_observation,
            "truth": narrow_truth,
            "estimate": narrow.curve_points if isinstance(narrow, BoundaryEstimateV2) else np.empty((0, 2)),
        }
    )
    return fixtures


def _save_failure_gallery(output: Path, fixtures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actual = [fixture for fixture in fixtures if fixture["status"] not in {"VALID", "CONVERGED", "UNEXPECTED_VALID"}]
    import os

    os.environ.setdefault("MPLCONFIGDIR", str((output / ".mplconfig").resolve()))
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(1, max(1, len(actual)), figsize=(6 * max(1, len(actual)), 5), squeeze=False)
    for axis, fixture in zip(axes.ravel(), actual, strict=False):
        observation = fixture["observation"]
        truth = fixture["truth"]
        estimate = fixture["estimate"]
        axis.scatter(observation[:, 0], observation[:, 1], s=8, alpha=0.35, label="observation")
        if len(truth):
            axis.plot(*np.vstack((truth, truth[0])).T, color="black", linewidth=1.3, label="independent truth")
        if len(estimate):
            axis.plot(*np.vstack((estimate, estimate[0])).T, color="tab:red", linewidth=1.2, label="estimate")
        axis.set_title(f"{fixture['fixture']}\n{fixture['status']}")
        axis.set_aspect("equal")
        axis.legend(loc="best")
    for axis in axes.ravel()[len(actual) :]:
        axis.axis("off")
    figure.tight_layout()
    figure.savefig(output / "failure_gallery.png", dpi=150)
    plt.close(figure)
    serializable = [
        {"fixture": fixture["fixture"], "status": fixture["status"], "reason": fixture["reason"], "selection_role": "actual_failure"}
        for fixture in actual
    ]
    _write_json(output / "failure_gallery.json", serializable)
    return serializable


def _repository_snapshot(repo: Path, source_paths: list[Path]) -> dict[str, Any]:
    def git(*args: str) -> str:
        result = subprocess.run(["git", *args], cwd=repo, check=False, capture_output=True, text=True)
        return result.stdout.strip() if result.returncode == 0 else "unknown"

    digest = hashlib.sha256()
    for path in sorted(source_paths):
        digest.update(str(path.relative_to(repo)).encode("utf-8"))
        digest.update(path.read_bytes())
    dirty = [line for line in git("status", "--porcelain").splitlines() if line]
    return {
        "commit": git("rev-parse", "HEAD"),
        "branch": git("branch", "--show-current"),
        "dirty": bool(dirty),
        "dirty_entry_count": len(dirty),
        "source_sha256": digest.hexdigest(),
        "frozen_commit": not dirty,
        "freeze_status": "FROZEN_COMMIT" if not dirty else "UNFROZEN_DIRTY_WORKTREE",
        "python": platform.python_version(),
        "platform": platform.platform(),
        "packages": {
            name: importlib.metadata.version(name)
            for name in ("numpy", "scipy", "shapely", "matplotlib", "PyYAML")
        },
    }


def _run_preflight_command(repo: Path, name: str, command: list[str]) -> dict[str, Any]:
    """Run one formal preflight command and retain an auditable compact result."""
    print(f"[G6 preflight] {name}: {' '.join(command)}", flush=True)
    started = time.perf_counter()
    result = subprocess.run(command, cwd=repo, check=False, capture_output=True, text=True)
    duration_s = time.perf_counter() - started
    stdout = result.stdout or ""
    stderr = result.stderr or ""
    if stdout:
        print(stdout.rstrip(), flush=True)
    if stderr:
        print(stderr.rstrip(), file=sys.stderr, flush=True)
    return {
        "name": name,
        "command": command,
        "return_code": int(result.returncode),
        "duration_s": duration_s,
        "stdout_tail": stdout[-8000:],
        "stderr_tail": stderr[-8000:],
    }


def run_g6_preflight(repo: str | Path | None = None) -> dict[str, Any]:
    """Run the mandatory G0-G5 environment and regression checks.

    The formal CLI calls this function directly. The returned evidence is
    commit-bound and is validated again by :func:`run_g6_evaluation`; there is
    no command-line switch that can assert a passing preflight manually.
    """
    repository = Path(repo).resolve() if repo is not None else Path(__file__).resolve().parents[3]

    def git(*args: str) -> str:
        result = subprocess.run(["git", *args], cwd=repository, check=False, capture_output=True, text=True)
        return result.stdout.strip() if result.returncode == 0 else "unknown"

    commit = git("rev-parse", "HEAD")
    dirty_before = bool(git("status", "--porcelain"))
    (repository / ".tmp").mkdir(parents=True, exist_ok=True)
    commands = [
        _run_preflight_command(
            repository,
            "pytest",
            [
                sys.executable,
                "-m",
                "pytest",
                "--basetemp=.tmp/pytest-temp",
                "-o",
                "cache_dir=.tmp/pytest-cache",
            ],
        ),
        _run_preflight_command(
            repository,
            "compileall",
            [sys.executable, "-m", "compileall", "-q", "src", "scripts"],
        ),
        _run_preflight_command(repository, "pip_check", [sys.executable, "-m", "pip", "check"]),
    ]
    dirty_after = bool(git("status", "--porcelain"))
    return {
        "schema": "abcg-v2-step1-preflight-v1",
        "evaluated_commit": commit,
        "python_executable": sys.executable,
        "python_version": platform.python_version(),
        "environment_name": "abcg" if "abcg" in str(sys.prefix).lower() else Path(sys.prefix).name,
        "repository_clean_before": not dirty_before,
        "repository_clean_after": not dirty_after,
        "commands": commands,
        "all_passed": all(command["return_code"] == 0 for command in commands),
    }


def _preflight_is_valid(preflight: dict[str, Any] | None, snapshot: dict[str, Any]) -> bool:
    if not isinstance(preflight, dict):
        return False
    commands = preflight.get("commands")
    if not isinstance(commands, list) or not all(isinstance(command, dict) for command in commands):
        return False
    return bool(
        preflight.get("schema") == "abcg-v2-step1-preflight-v1"
        and preflight.get("evaluated_commit") == snapshot["commit"]
        and preflight.get("repository_clean_before") is True
        and preflight.get("repository_clean_after") is True
        and preflight.get("all_passed") is True
        and {command.get("name") for command in commands} == {"pytest", "compileall", "pip_check"}
        and all(command.get("return_code") == 0 for command in commands)
    )


def _process_peak_memory_bytes() -> int:
    """Return process peak resident memory without tracing every allocation."""
    if platform.system() == "Windows":
        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong),
                ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        get_current_process = ctypes.windll.kernel32.GetCurrentProcess
        get_current_process.restype = ctypes.c_void_p
        get_process_memory_info = ctypes.windll.psapi.GetProcessMemoryInfo
        get_process_memory_info.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ProcessMemoryCounters),
            ctypes.c_ulong,
        ]
        get_process_memory_info.restype = ctypes.c_int
        process = get_current_process()
        success = get_process_memory_info(
            process,
            ctypes.byref(counters),
            counters.cb,
        )
        return int(counters.PeakWorkingSetSize) if success else 0
    try:
        import resource

        peak = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        return peak if platform.system() == "Darwin" else peak * 1024
    except (ImportError, OSError):
        return 0


def _write_records_csv(path: Path, records: list[dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(records[0].keys()))
        writer.writeheader()
        writer.writerows(_jsonable(records))


def _write_report(
    output: Path,
    config: G6EvaluationConfig,
    aggregate: dict[str, Any],
    snapshot: dict[str, Any],
    gate: dict[str, Any],
) -> None:
    lines = [
        "# ABCG-v2 Step 1 G6 formal compliance report",
        "",
        f"- Primary matrix: {len(config.scenarios)} scenarios × {len(config.methods)} methods × {len(config.seeds)} paired seeds",
        f"- Bootstrap boundary samples: {config.bootstrap_samples}",
        f"- Initial layouts: balanced perimeter, one-sided, opposed sides",
        f"- Freeze status: `{snapshot['freeze_status']}`",
        f"- Overall status: `{gate['overall_status']}`",
        f"- G6 status: `{gate['g6_status']}`",
        f"- Evaluated commit: `{gate['evaluated_commit']}`",
        "",
        "## Primary closed-loop outcomes",
        "",
        "| Scenario | Method | Success/total | Failure rate | Arc gap mean | Coverage mean | Runtime P95 ms |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for scenario in config.scenarios:
        for method in config.methods:
            values = aggregate[scenario][method]
            metrics = values["metrics"]
            lines.append(
                f"| {scenario} | {method} | {values['success_count']}/{values['run_count']} | "
                f"{values['failure_rate']:.3f} | {metrics['plan_max_arc_gap_m']['mean']} | "
                f"{metrics['coverage_ratio']['mean']} | {metrics['total_runtime_ms']['p95']} |"
            )
    lines.extend(
        [
            "",
            "## Evidence boundary",
            "",
            "Analytic truth is used only by the evaluator. Each method receives the same paired observation and initial guide state.",
            "Invalid boundary, capacity, assignment, safety, degraded, and timeout states remain in the denominator.",
            "The report is synthetic Step 1 evidence; it does not claim human-crowd interaction or decentralized Step 2/3 performance.",
            (
                "The evaluator recorded a clean frozen commit."
                if snapshot["frozen_commit"]
                else "The evaluator recorded a dirty checkout, so frozen-commit compliance remains unmet."
            ),
        ]
    )
    (output / "G6_COMPLIANCE_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_g6_evaluation(
    output_dir: str | Path,
    config: G6EvaluationConfig,
    run_root: str | Path | None = None,
    *,
    preflight_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run formal G6 evidence and return explicit gate status."""
    if not isinstance(config, G6EvaluationConfig):
        raise TypeError("config must be G6EvaluationConfig.")
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    runs = Path(run_root) if run_root is not None else output / "run_artifacts"
    runs.mkdir(parents=True, exist_ok=True)
    repo = Path(__file__).resolve().parents[3]
    source_paths = [
        Path(__file__).resolve(),
        repo / "scripts" / "run_step1_g6_compliance.py",
        repo / "src" / "crowd_management" / "controllers" / "abcg_v2.py",
        repo / "src" / "crowd_management" / "controllers" / "assignment.py",
        repo / "src" / "crowd_management" / "estimation" / "boundary_v2.py",
    ]
    snapshot = _repository_snapshot(repo, source_paths)
    _write_json(output / "evaluation_config.json", asdict(config))
    _write_json(output / "evaluation_snapshot.json", snapshot)
    _write_json(
        output / "preflight_evidence.json",
        preflight_evidence
        if preflight_evidence is not None
        else {
            "schema": "abcg-v2-step1-preflight-v1",
            "evaluated_commit": snapshot["commit"],
            "all_passed": False,
            "status": "NOT_RUN",
        },
    )

    started = time.perf_counter()
    cases = [(scenario, seed) for scenario in config.scenarios for seed in config.seeds]
    case_records = run_tasks(
        _run_primary_case,
        [(scenario, seed, config, runs, snapshot) for scenario, seed in cases],
        config.workers,
    )
    records = [record for group in case_records for record in group]
    records.sort(key=lambda record: (str(record["scenario"]), int(record["seed"]), str(record["method"])))
    aggregate = _aggregate(records, config)
    paired = _paired_comparisons(records, config)
    ablations = _run_ablations(config, records)
    ablation_aggregate = _ablation_summary(ablations, config)
    robustness = _run_robustness(config)
    robustness_aggregate = _robustness_summary(robustness, config)
    stress_fixtures = _failure_fixtures(config)
    _write_json(
        output / "stress_cases.json",
        [
            {
                "fixture": fixture["fixture"],
                "status": fixture["status"],
                "reason": fixture["reason"],
                "selection_role": "stress_case",
            }
            for fixture in stress_fixtures
        ],
    )
    gallery = _save_failure_gallery(output, stress_fixtures)
    peak_memory = _process_peak_memory_bytes()
    wall_time_s = time.perf_counter() - started

    _write_json(output / "records.json", records)
    _write_records_csv(output / "records.csv", records)
    _write_json(output / "aggregate.json", aggregate)
    _write_json(output / "paired_comparisons.json", paired)
    _write_json(output / "ablation_records.json", ablations)
    _write_json(output / "ablation_aggregate.json", ablation_aggregate)
    _write_json(output / "robustness_records.json", robustness)
    _write_json(output / "robustness_aggregate.json", robustness_aggregate)
    performance = {
        "wall_time_s": wall_time_s,
        "peak_process_resident_memory_bytes": int(peak_memory),
        "primary_runtime_ms": _summary(
            [float(record["total_runtime_ms"]) for record in records],
            np.random.default_rng(700_007),
            config.confidence_interval_resamples,
            "lower",
        ),
    }
    _write_json(output / "performance.json", performance)

    expected = len(config.seeds) * len(config.scenarios) * len(config.methods)
    preflight_valid = _preflight_is_valid(preflight_evidence, snapshot)
    checks = {
        "formal_preflight": preflight_valid,
        "research_dependencies": all(name in snapshot["packages"] for name in ("scipy", "shapely")),
        "reset_step_api": all(hasattr(ABCGv2Controller, name) for name in ("reset", "step")),
        "primary_scenarios": set(config.scenarios) == set(PRIMARY_SCENARIOS),
        "required_methods": set(config.methods) == set(PRIMARY_METHODS),
        "paired_seed_count_at_least_30": len(config.seeds) >= 30,
        "bootstrap_samples_at_least_30": config.bootstrap_samples >= 30,
        "all_primary_records_accounted_for": len(records) == expected,
        "all_failures_in_denominator": sum(item["run_count"] for scenario in aggregate.values() for item in scenario.values()) == expected,
        "ablations_present": {record["variant"] for record in ablations} == set(ABLATION_VARIANTS),
        "robustness_noise_dropout_scale": {record["dimension"] for record in robustness} == {"noise", "dropout", "scale"},
        "statistics_mean_median_ci_effect_worst5_failure": bool(paired) and all(
            {"mean", "median", "ci95_low", "ci95_high", "worst_5_percent_mean"}.issubset(summary)
            for scenario in aggregate.values()
            for method in scenario.values()
            for summary in method["metrics"].values()
        ),
        "actual_failure_gallery": len(gallery) >= 1 and (output / "failure_gallery.png").is_file(),
        "stress_double_cluster_and_narrow_neck": {fixture["fixture"] for fixture in stress_fixtures}.issuperset(
            {"double_cluster", "narrow_neck"}
        ),
        "runtime_p95_memory": performance["primary_runtime_ms"]["p95"] is not None and peak_memory > 0,
        "run_artifact_contract": all(
            (runs / record["scenario"] / record["method"] / f"seed_{record['seed']:03d}" / name).is_file()
            for record in records
            for name in (
                "config_resolved.json",
                "manifest.json",
                "observations.npz",
                "boundary_versions.npz",
                "plan_trace.npz",
                "trajectory.npz",
                "events.jsonl",
                "metrics.json",
            )
        ),
        "independent_truth_evidence": all(
            json.loads(
                (runs / record["scenario"] / record["method"] / f"seed_{record['seed']:03d}" / "manifest.json").read_text(
                    encoding="utf-8"
                )
            ).get("truth_access")
            == "evaluator_only"
            for record in records
        ),
        "frozen_commit": snapshot["frozen_commit"],
    }
    compliance_without_freeze = all(
        value for key, value in checks.items() if key not in {"formal_preflight", "frozen_commit"}
    )
    g0_to_g5_status = "PASS" if preflight_valid else "UNMET_PREFLIGHT"
    if preflight_valid and compliance_without_freeze and checks["frozen_commit"]:
        status = "PASS"
    elif preflight_valid and compliance_without_freeze:
        status = "UNMET_FROZEN_COMMIT"
    elif not preflight_valid and compliance_without_freeze and checks["frozen_commit"]:
        status = "UNMET_PREFLIGHT"
    elif not preflight_valid and compliance_without_freeze:
        status = "UNMET_PREFLIGHT_AND_FROZEN_COMMIT"
    else:
        status = "UNMET_COMPLIANCE_AND_FROZEN_COMMIT" if not checks["frozen_commit"] else "UNMET_COMPLIANCE"
    gates = {f"G{index}": g0_to_g5_status for index in range(6)}
    gates["G6"] = status
    status_counts = {
        item_status: int(sum(record["status"] == item_status for record in records))
        for item_status in sorted({str(record["status"]) for record in records})
    }
    gate = {
        "schema": "abcg-v2-step1-gates-v2",
        "overall_status": "PASS" if all(value == "PASS" for value in gates.values()) else status,
        "g6_status": status,
        "evaluated_commit": snapshot["commit"],
        "code_freeze_commit": snapshot["commit"],
        "frozen_commit": "PASS" if snapshot["frozen_commit"] else "FAIL",
        "gates": gates,
        "gate_basis": {
            "G0-G5": "commit-bound pytest, compileall, and pip check preflight",
            "G6": "formal paired evaluation checks plus a clean frozen checkout",
        },
        "checks": checks,
        "primary_record_count": len(records),
        "expected_primary_record_count": expected,
        "success_count": int(sum(record["success"] for record in records)),
        "failure_count": int(sum(not record["success"] for record in records)),
        "status_counts": status_counts,
        "actual_failure_gallery_count": len(gallery),
    }
    _write_json(output / "gate_evidence.json", gate)
    _write_report(output, config, aggregate, snapshot, gate)
    return gate
