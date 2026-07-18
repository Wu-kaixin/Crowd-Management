from __future__ import annotations

import numpy as np
import pytest

from crowd_management.crowd import StaticCrowdConfig, generate_static_crowd
from crowd_management.estimation import (
    BoundaryEstimateFailure,
    BoundaryEstimateV2,
    BoundaryV2Config,
    boundary_v2_from_curve,
    estimate_boundary_v2,
)


def test_radial_adapter_builds_valid_circle_geometry() -> None:
    crowd_cfg = StaticCrowdConfig.from_dict(
        {
            "shape": "circle",
            "count": 900,
            "center": [5.0, 4.0],
            "radius": 2.0,
            "noise_std": 0.0,
        },
        seed=11,
    )
    observation = generate_static_crowd(crowd_cfg)
    config = BoundaryV2Config(
        safety_distance=0.4,
        sample_spacing=0.1,
        radial_bins=36,
        radial_percentile=99.0,
        radial_smoothing_passes=4,
    )

    result = estimate_boundary_v2(observation, config, np.random.default_rng(11))

    assert isinstance(result, BoundaryEstimateV2)
    assert result.topology_valid
    assert result.component_count == 1
    assert result.method == "radial_adapter"
    assert result.version == 2
    assert result.length == pytest.approx(2.0 * np.pi * 2.0, rel=0.08)
    assert result.arc_s.shape == (len(result.curve_points),)
    assert result.offset_points.shape == result.curve_points.shape
    assert np.allclose(np.linalg.norm(result.tangents, axis=1), 1.0)
    assert np.allclose(np.linalg.norm(result.outward_normals, axis=1), 1.0)
    offsets = result.offset_points - result.curve_points
    assert np.allclose(np.sum(offsets * result.outward_normals, axis=1), 0.4)
    assert np.all(result.uncertainty == 0.0)
    assert np.all(result.confidence == 1.0)
    assert result.diagnostics["confidence_status"] == "neutral_not_estimated_pr1"
    assert result.diagnostics["observation_coverage_ratio"] >= 0.9


def test_estimate_boundary_v2_is_deterministic_for_radial_adapter() -> None:
    crowd_cfg = StaticCrowdConfig.from_dict(
        {"shape": "ellipse", "count": 400, "center": [5.0, 4.0], "axes": [2.5, 1.2], "noise_std": 0.0},
        seed=12,
    )
    observation = generate_static_crowd(crowd_cfg)
    config = BoundaryV2Config(sample_spacing=0.12, radial_bins=36, radial_smoothing_passes=4)

    first = estimate_boundary_v2(observation, config, np.random.default_rng(1))
    second = estimate_boundary_v2(observation, config, np.random.default_rng(999))

    assert isinstance(first, BoundaryEstimateV2)
    assert isinstance(second, BoundaryEstimateV2)
    assert np.array_equal(first.curve_points, second.curve_points)
    assert first.length == second.length


def test_disconnected_observation_returns_boundary_invalid() -> None:
    rng = np.random.default_rng(13)
    left = rng.normal([-3.0, 0.0], 0.18, size=(80, 2))
    right = rng.normal([3.0, 0.0], 0.18, size=(80, 2))
    observation = np.vstack((left, right))

    result = estimate_boundary_v2(
        observation,
        BoundaryV2Config(sample_spacing=0.1, radial_bins=64),
        np.random.default_rng(13),
    )

    assert isinstance(result, BoundaryEstimateFailure)
    assert result.status == "BOUNDARY_INVALID"
    assert result.component_count == 2
    assert result.diagnostics["reason"] == "multiple_significant_components"


def test_boundary_that_does_not_cover_observation_returns_boundary_invalid() -> None:
    crowd_cfg = StaticCrowdConfig.from_dict(
        {"shape": "circle", "count": 500, "center": [0.0, 0.0], "radius": 2.0, "noise_std": 0.0},
        seed=15,
    )
    observation = generate_static_crowd(crowd_cfg)

    result = estimate_boundary_v2(
        observation,
        BoundaryV2Config(
            safety_distance=0.0,
            radial_bins=24,
            radial_percentile=10.0,
            radial_smoothing_passes=4,
            min_observation_coverage=0.9,
        ),
        np.random.default_rng(15),
    )

    assert isinstance(result, BoundaryEstimateFailure)
    assert result.status == "BOUNDARY_INVALID"
    assert result.diagnostics["reason"] == "insufficient_observation_coverage"


@pytest.mark.parametrize(
    "observation",
    [
        np.array([[0.0, 0.0], [1.0, 0.0]]),
        np.array([[0.0, 0.0], [1.0, np.nan], [0.0, 1.0]]),
        np.ones((8, 3)),
    ],
)
def test_invalid_observation_returns_explicit_status(observation: np.ndarray) -> None:
    result = estimate_boundary_v2(
        observation,
        BoundaryV2Config(min_observation_points=8),
        np.random.default_rng(14),
    )

    assert isinstance(result, BoundaryEstimateFailure)
    assert result.status == "OBSERVATION_INVALID"


def test_offset_self_intersection_returns_offset_invalid() -> None:
    narrow_notch = np.array(
        [
            [0.0, 0.0],
            [4.0, 0.0],
            [4.0, 4.0],
            [2.2, 4.0],
            [2.2, 1.0],
            [1.8, 1.0],
            [1.8, 4.0],
            [0.0, 4.0],
        ]
    )

    result = boundary_v2_from_curve(
        narrow_notch,
        safety_distance=0.35,
        sample_spacing=0.08,
        method="test_curve",
    )

    assert isinstance(result, BoundaryEstimateFailure)
    assert result.status == "OFFSET_INVALID"
    assert result.diagnostics["reason"] == "offset_self_intersection"


def test_room_infeasible_offset_returns_offset_invalid() -> None:
    square = np.array([[0.2, 0.2], [1.8, 0.2], [1.8, 1.8], [0.2, 1.8]])

    result = boundary_v2_from_curve(
        square,
        safety_distance=0.4,
        sample_spacing=0.1,
        method="test_curve",
        room_size=(2.0, 2.0),
        room_margin=0.05,
    )

    assert isinstance(result, BoundaryEstimateFailure)
    assert result.status == "OFFSET_INVALID"
    assert result.diagnostics["reason"] == "offset_outside_room"
