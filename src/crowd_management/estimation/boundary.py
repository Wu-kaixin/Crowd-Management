"""Boundary estimation for static unknown-crowd point clouds."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..types import Array, unit


@dataclass(frozen=True)
class BoundaryEstimate:
    center: Array
    angles: Array
    radii: Array
    boundary_points: Array
    safety_points: Array
    safety_distance: float
    bin_counts: Array


def estimate_crowd_center(points: Array, method: str = "mean") -> Array:
    points = np.asarray(points, dtype=float)
    if points.ndim != 2 or points.shape[1] != 2 or len(points) == 0:
        raise ValueError("points must be a non-empty (N, 2) array.")
    if method == "mean":
        return points.mean(axis=0)
    if method == "median":
        return np.median(points, axis=0)
    raise ValueError(f"Unsupported center method: {method}")


def smooth_radii(radii: Array, passes: int = 1) -> Array:
    out = np.asarray(radii, dtype=float).copy()
    for _ in range(max(0, int(passes))):
        out = 0.25 * np.roll(out, 1) + 0.5 * out + 0.25 * np.roll(out, -1)
    return out


def estimate_radial_boundary(
    points: Array,
    num_bins: int = 72,
    safety_distance: float = 0.8,
    center: Array | None = None,
    percentile: float = 96.0,
    smoothing_passes: int = 1,
) -> BoundaryEstimate:
    """Estimate a closed polar boundary using angular maximum/percentile bins."""
    points = np.asarray(points, dtype=float)
    if len(points) < 3:
        raise ValueError("At least three points are required to estimate a boundary.")
    center_arr = estimate_crowd_center(points) if center is None else np.asarray(center, dtype=float)
    rel = points - center_arr
    theta = (np.arctan2(rel[:, 1], rel[:, 0]) + 2.0 * np.pi) % (2.0 * np.pi)
    radius = np.linalg.norm(rel, axis=1)

    edges = np.linspace(0.0, 2.0 * np.pi, num_bins + 1)
    bin_ids = np.clip(np.searchsorted(edges, theta, side="right") - 1, 0, num_bins - 1)
    radii = np.zeros(num_bins, dtype=float)
    counts = np.zeros(num_bins, dtype=int)
    fallback = float(np.percentile(radius, percentile))
    for idx in range(num_bins):
        values = radius[bin_ids == idx]
        counts[idx] = len(values)
        radii[idx] = float(np.percentile(values, percentile)) if len(values) else fallback

    # Fill empty runs from neighbors before smoothing.
    for idx in np.where(counts == 0)[0]:
        left = radii[(idx - 1) % num_bins]
        right = radii[(idx + 1) % num_bins]
        radii[idx] = 0.5 * (left + right)
    radii = smooth_radii(radii, passes=smoothing_passes)
    angles = edges[:-1] + np.pi / num_bins
    dirs = np.column_stack((np.cos(angles), np.sin(angles)))
    boundary = center_arr + dirs * radii[:, None]
    safety = center_arr + dirs * (radii + safety_distance)[:, None]
    return BoundaryEstimate(center_arr, angles, radii, boundary, safety, float(safety_distance), counts)


def offset_boundary(boundary: BoundaryEstimate, distance: float) -> Array:
    """Return an outward radial offset of an existing boundary estimate."""
    dirs = np.vstack([unit(point - boundary.center, fallback=np.array([1.0, 0.0])) for point in boundary.boundary_points])
    return boundary.boundary_points + dirs * float(distance)
