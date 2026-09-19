"""Boundary-aware safe routing for ABCG-v2 nominal motion.

ROLE: CORE MATH — choose a waypoint so the nominal command does not demand
crossing the crowd.  PR5 remains the authority on forbidden velocities.

This module never changes safety distances.  The final CVT target ``z_i`` is
unchanged; only the path taken toward it is rewritten.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from shapely.geometry import MultiPoint

from ..geometry.deployment_curve import DeploymentCurve, build_deployment_curve
from ..scenarios.rectangular import RectangularScenario
from ..types import Array


ROUTE_DIRECT = "DIRECT"
ROUTE_APPROACH_RING = "APPROACH_RING"
ROUTE_FOLLOW_BOUNDARY = "FOLLOW_BOUNDARY"
ROUTE_FOLLOW_DEPLOYMENT = "FOLLOW_DEPLOYMENT"
ROUTE_FINAL_APPROACH = "FINAL_APPROACH"

_TRANSIT_CLEARANCE_FRACTIONS = (1.0, 0.75, 0.5, 0.25, 0.0)


@dataclass(frozen=True)
class BoundaryRouteConfig:
    """Development-tunable routing parameters. Not a PR5 / success-criterion change.

    ``transit_clearance`` is the extra offset beyond the frozen safety distance
    used only as a movement (not deployment) curve.  Its numeric value belongs
    on a development seed set, not on the spent holdout.
    """

    enabled: bool = True
    transit_clearance: float = 0.25
    lookahead: float = 0.8
    approach_radius: float = 0.40
    entry_sample_spacing: float = 0.25
    los_sample_spacing: float = 0.10
    stall_speed: float = 0.02

    def __post_init__(self) -> None:
        for name in (
            "transit_clearance",
            "lookahead",
            "approach_radius",
            "entry_sample_spacing",
            "los_sample_spacing",
            "stall_speed",
        ):
            value = float(getattr(self, name))
            if not np.isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be finite and non-negative.")
        if self.lookahead <= 0.0:
            raise ValueError("lookahead must be positive.")
        if self.approach_radius <= 0.0:
            raise ValueError("approach_radius must be positive.")
        if self.entry_sample_spacing <= 0.0 or self.los_sample_spacing <= 0.0:
            raise ValueError("sample spacings must be positive.")


@dataclass(frozen=True)
class TransitCurve:
    """Sampled movement curve outside the frozen deployment ring."""

    curve_points: Array
    arc_s: Array
    length: float
    tangents: Array
    clearance: float
    diagnostics: dict[str, object]


@dataclass(frozen=True)
class RoutePlan:
    """Per-guide waypoints and route-mode labels for one control step."""

    waypoints: Array
    modes: tuple[str, ...]
    target_arc_s: Array
    guide_arc_s: Array
    remaining_arc: Array
    direction: Array
    blocked_direct: Array
    diagnostics: dict[str, object]


def interpolate_closed_curve(curve: Array, arc_s: Array, length: float, query_s: Array) -> Array:
    """Linear interpolation on a periodic arc-length parameterization."""
    samples = np.asarray(curve, dtype=float)
    coordinates = np.asarray(arc_s, dtype=float)
    period = float(length)
    queries = np.mod(np.asarray(query_s, dtype=float), period)
    if samples.ndim != 2 or samples.shape[1] != 2:
        raise ValueError("curve must have shape (K, 2).")
    if coordinates.shape != (len(samples),) or not np.isfinite(period) or period <= 0.0:
        raise ValueError("arc_s and length must describe a positive closed curve.")
    extended_s = np.r_[coordinates, period]
    return np.column_stack(
        [
            np.interp(queries, extended_s, np.r_[samples[:, column], samples[0, column]])
            for column in range(2)
        ]
    )


def project_onto_curve(points: Array, curve: Array, arc_s: Array) -> tuple[Array, Array, Array]:
    """Return nearest curve points, arc coordinates, and Euclidean distances."""
    query = np.asarray(points, dtype=float)
    samples = np.asarray(curve, dtype=float)
    coordinates = np.asarray(arc_s, dtype=float)
    if query.ndim != 2 or query.shape[1] != 2:
        raise ValueError("points must have shape (N, 2).")
    if samples.ndim != 2 or samples.shape[1] != 2 or coordinates.shape != (len(samples),):
        raise ValueError("curve and arc_s must be aligned (K, 2) / (K,) arrays.")
    delta = query[:, None, :] - samples[None, :, :]
    distances = np.linalg.norm(delta, axis=2)
    index = np.argmin(distances, axis=1)
    return samples[index].copy(), coordinates[index].copy(), distances[np.arange(len(query)), index].copy()


def shorter_arc_direction(current_s: Array, target_s: Array, length: float) -> tuple[Array, Array]:
    """Return signed direction (+1 increasing-s, -1 decreasing-s) and remaining arc.

    On a counter-clockwise curve, +1 is the CCW transit.  The shorter of the two
    periodic distances is selected; ties break toward increasing ``s``.
    """
    period = float(length)
    current = np.mod(np.asarray(current_s, dtype=float), period)
    target = np.mod(np.asarray(target_s, dtype=float), period)
    forward = np.mod(target - current, period)
    backward = np.mod(current - target, period)
    go_forward = forward <= backward
    direction = np.where(go_forward, 1.0, -1.0)
    remaining = np.where(go_forward, forward, backward)
    return direction.astype(float), remaining.astype(float)


def sample_segment(start: Array, end: Array, spacing: float) -> Array:
    """Return inclusive samples along a straight segment."""
    origin = np.asarray(start, dtype=float)
    finish = np.asarray(end, dtype=float)
    if origin.shape != (2,) or finish.shape != (2,):
        raise ValueError("segment endpoints must be length-2 vectors.")
    distance = float(np.linalg.norm(finish - origin))
    step = float(spacing)
    if not np.isfinite(step) or step <= 0.0:
        raise ValueError("spacing must be finite and positive.")
    if distance <= step:
        return np.vstack((origin, finish))
    count = int(np.ceil(distance / step)) + 1
    fraction = np.linspace(0.0, 1.0, count)
    return origin[None, :] + fraction[:, None] * (finish - origin)[None, :]


def line_of_sight_clear(
    start: Array,
    end: Array,
    crowd_points: Array,
    clearance: float,
    *,
    room_size: Array | None = None,
    wall_margin: float = 0.0,
    spacing: float = 0.10,
) -> bool:
    """True iff the chord stays outside the crowd clearance and the room margin."""
    if not np.isfinite(clearance) or clearance < 0.0:
        raise ValueError("clearance must be finite and non-negative.")
    samples = sample_segment(start, end, spacing)
    crowd = np.asarray(crowd_points, dtype=float)
    if crowd.size:
        if crowd.ndim != 2 or crowd.shape[1] != 2:
            raise ValueError("crowd_points must have shape (N, 2).")
        nearest = np.min(np.linalg.norm(samples[:, None, :] - crowd[None, :, :], axis=2), axis=1)
        if np.any(nearest + 1.0e-9 < float(clearance)):
            return False
    if room_size is not None:
        room = np.asarray(room_size, dtype=float)
        margin = float(wall_margin)
        if room.shape != (2,) or not np.all(np.isfinite(room)):
            raise ValueError("room_size must be a finite length-2 vector.")
        if np.any(samples[:, 0] < margin - 1.0e-9) or np.any(samples[:, 0] > room[0] - margin + 1.0e-9):
            return False
        if np.any(samples[:, 1] < margin - 1.0e-9) or np.any(samples[:, 1] > room[1] - margin + 1.0e-9):
            return False
    return True


def nearest_safe_entry(
    point: Array,
    transit: TransitCurve,
    crowd_points: Array,
    clearance: float,
    *,
    room_size: Array | None = None,
    wall_margin: float = 0.0,
    sample_spacing: float = 0.25,
    los_spacing: float = 0.10,
) -> Array:
    """Return the closest transit point whose chord from ``point`` is feasible."""
    origin = np.asarray(point, dtype=float)
    stride = max(1, int(round(float(sample_spacing) / _mean_sample_spacing(transit))))
    candidates = transit.curve_points[::stride]
    if len(candidates) == 0:
        return transit.curve_points[0].copy()
    distances = np.linalg.norm(candidates - origin[None, :], axis=1)
    order = np.argsort(distances)
    for index in order:
        candidate = candidates[int(index)]
        if line_of_sight_clear(
            origin,
            candidate,
            crowd_points,
            clearance,
            room_size=room_size,
            wall_margin=wall_margin,
            spacing=los_spacing,
        ):
            return candidate.copy()
    nearest, arc_s, _ = project_onto_curve(origin[None, :], transit.curve_points, transit.arc_s)
    _tangent, normal = _tangent_normal_at(transit, float(arc_s[0]))
    return nearest[0] + 0.25 * normal


def _mean_sample_spacing(transit: TransitCurve) -> float:
    if len(transit.curve_points) <= 1:
        return max(float(transit.length), 1.0e-3)
    return max(float(transit.length) / float(len(transit.curve_points)), 1.0e-6)


def _outward_normal(tangent: Array) -> Array:
    vector = np.asarray(tangent, dtype=float)
    return np.array([float(vector[1]), -float(vector[0])], dtype=float)


def _tangent_normal_at(transit: TransitCurve, s: float) -> tuple[Array, Array]:
    period = float(transit.length)
    query = float(np.mod(float(s), period))
    delta = np.abs(np.asarray(transit.arc_s, dtype=float) - query)
    circular = np.minimum(delta, period - delta)
    index = int(np.argmin(circular))
    tangent = np.asarray(transit.tangents[index], dtype=float)
    return tangent, _outward_normal(tangent)


def _safe_follow_waypoint(
    point: Array,
    transit: TransitCurve,
    s_now: float,
    sigma: float,
    arc_left: float,
    config: BoundaryRouteConfig,
    crowd_points: Array,
    clearance: float,
    room_size: Array | None,
    wall_margin: float,
) -> Array:
    """Advance along the transit without commanding a chord through the crowd.

    A lookahead sample on a convex ring sags inward.  If that chord is blocked,
    command the local tangent plus a small outward offset from the current pose.
    """
    advance = min(float(config.lookahead), float(arc_left))
    query = np.array([float(s_now) + float(sigma) * advance], dtype=float)
    curve_wp = interpolate_closed_curve(
        transit.curve_points,
        transit.arc_s,
        transit.length,
        query,
    )[0]
    if line_of_sight_clear(
        point,
        curve_wp,
        crowd_points,
        clearance,
        room_size=room_size,
        wall_margin=wall_margin,
        spacing=config.los_sample_spacing,
    ):
        return curve_wp
    tangent, normal = _tangent_normal_at(transit, s_now)
    outward = 0.15 * normal
    tangent_wp = np.asarray(point, dtype=float) + float(sigma) * advance * tangent + outward
    if line_of_sight_clear(
        point,
        tangent_wp,
        crowd_points,
        clearance,
        room_size=room_size,
        wall_margin=wall_margin,
        spacing=config.los_sample_spacing,
    ):
        return tangent_wp
    return np.asarray(point, dtype=float) + 0.25 * normal + 0.40 * float(sigma) * tangent


def _covering_hull_vertices(crowd_points: Array | None) -> Array | None:
    if crowd_points is None:
        return None
    cloud = np.asarray(crowd_points, dtype=float)
    if cloud.ndim != 2 or cloud.shape[1] != 2 or len(cloud) < 3 or not np.all(np.isfinite(cloud)):
        return None
    hull = MultiPoint([tuple(map(float, row)) for row in cloud]).convex_hull
    if hull.geom_type != "Polygon" or hull.is_empty:
        return None
    coords = np.asarray(hull.exterior.coords[:-1], dtype=float)
    return coords if len(coords) >= 3 else None


def _buffer_transit_source(
    source: Array,
    *,
    base: float,
    extra: float,
    crowd_points: Array | None,
    workspace: RectangularScenario | None,
    wall_margin: float,
    sample_spacing: float,
    construction: str,
    attempts: list[tuple[str, float, str]],
) -> TransitCurve | None:
    for fraction in _TRANSIT_CLEARANCE_FRACTIONS:
        delta = extra * float(fraction)
        result = build_deployment_curve(
            source,
            base + delta,
            crowd_points=crowd_points,
            workspace=workspace,
            wall_margin=wall_margin,
            sample_spacing=sample_spacing,
            min_crowd_clearance=base,
        )
        if isinstance(result, DeploymentCurve):
            return TransitCurve(
                curve_points=result.curve_points,
                arc_s=result.arc_s,
                length=float(result.length),
                tangents=result.tangents,
                clearance=delta,
                diagnostics={
                    "status": "VALID",
                    "requested_clearance": extra,
                    "used_clearance": delta,
                    "construction": construction,
                    "attempts": attempts,
                },
            )
        attempts.append((construction, delta, str(result.reason)))
    return None


def transit_from_deployment(deployment: DeploymentCurve, *, clearance: float = 0.0) -> TransitCurve:
    """Wrap a frozen deployment ring as a movement curve. Clearance is diagnostic only."""
    if not isinstance(deployment, DeploymentCurve):
        raise TypeError("deployment must be DeploymentCurve.")
    extra = float(clearance)
    if not np.isfinite(extra) or extra < 0.0:
        raise ValueError("clearance must be finite and non-negative.")
    return TransitCurve(
        curve_points=deployment.curve_points,
        arc_s=deployment.arc_s,
        length=float(deployment.length),
        tangents=deployment.tangents,
        clearance=extra,
        diagnostics={
            "status": "DEPLOYMENT_INNER",
            "construction": "deployment_curve",
            "used_clearance": extra,
        },
    )


def _distinct_inner(inner: TransitCurve | None, transit: TransitCurve | None) -> bool:
    if inner is None or transit is None or inner is transit:
        return False
    return float(transit.clearance) - float(inner.clearance) > 1.0e-6


def build_transit_curve(
    crowd_curve: Array,
    safety_distance: float,
    transit_clearance: float,
    *,
    crowd_points: Array | None = None,
    workspace: RectangularScenario | None = None,
    wall_margin: float = 0.0,
    sample_spacing: float = 0.08,
    fallback: DeploymentCurve | None = None,
) -> TransitCurve | None:
    """Buffer a movement curve at ``d_safe + delta``, shrinking delta if needed.

    The frozen deployment distance is never reduced.  If the estimated crowd
    polygon leaks observations, a covering hull of the actual crowd points is
    used for the movement curve only.  The last resort is the already-valid
    deployment curve.
    """
    base = float(safety_distance)
    extra = float(transit_clearance)
    if not np.isfinite(base) or base < 0.0 or not np.isfinite(extra) or extra < 0.0:
        raise ValueError("safety_distance and transit_clearance must be finite and non-negative.")
    attempts: list[tuple[str, float, str]] = []
    estimated = _buffer_transit_source(
        crowd_curve,
        base=base,
        extra=extra,
        crowd_points=crowd_points,
        workspace=workspace,
        wall_margin=wall_margin,
        sample_spacing=sample_spacing,
        construction="shapely_minkowski_buffer",
        attempts=attempts,
    )
    if estimated is not None:
        return estimated
    hull = _covering_hull_vertices(crowd_points)
    if hull is not None:
        covering = _buffer_transit_source(
            hull,
            base=base,
            extra=extra,
            crowd_points=crowd_points,
            workspace=workspace,
            wall_margin=wall_margin,
            sample_spacing=sample_spacing,
            construction="crowd_hull_buffer",
            attempts=attempts,
        )
        if covering is not None:
            return covering
    if fallback is not None:
        return TransitCurve(
            curve_points=fallback.curve_points,
            arc_s=fallback.arc_s,
            length=float(fallback.length),
            tangents=fallback.tangents,
            clearance=0.0,
            diagnostics={
                "status": "FALLBACK_DEPLOYMENT_CURVE",
                "requested_clearance": extra,
                "used_clearance": 0.0,
                "attempts": attempts,
            },
        )
    return None


def plan_route_waypoints(
    positions: Array,
    targets: Array,
    active_mask: Array,
    transit: TransitCurve | None,
    crowd_points: Array,
    config: BoundaryRouteConfig,
    *,
    clearance: float,
    room_size: Array | None = None,
    wall_margin: float = 0.0,
    previous_applied: Array | None = None,
    tracking_tolerance: float = 0.03,
    inner: TransitCurve | None = None,
) -> RoutePlan:
    """Compute one-step waypoints. Inactive guides receive their current position."""
    current = np.asarray(positions, dtype=float)
    goal = np.asarray(targets, dtype=float)
    active = np.asarray(active_mask, dtype=bool)
    if current.shape != goal.shape or current.ndim != 2 or current.shape[1] != 2:
        raise ValueError("positions and targets must be matching finite (M, 2) arrays.")
    if active.shape != (len(current),):
        raise ValueError("active_mask must match the guide count.")
    if not np.all(np.isfinite(current)) or not np.all(np.isfinite(goal)):
        raise ValueError("positions and targets must be finite.")

    waypoints = current.copy()
    modes = [ROUTE_DIRECT] * len(current)
    target_arc = np.full(len(current), np.nan, dtype=float)
    guide_arc = np.full(len(current), np.nan, dtype=float)
    remaining = np.zeros(len(current), dtype=float)
    direction = np.zeros(len(current), dtype=float)
    blocked = np.zeros(len(current), dtype=bool)
    direct_count = 0
    approach_count = 0
    follow_count = 0
    follow_inner_count = 0
    final_count = 0
    use_inner = _distinct_inner(inner, transit)

    previous = None
    if previous_applied is not None:
        previous = np.asarray(previous_applied, dtype=float)
        if previous.shape != current.shape:
            raise ValueError("previous_applied must match positions.")

    for index in range(len(current)):
        if not active[index]:
            continue
        point = current[index]
        target = goal[index]
        stalled = False
        if previous is not None:
            speed = float(np.linalg.norm(previous[index]))
            target_error = float(np.linalg.norm(target - point))
            stalled = speed <= float(config.stall_speed) and target_error > 2.0 * float(tracking_tolerance)
        los = line_of_sight_clear(
            point,
            target,
            crowd_points,
            clearance,
            room_size=room_size,
            wall_margin=wall_margin,
            spacing=config.los_sample_spacing,
        )
        if los and not stalled:
            waypoints[index] = target
            modes[index] = ROUTE_DIRECT
            direct_count += 1
            continue
        blocked[index] = True
        if transit is None:
            waypoints[index] = target
            modes[index] = ROUTE_DIRECT
            direct_count += 1
            continue
        projected, s_now, dist_ring = project_onto_curve(
            point[None, :],
            transit.curve_points,
            transit.arc_s,
        )
        target_proj, s_star, _ = project_onto_curve(
            target[None, :],
            transit.curve_points,
            transit.arc_s,
        )
        guide_arc[index] = float(s_now[0])
        target_arc[index] = float(s_star[0])
        sigma, arc_left = shorter_arc_direction(s_now, s_star, transit.length)
        direction[index] = float(sigma[0])
        remaining[index] = float(arc_left[0])
        if float(dist_ring[0]) > float(config.approach_radius):
            waypoints[index] = nearest_safe_entry(
                point,
                transit,
                crowd_points,
                clearance,
                room_size=room_size,
                wall_margin=wall_margin,
                sample_spacing=config.entry_sample_spacing,
                los_spacing=config.los_sample_spacing,
            )
            modes[index] = ROUTE_APPROACH_RING
            approach_count += 1
            continue
        at_target_foot = float(np.linalg.norm(point - target_proj[0])) <= float(config.approach_radius)
        enter_inner = (
            use_inner
            and inner is not None
            and (float(arc_left[0]) <= float(config.lookahead) or at_target_foot)
        )
        if enter_inner and inner is not None:
            _inner_proj, inner_s, inner_dist = project_onto_curve(
                point[None, :],
                inner.curve_points,
                inner.arc_s,
            )
            _inner_target, inner_star, _ = project_onto_curve(
                target[None, :],
                inner.curve_points,
                inner.arc_s,
            )
            inner_sigma, inner_left = shorter_arc_direction(inner_s, inner_star, inner.length)
            near_inner_target = (
                float(inner_left[0]) <= float(config.lookahead)
                and float(np.linalg.norm(point - target)) <= float(config.approach_radius)
            )
            if los or near_inner_target:
                waypoints[index] = target
                modes[index] = ROUTE_FINAL_APPROACH
                final_count += 1
                continue
            if float(inner_dist[0]) > float(config.approach_radius):
                waypoints[index] = nearest_safe_entry(
                    point,
                    inner,
                    crowd_points,
                    clearance,
                    room_size=room_size,
                    wall_margin=wall_margin,
                    sample_spacing=config.entry_sample_spacing,
                    los_spacing=config.los_sample_spacing,
                )
            else:
                waypoints[index] = _safe_follow_waypoint(
                    point,
                    inner,
                    float(inner_s[0]),
                    float(inner_sigma[0]),
                    float(inner_left[0]),
                    config,
                    crowd_points,
                    clearance,
                    room_size,
                    wall_margin,
                )
            modes[index] = ROUTE_FOLLOW_DEPLOYMENT
            follow_inner_count += 1
            continue
        if los or (float(arc_left[0]) <= float(config.lookahead) and at_target_foot):
            waypoints[index] = target
            modes[index] = ROUTE_FINAL_APPROACH
            final_count += 1
            continue
        waypoints[index] = _safe_follow_waypoint(
            point,
            transit,
            float(s_now[0]),
            float(sigma[0]),
            float(arc_left[0]),
            config,
            crowd_points,
            clearance,
            room_size,
            wall_margin,
        )
        modes[index] = ROUTE_FOLLOW_BOUNDARY
        follow_count += 1

    return RoutePlan(
        waypoints=waypoints,
        modes=tuple(modes),
        target_arc_s=target_arc,
        guide_arc_s=guide_arc,
        remaining_arc=remaining,
        direction=direction,
        blocked_direct=blocked,
        diagnostics={
            "direct_count": int(direct_count),
            "approach_ring_count": int(approach_count),
            "follow_boundary_count": int(follow_count),
            "follow_deployment_count": int(follow_inner_count),
            "final_approach_count": int(final_count),
            "blocked_direct_count": int(np.count_nonzero(blocked)),
            "transit_clearance": None if transit is None else float(transit.clearance),
        },
    )


__all__ = [
    "ROUTE_APPROACH_RING",
    "ROUTE_DIRECT",
    "ROUTE_FINAL_APPROACH",
    "ROUTE_FOLLOW_BOUNDARY",
    "ROUTE_FOLLOW_DEPLOYMENT",
    "BoundaryRouteConfig",
    "RoutePlan",
    "TransitCurve",
    "build_transit_curve",
    "interpolate_closed_curve",
    "line_of_sight_clear",
    "nearest_safe_entry",
    "plan_route_waypoints",
    "project_onto_curve",
    "sample_segment",
    "shorter_arc_direction",
    "transit_from_deployment",
]
