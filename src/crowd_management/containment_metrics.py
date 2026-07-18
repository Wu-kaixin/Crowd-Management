"""Metrics for static unknown-crowd containment experiments."""
from __future__ import annotations

import json
import warnings
from pathlib import Path

import numpy as np

from .estimation.boundary import BoundaryEstimate
from .crowd.truth import StaticCrowdTruth
from .geometry import max_consecutive_arc_gap as _max_consecutive_arc_gap
from .types import Array


def coverage_ratio_to_points(guide_points: Array, boundary_points: Array, coverage_radius: float) -> float:
    """Return the sampled-boundary coverage ratio for explicit evaluator points."""
    guides = np.asarray(guide_points, dtype=float)
    samples = np.asarray(boundary_points, dtype=float)
    if guides.ndim != 2 or guides.shape[1] != 2 or len(guides) == 0:
        raise ValueError("guide_points must be a non-empty (M, 2) array.")
    if samples.ndim != 2 or samples.shape[1] != 2 or len(samples) == 0:
        raise ValueError("boundary_points must be a non-empty (K, 2) array.")
    dist = np.linalg.norm(samples[:, None, :] - guides[None, :, :], axis=2)
    covered = np.min(dist, axis=1) <= float(coverage_radius)
    return float(np.mean(covered))


def coverage_ratio(guide_points: Array, boundary: BoundaryEstimate, coverage_radius: float) -> float:
    """Compatibility evaluator using an estimated safety boundary."""
    return coverage_ratio_to_points(guide_points, boundary.safety_points, coverage_radius)


def max_euclidean_boundary_distance_to_points(guide_points: Array, boundary_points: Array) -> float:
    """Maximum sampled-boundary distance to the nearest guide, in metres.

    This is an Euclidean nearest-point diagnostic.  It is not the consecutive
    periodic arc gap introduced by the later CA-ALCC work packages.
    """
    guides = np.asarray(guide_points, dtype=float)
    samples = np.asarray(boundary_points, dtype=float)
    if guides.ndim != 2 or guides.shape[1] != 2 or len(guides) == 0:
        raise ValueError("guide_points must be a non-empty (M, 2) array.")
    if samples.ndim != 2 or samples.shape[1] != 2 or len(samples) == 0:
        raise ValueError("boundary_points must be a non-empty (K, 2) array.")
    dist = np.linalg.norm(samples[:, None, :] - guides[None, :, :], axis=2)
    return float(np.max(np.min(dist, axis=1)))


def max_euclidean_boundary_distance(guide_points: Array, boundary: BoundaryEstimate) -> float:
    """Estimated-boundary version of the Euclidean nearest-point diagnostic."""
    return max_euclidean_boundary_distance_to_points(guide_points, boundary.safety_points)


def max_boundary_gap(guide_points: Array, boundary: BoundaryEstimate) -> float:
    """Deprecated name retained for direct-call compatibility."""
    warnings.warn(
        "max_boundary_gap is an Euclidean nearest-point distance; use "
        "max_euclidean_boundary_distance instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return max_euclidean_boundary_distance(guide_points, boundary)


def max_consecutive_arc_gap(target_s: Array, boundary_length: float) -> float:
    """Return the true periodic gap ``G`` between consecutive arc targets."""
    return _max_consecutive_arc_gap(target_s, boundary_length)


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
    truth_boundary: StaticCrowdTruth | None = None,
) -> dict[str, float | int | str]:
    if truth_boundary is None:
        evaluation_points = boundary.safety_points
        evaluation_boundary_source = "estimated_boundary_fallback"
        evaluation_status = "truth_not_provided"
        truth_component_count = 0
    else:
        evaluation_points = truth_boundary.safety_points
        evaluation_boundary_source = "analytic_truth_safety_offset"
        evaluation_status = truth_boundary.status
        truth_component_count = truth_boundary.component_count

    euclidean_distance = max_euclidean_boundary_distance_to_points(guide_points, evaluation_points)
    return {
        "evaluation_status": evaluation_status,
        "evaluation_boundary_source": evaluation_boundary_source,
        "truth_component_count": truth_component_count,
        "coverage_ratio": coverage_ratio_to_points(guide_points, evaluation_points, coverage_radius),
        "max_euclidean_boundary_distance": euclidean_distance,
        # Serialized compatibility alias.  Direct Python callers receive a
        # DeprecationWarning from max_boundary_gap().
        "max_boundary_gap": euclidean_distance,
        "radial_deployment_error": radial_deployment_error(guide_points, boundary),
        "angular_uniformity_error": angular_uniformity_error(guide_points, boundary.center),
        "minimum_inter_guider_distance": minimum_inter_guider_distance(guide_points),
        "guide_crowd_safety_violation_count": guide_crowd_safety_violation_count(
            guide_points,
            crowd_points,
            min_crowd_distance,
        ),
    }


def save_containment_summary(summary: dict[str, float | int | str], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
