"""PR6 held-out case generation and estimator setup."""
from __future__ import annotations

import numpy as np

from ...estimation import BoundaryEstimateV2, BoundaryV2Config
from ...geometry import resample_closed_curve_by_arclength
from ...types import Array
from ..shared import neutralize_confidence as _shared_neutralize_confidence
from ..shared import points_inside_polygon as _points_inside_polygon
from .config import PR6EvaluationConfig


def _polygon_for_shape(shape: str) -> Array:
    if shape == "u_shape":
        return np.array(
            [[2.0, 2.0], [6.0, 2.0], [6.0, 6.0], [5.0, 6.0], [5.0, 3.0], [3.0, 3.0], [3.0, 6.0], [2.0, 6.0]],
            dtype=float,
        )
    if shape == "c_shape":
        return np.array(
            [[2.0, 2.0], [6.0, 2.0], [6.0, 3.0], [3.5, 3.0], [3.5, 5.0], [6.0, 5.0], [6.0, 6.0], [2.0, 6.0]],
            dtype=float,
        )
    raise ValueError(f"unsupported held-out shape: {shape}")


def _heldout_case(shape: str, seed: int, count: int, spacing: float) -> tuple[Array, Array]:
    polygon = _polygon_for_shape(shape)
    rng = np.random.default_rng(100_000 + int(seed) + (0 if shape == "u_shape" else 10_000))
    accepted: list[Array] = []
    accepted_count = 0
    while accepted_count < count:
        candidates = rng.uniform(np.min(polygon, axis=0), np.max(polygon, axis=0), size=(count, 2))
        batch = candidates[_points_inside_polygon(candidates, polygon)]
        accepted.append(batch)
        accepted_count += len(batch)
    observation = np.vstack(accepted)[:count]
    truth, _, _, _, _ = resample_closed_curve_by_arclength(polygon, spacing=spacing)
    return observation, truth


def _truth_length(truth: Array) -> float:
    return float(np.sum(np.linalg.norm(np.roll(truth, -1, axis=0) - truth, axis=1)))


def _estimator_configs(config: PR6EvaluationConfig) -> dict[str, BoundaryV2Config]:
    common = {
        "safety_distance": 0.0,
        "sample_spacing": config.sample_spacing,
        "min_observation_coverage": 0.8,
    }
    return {
        "radial_neutral": BoundaryV2Config(
            estimator="radial",
            radial_bins=72,
            radial_smoothing_passes=3,
            bootstrap_samples=0,
            safety_distance=0.0,
            sample_spacing=config.sample_spacing,
            min_observation_coverage=0.6,
        ),
        "alpha_neutral": BoundaryV2Config(
            estimator="alpha",
            alpha_scale=config.alpha_scale,
            alpha_smoothing_passes=config.alpha_smoothing_passes,
            bootstrap_samples=0,
            **common,
        ),
        "alpha_bootstrap_gain": BoundaryV2Config(
            estimator="alpha",
            alpha_scale=config.alpha_scale,
            alpha_smoothing_passes=config.alpha_smoothing_passes,
            bootstrap_samples=config.bootstrap_samples,
            bootstrap_min_success_fraction=0.5,
            bootstrap_confidence_floor=0.15,
            **common,
        ),
    }


def _neutralize_confidence(boundary: BoundaryEstimateV2) -> BoundaryEstimateV2:
    return _shared_neutralize_confidence(
        boundary,
        status_label="bootstrap_computed_but_gain_ablated_pr6",
    )
