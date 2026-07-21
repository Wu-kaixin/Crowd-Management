"""Characterization tests locking hotspot behavior before vectorization.

The reference implementations below are verbatim copies of the original
pure-Python loops from ``geometry/arclength.py`` and
``controllers/safety.py`` (as of commit 3cb51f8). The production functions
must keep returning exactly the same values -- bitwise, not just within a
tolerance -- for any input.
"""
from __future__ import annotations

import numpy as np
import pytest

from crowd_management.controllers.safety import (
    VelocitySafetyConfig,
    _build_velocity_halfspaces,
    project_velocity_safety,
)
from crowd_management.geometry import has_self_intersections
from crowd_management.geometry.arclength import _as_closed_curve

# --- reference: original has_self_intersections ----------------------------


def _ref_cross(a, b, c) -> float:
    ab = b - a
    ac = c - a
    return float(ab[0] * ac[1] - ab[1] * ac[0])


def _ref_on_segment(a, b, point, atol) -> bool:
    return bool(
        min(a[0], b[0]) - atol <= point[0] <= max(a[0], b[0]) + atol
        and min(a[1], b[1]) - atol <= point[1] <= max(a[1], b[1]) + atol
    )


def _ref_segments_intersect(a, b, c, d, atol) -> bool:
    abc = _ref_cross(a, b, c)
    abd = _ref_cross(a, b, d)
    cda = _ref_cross(c, d, a)
    cdb = _ref_cross(c, d, b)
    if ((abc > atol and abd < -atol) or (abc < -atol and abd > atol)) and (
        (cda > atol and cdb < -atol) or (cda < -atol and cdb > atol)
    ):
        return True
    if abs(abc) <= atol and _ref_on_segment(a, b, c, atol):
        return True
    if abs(abd) <= atol and _ref_on_segment(a, b, d, atol):
        return True
    if abs(cda) <= atol and _ref_on_segment(c, d, a, atol):
        return True
    if abs(cdb) <= atol and _ref_on_segment(c, d, b, atol):
        return True
    return False


def _ref_has_self_intersections(points, atol: float = 1.0e-9) -> bool:
    curve = _as_closed_curve(points, atol=atol)
    count = len(curve)
    for first in range(count):
        a = curve[first]
        b = curve[(first + 1) % count]
        for second in range(first + 1, count):
            if second == first + 1 or (first == 0 and second == count - 1):
                continue
            c = curve[second]
            d = curve[(second + 1) % count]
            if _ref_segments_intersect(a, b, c, d, atol):
                return True
    return False


# --- reference: original _build_velocity_halfspaces ------------------------


def _ref_fallback_normal(first_id: int, second_id: int):
    angle = (first_id * 0.754877666 + second_id * 0.569840291) * 2.0 * np.pi
    return np.array([np.cos(angle), np.sin(angle)], dtype=float)


def _ref_append_reachable(rows, bounds, kinds, row, bound, reachable_lower_bound, kind, tolerance):
    if bound > reachable_lower_bound - tolerance:
        rows.append(row)
        bounds.append(float(bound))
        kinds.append(kind)


def _ref_build_velocity_halfspaces(positions, crowd_points, room_size, dt, v_max, config):
    guide_count = len(positions)
    dimension = 2 * guide_count
    rows: list = []
    bounds: list = []
    kinds: list = []
    tol = config.residual_tolerance
    numerical_distance_buffer = max(
        10.0 * dt * tol,
        64.0 * np.finfo(float).eps * max(1.0, float(np.max(room_size))),
    )

    if config.min_guide_distance > 0.0:
        for i in range(guide_count):
            for j in range(i + 1, guide_count):
                delta = positions[i] - positions[j]
                distance = float(np.linalg.norm(delta))
                normal = delta / distance if distance > tol else _ref_fallback_normal(i, j)
                row = np.zeros(dimension, dtype=float)
                row[2 * i : 2 * i + 2] = normal
                row[2 * j : 2 * j + 2] = -normal
                bound = (config.min_guide_distance + numerical_distance_buffer - distance) / dt
                _ref_append_reachable(rows, bounds, kinds, row, bound, -2.0 * v_max, "guide_pair", tol)

    if config.min_crowd_distance > 0.0 and len(crowd_points):
        for guide_id, position in enumerate(positions):
            for crowd_id, crowd_point in enumerate(crowd_points):
                delta = position - crowd_point
                distance = float(np.linalg.norm(delta))
                normal = (
                    delta / distance
                    if distance > tol
                    else _ref_fallback_normal(guide_id, guide_count + crowd_id)
                )
                row = np.zeros(dimension, dtype=float)
                row[2 * guide_id : 2 * guide_id + 2] = normal
                bound = (config.min_crowd_distance + numerical_distance_buffer - distance) / dt
                _ref_append_reachable(rows, bounds, kinds, row, bound, -v_max, "crowd", tol)

    lower = np.full(2, config.room_margin + numerical_distance_buffer, dtype=float)
    upper = room_size - config.room_margin - numerical_distance_buffer
    for guide_id, position in enumerate(positions):
        for axis in range(2):
            row_lower = np.zeros(dimension, dtype=float)
            row_lower[2 * guide_id + axis] = 1.0
            lower_bound = (lower[axis] - position[axis]) / dt
            _ref_append_reachable(rows, bounds, kinds, row_lower, lower_bound, -v_max, "room", tol)

            row_upper = np.zeros(dimension, dtype=float)
            row_upper[2 * guide_id + axis] = -1.0
            upper_bound = (position[axis] - upper[axis]) / dt
            _ref_append_reachable(rows, bounds, kinds, row_upper, upper_bound, -v_max, "room", tol)

    matrix = np.asarray(rows, dtype=float).reshape((-1, dimension))
    vector = np.asarray(bounds, dtype=float)
    kind_array = np.asarray(kinds, dtype="U16")
    counts = {
        kind: int(np.count_nonzero(kind_array == kind))
        for kind in ("guide_pair", "crowd", "room")
    }
    return matrix, vector, kind_array, counts


# --- curve fixtures ---------------------------------------------------------


def _noisy_closed_curve(rng: np.random.Generator, count: int) -> np.ndarray:
    angles = np.sort(rng.uniform(0.0, 2.0 * np.pi, size=count))
    radii = rng.uniform(0.5, 2.5, size=count)
    return np.column_stack((radii * np.cos(angles), radii * np.sin(angles)))


def _star_polygon(count: int, inner: float, outer: float) -> np.ndarray:
    angles = np.linspace(0.0, 2.0 * np.pi, 2 * count, endpoint=False)
    radii = np.where(np.arange(2 * count) % 2 == 0, outer, inner)
    return np.column_stack((radii * np.cos(angles), radii * np.sin(angles)))


CURVE_CASES = []
_rng = np.random.default_rng(20260721)
for _ in range(40):
    CURVE_CASES.append(_noisy_closed_curve(_rng, int(_rng.integers(4, 60))))
CURVE_CASES.append(_star_polygon(7, 0.4, 2.0))
CURVE_CASES.append(np.array([[0.0, 0.0], [2.0, 2.0], [2.0, 0.0], [0.0, 2.0]]))  # bow tie
CURVE_CASES.append(np.array([[0.0, 0.0], [4.0, 0.0], [4.0, 4.0], [0.0, 4.0]]))  # square
# touching (collinear/on-segment) configuration
CURVE_CASES.append(np.array([[0.0, 0.0], [4.0, 0.0], [4.0, 2.0], [2.0, 0.0], [0.0, 2.0]]))


@pytest.mark.parametrize("index", range(len(CURVE_CASES)))
def test_self_intersection_matches_loop_reference(index: int) -> None:
    curve = CURVE_CASES[index]
    assert has_self_intersections(curve) == _ref_has_self_intersections(curve)


def test_self_intersection_respects_custom_atol() -> None:
    square = np.array([[0.0, 0.0], [4.0, 0.0], [4.0, 4.0], [0.0, 4.0]])
    for atol in (1.0e-12, 1.0e-9, 1.0e-3, 1.0):
        assert has_self_intersections(square, atol=atol) == _ref_has_self_intersections(square, atol=atol)


# --- halfspace fixtures ------------------------------------------------------


def _halfspace_inputs(seed: int, guide_count: int, crowd_count: int):
    rng = np.random.default_rng(seed)
    room = np.array([24.0, 18.0])
    positions = rng.uniform(1.0, 17.0, size=(guide_count, 2))
    crowd = rng.uniform(4.0, 14.0, size=(crowd_count, 2))
    return positions, crowd, room


@pytest.mark.parametrize("seed", range(20))
def test_halfspaces_match_loop_reference(seed: int) -> None:
    guide_count = 2 + seed % 7
    crowd_count = (seed * 13) % 120
    positions, crowd, room = _halfspace_inputs(seed, guide_count, crowd_count)
    config = VelocitySafetyConfig()
    dt, v_max = 0.1, 1.5

    expected = _ref_build_velocity_halfspaces(positions, crowd, room, dt, v_max, config)
    actual = _build_velocity_halfspaces(positions, crowd, room, dt, v_max, config)

    assert np.array_equal(expected[0], actual[0])
    assert np.array_equal(expected[1], actual[1])
    assert np.array_equal(expected[2], actual[2])
    assert expected[3] == actual[3]


def test_halfspaces_match_reference_with_coincident_points() -> None:
    """Coincident guides / guide-on-crowd trigger the deterministic fallback normal."""
    positions = np.array([[5.0, 5.0], [5.0, 5.0], [9.0, 9.0]])
    crowd = np.array([[9.0, 9.0], [7.0, 7.0]])
    room = np.array([20.0, 20.0])
    config = VelocitySafetyConfig()
    expected = _ref_build_velocity_halfspaces(positions, crowd, room, 0.1, 1.5, config)
    actual = _build_velocity_halfspaces(positions, crowd, room, 0.1, 1.5, config)
    assert np.array_equal(expected[0], actual[0])
    assert np.array_equal(expected[1], actual[1])
    assert np.array_equal(expected[2], actual[2])
    assert expected[3] == actual[3]


def test_halfspaces_match_reference_without_crowd_or_pairs() -> None:
    positions = np.array([[2.0, 2.0], [10.0, 10.0]])
    room = np.array([20.0, 20.0])
    config_no_pairs = VelocitySafetyConfig(min_guide_distance=0.0)
    for crowd in (np.empty((0, 2)), np.array([[5.0, 5.0]])):
        expected = _ref_build_velocity_halfspaces(positions, crowd, room, 0.05, 2.0, config_no_pairs)
        actual = _build_velocity_halfspaces(positions, crowd, room, 0.05, 2.0, config_no_pairs)
        assert np.array_equal(expected[0], actual[0])
        assert np.array_equal(expected[1], actual[1])
        assert np.array_equal(expected[2], actual[2])


def test_projection_end_to_end_unchanged() -> None:
    """Full safety projection on a violating input keeps its exact outputs."""
    rng = np.random.default_rng(7)
    positions = np.array([[5.0, 5.0], [5.5, 5.0], [8.0, 8.0]])
    nominal = rng.uniform(-2.0, 2.0, size=(3, 2))
    crowd = rng.uniform(4.5, 8.5, size=(40, 2))
    room = np.array([20.0, 15.0])
    result = project_velocity_safety(positions, nominal, crowd, room, 0.1, 1.5, VelocitySafetyConfig())
    matrix, bounds, kinds, _ = _ref_build_velocity_halfspaces(
        positions, crowd, room, 0.1, 1.5, VelocitySafetyConfig()
    )
    assert result.constraint_count == len(bounds)
    assert np.array_equal(result.constraint_kinds, kinds)
    assert np.array_equal(
        result.constraint_residuals_before, bounds - matrix @ nominal.reshape(-1)
    )
