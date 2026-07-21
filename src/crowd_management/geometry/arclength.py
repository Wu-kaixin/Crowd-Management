"""Deterministic geometry for ordered simple closed planar curves.

Curves are represented by finite ``(K, 2)`` arrays in metres.  Closure is
implicit between the final and first point; a duplicated final endpoint is
accepted on input and removed on output.
"""
from __future__ import annotations

import numpy as np

from ..types import Array


def _as_closed_curve(points: Array, atol: float = 1.0e-9) -> Array:
    curve = np.asarray(points, dtype=float)
    if curve.ndim != 2 or curve.shape[1] != 2:
        raise ValueError("points must have shape (K, 2).")
    if not np.all(np.isfinite(curve)):
        raise ValueError("points must contain only finite values.")
    if len(curve) >= 2 and np.linalg.norm(curve[-1] - curve[0]) <= atol:
        curve = curve[:-1]
    if len(curve) < 3:
        raise ValueError("a closed curve requires at least three distinct points.")
    segment_lengths = np.linalg.norm(np.roll(curve, -1, axis=0) - curve, axis=1)
    if np.any(segment_lengths <= atol):
        raise ValueError("consecutive closed-curve points must be distinct.")
    return curve.copy()


def signed_area(points: Array) -> float:
    """Return the signed area in square metres; positive means counter-clockwise."""
    curve = _as_closed_curve(points)
    successor = np.roll(curve, -1, axis=0)
    return 0.5 * float(np.sum(curve[:, 0] * successor[:, 1] - successor[:, 0] * curve[:, 1]))


def _cross(a: Array, b: Array, c: Array) -> float:
    ab = b - a
    ac = c - a
    return float(ab[0] * ac[1] - ab[1] * ac[0])


def _on_segment(a: Array, b: Array, point: Array, atol: float) -> bool:
    return bool(
        min(a[0], b[0]) - atol <= point[0] <= max(a[0], b[0]) + atol
        and min(a[1], b[1]) - atol <= point[1] <= max(a[1], b[1]) + atol
    )


def _segments_intersect(a: Array, b: Array, c: Array, d: Array, atol: float) -> bool:
    abc = _cross(a, b, c)
    abd = _cross(a, b, d)
    cda = _cross(c, d, a)
    cdb = _cross(c, d, b)

    if ((abc > atol and abd < -atol) or (abc < -atol and abd > atol)) and (
        (cda > atol and cdb < -atol) or (cda < -atol and cdb > atol)
    ):
        return True
    if abs(abc) <= atol and _on_segment(a, b, c, atol):
        return True
    if abs(abd) <= atol and _on_segment(a, b, d, atol):
        return True
    if abs(cda) <= atol and _on_segment(c, d, a, atol):
        return True
    if abs(cdb) <= atol and _on_segment(c, d, b, atol):
        return True
    return False


def _cross_rows(a: Array, b: Array, c: Array) -> Array:
    """Vectorized ``_cross`` over row-aligned point arrays."""
    ab = b - a
    ac = c - a
    return ab[:, 0] * ac[:, 1] - ab[:, 1] * ac[:, 0]


def _on_segment_rows(a: Array, b: Array, points: Array, atol: float) -> Array:
    """Vectorized ``_on_segment`` over row-aligned point arrays."""
    low = np.minimum(a, b) - atol
    high = np.maximum(a, b) + atol
    return np.all((points >= low) & (points <= high), axis=1)


def _segments_intersect_rows(a: Array, b: Array, c: Array, d: Array, atol: float) -> Array:
    """Vectorized ``_segments_intersect`` over row-aligned segment pairs."""
    abc = _cross_rows(a, b, c)
    abd = _cross_rows(a, b, d)
    cda = _cross_rows(c, d, a)
    cdb = _cross_rows(c, d, b)

    proper = (((abc > atol) & (abd < -atol)) | ((abc < -atol) & (abd > atol))) & (
        ((cda > atol) & (cdb < -atol)) | ((cda < -atol) & (cdb > atol))
    )
    touching = (
        ((np.abs(abc) <= atol) & _on_segment_rows(a, b, c, atol))
        | ((np.abs(abd) <= atol) & _on_segment_rows(a, b, d, atol))
        | ((np.abs(cda) <= atol) & _on_segment_rows(c, d, a, atol))
        | ((np.abs(cdb) <= atol) & _on_segment_rows(c, d, b, atol))
    )
    return proper | touching


_PAIR_CHUNK = 262_144


def has_self_intersections(points: Array, atol: float = 1.0e-9) -> bool:
    """Return whether non-adjacent segments of an implicit closed curve meet.

    Evaluates the exact same orientation/on-segment predicate as the original
    per-pair loop, vectorized over all non-adjacent segment pairs.  Pairs are
    processed in bounded chunks to cap memory and allow early exit.
    """
    curve = _as_closed_curve(points, atol=atol)
    count = len(curve)
    starts = curve
    ends = np.roll(curve, -1, axis=0)

    first, second = np.triu_indices(count, k=2)
    if count >= 3:
        keep = ~((first == 0) & (second == count - 1))
        first, second = first[keep], second[keep]

    for offset in range(0, len(first), _PAIR_CHUNK):
        i = first[offset : offset + _PAIR_CHUNK]
        j = second[offset : offset + _PAIR_CHUNK]
        hits = _segments_intersect_rows(starts[i], ends[i], starts[j], ends[j], atol)
        if bool(np.any(hits)):
            return True
    return False


def _unit_rows(vectors: Array) -> Array:
    norms = np.linalg.norm(vectors, axis=1)
    if np.any(norms <= 1.0e-12):
        raise ValueError("curve geometry produced a zero-length tangent.")
    return vectors / norms[:, None]


def resample_closed_curve_by_arclength(
    points: Array,
    spacing: float,
) -> tuple[Array, Array, float, Array, Array]:
    """Resample a simple closed curve at uniform periodic arc coordinates.

    Parameters
    ----------
    points:
        Ordered ``(K, 2)`` world-frame points in metres.  The final endpoint
        may duplicate the first, but the returned curve never does.
    spacing:
        Maximum requested sample spacing in metres.  The actual spacing is
        ``length / ceil(length / spacing)``.

    Returns
    -------
    curve_points, arc_s, length, tangents, outward_normals
        ``arc_s`` starts at zero and is strictly increasing.  The curve is
        normalized counter-clockwise, so outward normals are the right-hand
        normals ``(t_y, -t_x)``.

    Raises
    ------
    ValueError
        If the input is non-finite, degenerate, self-intersecting, or has a
        non-positive spacing.
    """
    sample_spacing = float(spacing)
    if not np.isfinite(sample_spacing) or sample_spacing <= 0.0:
        raise ValueError("spacing must be finite and positive.")

    curve = _as_closed_curve(points)
    if has_self_intersections(curve):
        raise ValueError("closed curve self-intersects.")
    area = signed_area(curve)
    if abs(area) <= 1.0e-12:
        raise ValueError("closed curve must have non-zero signed area.")
    if area < 0.0:
        curve = curve[::-1].copy()

    segment_vectors = np.roll(curve, -1, axis=0) - curve
    segment_lengths = np.linalg.norm(segment_vectors, axis=1)
    length = float(np.sum(segment_lengths))
    if not np.isfinite(length) or length <= 0.0:
        raise ValueError("closed curve length must be finite and positive.")

    sample_count = max(3, int(np.ceil(length / sample_spacing - 1.0e-12)))
    arc_s = np.arange(sample_count, dtype=float) * (length / sample_count)
    cumulative = np.r_[0.0, np.cumsum(segment_lengths)]
    segment_ids = np.searchsorted(cumulative, arc_s, side="right") - 1
    segment_ids = np.clip(segment_ids, 0, len(curve) - 1)
    local_fraction = (arc_s - cumulative[segment_ids]) / segment_lengths[segment_ids]
    resampled = curve[segment_ids] + local_fraction[:, None] * segment_vectors[segment_ids]

    central_differences = np.roll(resampled, -1, axis=0) - np.roll(resampled, 1, axis=0)
    tangents = _unit_rows(central_differences)
    outward_normals = np.column_stack((tangents[:, 1], -tangents[:, 0]))
    return resampled, arc_s, length, tangents, outward_normals


def periodic_arclength_distance(a: Array | float, b: Array | float, length: float) -> Array | float:
    """Return shortest distances on a periodic arc domain of positive length."""
    period = float(length)
    if not np.isfinite(period) or period <= 0.0:
        raise ValueError("length must be finite and positive.")
    first = np.asarray(a, dtype=float)
    second = np.asarray(b, dtype=float)
    if not np.all(np.isfinite(first)) or not np.all(np.isfinite(second)):
        raise ValueError("periodic coordinates must be finite.")
    distance = np.abs((first - second + 0.5 * period) % period - 0.5 * period)
    return float(distance) if distance.ndim == 0 else distance


def max_consecutive_arc_gap(target_s: Array, length: float) -> float:
    """Return the largest consecutive gap on a closed arc domain.

    Unlike the legacy ``max_boundary_gap`` compatibility metric, this is a
    one-dimensional periodic arc-length quantity.  The seam between the last
    and first sorted coordinates is included.
    """
    period = float(length)
    coordinates = np.asarray(target_s, dtype=float)
    if not np.isfinite(period) or period <= 0.0:
        raise ValueError("length must be finite and positive.")
    if coordinates.ndim != 1 or len(coordinates) == 0 or not np.all(np.isfinite(coordinates)):
        raise ValueError("target_s must be a non-empty finite one-dimensional array.")
    ordered = np.sort(np.mod(coordinates, period))
    gaps = np.diff(np.r_[ordered, ordered[0] + period])
    return float(np.max(gaps))
