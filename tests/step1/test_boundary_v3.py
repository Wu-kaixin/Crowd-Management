from __future__ import annotations

import numpy as np
import pytest
from shapely.geometry import MultiPolygon, Polygon, box

from crowd_management.estimation import (
    BoundaryCalibrationCase,
    BoundaryStabilityConfig,
    BoundaryStabilityEstimate,
    align_boundary_replica,
    estimate_boundary_stability,
    normalize_boundary_curve,
)
from crowd_management.geometry import (
    BufferedPolygonGeometry,
    PolygonBufferConfig,
    PolygonBufferFailure,
    build_polygon_buffer,
)


def _u_curve() -> np.ndarray:
    return np.array(
        [
            [0.0, 0.0],
            [4.0, 0.0],
            [4.0, 4.0],
            [3.0, 4.0],
            [3.0, 1.0],
            [1.0, 1.0],
            [1.0, 4.0],
            [0.0, 4.0],
        ]
    )


def _c_curve() -> np.ndarray:
    return np.array(
        [
            [0.0, 0.0],
            [4.0, 0.0],
            [4.0, 1.0],
            [1.0, 1.0],
            [1.0, 3.0],
            [4.0, 3.0],
            [4.0, 4.0],
            [0.0, 4.0],
        ]
    )


def _ellipse_curve(a: float = 2.2, b: float = 1.2, count: int = 180) -> np.ndarray:
    theta = np.linspace(0.0, 2.0 * np.pi, count, endpoint=False)
    return np.column_stack((a * np.cos(theta), b * np.sin(theta)))


def _normal_replica(
    curve: np.ndarray,
    displacement: float,
    *,
    roll: int,
    sample_count: int = 128,
) -> np.ndarray:
    registered = normalize_boundary_curve(curve, sample_count)
    replica = registered.points + displacement * registered.outward_normals
    return np.roll(replica, int(roll), axis=0)


@pytest.mark.parametrize("curve", [_u_curve(), _c_curve()])
def test_u_and_c_signed_normal_registration_is_phase_deterministic(curve: np.ndarray) -> None:
    sample_count = 128
    base = normalize_boundary_curve(curve, sample_count)
    replica = _normal_replica(curve, 0.025, roll=37, sample_count=sample_count)

    first = align_boundary_replica(base, replica)
    second = align_boundary_replica(base, replica)

    assert first.phase_shift_index == second.phase_shift_index
    assert first.phase_shift_fraction == second.phase_shift_fraction
    assert np.array_equal(first.signed_normal_displacement, second.signed_normal_displacement)
    assert np.median(first.signed_normal_displacement) == pytest.approx(0.025, abs=0.008)
    # Concave polygon offsets change the local normalized-arc parameterization
    # around corners; the residual is retained explicitly instead of hidden.
    assert np.sqrt(np.mean(first.tangential_residual**2)) < 0.11
    assert first.max_abs_displacement >= 0.02


def test_without_independent_calibration_is_named_uncalibrated_stability() -> None:
    base = _u_curve()
    replicas = tuple(
        _normal_replica(base, displacement, roll=roll)
        for displacement, roll in ((-0.02, 3), (0.01, 17), (0.025, 31), (-0.01, 49))
    )
    result = estimate_boundary_stability(
        base,
        replicas,
        config=BoundaryStabilityConfig(
            sample_count=128,
            min_bootstrap_success_fraction=1.0,
            min_calibration_replicas=4,
        ),
        base_shape_id="deployment-u",
    )

    assert isinstance(result, BoundaryStabilityEstimate)
    assert result.status == "UNCALIBRATED_STABILITY"
    assert result.calibrated_tube_radius is None
    assert result.calibration_factor is None
    assert 0.0 <= result.stability_score <= 1.0
    assert result.max_abs_displacement > 0.0
    assert "confidence" not in str(result.diagnostics).lower()
    assert result.diagnostics["calibration_rejection_reason"] == "no_independent_calibration_cases"


def _calibration_case(
    shape_id: str,
    reference: np.ndarray,
    error: float,
) -> BoundaryCalibrationCase:
    estimate = _normal_replica(reference, -error, roll=11)
    replicas = tuple(
        _normal_replica(estimate, displacement, roll=roll)
        for displacement, roll in ((-0.018, 5), (0.012, 19), (0.022, 37), (-0.01, 53))
    )
    return BoundaryCalibrationCase(
        shape_id=shape_id,
        reference_curve=reference,
        estimate_curve=estimate,
        bootstrap_replicas=replicas,
    )


def test_independent_shape_calibration_outputs_tube_and_empirical_coverage() -> None:
    base = _u_curve()
    replicas = tuple(
        _normal_replica(base, displacement, roll=roll)
        for displacement, roll in ((-0.02, 7), (0.013, 23), (0.024, 41), (-0.012, 61))
    )
    config = BoundaryStabilityConfig(
        sample_count=128,
        min_bootstrap_success_fraction=1.0,
        calibration_target_coverage=0.9,
        min_calibration_shapes=2,
        min_calibration_replicas=4,
    )
    calibration = (
        _calibration_case("heldout-c", _c_curve() + np.array([8.0, 0.0]), 0.025),
        _calibration_case("heldout-ellipse", _ellipse_curve() + np.array([3.0, 8.0]), 0.03),
    )

    result = estimate_boundary_stability(
        base,
        replicas,
        config=config,
        base_shape_id="deployment-u",
        calibration_cases=calibration,
    )

    assert isinstance(result, BoundaryStabilityEstimate)
    assert result.status == "CALIBRATED_TUBE"
    assert result.calibrated_tube_radius is not None
    assert np.all(np.isfinite(result.calibrated_tube_radius))
    assert np.all(result.calibrated_tube_radius > 0.0)
    assert result.calibration_factor is not None and result.calibration_factor > 0.0
    assert result.calibration_pointwise_coverage is not None
    assert result.calibration_pointwise_coverage >= config.calibration_target_coverage
    assert result.calibration_simultaneous_coverage is not None
    assert result.calibration_simultaneous_coverage >= config.calibration_target_coverage
    assert result.calibration_shape_ids == ("heldout-c", "heldout-ellipse")


def test_overlapping_calibration_shape_cannot_be_called_calibrated() -> None:
    base = _u_curve()
    replicas = tuple(
        _normal_replica(base, displacement, roll=roll)
        for displacement, roll in ((-0.02, 3), (0.01, 17), (0.025, 31), (-0.01, 49))
    )
    overlapping = (
        _calibration_case("deployment-u", _c_curve() + np.array([8.0, 0.0]), 0.025),
        _calibration_case("heldout-ellipse", _ellipse_curve() + np.array([3.0, 8.0]), 0.03),
    )
    result = estimate_boundary_stability(
        base,
        replicas,
        config=BoundaryStabilityConfig(sample_count=128),
        base_shape_id="deployment-u",
        calibration_cases=overlapping,
    )

    assert isinstance(result, BoundaryStabilityEstimate)
    assert result.status == "UNCALIBRATED_STABILITY"
    assert result.calibrated_tube_radius is None
    assert result.diagnostics["calibration_rejection_reason"] == (
        "calibration_shape_overlaps_deployment_shape"
    )


def test_cyclic_roll_of_same_curve_cannot_bypass_calibration_hash_gate() -> None:
    base = _ellipse_curve(count=128)
    replicas = tuple(
        _normal_replica(base, displacement, roll=roll, sample_count=128)
        for displacement, roll in ((-0.02, 3), (0.01, 17), (0.025, 31), (-0.01, 49))
    )
    disguised_same = BoundaryCalibrationCase(
        shape_id="fake-independent-a",
        reference_curve=np.roll(base, 23, axis=0),
        estimate_curve=np.roll(base, 41, axis=0),
        bootstrap_replicas=tuple(np.roll(replica, 11, axis=0) for replica in replicas),
    )
    other = _calibration_case("genuine-other", _c_curve() + np.array([8.0, 8.0]), 0.02)

    result = estimate_boundary_stability(
        base,
        replicas,
        config=BoundaryStabilityConfig(sample_count=128, min_calibration_shapes=2),
        base_shape_id="deployment",
        calibration_cases=(disguised_same, other),
    )

    assert isinstance(result, BoundaryStabilityEstimate)
    assert result.status == "UNCALIBRATED_STABILITY"
    assert result.diagnostics["calibration_rejection_reason"] == "calibration_curve_hash_overlap"


def test_polygon_buffer_is_one_shared_target_forbidden_safety_geometry() -> None:
    source = _u_curve() + np.array([3.0, 3.0])
    result = build_polygon_buffer(
        source,
        PolygonBufferConfig(
            clearance=0.25,
            quad_segs=24,
            room_size=(10.0, 10.0),
            room_margin=0.1,
        ),
    )

    assert isinstance(result, BufferedPolygonGeometry)
    assert result.target_polygon is result.forbidden_polygon
    assert result.target_polygon is result.safety_polygon
    assert result.target_wkb == result.forbidden_wkb == result.safety_wkb
    assert len(result.sha256) == 64
    assert len(result.holes) == 0
    # Round joins are a documented finite chord approximation controlled by
    # quad_segs, so the measured geometric clearance is slightly conservative.
    assert result.measured_exterior_clearance == pytest.approx(0.25, abs=2.0e-4)
    assert result.diagnostics["shared_geometry_roles"] == "target,forbidden,safety"


def test_multipolygon_and_holes_are_never_silently_selected_or_dropped() -> None:
    multiple = MultiPolygon((box(0.0, 0.0, 1.0, 1.0), box(3.0, 0.0, 4.0, 1.0)))
    multi_result = build_polygon_buffer(multiple, PolygonBufferConfig(clearance=0.2))

    shell = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    hole = [(4.0, 4.0), (6.0, 4.0), (6.0, 6.0), (4.0, 6.0)]
    holed = Polygon(shell, [hole])
    hole_result = build_polygon_buffer(holed, PolygonBufferConfig(clearance=0.2))
    allowed = build_polygon_buffer(
        holed,
        PolygonBufferConfig(clearance=0.2, allow_holes=True),
    )

    assert isinstance(multi_result, PolygonBufferFailure)
    assert multi_result.status == "MULTIPOLYGON"
    assert isinstance(hole_result, PolygonBufferFailure)
    assert hole_result.status == "HOLES"
    assert isinstance(allowed, BufferedPolygonGeometry)
    assert len(allowed.holes) == 1


def test_offset_topology_change_is_explicit() -> None:
    shell = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    hole = [(4.0, 4.0), (6.0, 4.0), (6.0, 6.0), (4.0, 6.0)]
    result = build_polygon_buffer(
        Polygon(shell, [hole]),
        PolygonBufferConfig(
            clearance=1.1,
            allow_holes=True,
            allow_topology_change=False,
        ),
    )

    assert isinstance(result, PolygonBufferFailure)
    assert result.status == "OFFSET_TOPOLOGY_CHANGED"
    assert result.diagnostics["source_hole_count"] == 1
    assert result.diagnostics["result_hole_count"] == 0


def test_room_infeasible_and_invalid_geometry_are_explicit() -> None:
    room_failure = build_polygon_buffer(
        np.array([[0.2, 0.2], [1.8, 0.2], [1.8, 1.8], [0.2, 1.8]]),
        PolygonBufferConfig(
            clearance=0.4,
            room_size=(2.0, 2.0),
            room_margin=0.05,
        ),
    )
    invalid = build_polygon_buffer(
        np.array([[0.0, 0.0], [2.0, 2.0], [0.0, 2.0], [2.0, 0.0]]),
        PolygonBufferConfig(clearance=0.2),
    )
    empty = build_polygon_buffer(Polygon(), PolygonBufferConfig(clearance=0.2))

    assert isinstance(room_failure, PolygonBufferFailure)
    assert room_failure.status == "ROOM_INFEASIBLE"
    assert isinstance(invalid, PolygonBufferFailure)
    assert invalid.status == "INVALID"
    assert isinstance(empty, PolygonBufferFailure)
    assert empty.status == "EMPTY"
