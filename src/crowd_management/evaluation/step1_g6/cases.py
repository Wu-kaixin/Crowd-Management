"""G6 scenario generation and boundary setup."""
from __future__ import annotations

import numpy as np

from ...estimation import BoundaryEstimateV2, BoundaryV2Config
from ...geometry import resample_closed_curve_by_arclength
from ...types import Array
from ..shared import neutralize_confidence as _shared_neutralize_confidence
from ..shared import points_inside_polygon as _inside_polygon  # noqa: F401
from ..shared import sample_polygon as _sample_polygon
from .config import G6EvaluationConfig, PRIMARY_SCENARIOS



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
    return _shared_neutralize_confidence(
        boundary,
        status_label="bootstrap_computed_but_gain_ablated_g6",
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
