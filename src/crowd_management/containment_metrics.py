"""Metrics for static unknown-crowd containment experiments."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .estimation.boundary import BoundaryEstimate
from .types import Array


def coverage_ratio(guide_points: Array, boundary: BoundaryEstimate, coverage_radius: float) -> float:
    dist = np.linalg.norm(boundary.safety_points[:, None, :] - guide_points[None, :, :], axis=2)
    covered = np.min(dist, axis=1) <= float(coverage_radius)
    return float(np.mean(covered))


def max_boundary_gap(guide_points: Array, boundary: BoundaryEstimate) -> float:
    dist = np.linalg.norm(boundary.safety_points[:, None, :] - guide_points[None, :, :], axis=2)
    return float(np.max(np.min(dist, axis=1)))


def radial_deployment_error(guide_points: Array, boundary: BoundaryEstimate) -> float:
    rel = guide_points - boundary.center
    guide_radii = np.linalg.norm(rel, axis=1)
    desired = np.mean(boundary.radii) + boundary.safety_distance
    return float(np.mean(np.abs(guide_radii - desired)))


def angular_uniformity_error(guide_points: Array, center: Array) -> float:
    if len(guide_points) <= 1:
        return 0.0
    theta = np.sort((np.arctan2(guide_points[:, 1] - center[1], guide_points[:, 0] - center[0]) + 2.0 * np.pi) % (2.0 * np.pi))
    gaps = np.diff(np.r_[theta, theta[0] + 2.0 * np.pi])
    target = 2.0 * np.pi / len(guide_points)
    return float(np.mean(np.abs(gaps - target)) / target)


def minimum_inter_guider_distance(guide_points: Array) -> float:
    if len(guide_points) <= 1:
        return float("inf")
    best = float("inf")
    for i in range(len(guide_points)):
        dist = np.linalg.norm(guide_points[i + 1 :] - guide_points[i], axis=1)
        if len(dist):
            best = min(best, float(dist.min()))
    return best


def guide_crowd_safety_violation_count(guide_points: Array, crowd_points: Array, min_distance: float) -> int:
    dist = np.linalg.norm(guide_points[:, None, :] - crowd_points[None, :, :], axis=2)
    return int(np.sum(np.min(dist, axis=1) < float(min_distance)))


def formation_stability(history: Array) -> float:
    """Mean per-guide movement over the final half of a target history."""
    arr = np.asarray(history, dtype=float)
    if arr.ndim != 3 or arr.shape[0] <= 1:
        return 0.0
    tail = arr[arr.shape[0] // 2 :]
    return float(np.mean(np.linalg.norm(np.diff(tail, axis=0), axis=2))) if len(tail) > 1 else 0.0


def containment_summary(
    guide_points: Array,
    crowd_points: Array,
    boundary: BoundaryEstimate,
    coverage_radius: float,
    min_crowd_distance: float,
) -> dict[str, float | int]:
    return {
        "coverage_ratio": coverage_ratio(guide_points, boundary, coverage_radius),
        "max_boundary_gap": max_boundary_gap(guide_points, boundary),
        "radial_deployment_error": radial_deployment_error(guide_points, boundary),
        "angular_uniformity_error": angular_uniformity_error(guide_points, boundary.center),
        "minimum_inter_guider_distance": minimum_inter_guider_distance(guide_points),
        "guide_crowd_safety_violation_count": guide_crowd_safety_violation_count(
            guide_points,
            crowd_points,
            min_crowd_distance,
        ),
    }


def save_containment_summary(summary: dict[str, float | int], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
