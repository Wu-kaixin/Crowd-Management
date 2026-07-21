"""Export raw inputs and Python outputs for independent Wolfram verification.

Every case file contains raw inputs plus the current Python implementation's
outputs.  The Wolfram side (``wolfram/verify_main.wls``) recomputes each
quantity independently from the raw inputs and compares; it never echoes the
Python "expected" values back.

Outputs land in ``artifacts/math_verification/cases/``.  All randomness uses
fixed seeds recorded in the case files.
"""
from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path

import numpy as np
import scipy

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from crowd_management.containment_metrics import (  # noqa: E402
    angular_uniformity_error,
    coverage_ratio_to_points,
    max_euclidean_boundary_distance_to_points,
    minimum_inter_guider_distance,
)
from crowd_management.controllers.abcg_v2 import (  # noqa: E402
    ABCGv2Config,
    ABCGv2Controller,
    integrate_guide_positions,
    nominal_guide_velocity,
)
from crowd_management.controllers.assignment import (  # noqa: E402
    AssignmentConfig,
    assign_guides_to_targets,
)
from crowd_management.controllers.periodic_arc_cvt import (  # noqa: E402
    equal_arc_target_s,
    periodic_uniform_coverage_cost,
)
from crowd_management.controllers.resources import (  # noqa: E402
    ResourcePolicy,
    ResourcePolicyConfig,
)
from crowd_management.controllers.safety import (  # noqa: E402
    VelocitySafetyConfig,
    _build_velocity_halfspaces,
    project_velocity_safety,
)
from crowd_management.geometry.arclength import (  # noqa: E402
    has_self_intersections,
    max_consecutive_arc_gap,
    periodic_arclength_distance,
    resample_closed_curve_by_arclength,
    signed_area,
)

OUTPUT_DIR = REPO_ROOT / "artifacts" / "math_verification" / "cases"
SEED = 20260721


def _tolist(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    return value


def _write(name: str, payload: dict) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / name
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=1, sort_keys=True)
    print(f"wrote {path.relative_to(REPO_ROOT)}")


# ---------------------------------------------------------------- geometry
def _curve_bank() -> dict[str, np.ndarray]:
    theta = np.linspace(0.0, 2.0 * np.pi, 48, endpoint=False)
    circle = np.column_stack((5.0 + 2.0 * np.cos(theta), 5.0 + 2.0 * np.sin(theta)))
    ellipse = np.column_stack((5.0 + 3.0 * np.cos(theta), 5.0 + 1.4 * np.sin(theta)))
    convex_polygon = np.array(
        [[0.0, 0.0], [4.0, 0.0], [6.0, 2.0], [5.0, 5.0], [2.0, 6.0], [-1.0, 3.0]], dtype=float
    )
    nonconvex_polygon = np.array(
        [[0.0, 0.0], [6.0, 0.0], [6.0, 4.0], [3.0, 1.5], [0.0, 4.0]], dtype=float
    )
    nearly_collinear = np.array(
        [[0.0, 0.0], [2.0, 1.0e-7], [4.0, 0.0], [4.0, 3.0], [0.0, 3.0]], dtype=float
    )
    return {
        "circle": circle,
        "ellipse": ellipse,
        "convex_polygon": convex_polygon,
        "nonconvex_polygon": nonconvex_polygon,
        "nearly_collinear": nearly_collinear,
    }


def export_geometry() -> None:
    rng = np.random.default_rng(SEED)
    cases = []
    for name, points in _curve_bank().items():
        curve, arc_s, length, tangents, normals = resample_closed_curve_by_arclength(
            points, spacing=0.25
        )
        centroid = np.mean(curve, axis=0)
        cases.append(
            {
                "name": name,
                "input_points": _tolist(points),
                "spacing": 0.25,
                "python_signed_area": signed_area(points),
                "python_length": length,
                "python_sample_count": int(len(curve)),
                "python_arc_s_first3": _tolist(arc_s[:3]),
                "python_arc_s_last": float(arc_s[-1]),
                "python_curve_points": _tolist(curve),
                "python_tangents": _tolist(tangents),
                "python_outward_normals": _tolist(normals),
                "python_centroid": _tolist(centroid),
            }
        )

    # Degenerate/rejection cases (Python-side behaviour recorded for the report).
    rejections = []
    repeated = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 0.0], [0.0, 1.0]], dtype=float)
    bowtie = np.array([[0.0, 0.0], [2.0, 2.0], [2.0, 0.0], [0.0, 2.0]], dtype=float)
    for name, pts in (("repeated_point", repeated), ("self_intersecting", bowtie)):
        try:
            resample_closed_curve_by_arclength(pts, spacing=0.25)
            outcome = "accepted"
        except ValueError as error:
            outcome = f"ValueError: {error}"
        rejections.append({"name": name, "input_points": _tolist(pts), "python_outcome": outcome})
    rejections.append(
        {
            "name": "self_intersecting_flag",
            "input_points": _tolist(bowtie),
            "python_outcome": f"has_self_intersections={has_self_intersections(bowtie)}",
        }
    )

    # Periodic distance and max-gap samples on exact rationals plus random floats.
    length = 10.0
    pd_pairs = [[0.0, 9.0], [1.0, 6.0], [2.5, 2.5], [-3.0, 4.0], [12.5, 0.5], [9.999, 0.001]]
    pd_cases = [
        {"a": a, "b": b, "length": length, "python_d": periodic_arclength_distance(a, b, length)}
        for a, b in pd_pairs
    ]
    gap_sets = [
        {"sites": [0.0, 2.5, 5.0, 7.5], "length": 10.0},
        {"sites": [9.5, 0.5], "length": 10.0},
        {"sites": [3.0], "length": 10.0},
        {"sites": _tolist(np.sort(rng.uniform(0.0, 10.0, size=7))), "length": 10.0},
        {"sites": [11.0, 23.5, -2.0], "length": 10.0},
    ]
    for case in gap_sets:
        case["python_max_gap"] = max_consecutive_arc_gap(
            np.asarray(case["sites"], dtype=float), case["length"]
        )

    _write(
        "geometry_cases.json",
        {
            "seed": SEED,
            "curves": cases,
            "rejections": rejections,
            "periodic_distance": pd_cases,
            "max_gap": gap_sets,
        },
    )


# ------------------------------------------------------------- coverage
def export_coverage() -> None:
    rng = np.random.default_rng(SEED + 1)
    cases = []
    for length in (10.0, 6.283185307179586, 47.5):
        for m in (1, 2, 3, 5, 8):
            sites = equal_arc_target_s(length, m, phase=0.37)
            cases.append(
                {
                    "kind": "equal_arc",
                    "length": length,
                    "m": m,
                    "phase": 0.37,
                    "sites": _tolist(sites),
                    "python_H": periodic_uniform_coverage_cost(sites, length),
                    "python_max_gap": max_consecutive_arc_gap(sites, length),
                }
            )
    for trial in range(6):
        length = float(rng.uniform(5.0, 40.0))
        m = int(rng.integers(2, 9))
        sites = np.sort(rng.uniform(0.0, length, size=m))
        if np.any(np.diff(np.r_[sites, sites[0] + length]) <= 1.0e-6):
            continue
        cases.append(
            {
                "kind": "random",
                "trial": trial,
                "length": length,
                "m": m,
                "sites": _tolist(sites),
                "python_H": periodic_uniform_coverage_cost(sites, length),
                "python_max_gap": max_consecutive_arc_gap(sites, length),
            }
        )
    # Relaxed-Lloyd monotonicity property case (COV-005): run the actual planner
    # on a synthetic valid boundary with non-trivial confidence and export the
    # H history plus final sites for independent recomputation.
    from dataclasses import replace as dc_replace

    from crowd_management.controllers.periodic_arc_cvt import (
        PeriodicArcCVTConfig,
        plan_periodic_arc_coverage,
    )
    from crowd_management.estimation.boundary_v2 import boundary_v2_from_curve

    theta = np.linspace(0.0, 2.0 * np.pi, 96, endpoint=False)
    curve = np.column_stack((8.0 + 3.0 * np.cos(theta), 6.0 + 2.0 * np.sin(theta)))
    boundary = boundary_v2_from_curve(curve, safety_distance=0.5, sample_spacing=0.15, method="synthetic")
    confidence = 0.2 + 0.8 * np.abs(np.sin(3.0 * boundary.arc_s / boundary.length * 2.0 * np.pi))
    boundary = dc_replace(boundary, confidence=np.clip(confidence, 0.0, 1.0))
    m_sites = 6
    init = np.mod(
        equal_arc_target_s(boundary.length, m_sites)
        + 0.18 * (boundary.length / m_sites) * np.sin(2.0 * np.pi * np.arange(m_sites) / m_sites + 0.3),
        boundary.length,
    )
    plan = plan_periodic_arc_coverage(boundary, m_sites, PeriodicArcCVTConfig(), init=init)
    lloyd_case = {
        "length": float(boundary.length),
        "m": m_sites,
        "init_sites": _tolist(init),
        "python_final_sites": _tolist(plan.target_s),
        "python_h_history": _tolist(plan.h_history),
        "python_status": plan.status,
        "python_converged": bool(plan.converged),
        "python_max_arc_gap": float(plan.max_arc_gap),
        "monotonic_tolerance": 1.0e-10,
    }
    _write("coverage_cases.json", {"seed": SEED + 1, "cases": cases, "lloyd_case": lloyd_case})


# ------------------------------------------------------------- resources
def export_resources() -> None:
    config = ResourcePolicyConfig(g_req=2.5, m_min=3, increase_hysteresis=0.1, decrease_hysteresis=0.1)
    policy = ResourcePolicy(config)
    grid = []
    lengths = [0.5, 2.4, 2.5, 2.6, 7.4, 7.5, 7.6, 12.49, 12.5, 12.51, 25.0, 60.0]
    for length in lengths:
        for available in (0, 2, 3, 5, 10):
            for previous in (None, 3, 5, 8):
                decision = policy.decide(length, available, previous)
                grid.append(
                    {
                        "length": length,
                        "available": available,
                        "previous": previous,
                        "python_requested": decision.requested_count,
                        "python_desired": decision.desired_count,
                        "python_active": decision.active_count,
                        "python_reserve": decision.reserve_count,
                        "python_unmet": decision.unmet_target_count,
                        "python_status": decision.status,
                        "python_hysteresis_applied": decision.hysteresis_applied,
                    }
                )
    rejections = []
    for kwargs in (
        {"boundary_length": 0.0, "available_count": 3},
        {"boundary_length": -1.0, "available_count": 3},
        {"boundary_length": float("nan"), "available_count": 3},
        {"boundary_length": 5.0, "available_count": -1},
    ):
        try:
            policy.decide(**kwargs)
            outcome = "accepted"
        except (ValueError, TypeError) as error:
            outcome = f"{type(error).__name__}: {error}"
        rejections.append({"inputs": {k: str(v) for k, v in kwargs.items()}, "python_outcome": outcome})
    try:
        ResourcePolicyConfig(g_req=0.0)
        greq_outcome = "accepted"
    except ValueError as error:
        greq_outcome = f"ValueError: {error}"
    rejections.append({"inputs": {"g_req": "0.0"}, "python_outcome": greq_outcome})

    _write(
        "resources_cases.json",
        {
            "config": {
                "g_req": config.g_req,
                "m_min": config.m_min,
                "increase_hysteresis": config.increase_hysteresis,
                "decrease_hysteresis": config.decrease_hysteresis,
            },
            "grid": grid,
            "rejections": rejections,
        },
    )


# ------------------------------------------------------------ assignment
def export_assignment() -> None:
    rng = np.random.default_rng(SEED + 2)
    config = AssignmentConfig()
    cases = []
    for n in range(1, 8):
        for trial in range(3):
            # Integer coordinates keep all costs exactly representable.
            guides = rng.integers(0, 21, size=(n, 2)).astype(float)
            targets = rng.integers(0, 21, size=(n, 2)).astype(float)
            previous = None
            if trial == 2 and n >= 2:
                previous = np.arange(n)
                previous = np.roll(previous, 1)
            result = assign_guides_to_targets(guides, targets, config, previous)
            cases.append(
                {
                    "n_guides": n,
                    "n_targets": n,
                    "trial": trial,
                    "guides": _tolist(guides),
                    "targets": _tolist(targets),
                    "previous": _tolist(previous) if previous is not None else None,
                    "lambda_switch": config.lambda_switch,
                    "reserve_cost": config.reserve_cost,
                    "unmet_target_cost": config.unmet_target_cost,
                    "python_guide_to_target": _tolist(result.guide_to_target),
                    "python_total_cost": result.total_cost,
                    "python_switch_count": result.switch_count,
                    "python_status": result.status,
                }
            )
    # Rectangular cases: more guides than targets (reserve) and vice versa (unmet).
    for n_guides, n_targets in ((5, 3), (3, 5), (4, 1)):
        guides = rng.integers(0, 21, size=(n_guides, 2)).astype(float)
        targets = rng.integers(0, 21, size=(n_targets, 2)).astype(float)
        result = assign_guides_to_targets(guides, targets, config, None)
        cases.append(
            {
                "n_guides": n_guides,
                "n_targets": n_targets,
                "trial": 0,
                "guides": _tolist(guides),
                "targets": _tolist(targets),
                "previous": None,
                "lambda_switch": config.lambda_switch,
                "reserve_cost": config.reserve_cost,
                "unmet_target_cost": config.unmet_target_cost,
                "python_guide_to_target": _tolist(result.guide_to_target),
                "python_total_cost": result.total_cost,
                "python_switch_count": result.switch_count,
                "python_status": result.status,
            }
        )
    # Deliberate tie instance: symmetric square, two optimal assignments.
    guides = np.array([[0.0, 0.0], [2.0, 0.0]])
    targets = np.array([[1.0, 1.0], [1.0, -1.0]])
    result = assign_guides_to_targets(guides, targets, config, None)
    tie_case = {
        "guides": _tolist(guides),
        "targets": _tolist(targets),
        "previous": None,
        "lambda_switch": config.lambda_switch,
        "python_guide_to_target": _tolist(result.guide_to_target),
        "python_total_cost": result.total_cost,
        "python_status": result.status,
        "note": "both assignments cost 4; records which one SciPy returns deterministically",
    }
    _write("assignment_cases.json", {"seed": SEED + 2, "cases": cases, "tie_case": tie_case})


# ------------------------------------------------------------ controller
def export_controller() -> None:
    from crowd_management.controllers.assignment import AssignmentResult

    def _make_assignment(mapping: np.ndarray, n_targets: int) -> AssignmentResult:
        target_to_guide = np.full(n_targets, -1, dtype=int)
        for guide_id, target_id in enumerate(mapping):
            if target_id >= 0:
                target_to_guide[target_id] = guide_id
        return AssignmentResult(
            guide_to_target=mapping,
            target_to_guide=target_to_guide,
            reserve_guide_ids=np.flatnonzero(mapping < 0),
            unmet_target_ids=np.flatnonzero(target_to_guide < 0),
            cost_matrix=np.zeros((len(mapping), n_targets)),
            total_cost=0.0,
            switch_count=0,
            status="VALID",
        )

    episodes = []
    scenarios = [
        # (name, dt, k_p, v_max, initial, targets, mapping)
        (
            "unsaturated_contraction",
            0.1,
            1.5,
            100.0,
            np.array([[0.0, 0.0], [4.0, 1.0]]),
            np.array([[1.0, 2.0], [3.0, -1.0]]),
            np.array([0, 1]),
        ),
        (
            "saturated_then_unsaturated",
            0.1,
            1.5,
            1.0,
            np.array([[0.0, 0.0]]),
            np.array([[6.0, 8.0]]),
            np.array([0]),
        ),
        (
            "with_reserve_guide",
            0.1,
            1.0,
            1.0,
            np.array([[0.0, 0.0], [5.0, 5.0], [9.0, 1.0]]),
            np.array([[2.0, 2.0], [8.0, 2.0]]),
            np.array([0, -1, 1]),
        ),
    ]
    for name, dt, k_p, v_max, initial, targets, mapping in scenarios:
        config = ABCGv2Config(dt=dt, k_p=k_p, v_max=v_max, max_steps=120)
        controller = ABCGv2Controller(config)
        assignment = _make_assignment(mapping, len(targets))
        episode = controller.run_fixed_target_episode(initial, targets, assignment)
        episodes.append(
            {
                "name": name,
                "dt": dt,
                "k_p": k_p,
                "v_max": v_max,
                "initial": _tolist(initial),
                "targets": _tolist(targets),
                "guide_to_target": _tolist(mapping),
                "python_positions": _tolist(episode.positions),
                "python_nominal_controls": _tolist(episode.nominal_controls),
                "python_applied_controls": _tolist(episode.applied_controls),
                "python_tracking_rmse": _tolist(episode.tracking_rmse),
                "python_status": episode.status,
                "python_stop_reason": episode.stop_reason,
            }
        )

    # Saturation boundary sampling for CTRL-006.
    rng = np.random.default_rng(SEED + 3)
    sat_samples = []
    for _ in range(200):
        p = rng.uniform(-10, 10, size=(1, 2))
        z = p + rng.uniform(-5, 5, size=(1, 2))
        k_p = float(rng.uniform(0.1, 10.0))
        v_max = float(rng.uniform(0.01, 3.0))
        u = nominal_guide_velocity(p, z, np.array([True]), k_p, v_max)
        sat_samples.append(
            {
                "p": _tolist(p[0]),
                "z": _tolist(z[0]),
                "k_p": k_p,
                "v_max": v_max,
                "python_u": _tolist(u[0]),
                "python_speed": float(np.linalg.norm(u[0])),
            }
        )
    config_rejection = None
    try:
        ABCGv2Config(dt=0.5, k_p=2.5)
    except ValueError as error:
        config_rejection = f"ValueError: {error}"
    _write(
        "controller_cases.json",
        {
            "seed": SEED + 3,
            "episodes": episodes,
            "saturation_samples": sat_samples,
            "python_kp_dt_guard": config_rejection,
        },
    )


# ---------------------------------------------------------------- safety
def export_safety() -> None:
    instances = []
    scenarios = [
        (
            "guide_pair_and_crowd_projected",
            np.array([[4.0, 5.0], [4.65, 5.0]]),
            np.array([[1.0, 0.0], [-1.0, 0.0]]),
            np.array([[4.0, 5.9], [6.0, 5.0]]),
            np.array([20.0, 14.0]),
            VelocitySafetyConfig(min_guide_distance=0.6, min_crowd_distance=0.8, room_margin=0.25),
        ),
        (
            "room_wall_and_speed_ball",
            np.array([[0.3, 7.0]]),
            np.array([[-3.0, 0.5]]),
            np.empty((0, 2)),
            np.array([20.0, 14.0]),
            VelocitySafetyConfig(min_guide_distance=0.6, min_crowd_distance=0.8, room_margin=0.25),
        ),
        (
            "three_guides_mixed",
            np.array([[5.0, 5.0], [5.7, 5.15], [5.3, 4.35]]),
            np.array([[0.9, 0.3], [-0.9, -0.2], [0.2, 0.9]]),
            np.array([[5.35, 5.95], [4.15, 4.6]]),
            np.array([20.0, 14.0]),
            VelocitySafetyConfig(min_guide_distance=0.6, min_crowd_distance=0.8, room_margin=0.25),
        ),
        (
            "infeasible_emergency_stop",
            np.array([[5.0, 5.0]]),
            np.array([[0.5, 0.0]]),
            np.array([[5.2, 5.0]]),
            np.array([20.0, 14.0]),
            VelocitySafetyConfig(
                min_guide_distance=0.6,
                min_crowd_distance=5.0,
                room_margin=0.25,
                max_projection_sweeps=60,
            ),
        ),
    ]
    dt, v_max = 0.1, 1.0
    for name, positions, nominal, crowd, room, config in scenarios:
        matrix, bounds, kinds, counts = _build_velocity_halfspaces(
            positions, crowd, room, dt, v_max, config
        )
        result = project_velocity_safety(positions, nominal, crowd, room, dt, v_max, config)
        instances.append(
            {
                "name": name,
                "positions": _tolist(positions),
                "nominal": _tolist(nominal),
                "crowd": _tolist(crowd),
                "room": _tolist(room),
                "dt": dt,
                "v_max": v_max,
                "config": {
                    "min_guide_distance": config.min_guide_distance,
                    "min_crowd_distance": config.min_crowd_distance,
                    "room_margin": config.room_margin,
                    "residual_tolerance": config.residual_tolerance,
                    "max_projection_sweeps": config.max_projection_sweeps,
                },
                "python_matrix": _tolist(matrix),
                "python_bounds": _tolist(bounds),
                "python_kinds": _tolist(list(kinds)),
                "python_type_counts": counts,
                "python_projected": _tolist(result.projected_control),
                "python_applied": _tolist(result.applied_control),
                "python_status": result.status,
                "python_sweeps": result.projection_sweeps,
                "python_max_residual_after": result.max_residual_after,
                "python_emergency_stop": bool(result.emergency_stop),
            }
        )
    _write("safety_cases.json", {"dt": dt, "v_max": v_max, "instances": instances})


# --------------------------------------------------------------- metrics
def export_metrics() -> None:
    rng = np.random.default_rng(SEED + 4)
    hand = {
        "guides": [[0.0, 0.0], [4.0, 0.0]],
        "boundary": [[1.0, 0.0], [3.0, 0.0], [2.0, 2.0]],
        "coverage_radius": 1.5,
    }
    hand["python_coverage_ratio"] = coverage_ratio_to_points(
        np.asarray(hand["guides"]), np.asarray(hand["boundary"]), hand["coverage_radius"]
    )
    hand["python_max_euclidean_distance"] = max_euclidean_boundary_distance_to_points(
        np.asarray(hand["guides"]), np.asarray(hand["boundary"])
    )

    random_cases = []
    for trial in range(5):
        guides = rng.uniform(0.0, 10.0, size=(4, 2))
        boundary = rng.uniform(0.0, 10.0, size=(12, 2))
        angle = float(rng.uniform(0.0, 2.0 * np.pi))
        shift = rng.uniform(-5.0, 5.0, size=2)
        rotation = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
        random_cases.append(
            {
                "trial": trial,
                "guides": _tolist(guides),
                "boundary": _tolist(boundary),
                "coverage_radius": 2.0,
                "rotation_angle": angle,
                "shift": _tolist(shift),
                "python_coverage_ratio": coverage_ratio_to_points(guides, boundary, 2.0),
                "python_max_euclidean_distance": max_euclidean_boundary_distance_to_points(
                    guides, boundary
                ),
                "python_min_inter_guide": minimum_inter_guider_distance(guides),
                "python_coverage_ratio_transformed": coverage_ratio_to_points(
                    guides @ rotation.T + shift, boundary @ rotation.T + shift, 2.0
                ),
            }
        )

    center = np.array([5.0, 5.0])
    angular = {
        "center": _tolist(center),
        "guides": [[7.0, 5.0], [5.0, 7.0], [3.0, 5.0], [5.0, 3.0]],
    }
    angular["python_angular_uniformity_error"] = angular_uniformity_error(
        np.asarray(angular["guides"]), center
    )
    uneven = {
        "center": _tolist(center),
        "guides": [[7.0, 5.0], [7.001, 5.1], [3.0, 5.0]],
    }
    uneven["python_angular_uniformity_error"] = angular_uniformity_error(
        np.asarray(uneven["guides"]), center
    )

    # Path length / control energy on a recorded mini-trace.
    positions = np.array(
        [
            [[0.0, 0.0], [10.0, 0.0]],
            [[0.1, 0.0], [9.9, 0.1]],
            [[0.25, 0.05], [9.7, 0.25]],
        ]
    )
    controls = np.array(
        [
            [[1.0, 0.0], [-1.0, 1.0]],
            [[1.5, 0.5], [-2.0, 1.5]],
        ]
    )
    dt = 0.1
    path_length = float(np.sum(np.linalg.norm(np.diff(positions, axis=0), axis=2)))
    control_energy = float(dt * np.sum(controls**2))
    trace = {
        "positions": _tolist(positions),
        "controls": _tolist(controls),
        "dt": dt,
        "python_path_length": path_length,
        "python_control_energy": control_energy,
    }
    _write(
        "metrics_cases.json",
        {
            "seed": SEED + 4,
            "hand_case": hand,
            "random_cases": random_cases,
            "angular_case": angular,
            "angular_uneven_case": uneven,
            "trace_case": trace,
        },
    )


# ------------------------------------------------------------ statistics
def export_statistics() -> None:
    rng = np.random.default_rng(SEED + 5)
    values = np.round(rng.normal(1.0, 0.4, size=30), 6)
    resamples = 400
    indices = rng.integers(0, len(values), size=(resamples, len(values)))
    means = np.mean(values[indices], axis=1)
    worst_count = max(1, int(np.ceil(0.05 * len(values))))
    ordered = np.sort(values)

    summary_lower = {
        "direction": "lower",
        "values": _tolist(values),
        "resample_indices": _tolist(indices),
        "python_mean": float(np.mean(values)),
        "python_median": float(np.median(values)),
        "python_p95": float(np.percentile(values, 95.0)),
        "python_ci95_low": float(np.percentile(means, 2.5)),
        "python_ci95_high": float(np.percentile(means, 97.5)),
        "python_worst5_mean": float(np.mean(ordered[-worst_count:])),
    }

    differences = np.round(rng.normal(-0.15, 0.3, size=30), 6)
    diff_indices = rng.integers(0, len(differences), size=(resamples, len(differences)))
    diff_means = np.mean(differences[diff_indices], axis=1)
    std = float(np.std(differences, ddof=1))
    paired = {
        "direction": "lower",
        "differences": _tolist(differences),
        "resample_indices": _tolist(diff_indices),
        "python_mean_difference": float(np.mean(differences)),
        "python_median_difference": float(np.median(differences)),
        "python_ci95_low": float(np.percentile(diff_means, 2.5)),
        "python_ci95_high": float(np.percentile(diff_means, 97.5)),
        "python_cohen_dz": float(np.mean(differences) / std),
        "python_win_rate": float(np.mean(differences < 0.0)),
    }

    degenerate = {
        "values": [2.5, 2.5, 2.5],
        "python_std_ddof1": float(np.std(np.array([2.5, 2.5, 2.5]), ddof=1)),
        "python_cohen_dz": None,
        "note": "identical samples: std=0 so Cohen d_z is reported as None",
    }

    # Bootstrap-uncertainty formula cross-check (BND-001/BND-002).
    base_curve = np.column_stack(
        (np.cos(np.linspace(0, 2 * np.pi, 20, endpoint=False)), np.sin(np.linspace(0, 2 * np.pi, 20, endpoint=False)))
    )
    replicas = []
    for _ in range(4):
        jitter = rng.normal(0.0, 0.05, size=base_curve.shape)
        replicas.append(base_curve + jitter)
    pairwise = [
        np.min(np.linalg.norm(base_curve[:, None, :] - replica[None, :, :], axis=2), axis=1)
        for replica in replicas
    ]
    samples = np.asarray(pairwise)
    uncertainty = np.sqrt(np.mean(samples**2, axis=0))
    scale = max(0.08, float(np.median(uncertainty)), 1.0e-12)
    confidence = np.clip(np.exp(-uncertainty / scale), 0.15, 1.0)
    bootstrap_case = {
        "base_curve": _tolist(base_curve),
        "replicas": [_tolist(r) for r in replicas],
        "sample_spacing": 0.08,
        "confidence_floor": 0.15,
        "python_uncertainty": _tolist(uncertainty),
        "python_confidence_scale": scale,
        "python_confidence": _tolist(confidence),
    }

    # Synthetic-record aggregation: failure denominator and missing pairs.
    from crowd_management.evaluation.step1_g6 import (
        G6EvaluationConfig,
        METRIC_DIRECTIONS,
        _aggregate,
        _paired_comparisons,
    )

    config = G6EvaluationConfig(seeds=tuple(range(6)), scenarios=("circle",), methods=("uniform_arc", "abcg_v2"))
    records = []
    for seed in config.seeds:
        for method in config.methods:
            failed = method == "abcg_v2" and seed in (2, 4)
            record = {
                "scenario": "circle",
                "seed": seed,
                "method": method,
                "status": "TIMEOUT" if failed else "CONVERGED",
                "success": not failed,
            }
            for metric in METRIC_DIRECTIONS:
                if failed and metric in ("tracking_rmse_final", "convergence_time_s"):
                    record[metric] = None
                else:
                    record[metric] = round(1.0 + 0.1 * seed + (0.05 if method == "abcg_v2" else 0.0), 6)
            records.append(record)
    aggregate = _aggregate(records, config)
    comparisons = _paired_comparisons(records, config)
    circle_abcg = aggregate["circle"]["abcg_v2"]
    circle_cmp = comparisons["circle"]["abcg_v2_minus_uniform_arc"]
    aggregation_case = {
        "records": records,
        "python_run_count": circle_abcg["run_count"],
        "python_failure_count": circle_abcg["failure_count"],
        "python_failure_rate": circle_abcg["failure_rate"],
        "python_paired_count_rmse": circle_cmp["tracking_rmse_final"]["paired_count"],
        "python_missing_pair_count_rmse": circle_cmp["tracking_rmse_final"]["missing_pair_count"],
        "python_paired_count_path": circle_cmp["path_length_m"]["paired_count"],
        "python_mean_difference_path": circle_cmp["path_length_m"][
            "mean_difference_abcg_v2_minus_baseline"
        ],
    }

    _write(
        "statistics_cases.json",
        {
            "seed": SEED + 5,
            "summary_case": summary_lower,
            "paired_case": paired,
            "degenerate_case": degenerate,
            "bootstrap_case": bootstrap_case,
            "aggregation_case": aggregation_case,
        },
    )


def export_environment() -> None:
    def _git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], capture_output=True, text=True, cwd=REPO_ROOT, check=True
        ).stdout.strip()

    _write(
        "environment.json",
        {
            "python_version": platform.python_version(),
            "numpy_version": np.__version__,
            "scipy_version": scipy.__version__,
            "os": f"{platform.system()} {platform.release()}",
            "repo_head_sha": _git("rev-parse", "HEAD"),
            "audited_main_sha": _git("merge-base", "HEAD", "main"),
            "export_seed_base": SEED,
        },
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    export_geometry()
    export_coverage()
    export_resources()
    export_assignment()
    export_controller()
    export_safety()
    export_metrics()
    export_statistics()
    export_environment()
    hashes = {
        path.name: _sha256(path)
        for path in sorted(OUTPUT_DIR.glob("*.json"))
        if path.name != "case_hashes.json"
    }
    _write("case_hashes.json", hashes)


if __name__ == "__main__":
    main()
