"""PR6 per-case boundary and planner evaluation."""
from __future__ import annotations

from typing import Any

import numpy as np

from ...controllers import PeriodicArcCVTConfig, equal_arc_target_s, plan_periodic_arc_coverage
from ...estimation import BoundaryEstimateFailure, BoundaryEstimateV2, BoundaryV2Config, estimate_boundary_v2
from ...types import Array
from ..shared import symmetric_curve_errors as _symmetric_curve_errors
from .cases import _heldout_case, _neutralize_confidence, _truth_length
from .config import PR6EvaluationConfig


def _evaluate_boundary(
    boundary: BoundaryEstimateV2 | BoundaryEstimateFailure,
    truth: Array,
    planner_confidence: bool,
    config: PR6EvaluationConfig,
) -> tuple[dict[str, Any], Array | None]:
    if isinstance(boundary, BoundaryEstimateFailure):
        return {
            "valid": False,
            "boundary_status": boundary.status,
            "boundary_reason": str(boundary.diagnostics.get("reason", "unknown")),
            "boundary_method": boundary.method,
            "curve_chamfer": None,
            "curve_hausdorff": None,
            "length_relative_error": None,
            "confidence_mean": None,
            "confidence_min": None,
            "uncertainty_mean": None,
            "plan_status": "PLAN_SKIPPED_BOUNDARY_INVALID",
            "plan_h_initial": None,
            "plan_h_final": None,
            "plan_iterations": 0,
            "plan_max_arc_gap": None,
        }, None

    curve_chamfer, curve_hausdorff = _symmetric_curve_errors(boundary.curve_points, truth)
    truth_length = _truth_length(truth)
    planner_boundary = boundary if planner_confidence else _neutralize_confidence(boundary)
    guide_count = min(
        config.max_guides,
        max(3, int(np.ceil(boundary.length / config.required_arc_gap))),
    )
    equal = equal_arc_target_s(boundary.length, guide_count)
    phase = np.arange(guide_count, dtype=float)
    uneven = np.sort(
        np.mod(
            equal + 0.18 * (boundary.length / guide_count) * np.sin(2.0 * np.pi * phase / guide_count + 0.3),
            boundary.length,
        )
    )
    plan = plan_periodic_arc_coverage(
        planner_boundary,
        guide_count,
        PeriodicArcCVTConfig(
            max_iterations=300,
            h_tolerance=1.0e-8,
            target_tolerance=1.0e-6,
        ),
        init=uneven,
    )
    return {
        "valid": True,
        "boundary_status": "VALID",
        "boundary_reason": "valid",
        "boundary_method": boundary.method,
        "curve_chamfer": curve_chamfer,
        "curve_hausdorff": curve_hausdorff,
        "length_relative_error": abs(boundary.length - truth_length) / truth_length,
        "confidence_mean": float(np.mean(boundary.confidence)),
        "confidence_min": float(np.min(boundary.confidence)),
        "uncertainty_mean": float(np.mean(boundary.uncertainty)),
        "plan_status": plan.status,
        "plan_h_initial": float(plan.h_history[0]),
        "plan_h_final": float(plan.h_history[-1]),
        "plan_iterations": int(len(plan.gain_history)),
        "plan_max_arc_gap": float(plan.max_arc_gap),
    }, boundary.curve_points


def _run_paired_case(
    shape: str,
    seed: int,
    config: PR6EvaluationConfig,
    estimator_configs: dict[str, BoundaryV2Config],
) -> tuple[list[dict[str, Any]], dict[tuple[str, int, str], tuple[Array, Array, Array | None]]]:
    observation, truth = _heldout_case(shape, seed, config.observation_count, config.sample_spacing / 2.0)
    estimates = {
        name: estimate_boundary_v2(
            observation,
            estimator_config,
            np.random.default_rng(10_000_000 + seed),
        )
        for name, estimator_config in estimator_configs.items()
    }
    variants: dict[str, tuple[BoundaryEstimateV2 | BoundaryEstimateFailure, bool]] = {
        "radial_neutral": (estimates["radial_neutral"], False),
        "alpha_neutral": (estimates["alpha_neutral"], False),
        "alpha_bootstrap_gain": (estimates["alpha_bootstrap_gain"], True),
        "alpha_bootstrap_no_gain": (estimates["alpha_bootstrap_gain"], False),
    }
    case_records: list[dict[str, Any]] = []
    case_visuals: dict[tuple[str, int, str], tuple[Array, Array, Array | None]] = {}
    for variant, (boundary, planner_confidence) in variants.items():
        values, curve = _evaluate_boundary(boundary, truth, planner_confidence, config)
        estimator_key = (
            "radial_neutral"
            if variant == "radial_neutral"
            else "alpha_neutral"
            if variant == "alpha_neutral"
            else "alpha_bootstrap_gain"
        )
        record = {
            "shape": shape,
            "seed": int(seed),
            "variant": variant,
            "min_observation_coverage": estimator_configs[estimator_key].min_observation_coverage,
            **values,
        }
        case_records.append(record)
        case_visuals[(shape, int(seed), variant)] = (observation, truth, curve)
    return case_records, case_visuals
