from __future__ import annotations

import numpy as np
import pytest

from crowd_management.geometry import (
    has_self_intersections,
    periodic_arclength_distance,
    resample_closed_curve_by_arclength,
    signed_area,
)


def test_closed_square_length_and_equal_arclength_resampling() -> None:
    square_with_duplicate_endpoint = np.array(
        [[0.0, 0.0], [2.0, 0.0], [2.0, 2.0], [0.0, 2.0], [0.0, 0.0]]
    )

    points, arc_s, length, tangents, normals = resample_closed_curve_by_arclength(
        square_with_duplicate_endpoint,
        spacing=0.5,
    )

    assert length == pytest.approx(8.0)
    assert points.shape == (16, 2)
    assert arc_s[0] == 0.0
    assert np.allclose(np.diff(arc_s), 0.5)
    assert not np.allclose(points[0], points[-1])
    assert np.allclose(np.linalg.norm(tangents, axis=1), 1.0)
    assert np.allclose(np.linalg.norm(normals, axis=1), 1.0)
    assert np.allclose(np.sum(tangents * normals, axis=1), 0.0)


def test_clockwise_input_is_normalized_and_normals_point_outward() -> None:
    clockwise_square = np.array(
        [[-1.0, -1.0], [-1.0, 1.0], [1.0, 1.0], [1.0, -1.0]]
    )

    points, _, _, _, normals = resample_closed_curve_by_arclength(clockwise_square, spacing=0.25)

    assert signed_area(points) > 0.0
    assert np.all(np.sum(points * normals, axis=1) > 0.0)


def test_periodic_arclength_distance_handles_seam_and_vector_inputs() -> None:
    assert periodic_arclength_distance(0.1, 9.9, length=10.0) == pytest.approx(0.2)
    assert np.allclose(
        periodic_arclength_distance(np.array([0.1, 2.0]), np.array([9.9, 7.0]), length=10.0),
        np.array([0.2, 5.0]),
    )
    assert periodic_arclength_distance(12.0, 1.0, length=10.0) == pytest.approx(1.0)


def test_self_intersection_detection_distinguishes_bow_tie_from_simple_curve() -> None:
    bow_tie = np.array([[0.0, 0.0], [2.0, 2.0], [0.0, 2.0], [2.0, 0.0]])
    square = np.array([[0.0, 0.0], [2.0, 0.0], [2.0, 2.0], [0.0, 2.0]])

    assert has_self_intersections(bow_tie)
    assert not has_self_intersections(square)


@pytest.mark.parametrize(
    ("points", "message"),
    [
        (np.array([[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]]), "non-zero signed area"),
        (np.array([[0.0, 0.0], [1.0, 1.0], [0.0, 1.0], [1.0, 0.0]]), "self-intersects"),
        (np.array([[0.0, 0.0], [1.0, 0.0], [1.0, np.nan]]), "finite"),
    ],
)
def test_invalid_closed_curves_fail_explicitly(points: np.ndarray, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        resample_closed_curve_by_arclength(points, spacing=0.2)


def test_nonpositive_period_or_spacing_is_rejected() -> None:
    square = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]])
    with pytest.raises(ValueError, match="spacing"):
        resample_closed_curve_by_arclength(square, spacing=0.0)
    with pytest.raises(ValueError, match="length"):
        periodic_arclength_distance(0.0, 1.0, length=0.0)
