"""Endpoint helpers and PR5 auditable velocity-safety projection."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np

from ..types import Array, unit


@dataclass(frozen=True)
class VelocitySafetyConfig:
    """Discrete one-step separation and room constraints for PR5.

    The filter projects onto ordered linear half-spaces and per-guide speed
    balls.  This is an auditable sampled-data safety layer, not ORCA or a CBF.
    """

    enabled: bool = True
    min_guide_distance: float = 0.6
    min_crowd_distance: float = 0.8
    room_margin: float = 0.25
    residual_tolerance: float = 1.0e-9
    max_projection_sweeps: int = 200

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, (bool, np.bool_)):
            raise ValueError("enabled must be boolean.")
        for name in ("min_guide_distance", "min_crowd_distance", "room_margin"):
            value = float(getattr(self, name))
            if not np.isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be finite and non-negative.")
        if not np.isfinite(self.residual_tolerance) or self.residual_tolerance <= 0.0:
            raise ValueError("residual_tolerance must be finite and positive.")
        if (
            isinstance(self.max_projection_sweeps, bool)
            or not isinstance(self.max_projection_sweeps, (int, np.integer))
            or self.max_projection_sweeps < 1
        ):
            raise ValueError("max_projection_sweeps must be a positive integer.")


@dataclass(frozen=True)
class SafetyProjectionResult:
    """One PR5 control projection and its complete finite diagnostics."""

    nominal_control: Array
    projected_control: Array
    applied_control: Array
    constraint_residuals_before: Array
    constraint_residuals_after: Array
    constraint_kinds: Array
    status: str
    feasible: bool
    emergency_stop: bool
    constraint_count: int
    violated_constraint_count: int
    projection_sweeps: int
    max_residual_before: float
    max_residual_after: float
    control_adjustment_norm: float
    constraint_type_counts: dict[str, int]
    diagnostics: dict[str, object] = field(default_factory=dict)


def _finite_points(values: Array, name: str, *, allow_empty: bool = True) -> Array:
    points = np.asarray(values, dtype=float)
    if points.ndim != 2 or points.shape[1:] != (2,) or not np.all(np.isfinite(points)):
        raise ValueError(f"{name} must be a finite (N, 2) array.")
    if not allow_empty and len(points) == 0:
        raise ValueError(f"{name} must not be empty.")
    return points.copy()


def _fallback_normal(first_id: int, second_id: int) -> Array:
    """Return a deterministic unit direction for coincident constraint points."""
    angle = (first_id * 0.754877666 + second_id * 0.569840291) * 2.0 * np.pi
    return np.array([np.cos(angle), np.sin(angle)], dtype=float)


def _append_reachable_constraint(
    rows: list[Array],
    bounds: list[float],
    kinds: list[str],
    row: Array,
    bound: float,
    reachable_lower_bound: float,
    kind: str,
    tolerance: float,
) -> None:
    """Keep constraints that can become active under the bounded control."""
    if bound > reachable_lower_bound - tolerance:
        rows.append(row)
        bounds.append(float(bound))
        kinds.append(kind)


def _build_velocity_halfspaces(
    positions: Array,
    crowd_points: Array,
    room_size: Array,
    dt: float,
    v_max: float,
    config: VelocitySafetyConfig,
) -> tuple[Array, Array, Array, dict[str, int]]:
    guide_count = len(positions)
    dimension = 2 * guide_count
    rows: list[Array] = []
    bounds: list[float] = []
    kinds: list[str] = []
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
                normal = delta / distance if distance > tol else _fallback_normal(i, j)
                row = np.zeros(dimension, dtype=float)
                row[2 * i : 2 * i + 2] = normal
                row[2 * j : 2 * j + 2] = -normal
                bound = (config.min_guide_distance + numerical_distance_buffer - distance) / dt
                _append_reachable_constraint(
                    rows,
                    bounds,
                    kinds,
                    row,
                    bound,
                    -2.0 * v_max,
                    "guide_pair",
                    tol,
                )

    if config.min_crowd_distance > 0.0 and len(crowd_points):
        for guide_id, position in enumerate(positions):
            for crowd_id, crowd_point in enumerate(crowd_points):
                delta = position - crowd_point
                distance = float(np.linalg.norm(delta))
                normal = (
                    delta / distance
                    if distance > tol
                    else _fallback_normal(guide_id, guide_count + crowd_id)
                )
                row = np.zeros(dimension, dtype=float)
                row[2 * guide_id : 2 * guide_id + 2] = normal
                bound = (config.min_crowd_distance + numerical_distance_buffer - distance) / dt
                _append_reachable_constraint(
                    rows,
                    bounds,
                    kinds,
                    row,
                    bound,
                    -v_max,
                    "crowd",
                    tol,
                )

    lower = np.full(2, config.room_margin + numerical_distance_buffer, dtype=float)
    upper = room_size - config.room_margin - numerical_distance_buffer
    for guide_id, position in enumerate(positions):
        for axis in range(2):
            row_lower = np.zeros(dimension, dtype=float)
            row_lower[2 * guide_id + axis] = 1.0
            lower_bound = (lower[axis] - position[axis]) / dt
            _append_reachable_constraint(
                rows,
                bounds,
                kinds,
                row_lower,
                lower_bound,
                -v_max,
                "room",
                tol,
            )

            row_upper = np.zeros(dimension, dtype=float)
            row_upper[2 * guide_id + axis] = -1.0
            upper_bound = (position[axis] - upper[axis]) / dt
            _append_reachable_constraint(
                rows,
                bounds,
                kinds,
                row_upper,
                upper_bound,
                -v_max,
                "room",
                tol,
            )

    matrix = np.asarray(rows, dtype=float).reshape((-1, dimension))
    vector = np.asarray(bounds, dtype=float)
    kind_array = np.asarray(kinds, dtype="U16")
    counts = {
        kind: int(np.count_nonzero(kind_array == kind))
        for kind in ("guide_pair", "crowd", "room")
    }
    return matrix, vector, kind_array, counts


def _halfspace_residuals(matrix: Array, bounds: Array, vector: Array) -> Array:
    return bounds - matrix @ vector if len(bounds) else np.empty(0, dtype=float)


def _speed_residual(vector: Array, guide_count: int, v_max: float) -> float:
    controls = vector.reshape((guide_count, 2))
    return max(0.0, float(np.max(np.linalg.norm(controls, axis=1)) - v_max)) if guide_count else 0.0


def _max_positive(values: Array) -> float:
    return max(0.0, float(np.max(values))) if len(values) else 0.0


def project_velocity_safety(
    positions: Array,
    nominal_control: Array,
    crowd_points: Array,
    room_size: Array,
    dt: float,
    v_max: float,
    config: VelocitySafetyConfig,
) -> SafetyProjectionResult:
    """Project nominal controls onto ordered PR5 sampled-data constraints.

    Each retained half-space is sufficient for its corresponding one-step
    distance or room-margin condition.  Constraints that cannot become active
    under the speed limit are omitted and counted as unreachable.  Dykstra's
    ordered projections include one speed ball per guide.  Failure to meet the
    residual tolerance returns a finite zero-velocity emergency stop.
    """
    if not isinstance(config, VelocitySafetyConfig):
        raise TypeError("config must be VelocitySafetyConfig.")
    current = _finite_points(positions, "positions", allow_empty=False)
    nominal = _finite_points(nominal_control, "nominal_control", allow_empty=False)
    crowd = _finite_points(crowd_points, "crowd_points")
    room = np.asarray(room_size, dtype=float)
    step = float(dt)
    speed_limit = float(v_max)
    if nominal.shape != current.shape:
        raise ValueError("nominal_control must match positions.")
    if room.shape != (2,) or not np.all(np.isfinite(room)) or np.any(room <= 0.0):
        raise ValueError("room_size must be a finite positive length-2 vector.")
    if np.any(room <= 2.0 * config.room_margin):
        raise ValueError("room_size must exceed twice room_margin on each axis.")
    if not np.isfinite(step) or step <= 0.0 or not np.isfinite(speed_limit) or speed_limit <= 0.0:
        raise ValueError("dt and v_max must be finite and positive.")

    matrix, bounds, kinds, type_counts = _build_velocity_halfspaces(
        current,
        crowd,
        room,
        step,
        speed_limit,
        config,
    )
    flat_nominal = nominal.reshape(-1)
    residuals_before = _halfspace_residuals(matrix, bounds, flat_nominal)
    max_before = max(_max_positive(residuals_before), _speed_residual(flat_nominal, len(current), speed_limit))
    violated = int(np.count_nonzero(residuals_before > config.residual_tolerance))
    violated += int(
        np.count_nonzero(np.linalg.norm(nominal, axis=1) > speed_limit + config.residual_tolerance)
    )

    if not config.enabled or max_before <= config.residual_tolerance:
        status = "DISABLED" if not config.enabled else "VALID"
        return SafetyProjectionResult(
            nominal_control=nominal,
            projected_control=nominal.copy(),
            applied_control=nominal.copy(),
            constraint_residuals_before=residuals_before,
            constraint_residuals_after=residuals_before.copy(),
            constraint_kinds=kinds,
            status=status,
            feasible=True,
            emergency_stop=False,
            constraint_count=int(len(bounds)),
            violated_constraint_count=violated,
            projection_sweeps=0,
            max_residual_before=max_before,
            max_residual_after=max_before,
            control_adjustment_norm=0.0,
            constraint_type_counts=type_counts,
            diagnostics={
                "projection": "ordered_halfspaces_plus_speed_balls_dykstra",
                "numerical_distance_buffer": max(
                    10.0 * step * config.residual_tolerance,
                    64.0 * np.finfo(float).eps * max(1.0, float(np.max(room))),
                ),
                "config": asdict(config),
            },
        )

    guide_count = len(current)
    dimension = len(flat_nominal)
    set_count = len(bounds) + guide_count
    corrections = np.zeros((set_count, dimension), dtype=float)
    projected = flat_nominal.copy()
    sweeps = 0
    feasible = False
    candidate_max_residual = max_before
    for sweep in range(1, config.max_projection_sweeps + 1):
        sweeps = sweep
        for constraint_id, (row, bound) in enumerate(zip(matrix, bounds, strict=True)):
            shifted = projected + corrections[constraint_id]
            residual = float(bound - row @ shifted)
            if residual > 0.0:
                denominator = float(row @ row)
                updated = shifted + (residual / denominator) * row
            else:
                updated = shifted
            corrections[constraint_id] = shifted - updated
            projected = updated

        for guide_id in range(guide_count):
            set_id = len(bounds) + guide_id
            shifted = projected + corrections[set_id]
            block = shifted[2 * guide_id : 2 * guide_id + 2]
            speed = float(np.linalg.norm(block))
            updated = shifted.copy()
            if speed > speed_limit:
                updated[2 * guide_id : 2 * guide_id + 2] = block * (
                    np.nextafter(speed_limit, 0.0) / speed
                )
            corrections[set_id] = shifted - updated
            projected = updated

        residuals_candidate = _halfspace_residuals(matrix, bounds, projected)
        candidate_max_residual = max(
            _max_positive(residuals_candidate),
            _speed_residual(projected, guide_count, speed_limit),
        )
        if candidate_max_residual <= config.residual_tolerance:
            feasible = True
            break

    projected_control = projected.reshape(current.shape)
    if feasible:
        applied = projected_control.copy()
        status = "PROJECTED"
        emergency_stop = False
    else:
        applied = np.zeros_like(nominal)
        status = "SAFETY_INFEASIBLE"
        emergency_stop = True

    residuals_after = _halfspace_residuals(matrix, bounds, applied.reshape(-1))
    max_after = max(
        _max_positive(residuals_after),
        _speed_residual(applied.reshape(-1), guide_count, speed_limit),
    )
    return SafetyProjectionResult(
        nominal_control=nominal,
        projected_control=projected_control,
        applied_control=applied,
        constraint_residuals_before=residuals_before,
        constraint_residuals_after=residuals_after,
        constraint_kinds=kinds,
        status=status,
        feasible=feasible,
        emergency_stop=emergency_stop,
        constraint_count=int(len(bounds)),
        violated_constraint_count=violated,
        projection_sweeps=sweeps,
        max_residual_before=max_before,
        max_residual_after=max_after,
        control_adjustment_norm=float(np.linalg.norm(applied - nominal)),
        constraint_type_counts=type_counts,
        diagnostics={
            "projection": "ordered_halfspaces_plus_speed_balls_dykstra",
            "numerical_distance_buffer": max(
                10.0 * step * config.residual_tolerance,
                64.0 * np.finfo(float).eps * max(1.0, float(np.max(room))),
            ),
            "candidate_max_residual": float(candidate_max_residual),
            "emergency_action": "zero_velocity" if emergency_stop else "none",
            "config": asdict(config),
        },
    )


def enforce_minimum_separation(points: Array, min_distance: float, iterations: int = 8) -> Array:
    """Push guide points apart when they are closer than min_distance."""
    out = np.asarray(points, dtype=float).copy()
    for _ in range(max(0, int(iterations))):
        for i in range(len(out)):
            for j in range(i + 1, len(out)):
                delta = out[i] - out[j]
                dist = float(np.linalg.norm(delta))
                if dist >= min_distance or dist < 1e-9:
                    continue
                direction = unit(delta, fallback=np.array([1.0, 0.0]))
                shift = 0.5 * (min_distance - dist) * direction
                out[i] += shift
                out[j] -= shift
    return out


def clip_to_room(points: Array, room_size: Array, margin: float = 0.25) -> Array:
    room = np.asarray(room_size, dtype=float)
    return np.clip(np.asarray(points, dtype=float), margin, room - margin)


def enforce_distance_from_cloud(points: Array, cloud: Array, center: Array, min_distance: float, iterations: int = 12) -> Array:
    """Push guide points outward until they clear the observed crowd cloud."""
    out = np.asarray(points, dtype=float).copy()
    cloud_arr = np.asarray(cloud, dtype=float)
    center_arr = np.asarray(center, dtype=float)
    for _ in range(max(0, int(iterations))):
        changed = False
        for i, point in enumerate(out):
            dist = np.linalg.norm(cloud_arr - point, axis=1)
            nearest = float(dist.min()) if len(dist) else float("inf")
            if nearest >= min_distance:
                continue
            direction = unit(point - center_arr, fallback=point - cloud_arr[int(np.argmin(dist))])
            out[i] = point + direction * (min_distance - nearest + 1e-3)
            changed = True
        if not changed:
            break
    return out
