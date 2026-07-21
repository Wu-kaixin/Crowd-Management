"""G6 ablation, robustness, and stress-fixture runners."""
from __future__ import annotations

from typing import Any

import numpy as np

from ...controllers import PeriodicArcCVTConfig, ResourcePolicyConfig, allocate_guide_resources, plan_periodic_arc_coverage
from ...estimation import BoundaryEstimateFailure, BoundaryEstimateV2, BoundaryV2Config, estimate_boundary_v2
from ...geometry import resample_closed_curve_by_arclength
from ...runtime import run_tasks
from ...types import Array
from ..shared import bootstrap_metric_summary as _summary
from ..shared import curve_errors_with_p95 as _curve_errors
from ..shared import sample_polygon as _sample_polygon
from .cases import _boundary_config, _observed_case
from .config import ABLATION_VARIANTS, G6EvaluationConfig, NONCONVEX_SCENARIOS


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
