"""ABCG-v2 Step 1 radial/alpha boundary and bootstrap confidence contract.

PR1 established the radial adapter and explicit validity states. PR6 adds a
single-component alpha-shape estimator plus aligned bootstrap uncertainty; it
does not expose synthetic truth to the estimator.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
from scipy.spatial import Delaunay, QhullError
from shapely.geometry import LineString, Polygon
from shapely.ops import polygonize
from shapely.validation import explain_validity

from ..geometry import has_self_intersections, resample_closed_curve_by_arclength
from ..types import Array
from .boundary import BoundaryEstimate, estimate_radial_boundary

BoundaryDiagnostics = dict[str, float | int | str]


@dataclass(frozen=True)
class BoundaryV2Config:
    """Configuration for the PR1 radial adapter and PR6 alpha/bootstrap path.

    Distances use metres.  ``room_size`` is an optional ``(width, height)``
    tuple used only for offset-feasibility validation.
    """

    estimator: str = "radial"
    safety_distance: float = 0.8
    sample_spacing: float = 0.08
    radial_bins: int = 24
    radial_percentile: float = 96.0
    radial_smoothing_passes: int = 6
    min_observation_points: int = 8
    connectivity_radius: float | None = None
    connectivity_scale: float = 5.0
    min_component_fraction: float = 0.1
    min_observation_coverage: float = 0.8
    room_size: tuple[float, float] | None = None
    room_margin: float = 0.0
    alpha_radius: float | None = None
    alpha_scale: float = 2.5
    alpha_growth_factors: tuple[float, ...] = (1.0, 1.25, 1.5, 2.0, 3.0, 4.0)
    alpha_smoothing_passes: int = 5
    bootstrap_samples: int = 0
    bootstrap_min_success_fraction: float = 0.7
    bootstrap_confidence_floor: float = 0.15
    bootstrap_confidence_scale: float | None = None

    def __post_init__(self) -> None:
        if self.estimator not in {"radial", "alpha"}:
            raise ValueError("estimator must be 'radial' or 'alpha'.")
        if self.safety_distance < 0.0 or not np.isfinite(self.safety_distance):
            raise ValueError("safety_distance must be finite and non-negative.")
        if self.sample_spacing <= 0.0 or not np.isfinite(self.sample_spacing):
            raise ValueError("sample_spacing must be finite and positive.")
        if self.radial_bins < 8:
            raise ValueError("radial_bins must be at least 8.")
        if not 0.0 < self.radial_percentile <= 100.0:
            raise ValueError("radial_percentile must be in (0, 100].")
        if self.min_observation_points < 3:
            raise ValueError("min_observation_points must be at least 3.")
        if self.radial_smoothing_passes < 0:
            raise ValueError("radial_smoothing_passes must be non-negative.")
        if self.connectivity_radius is not None and (
            self.connectivity_radius <= 0.0 or not np.isfinite(self.connectivity_radius)
        ):
            raise ValueError("connectivity_radius must be positive when provided.")
        if self.connectivity_scale <= 0.0 or not np.isfinite(self.connectivity_scale):
            raise ValueError("connectivity_scale must be positive.")
        if not 0.0 < self.min_component_fraction <= 1.0:
            raise ValueError("min_component_fraction must be in (0, 1].")
        if not 0.0 < self.min_observation_coverage <= 1.0:
            raise ValueError("min_observation_coverage must be in (0, 1].")
        if self.room_margin < 0.0 or not np.isfinite(self.room_margin):
            raise ValueError("room_margin must be non-negative.")
        if self.room_size is not None:
            room = np.asarray(self.room_size, dtype=float)
            if room.shape != (2,) or not np.all(np.isfinite(room)) or np.any(room <= 0.0):
                raise ValueError("room_size must contain two finite positive dimensions.")
        if self.alpha_radius is not None and (
            not np.isfinite(self.alpha_radius) or self.alpha_radius <= 0.0
        ):
            raise ValueError("alpha_radius must be finite and positive when provided.")
        if not np.isfinite(self.alpha_scale) or self.alpha_scale <= 0.0:
            raise ValueError("alpha_scale must be finite and positive.")
        factors = np.asarray(self.alpha_growth_factors, dtype=float)
        if factors.ndim != 1 or len(factors) == 0 or not np.all(np.isfinite(factors)) or np.any(factors <= 0.0):
            raise ValueError("alpha_growth_factors must contain finite positive values.")
        if np.any(np.diff(factors) < 0.0):
            raise ValueError("alpha_growth_factors must be nondecreasing.")
        if (
            isinstance(self.alpha_smoothing_passes, bool)
            or not isinstance(self.alpha_smoothing_passes, (int, np.integer))
            or self.alpha_smoothing_passes < 0
        ):
            raise ValueError("alpha_smoothing_passes must be a non-negative integer.")
        if (
            isinstance(self.bootstrap_samples, bool)
            or not isinstance(self.bootstrap_samples, (int, np.integer))
            or self.bootstrap_samples < 0
        ):
            raise ValueError("bootstrap_samples must be a non-negative integer.")
        if not 0.0 < self.bootstrap_min_success_fraction <= 1.0:
            raise ValueError("bootstrap_min_success_fraction must be in (0, 1].")
        if not 0.0 < self.bootstrap_confidence_floor <= 1.0:
            raise ValueError("bootstrap_confidence_floor must be in (0, 1].")
        if self.bootstrap_confidence_scale is not None and (
            not np.isfinite(self.bootstrap_confidence_scale) or self.bootstrap_confidence_scale <= 0.0
        ):
            raise ValueError("bootstrap_confidence_scale must be finite and positive when provided.")


@dataclass(frozen=True)
class BoundaryEstimateV2:
    """Valid ordered boundary geometry.

    Point/vector arrays have shape ``(K, 2)`` in metres.  ``arc_s`` is a
    strictly increasing ``(K,)`` array in metres with ``arc_s[0] == 0``.
    The radial/no-bootstrap ablation fills uncertainty/confidence with neutral
    zero/one values. PR6 alpha/bootstrap estimates them and labels the method in
    diagnostics; confidence gates controller gain and is not a risk density.
    """

    curve_points: Array
    offset_points: Array
    arc_s: Array
    length: float
    tangents: Array
    outward_normals: Array
    uncertainty: Array
    confidence: Array
    component_count: int
    topology_valid: bool
    method: str
    version: int
    diagnostics: BoundaryDiagnostics


@dataclass(frozen=True)
class BoundaryEstimateFailure:
    """Explicit failure returned instead of fabricating invalid geometry."""

    status: str
    component_count: int
    method: str
    version: int
    diagnostics: BoundaryDiagnostics


BoundaryEstimateV2Result = BoundaryEstimateV2 | BoundaryEstimateFailure


def _failure(
    status: str,
    reason: str,
    component_count: int = 0,
    method: str = "radial_adapter",
    **diagnostics: float | int | str,
) -> BoundaryEstimateFailure:
    return BoundaryEstimateFailure(
        status=status,
        component_count=int(component_count),
        method=method,
        version=2,
        diagnostics={"status": status, "reason": reason, **diagnostics},
    )


def _validate_observation(observation: Array, minimum: int) -> Array | None:
    points = np.asarray(observation, dtype=float)
    if points.ndim != 2 or points.shape[1:] != (2,):
        return None
    if len(points) < minimum or not np.all(np.isfinite(points)):
        return None
    return points


def _significant_component_summary(points: Array, config: BoundaryV2Config) -> tuple[int, float, list[int]]:
    pairwise = np.linalg.norm(points[:, None, :] - points[None, :, :], axis=2)
    np.fill_diagonal(pairwise, np.inf)
    nearest = np.min(pairwise, axis=1)
    median_nearest = float(np.median(nearest))
    if config.connectivity_radius is None:
        radius = max(config.connectivity_scale * median_nearest, 1.0e-9)
    else:
        radius = float(config.connectivity_radius)

    adjacency = pairwise <= radius
    visited = np.zeros(len(points), dtype=bool)
    sizes: list[int] = []
    for start in range(len(points)):
        if visited[start]:
            continue
        stack = [start]
        visited[start] = True
        size = 0
        while stack:
            current = stack.pop()
            size += 1
            neighbors = np.flatnonzero(adjacency[current] & ~visited)
            if len(neighbors):
                visited[neighbors] = True
                stack.extend(int(item) for item in neighbors)
        sizes.append(size)

    minimum_size = max(3, int(np.ceil(config.min_component_fraction * len(points))))
    significant = sorted((size for size in sizes if size >= minimum_size), reverse=True)
    component_count = len(significant)
    return component_count, radius, sorted(sizes, reverse=True)


def _observation_coverage_ratio(points: Array, polygon: Array) -> float:
    """Return the fraction of observation points inside an implicit polygon."""
    x = points[:, 0]
    y = points[:, 1]
    inside = np.zeros(len(points), dtype=bool)
    previous = polygon[-1]
    for current in polygon:
        y_crosses = (current[1] > y) != (previous[1] > y)
        denominator = previous[1] - current[1]
        if abs(denominator) <= 1.0e-15:
            previous = current
            continue
        crossing_x = (previous[0] - current[0]) * (y - current[1]) / denominator + current[0]
        inside ^= y_crosses & (x < crossing_x)
        previous = current
    return float(np.mean(inside))


def _polygon_area(polygon: Array) -> float:
    points = np.asarray(polygon, dtype=float)
    return 0.5 * float(
        np.sum(points[:, 0] * np.roll(points[:, 1], -1) - points[:, 1] * np.roll(points[:, 0], -1))
    )


def _smooth_closed_curve(points: Array, passes: int) -> Array:
    curve = np.asarray(points, dtype=float).copy()
    for _ in range(int(passes)):
        curve = 0.25 * np.roll(curve, 1, axis=0) + 0.5 * curve + 0.25 * np.roll(curve, -1, axis=0)
    return curve


def _delaunay_triangles(points: Array) -> Array:
    """Return deterministic SciPy/Qhull Delaunay triangle vertex indices."""
    triangulation = Delaunay(np.asarray(points, dtype=float))
    return np.asarray(triangulation.simplices, dtype=int)


def _boundary_loops(boundary_edges: list[tuple[int, int]]) -> list[list[int]] | None:
    adjacency: dict[int, list[int]] = {}
    for first, second in boundary_edges:
        adjacency.setdefault(first, []).append(second)
        adjacency.setdefault(second, []).append(first)
    if not adjacency or any(len(neighbors) != 2 for neighbors in adjacency.values()):
        return None

    unused = {tuple(sorted(edge)) for edge in boundary_edges}
    loops: list[list[int]] = []
    while unused:
        first, second = min(unused)
        unused.remove((first, second))
        loop = [first]
        previous = first
        current = second
        while current != first:
            loop.append(current)
            candidates = sorted(adjacency[current])
            following = candidates[0] if candidates[0] != previous else candidates[1]
            edge = tuple(sorted((current, following)))
            if edge not in unused:
                return None
            unused.remove(edge)
            previous, current = current, following
            if len(loop) > len(adjacency) + 1:
                return None
        if len(loop) < 3:
            return None
        loops.append(loop)
    return loops


def _alpha_shape_candidate(points: Array, radius: float) -> tuple[Array | None, dict[str, float | int | str]]:
    unique = np.unique(np.asarray(points, dtype=float), axis=0)
    if len(unique) < 4:
        return None, {"reason": "alpha_requires_four_unique_points", "unique_count": len(unique)}
    try:
        triangles = _delaunay_triangles(unique)
    except (QhullError, RuntimeError, ValueError) as error:
        return None, {"reason": f"alpha_delaunay_failed:{error}", "unique_count": len(unique)}
    if len(triangles) == 0:
        return None, {"reason": "alpha_delaunay_empty", "unique_count": len(unique)}

    triangle_points = unique[triangles]
    side_a = np.linalg.norm(triangle_points[:, 1] - triangle_points[:, 0], axis=1)
    side_b = np.linalg.norm(triangle_points[:, 2] - triangle_points[:, 1], axis=1)
    side_c = np.linalg.norm(triangle_points[:, 0] - triangle_points[:, 2], axis=1)
    first_vector = triangle_points[:, 1] - triangle_points[:, 0]
    second_vector = triangle_points[:, 2] - triangle_points[:, 0]
    doubled_area = np.abs(
        first_vector[:, 0] * second_vector[:, 1] - first_vector[:, 1] * second_vector[:, 0]
    )
    circumradius = np.full(len(triangles), np.inf, dtype=float)
    nondegenerate = doubled_area > 1.0e-14
    circumradius[nondegenerate] = (
        side_a[nondegenerate] * side_b[nondegenerate] * side_c[nondegenerate]
    ) / (2.0 * doubled_area[nondegenerate])
    kept = triangles[circumradius <= float(radius)]
    if len(kept) == 0:
        return None, {
            "reason": "alpha_no_triangles_within_radius",
            "alpha_radius": float(radius),
            "triangle_count": len(triangles),
        }

    edge_counts: dict[tuple[int, int], int] = {}
    for triangle in kept:
        for first, second in (
            (int(triangle[0]), int(triangle[1])),
            (int(triangle[1]), int(triangle[2])),
            (int(triangle[2]), int(triangle[0])),
        ):
            edge = tuple(sorted((first, second)))
            edge_counts[edge] = edge_counts.get(edge, 0) + 1
    edges = sorted(edge for edge, count in edge_counts.items() if count == 1)
    loops = _boundary_loops(edges)
    if loops is None:
        return None, {
            "reason": "alpha_nonmanifold_boundary",
            "alpha_radius": float(radius),
            "kept_triangle_count": len(kept),
            "boundary_edge_count": len(edges),
        }

    polygonized = list(
        polygonize(
            LineString([unique[first], unique[second]])
            for first, second in edges
        )
    )
    if not polygonized:
        return None, {
            "reason": "alpha_polygonize_empty",
            "alpha_radius": float(radius),
            "kept_triangle_count": len(kept),
            "boundary_edge_count": len(edges),
        }

    polygons = [unique[np.asarray(loop, dtype=int)] for loop in loops]
    areas = np.asarray([abs(_polygon_area(polygon)) for polygon in polygons], dtype=float)
    outer_id = int(np.argmax(areas))
    outer = polygons[outer_id]
    outside_loops = 0
    hole_count = 0
    for loop_id, polygon in enumerate(polygons):
        if loop_id == outer_id:
            continue
        representative = np.mean(polygon, axis=0, keepdims=True)
        if _observation_coverage_ratio(representative, outer) >= 1.0:
            hole_count += 1
        else:
            outside_loops += 1
    if outside_loops:
        return None, {
            "reason": "alpha_multiple_outer_components",
            "alpha_radius": float(radius),
            "outer_component_count": outside_loops + 1,
            "loop_count": len(loops),
        }
    if _polygon_area(outer) < 0.0:
        outer = outer[::-1].copy()
    return outer, {
        "reason": "alpha_candidate_valid",
        "alpha_radius": float(radius),
        "unique_count": len(unique),
        "triangle_count": len(triangles),
        "kept_triangle_count": len(kept),
        "boundary_edge_count": len(edges),
        "loop_count": len(loops),
        "hole_count": hole_count,
        "polygonized_face_count": len(polygonized),
    }


def _adaptive_alpha_curve(
    points: Array,
    config: BoundaryV2Config,
) -> tuple[Array | None, dict[str, float | int | str]]:
    pairwise = np.linalg.norm(points[:, None, :] - points[None, :, :], axis=2)
    np.fill_diagonal(pairwise, np.inf)
    median_nearest = float(np.median(np.min(pairwise, axis=1)))
    if config.alpha_radius is not None:
        radii = [float(config.alpha_radius)]
    else:
        base = max(config.alpha_scale * median_nearest, config.sample_spacing)
        radii = [base * float(factor) for factor in config.alpha_growth_factors]

    last: dict[str, float | int | str] = {"reason": "alpha_no_candidate_attempted"}
    for attempt, radius in enumerate(radii, start=1):
        curve, diagnostics = _alpha_shape_candidate(points, radius)
        last = {**diagnostics, "alpha_attempt": attempt, "median_nearest_distance": median_nearest}
        if curve is None:
            continue
        selection_coverage = min(
            1.0,
            config.min_observation_coverage + max(2.0 / len(points), 0.03),
        )
        for smoothing_passes in range(config.alpha_smoothing_passes, -1, -1):
            smoothed = _smooth_closed_curve(curve, smoothing_passes)
            coverage = _observation_coverage_ratio(points, smoothed)
            last["observation_coverage_ratio"] = coverage
            last["alpha_selection_coverage"] = selection_coverage
            last["alpha_smoothing_passes"] = smoothing_passes
            if coverage >= selection_coverage:
                trial = boundary_v2_from_curve(
                    smoothed,
                    safety_distance=config.safety_distance,
                    sample_spacing=config.sample_spacing,
                    method="alpha_shape",
                    room_size=config.room_size,
                    room_margin=config.room_margin,
                )
                if isinstance(trial, BoundaryEstimateFailure):
                    last["reason"] = f"alpha_candidate_{trial.diagnostics['reason']}"
                    continue
                resampled_coverage = _observation_coverage_ratio(points, trial.curve_points)
                last["resampled_observation_coverage_ratio"] = resampled_coverage
                if resampled_coverage >= config.min_observation_coverage:
                    return smoothed, last
                last["reason"] = "alpha_insufficient_observation_coverage_after_resampling"
        last["reason"] = "alpha_insufficient_observation_coverage"
    return None, last


def boundary_v2_from_curve(
    curve_points: Array,
    safety_distance: float,
    sample_spacing: float,
    method: str,
    room_size: tuple[float, float] | None = None,
    room_margin: float = 0.0,
) -> BoundaryEstimateV2Result:
    """Build the V2 contract from one candidate closed curve.

    Invalid input topology returns ``BOUNDARY_INVALID``.  A self-intersecting
    or room-infeasible normal offset returns ``OFFSET_INVALID``.  The function
    never repairs either condition silently.
    """
    if safety_distance < 0.0 or not np.isfinite(safety_distance):
        raise ValueError("safety_distance must be finite and non-negative.")
    if room_margin < 0.0:
        raise ValueError("room_margin must be non-negative.")
    try:
        curve, arc_s, length, tangents, normals = resample_closed_curve_by_arclength(
            curve_points,
            spacing=sample_spacing,
        )
    except ValueError as error:
        return _failure("BOUNDARY_INVALID", str(error), component_count=1, method=method)

    closed_curve = np.vstack((curve, curve[0]))
    curve_line = LineString(closed_curve)
    curve_polygon = Polygon(curve)
    if not curve_line.is_simple or not curve_polygon.is_valid or curve_polygon.area <= 1.0e-12:
        return _failure(
            "BOUNDARY_INVALID",
            "shapely_curve_invalid",
            component_count=1,
            method=method,
            shapely_validity=explain_validity(curve_polygon),
        )

    offset = curve + float(safety_distance) * normals
    try:
        offset_self_intersection = has_self_intersections(offset)
    except ValueError:
        offset_self_intersection = True
    closed_offset = np.vstack((offset, offset[0]))
    offset_line = LineString(closed_offset)
    offset_polygon = Polygon(offset)
    if (
        offset_self_intersection
        or not offset_line.is_simple
        or not offset_polygon.is_valid
        or offset_polygon.area <= 1.0e-12
    ):
        return _failure(
            "OFFSET_INVALID",
            "offset_self_intersection",
            component_count=1,
            method=method,
            length=length,
            safety_distance=float(safety_distance),
            shapely_validity=explain_validity(offset_polygon),
        )

    if room_size is not None:
        room = np.asarray(room_size, dtype=float)
        if room.shape != (2,) or not np.all(np.isfinite(room)) or np.any(room <= 0.0):
            raise ValueError("room_size must contain two finite positive dimensions.")
        lower = float(room_margin)
        upper = room - float(room_margin)
        if np.any(offset < lower) or np.any(offset > upper):
            return _failure(
                "OFFSET_INVALID",
                "offset_outside_room",
                component_count=1,
                method=method,
                length=length,
                room_margin=float(room_margin),
            )

    count = len(curve)
    return BoundaryEstimateV2(
        curve_points=curve,
        offset_points=offset,
        arc_s=arc_s,
        length=length,
        tangents=tangents,
        outward_normals=normals,
        uncertainty=np.zeros(count, dtype=float),
        confidence=np.ones(count, dtype=float),
        component_count=1,
        topology_valid=True,
        method=method,
        version=2,
        diagnostics={
            "status": "VALID",
            "sample_count": count,
            "sample_spacing_requested": float(sample_spacing),
            "sample_spacing_actual": float(length / count),
            "safety_distance": float(safety_distance),
            "orientation": "counter_clockwise",
            "curve_self_intersections": 0,
            "offset_self_intersections": 0,
            "curve_shapely_valid": int(curve_polygon.is_valid),
            "offset_shapely_valid": int(offset_polygon.is_valid),
            "confidence_status": "neutral_not_estimated_pr1",
        },
    )


def adapt_radial_boundary(
    boundary: BoundaryEstimate,
    sample_spacing: float,
    safety_distance: float | None = None,
    room_size: tuple[float, float] | None = None,
    room_margin: float = 0.0,
) -> BoundaryEstimateV2Result:
    """Adapt the existing radial baseline without changing its v1 API."""
    distance = boundary.safety_distance if safety_distance is None else float(safety_distance)
    return boundary_v2_from_curve(
        boundary.boundary_points,
        safety_distance=distance,
        sample_spacing=sample_spacing,
        method="radial_adapter",
        room_size=room_size,
        room_margin=room_margin,
    )


def _estimate_radial_geometry(points: Array, config: BoundaryV2Config) -> BoundaryEstimateV2Result:
    try:
        radial = estimate_radial_boundary(
            points,
            num_bins=config.radial_bins,
            safety_distance=0.0,
            percentile=config.radial_percentile,
            smoothing_passes=config.radial_smoothing_passes,
        )
    except ValueError as error:
        return _failure(
            "BOUNDARY_INVALID",
            str(error),
            component_count=1,
            method="radial_adapter",
        )

    result = adapt_radial_boundary(
        radial,
        sample_spacing=config.sample_spacing,
        safety_distance=config.safety_distance,
        room_size=config.room_size,
        room_margin=config.room_margin,
    )
    if isinstance(result, BoundaryEstimateFailure):
        return result
    observation_coverage = _observation_coverage_ratio(points, result.curve_points)
    if observation_coverage < config.min_observation_coverage:
        return _failure(
            "BOUNDARY_INVALID",
            "insufficient_observation_coverage",
            component_count=1,
            method="radial_adapter",
            observation_coverage_ratio=observation_coverage,
            minimum_observation_coverage=float(config.min_observation_coverage),
        )
    return BoundaryEstimateV2(
        curve_points=result.curve_points,
        offset_points=result.offset_points,
        arc_s=result.arc_s,
        length=result.length,
        tangents=result.tangents,
        outward_normals=result.outward_normals,
        uncertainty=result.uncertainty,
        confidence=result.confidence,
        component_count=result.component_count,
        topology_valid=result.topology_valid,
        method=result.method,
        version=result.version,
        diagnostics={
            **result.diagnostics,
            "estimator": "radial",
            "observation_count": len(points),
            "radial_bins": config.radial_bins,
            "radial_percentile": float(config.radial_percentile),
            "observation_coverage_ratio": observation_coverage,
            "minimum_observation_coverage": float(config.min_observation_coverage),
        },
    )


def _estimate_alpha_geometry(points: Array, config: BoundaryV2Config) -> BoundaryEstimateV2Result:
    curve, alpha_diagnostics = _adaptive_alpha_curve(points, config)
    if curve is None:
        return _failure(
            "BOUNDARY_INVALID",
            str(alpha_diagnostics.get("reason", "alpha_shape_failed")),
            component_count=1,
            method="alpha_shape",
            **{
                key: value
                for key, value in alpha_diagnostics.items()
                if key != "reason" and isinstance(value, (float, int, str))
            },
        )
    result = boundary_v2_from_curve(
        curve,
        safety_distance=config.safety_distance,
        sample_spacing=config.sample_spacing,
        method="alpha_shape",
        room_size=config.room_size,
        room_margin=config.room_margin,
    )
    if isinstance(result, BoundaryEstimateFailure):
        return result
    observation_coverage = _observation_coverage_ratio(points, result.curve_points)
    if observation_coverage < config.min_observation_coverage:
        return _failure(
            "BOUNDARY_INVALID",
            "alpha_insufficient_observation_coverage_after_resampling",
            component_count=1,
            method="alpha_shape",
            observation_coverage_ratio=observation_coverage,
            minimum_observation_coverage=float(config.min_observation_coverage),
        )
    return BoundaryEstimateV2(
        curve_points=result.curve_points,
        offset_points=result.offset_points,
        arc_s=result.arc_s,
        length=result.length,
        tangents=result.tangents,
        outward_normals=result.outward_normals,
        uncertainty=result.uncertainty,
        confidence=result.confidence,
        component_count=1,
        topology_valid=True,
        method="alpha_shape",
        version=result.version,
        diagnostics={
            **result.diagnostics,
            **alpha_diagnostics,
            "status": "VALID",
            "estimator": "alpha",
            "observation_count": len(points),
            "alpha_radius_used": float(alpha_diagnostics["alpha_radius"]),
            "observation_coverage_ratio": observation_coverage,
            "minimum_observation_coverage": float(config.min_observation_coverage),
            "confidence_status": "neutral_disabled_pr6_ablation",
        },
    )


def _estimate_geometry(points: Array, config: BoundaryV2Config) -> BoundaryEstimateV2Result:
    return (
        _estimate_alpha_geometry(points, config)
        if config.estimator == "alpha"
        else _estimate_radial_geometry(points, config)
    )


def _bootstrap_boundary_confidence(
    base: BoundaryEstimateV2,
    points: Array,
    config: BoundaryV2Config,
    rng: np.random.Generator,
) -> BoundaryEstimateV2Result:
    if config.bootstrap_samples == 0:
        return base

    bootstrap_config = replace(
        config,
        safety_distance=0.0,
        room_size=None,
        room_margin=0.0,
        bootstrap_samples=0,
        min_observation_coverage=max(0.6, config.min_observation_coverage - 0.15),
    )
    distances: list[Array] = []
    failures = 0
    for _ in range(config.bootstrap_samples):
        indices = rng.integers(0, len(points), size=len(points))
        sample = np.unique(points[indices], axis=0)
        if len(sample) < config.min_observation_points:
            failures += 1
            continue
        estimate = _estimate_geometry(sample, bootstrap_config)
        if isinstance(estimate, BoundaryEstimateFailure):
            failures += 1
            continue
        pairwise = np.linalg.norm(
            base.curve_points[:, None, :] - estimate.curve_points[None, :, :],
            axis=2,
        )
        distances.append(np.min(pairwise, axis=1))

    success_count = len(distances)
    minimum_success = int(np.ceil(config.bootstrap_min_success_fraction * config.bootstrap_samples))
    if success_count < minimum_success:
        return _failure(
            "BOUNDARY_INVALID",
            "bootstrap_insufficient_success",
            component_count=1,
            method=base.method,
            bootstrap_samples=config.bootstrap_samples,
            bootstrap_success_count=success_count,
            bootstrap_failure_count=failures,
            bootstrap_minimum_success=minimum_success,
        )

    samples = np.asarray(distances, dtype=float)
    uncertainty = np.sqrt(np.mean(samples**2, axis=0))
    if config.bootstrap_confidence_scale is None:
        confidence_scale = max(
            config.sample_spacing,
            float(np.median(uncertainty)),
            1.0e-12,
        )
    else:
        confidence_scale = float(config.bootstrap_confidence_scale)
    confidence = np.clip(
        np.exp(-uncertainty / confidence_scale),
        config.bootstrap_confidence_floor,
        1.0,
    )
    return BoundaryEstimateV2(
        curve_points=base.curve_points,
        offset_points=base.offset_points,
        arc_s=base.arc_s,
        length=base.length,
        tangents=base.tangents,
        outward_normals=base.outward_normals,
        uncertainty=uncertainty,
        confidence=confidence,
        component_count=base.component_count,
        topology_valid=base.topology_valid,
        method=base.method,
        version=base.version,
        diagnostics={
            **base.diagnostics,
            "confidence_status": "bootstrap_estimated_pr6",
            "bootstrap_samples": config.bootstrap_samples,
            "bootstrap_success_count": success_count,
            "bootstrap_failure_count": failures,
            "bootstrap_success_fraction": float(success_count / config.bootstrap_samples),
            "bootstrap_confidence_floor": float(config.bootstrap_confidence_floor),
            "bootstrap_confidence_scale": confidence_scale,
            "bootstrap_observation_coverage_floor": float(
                bootstrap_config.min_observation_coverage
            ),
            "uncertainty_mean": float(np.mean(uncertainty)),
            "uncertainty_max": float(np.max(uncertainty)),
            "confidence_mean": float(np.mean(confidence)),
            "confidence_min": float(np.min(confidence)),
        },
    )


def estimate_boundary_v2(
    observation: Array,
    config: BoundaryV2Config,
    rng: np.random.Generator,
) -> BoundaryEstimateV2Result:
    """Estimate radial/alpha geometry and optional bootstrap confidence."""
    if not isinstance(rng, np.random.Generator):
        raise TypeError("rng must be an explicit numpy.random.Generator.")
    points = _validate_observation(observation, config.min_observation_points)
    if points is None:
        return _failure(
            "OBSERVATION_INVALID",
            "observation_must_be_finite_N_by_2_with_minimum_count",
            method="alpha_shape" if config.estimator == "alpha" else "radial_adapter",
            minimum_count=config.min_observation_points,
        )

    component_count, connectivity_radius, component_sizes = _significant_component_summary(points, config)
    if component_count != 1:
        reason = "no_significant_component" if component_count == 0 else "multiple_significant_components"
        return _failure(
            "BOUNDARY_INVALID",
            reason,
            component_count=component_count,
            method="alpha_shape" if config.estimator == "alpha" else "radial_adapter",
            connectivity_radius=connectivity_radius,
            component_sizes=",".join(str(size) for size in component_sizes),
        )

    result = _estimate_geometry(points, config)
    if isinstance(result, BoundaryEstimateFailure):
        return result
    diagnostics = {
        **result.diagnostics,
        "connectivity_radius": connectivity_radius,
        "component_sizes": ",".join(str(size) for size in component_sizes),
    }
    enriched = BoundaryEstimateV2(
        curve_points=result.curve_points,
        offset_points=result.offset_points,
        arc_s=result.arc_s,
        length=result.length,
        tangents=result.tangents,
        outward_normals=result.outward_normals,
        uncertainty=result.uncertainty,
        confidence=result.confidence,
        component_count=result.component_count,
        topology_valid=result.topology_valid,
        method=result.method,
        version=result.version,
        diagnostics=diagnostics,
    )
    return _bootstrap_boundary_confidence(enriched, points, config, rng)
