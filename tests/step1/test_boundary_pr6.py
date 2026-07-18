from __future__ import annotations

import numpy as np

from crowd_management.estimation import (
    BoundaryEstimateFailure,
    BoundaryEstimateV2,
    BoundaryV2Config,
    estimate_boundary_v2,
)


def _inside_polygon(points: np.ndarray, polygon: np.ndarray) -> np.ndarray:
    x = points[:, 0]
    y = points[:, 1]
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


def _u_shape_observation(seed: int = 0, count: int = 260) -> tuple[np.ndarray, np.ndarray]:
    polygon = np.array(
        [
            [2.0, 2.0],
            [6.0, 2.0],
            [6.0, 6.0],
            [5.0, 6.0],
            [5.0, 3.0],
            [3.0, 3.0],
            [3.0, 6.0],
            [2.0, 6.0],
        ]
    )
    rng = np.random.default_rng(seed)
    accepted: list[np.ndarray] = []
    while sum(len(batch) for batch in accepted) < count:
        candidates = rng.uniform([2.0, 2.0], [6.0, 6.0], size=(count, 2))
        accepted.append(candidates[_inside_polygon(candidates, polygon)])
    return np.vstack(accepted)[:count], polygon


def _alpha_config(**overrides: object) -> BoundaryV2Config:
    values: dict[str, object] = {
        "estimator": "alpha",
        "safety_distance": 0.0,
        "sample_spacing": 0.08,
        "alpha_scale": 2.5,
        "bootstrap_samples": 0,
        "min_observation_coverage": 0.8,
        "room_size": (8.0, 8.0),
    }
    values.update(overrides)
    return BoundaryV2Config(**values)


def test_alpha_shape_recovers_a_single_concave_u_boundary() -> None:
    points, _ = _u_shape_observation(seed=3)

    result = estimate_boundary_v2(points, _alpha_config(), np.random.default_rng(11))

    assert isinstance(result, BoundaryEstimateV2)
    assert result.method == "alpha_shape"
    assert result.diagnostics["estimator"] == "alpha"
    assert result.diagnostics["alpha_radius_used"] > 0.0
    assert result.diagnostics["observation_coverage_ratio"] >= 0.8
    assert np.min(np.linalg.norm(result.curve_points - np.array([4.0, 3.0]), axis=1)) < 0.55
    assert result.diagnostics["confidence_status"] == "neutral_disabled_pr6_ablation"


def test_alpha_bootstrap_is_finite_nontrivial_and_reproducible() -> None:
    points, _ = _u_shape_observation(seed=4)
    config = _alpha_config(
        bootstrap_samples=12,
        bootstrap_min_success_fraction=0.5,
        bootstrap_confidence_floor=0.2,
    )

    first = estimate_boundary_v2(points, config, np.random.default_rng(17))
    second = estimate_boundary_v2(points, config, np.random.default_rng(17))

    assert isinstance(first, BoundaryEstimateV2)
    assert isinstance(second, BoundaryEstimateV2)
    assert first.diagnostics["confidence_status"] == "bootstrap_estimated_pr6"
    assert first.diagnostics["bootstrap_success_count"] >= 6
    assert np.all(np.isfinite(first.uncertainty))
    assert np.all((first.confidence >= 0.2) & (first.confidence <= 1.0))
    assert np.any(first.uncertainty > 0.0)
    assert np.any(first.confidence < 1.0)
    assert np.array_equal(first.curve_points, second.curve_points)
    assert np.array_equal(first.uncertainty, second.uncertainty)
    assert np.array_equal(first.confidence, second.confidence)


def test_alpha_shape_too_small_fails_explicitly_without_nan() -> None:
    points, _ = _u_shape_observation(seed=5)

    result = estimate_boundary_v2(
        points,
        _alpha_config(alpha_radius=1.0e-4),
        np.random.default_rng(19),
    )

    assert isinstance(result, BoundaryEstimateFailure)
    assert result.status == "BOUNDARY_INVALID"
    assert "alpha" in str(result.diagnostics["reason"])
    assert all(np.isfinite(value) for value in result.diagnostics.values() if isinstance(value, float))


def test_alpha_shape_keeps_multicomponent_observation_as_failure() -> None:
    rng = np.random.default_rng(23)
    points = np.vstack(
        (
            rng.normal([2.0, 2.0], 0.15, size=(80, 2)),
            rng.normal([6.0, 6.0], 0.15, size=(80, 2)),
        )
    )

    result = estimate_boundary_v2(
        points,
        _alpha_config(connectivity_radius=0.5),
        np.random.default_rng(29),
    )

    assert isinstance(result, BoundaryEstimateFailure)
    assert result.status == "BOUNDARY_INVALID"
    assert result.component_count == 2
    assert result.diagnostics["reason"] == "multiple_significant_components"
