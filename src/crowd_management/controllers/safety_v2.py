"""Proof-strengthened sampled-data velocity projection for ABCG-v2.1.

Both numerical backends solve the same strongly convex projection with linear
half-spaces and one Euclidean speed ball per guide.  The speed balls make this
a convex QCQP (and an SOCP-representable projection), not a pure linear QP.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from time import perf_counter

import numpy as np
from scipy.optimize import LinearConstraint, NonlinearConstraint, minimize, nnls

from ..types import Array
from .safety import VelocitySafetyConfig, _build_velocity_halfspaces


@dataclass(frozen=True)
class VelocityProjectionConfig:
    """Solver, residual, and ZOH certificate controls."""

    backend: str = "dykstra"
    primal_tolerance: float = 1.0e-8
    kkt_tolerance: float = 2.0e-6
    active_tolerance: float = 2.0e-5
    iterate_tolerance: float = 1.0e-10
    max_iterations: int = 600
    slsqp_ftol: float = 1.0e-11
    state_tolerance: float = 1.0e-9
    zoh_samples: int = 21
    zoh_tolerance: float = 1.0e-9
    reject_unsafe_initial_state: bool = True
    enable_zoh_check: bool = True

    def __post_init__(self) -> None:
        if self.backend not in {"dykstra", "slsqp_convex_qcqp"}:
            raise ValueError("backend must be 'dykstra' or 'slsqp_convex_qcqp'.")
        for name in (
            "primal_tolerance",
            "kkt_tolerance",
            "active_tolerance",
            "iterate_tolerance",
            "slsqp_ftol",
            "state_tolerance",
            "zoh_tolerance",
        ):
            value = float(getattr(self, name))
            if not np.isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be finite and non-negative.")
        if (
            isinstance(self.max_iterations, bool)
            or not isinstance(self.max_iterations, (int, np.integer))
            or self.max_iterations < 1
        ):
            raise ValueError("max_iterations must be a positive integer.")
        if (
            isinstance(self.zoh_samples, bool)
            or not isinstance(self.zoh_samples, (int, np.integer))
            or self.zoh_samples < 2
        ):
            raise ValueError("zoh_samples must be an integer of at least two.")


@dataclass(frozen=True)
class VelocityProjectionProblem:
    """One immutable projection problem consumed by every backend."""

    u_nom: Array
    A: Array
    b: Array
    kinds: Array
    guide_count: int
    vmax: float
    positions: Array
    crowd_points: Array
    room_size: Array
    dt: float
    min_guide_distance: float
    min_crowd_distance: float
    room_margin: float
    numerical_distance_buffer: float
    initial_state_status: str
    initial_minimum_clearance: float
    context: dict[str, object]
    sha256: str


@dataclass(frozen=True)
class ProjectionResidualCertificate:
    halfspace_residuals: Array
    speed_residuals: Array
    multipliers: Array
    active_constraint_kinds: tuple[str, ...]
    primal_residual: float
    stationarity_residual: float
    complementarity_residual: float
    dual_residual: float
    kkt_residual: float

    def to_dict(self) -> dict[str, object]:
        return {
            "halfspace_residuals": self.halfspace_residuals.tolist(),
            "speed_residuals": self.speed_residuals.tolist(),
            "multipliers": self.multipliers.tolist(),
            "active_constraint_kinds": list(self.active_constraint_kinds),
            "primal_residual": self.primal_residual,
            "stationarity_residual": self.stationarity_residual,
            "complementarity_residual": self.complementarity_residual,
            "dual_residual": self.dual_residual,
            "kkt_residual": self.kkt_residual,
        }


@dataclass(frozen=True)
class ZOHDenseCheckCertificate:
    checked_times: Array
    safe: bool
    minimum_clearance: float
    minimum_guide_clearance: float | None
    minimum_crowd_clearance: float | None
    minimum_room_clearance: float
    minimum_speed_margin: float
    worst_kind: str
    worst_time: float
    worst_indices: tuple[int, ...]
    diagnostics: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "checked_times": self.checked_times.tolist(),
            "safe": self.safe,
            "minimum_clearance": self.minimum_clearance,
            "minimum_guide_clearance": self.minimum_guide_clearance,
            "minimum_crowd_clearance": self.minimum_crowd_clearance,
            "minimum_room_clearance": self.minimum_room_clearance,
            "minimum_speed_margin": self.minimum_speed_margin,
            "worst_kind": self.worst_kind,
            "worst_time": self.worst_time,
            "worst_indices": list(self.worst_indices),
            "diagnostics": self.diagnostics,
        }


@dataclass(frozen=True)
class VelocityProjectionCertificate:
    schema: str
    problem_sha256: str
    backend: str
    problem_class: str
    status: str
    solver_success: bool
    solver_message: str
    iterations: int
    runtime_ms: float
    objective: float
    control_adjustment_norm: float
    feasible: bool
    residuals: ProjectionResidualCertificate
    zoh: ZOHDenseCheckCertificate | None
    limitations: tuple[str, ...]
    diagnostics: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "problem_sha256": self.problem_sha256,
            "backend": self.backend,
            "problem_class": self.problem_class,
            "status": self.status,
            "solver_success": self.solver_success,
            "solver_message": self.solver_message,
            "iterations": self.iterations,
            "runtime_ms": self.runtime_ms,
            "objective": self.objective,
            "control_adjustment_norm": self.control_adjustment_norm,
            "feasible": self.feasible,
            "residuals": self.residuals.to_dict(),
            "zoh": None if self.zoh is None else self.zoh.to_dict(),
            "limitations": list(self.limitations),
            "diagnostics": self.diagnostics,
        }


@dataclass(frozen=True)
class VelocitySafetyV2Result:
    nominal_control: Array
    candidate_control: Array
    applied_control: Array
    status: str
    feasible: bool
    emergency_stop: bool
    certificate: VelocityProjectionCertificate


@dataclass(frozen=True)
class _BackendResult:
    vector: Array
    success: bool
    message: str
    iterations: int
    runtime_ms: float
    residuals: ProjectionResidualCertificate


_LIMITATIONS = (
    "not_human_safety_certification",
    "not_unconditional_continuous_time_safety_proof",
    "not_a_pure_linear_qp_speed_balls_make_convex_qcqp_socp_representable",
    "zoh_check_is_limited_to_static_points_and_first_order_zoh_motion",
)


def _immutable(values: Array, dtype: object = float) -> Array:
    array = np.asarray(values, dtype=dtype).copy()
    array.setflags(write=False)
    return array


def _points(values: Array, name: str, *, empty: bool = True) -> Array:
    array = np.asarray(values, dtype=float)
    if array.ndim != 2 or array.shape[1:] != (2,) or not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must be a finite (N, 2) array.")
    if not empty and len(array) == 0:
        raise ValueError(f"{name} must not be empty.")
    return array.copy()


def _initial_clearances(
    positions: Array,
    crowd: Array,
    room: Array,
    safety: VelocitySafetyConfig,
) -> tuple[float, str, tuple[int, ...], dict[str, float | None]]:
    candidates: list[tuple[float, str, tuple[int, ...]]] = []
    guide_min: float | None = None
    if safety.min_guide_distance > 0.0 and len(positions) >= 2:
        for first in range(len(positions)):
            for second in range(first + 1, len(positions)):
                clearance = float(
                    np.linalg.norm(positions[first] - positions[second])
                    - safety.min_guide_distance
                )
                candidates.append((clearance, "guide_pair", (first, second)))
                guide_min = clearance if guide_min is None else min(guide_min, clearance)
    crowd_min: float | None = None
    if safety.min_crowd_distance > 0.0 and len(crowd):
        for guide_id, position in enumerate(positions):
            distances = np.linalg.norm(crowd - position, axis=1) - safety.min_crowd_distance
            crowd_id = int(np.argmin(distances))
            clearance = float(distances[crowd_id])
            candidates.append((clearance, "crowd", (guide_id, crowd_id)))
            crowd_min = clearance if crowd_min is None else min(crowd_min, clearance)
    room_values = np.column_stack(
        (
            positions[:, 0] - safety.room_margin,
            room[0] - safety.room_margin - positions[:, 0],
            positions[:, 1] - safety.room_margin,
            room[1] - safety.room_margin - positions[:, 1],
        )
    )
    room_flat = int(np.argmin(room_values))
    guide_id, side = np.unravel_index(room_flat, room_values.shape)
    room_min = float(room_values[guide_id, side])
    candidates.append((room_min, "room", (int(guide_id), int(side))))
    worst = min(candidates, key=lambda item: (item[0], item[1], item[2]))
    return worst[0], worst[1], worst[2], {
        "guide_pair": guide_min,
        "crowd": crowd_min,
        "room": room_min,
    }


def build_velocity_projection_problem(
    positions: Array,
    nominal_control: Array,
    crowd_points: Array,
    room_size: Array,
    dt: float,
    vmax: float,
    safety_config: VelocitySafetyConfig,
    *,
    state_tolerance: float = 1.0e-9,
) -> VelocityProjectionProblem:
    """Build the single immutable QCQP/SOCP-representable projection contract."""

    if not isinstance(safety_config, VelocitySafetyConfig):
        raise TypeError("safety_config must be VelocitySafetyConfig.")
    current = _points(positions, "positions", empty=False)
    nominal = _points(nominal_control, "nominal_control", empty=False)
    crowd = _points(crowd_points, "crowd_points")
    room = np.asarray(room_size, dtype=float)
    step = float(dt)
    speed = float(vmax)
    if nominal.shape != current.shape:
        raise ValueError("nominal_control must match positions.")
    if room.shape != (2,) or not np.all(np.isfinite(room)) or np.any(room <= 0.0):
        raise ValueError("room_size must be a finite positive length-2 vector.")
    if np.any(room <= 2.0 * safety_config.room_margin):
        raise ValueError("room_size must exceed twice room_margin on each axis.")
    if not np.isfinite(step) or step <= 0.0 or not np.isfinite(speed) or speed <= 0.0:
        raise ValueError("dt and vmax must be finite and positive.")
    if not np.isfinite(state_tolerance) or state_tolerance < 0.0:
        raise ValueError("state_tolerance must be finite and non-negative.")

    matrix, bounds, kinds, counts = _build_velocity_halfspaces(
        current,
        crowd,
        room,
        step,
        speed,
        safety_config,
    )
    numerical_buffer = max(
        10.0 * step * safety_config.residual_tolerance,
        64.0 * np.finfo(float).eps * max(1.0, float(np.max(room))),
    )
    initial_clearance, worst_kind, worst_indices, clearances = _initial_clearances(
        current,
        crowd,
        room,
        safety_config,
    )
    initial_status = (
        "INITIAL_STATE_UNSAFE"
        if initial_clearance < -float(state_tolerance)
        else "INITIAL_STATE_SAFE"
    )
    u_nom = nominal.reshape(-1)
    context: dict[str, object] = {
        "constraint_type_counts": counts,
        "initial_worst_kind": worst_kind,
        "initial_worst_indices": list(worst_indices),
        "initial_clearance_by_kind": clearances,
        "physical_model": "static_points_first_order_velocity_zoh",
    }
    digest = hashlib.sha256()
    for array in (u_nom, matrix, bounds, current, crowd, room):
        digest.update(np.asarray(array, dtype="<f8").tobytes(order="C"))
    digest.update(np.asarray(kinds, dtype="U16").tobytes(order="C"))
    digest.update(
        json.dumps(
            {
                "dt": step,
                "vmax": speed,
                "min_guide_distance": safety_config.min_guide_distance,
                "min_crowd_distance": safety_config.min_crowd_distance,
                "room_margin": safety_config.room_margin,
                "numerical_distance_buffer": numerical_buffer,
            },
            sort_keys=True,
        ).encode("utf-8")
    )
    return VelocityProjectionProblem(
        u_nom=_immutable(u_nom),
        A=_immutable(matrix),
        b=_immutable(bounds),
        kinds=_immutable(kinds, dtype="U16"),
        guide_count=len(current),
        vmax=speed,
        positions=_immutable(current),
        crowd_points=_immutable(crowd),
        room_size=_immutable(room),
        dt=step,
        min_guide_distance=float(safety_config.min_guide_distance),
        min_crowd_distance=float(safety_config.min_crowd_distance),
        room_margin=float(safety_config.room_margin),
        numerical_distance_buffer=float(numerical_buffer),
        initial_state_status=initial_status,
        initial_minimum_clearance=float(initial_clearance),
        context=context,
        sha256=digest.hexdigest(),
    )


def projection_residual_certificate(
    problem: VelocityProjectionProblem,
    vector: Array,
    *,
    active_tolerance: float = 2.0e-5,
) -> ProjectionResidualCertificate:
    """Compute primal and independently reconstructed KKT residuals."""

    control = np.asarray(vector, dtype=float)
    if control.shape != problem.u_nom.shape or not np.all(np.isfinite(control)):
        raise ValueError("vector must be finite and match problem.u_nom.")
    halfspace = problem.b - problem.A @ control
    blocks = control.reshape((problem.guide_count, 2))
    speeds = np.linalg.norm(blocks, axis=1)
    speed_residuals = speeds - problem.vmax
    primal = max(
        0.0,
        float(np.max(halfspace)) if len(halfspace) else 0.0,
        float(np.max(speed_residuals)) if len(speed_residuals) else 0.0,
    )
    values: list[float] = []
    gradients: list[Array] = []
    active_kinds: list[str] = []
    for row, value, kind in zip(problem.A, halfspace, problem.kinds, strict=True):
        if value >= -active_tolerance:
            values.append(float(value))
            gradients.append(-np.asarray(row, dtype=float))
            active_kinds.append(str(kind))
    for guide_id, (speed, value) in enumerate(zip(speeds, speed_residuals, strict=True)):
        if value >= -active_tolerance:
            gradient = np.zeros_like(control)
            if speed > 1.0e-15:
                gradient[2 * guide_id : 2 * guide_id + 2] = blocks[guide_id] / speed
            gradients.append(gradient)
            values.append(float(value))
            active_kinds.append("speed_ball")
    objective_gradient = control - problem.u_nom
    if gradients:
        jacobian = np.asarray(gradients, dtype=float)
        multipliers, _ = nnls(jacobian.T, -objective_gradient)
        stationarity_vector = objective_gradient + jacobian.T @ multipliers
        complementarity = float(
            np.max(np.abs(multipliers * np.asarray(values, dtype=float)))
        )
    else:
        multipliers = np.empty(0, dtype=float)
        stationarity_vector = objective_gradient
        complementarity = 0.0
    stationarity = float(np.linalg.norm(stationarity_vector, ord=np.inf))
    dual = max(0.0, float(-np.min(multipliers))) if len(multipliers) else 0.0
    return ProjectionResidualCertificate(
        halfspace_residuals=halfspace,
        speed_residuals=speed_residuals,
        multipliers=multipliers,
        active_constraint_kinds=tuple(active_kinds),
        primal_residual=primal,
        stationarity_residual=stationarity,
        complementarity_residual=complementarity,
        dual_residual=dual,
        kkt_residual=max(stationarity, complementarity, dual),
    )


def _single_constraint_infeasible(
    problem: VelocityProjectionProblem,
    tolerance: float,
) -> tuple[bool, dict[str, object]]:
    for constraint_id, (row, bound, kind) in enumerate(
        zip(problem.A, problem.b, problem.kinds, strict=True)
    ):
        blocks = np.asarray(row, dtype=float).reshape((problem.guide_count, 2))
        support = problem.vmax * float(np.sum(np.linalg.norm(blocks, axis=1)))
        if float(bound) > support + tolerance:
            return True, {
                "reason": "single_halfspace_exceeds_product_speed_ball_support",
                "constraint_id": constraint_id,
                "constraint_kind": str(kind),
                "required_bound": float(bound),
                "maximum_support": support,
            }
    return False, {}


def _project_ball(vector: Array, guide_id: int, vmax: float) -> Array:
    result = vector.copy()
    block = result[2 * guide_id : 2 * guide_id + 2]
    speed = float(np.linalg.norm(block))
    if speed > vmax:
        result[2 * guide_id : 2 * guide_id + 2] = block * (vmax / speed)
    return result


def _solve_dykstra(
    problem: VelocityProjectionProblem,
    config: VelocityProjectionConfig,
) -> _BackendResult:
    start = perf_counter()
    dimension = len(problem.u_nom)
    set_count = len(problem.b) + problem.guide_count
    corrections = np.zeros((set_count, dimension), dtype=float)
    vector = problem.u_nom.copy()
    residuals = projection_residual_certificate(
        problem,
        vector,
        active_tolerance=config.active_tolerance,
    )
    success = False
    message = "maximum_iterations_reached"
    iterations = 0
    for iteration in range(1, config.max_iterations + 1):
        iterations = iteration
        previous = vector.copy()
        for constraint_id, (row, bound) in enumerate(zip(problem.A, problem.b, strict=True)):
            shifted = vector + corrections[constraint_id]
            violation = float(bound - row @ shifted)
            if violation > 0.0:
                denominator = float(row @ row)
                updated = shifted + violation * row / denominator
            else:
                updated = shifted
            corrections[constraint_id] = shifted - updated
            vector = updated
        for guide_id in range(problem.guide_count):
            set_id = len(problem.b) + guide_id
            shifted = vector + corrections[set_id]
            updated = _project_ball(shifted, guide_id, problem.vmax)
            corrections[set_id] = shifted - updated
            vector = updated
        residuals = projection_residual_certificate(
            problem,
            vector,
            active_tolerance=config.active_tolerance,
        )
        iterate_change = float(np.linalg.norm(vector - previous, ord=np.inf))
        if (
            residuals.primal_residual <= config.primal_tolerance
            and residuals.kkt_residual <= config.kkt_tolerance
            and iterate_change <= config.iterate_tolerance
        ):
            success = True
            message = "primal_kkt_and_iterate_converged"
            break
    return _BackendResult(
        vector=vector,
        success=success,
        message=message,
        iterations=iterations,
        runtime_ms=1000.0 * (perf_counter() - start),
        residuals=residuals,
    )


def _speed_squared_margin(problem: VelocityProjectionProblem, vector: Array) -> Array:
    blocks = np.asarray(vector, dtype=float).reshape((problem.guide_count, 2))
    return problem.vmax**2 - np.sum(blocks * blocks, axis=1)


def _speed_squared_jacobian(problem: VelocityProjectionProblem, vector: Array) -> Array:
    blocks = np.asarray(vector, dtype=float).reshape((problem.guide_count, 2))
    jacobian = np.zeros((problem.guide_count, len(problem.u_nom)), dtype=float)
    for guide_id, block in enumerate(blocks):
        jacobian[guide_id, 2 * guide_id : 2 * guide_id + 2] = -2.0 * block
    return jacobian


def _solve_slsqp(
    problem: VelocityProjectionProblem,
    config: VelocityProjectionConfig,
) -> _BackendResult:
    start = perf_counter()
    initial = problem.u_nom.copy()
    for guide_id in range(problem.guide_count):
        initial = _project_ball(initial, guide_id, problem.vmax)
    constraints: list[object] = []
    if len(problem.b):
        constraints.append(LinearConstraint(problem.A, problem.b, np.inf))
    constraints.append(
        NonlinearConstraint(
            lambda vector: _speed_squared_margin(problem, vector),
            0.0,
            np.inf,
            jac=lambda vector: _speed_squared_jacobian(problem, vector),
        )
    )
    result = minimize(
        lambda vector: 0.5 * float(np.sum((vector - problem.u_nom) ** 2)),
        initial,
        jac=lambda vector: vector - problem.u_nom,
        constraints=constraints,
        method="SLSQP",
        options={
            "maxiter": int(config.max_iterations),
            "ftol": float(config.slsqp_ftol),
            "disp": False,
        },
    )
    vector = np.asarray(result.x, dtype=float)
    residuals = projection_residual_certificate(
        problem,
        vector,
        active_tolerance=config.active_tolerance,
    )
    certified = bool(
        result.success
        and np.all(np.isfinite(vector))
        and residuals.primal_residual <= config.primal_tolerance
        and residuals.kkt_residual <= config.kkt_tolerance
    )
    return _BackendResult(
        vector=vector,
        success=certified,
        message=str(result.message),
        iterations=int(getattr(result, "nit", 0)),
        runtime_ms=1000.0 * (perf_counter() - start),
        residuals=residuals,
    )


def solve_velocity_projection(
    problem: VelocityProjectionProblem,
    config: VelocityProjectionConfig,
) -> _BackendResult:
    """Solve one shared problem without changing its constraints by backend."""

    if not isinstance(problem, VelocityProjectionProblem):
        raise TypeError("problem must be VelocityProjectionProblem.")
    if not isinstance(config, VelocityProjectionConfig):
        raise TypeError("config must be VelocityProjectionConfig.")
    return (
        _solve_dykstra(problem, config)
        if config.backend == "dykstra"
        else _solve_slsqp(problem, config)
    )


def _critical_time(relative_position: Array, relative_velocity: Array, dt: float) -> float | None:
    denominator = float(relative_velocity @ relative_velocity)
    if denominator <= 1.0e-18:
        return None
    return float(np.clip(-(relative_position @ relative_velocity) / denominator, 0.0, dt))


def zoh_dense_check(
    problem: VelocityProjectionProblem,
    control: Array,
    *,
    sample_count: int = 21,
    tolerance: float = 1.0e-9,
) -> ZOHDenseCheckCertificate:
    """Check ZOH motion on a dense grid plus pairwise distance critical times."""

    vector = np.asarray(control, dtype=float)
    if vector.shape == problem.u_nom.shape:
        velocities = vector.reshape((problem.guide_count, 2))
    elif vector.shape == problem.positions.shape:
        velocities = vector.copy()
    else:
        raise ValueError("control must match the flat or (M, 2) problem shape.")
    if not np.all(np.isfinite(velocities)):
        raise ValueError("control must be finite.")
    if isinstance(sample_count, bool) or int(sample_count) != sample_count or sample_count < 2:
        raise ValueError("sample_count must be an integer of at least two.")
    times = list(np.linspace(0.0, problem.dt, int(sample_count)))
    for first in range(problem.guide_count):
        for second in range(first + 1, problem.guide_count):
            critical = _critical_time(
                problem.positions[first] - problem.positions[second],
                velocities[first] - velocities[second],
                problem.dt,
            )
            if critical is not None:
                times.append(critical)
    for guide_id, position in enumerate(problem.positions):
        for crowd_point in problem.crowd_points:
            critical = _critical_time(position - crowd_point, velocities[guide_id], problem.dt)
            if critical is not None:
                times.append(critical)
    checked_times = np.unique(np.asarray(times, dtype=float))

    guide_min: float | None = None
    crowd_min: float | None = None
    room_min = float("inf")
    worst = (float("inf"), "room", 0.0, ())
    for time in checked_times:
        positions = problem.positions + float(time) * velocities
        if problem.min_guide_distance > 0.0:
            for first in range(problem.guide_count):
                for second in range(first + 1, problem.guide_count):
                    clearance = float(
                        np.linalg.norm(positions[first] - positions[second])
                        - problem.min_guide_distance
                    )
                    guide_min = clearance if guide_min is None else min(guide_min, clearance)
                    candidate = (clearance, "guide_pair", float(time), (first, second))
                    if candidate < worst:
                        worst = candidate
        if problem.min_crowd_distance > 0.0 and len(problem.crowd_points):
            for guide_id, position in enumerate(positions):
                distances = np.linalg.norm(problem.crowd_points - position, axis=1)
                crowd_id = int(np.argmin(distances))
                clearance = float(distances[crowd_id] - problem.min_crowd_distance)
                crowd_min = clearance if crowd_min is None else min(crowd_min, clearance)
                candidate = (clearance, "crowd", float(time), (guide_id, crowd_id))
                if candidate < worst:
                    worst = candidate
        room_values = np.column_stack(
            (
                positions[:, 0] - problem.room_margin,
                problem.room_size[0] - problem.room_margin - positions[:, 0],
                positions[:, 1] - problem.room_margin,
                problem.room_size[1] - problem.room_margin - positions[:, 1],
            )
        )
        flat = int(np.argmin(room_values))
        guide_id, side = np.unravel_index(flat, room_values.shape)
        clearance = float(room_values[guide_id, side])
        room_min = min(room_min, clearance)
        candidate = (clearance, "room", float(time), (int(guide_id), int(side)))
        if candidate < worst:
            worst = candidate
    spatial = [room_min]
    if guide_min is not None:
        spatial.append(guide_min)
    if crowd_min is not None:
        spatial.append(crowd_min)
    minimum = float(min(spatial))
    speed_margin = float(problem.vmax - np.max(np.linalg.norm(velocities, axis=1)))
    safe = bool(min(minimum, speed_margin) >= -float(tolerance))
    return ZOHDenseCheckCertificate(
        checked_times=checked_times,
        safe=safe,
        minimum_clearance=minimum,
        minimum_guide_clearance=guide_min,
        minimum_crowd_clearance=crowd_min,
        minimum_room_clearance=float(room_min),
        minimum_speed_margin=speed_margin,
        worst_kind=worst[1],
        worst_time=worst[2],
        worst_indices=worst[3],
        diagnostics={
            "uniform_sample_count": int(sample_count),
            "critical_times_included": True,
            "model_scope": "static_points_first_order_zoh",
        },
    )


def _certificate(
    problem: VelocityProjectionProblem,
    config: VelocityProjectionConfig,
    status: str,
    candidate: Array,
    residuals: ProjectionResidualCertificate,
    *,
    success: bool,
    message: str,
    iterations: int,
    runtime_ms: float,
    zoh: ZOHDenseCheckCertificate | None,
    diagnostics: dict[str, object] | None = None,
) -> VelocityProjectionCertificate:
    delta = np.asarray(candidate, dtype=float) - problem.u_nom
    return VelocityProjectionCertificate(
        schema="abcg-v2.1-velocity-projection-certificate-v1",
        problem_sha256=problem.sha256,
        backend=config.backend,
        problem_class="strongly_convex_qcqp_socp_representable_projection",
        status=status,
        solver_success=success,
        solver_message=message,
        iterations=int(iterations),
        runtime_ms=float(runtime_ms),
        objective=0.5 * float(delta @ delta),
        control_adjustment_norm=float(np.linalg.norm(delta)),
        feasible=status in {"VALID", "PROJECTED", "DISABLED"},
        residuals=residuals,
        zoh=zoh,
        limitations=_LIMITATIONS,
        diagnostics=diagnostics or {},
    )


def project_velocity_safety_v2(
    positions: Array,
    nominal_control: Array,
    crowd_points: Array,
    room_size: Array,
    dt: float,
    vmax: float,
    safety_config: VelocitySafetyConfig,
    projection_config: VelocityProjectionConfig | None = None,
) -> VelocitySafetyV2Result:
    """Build, solve, residual-check, and ZOH-check one velocity projection."""

    config = projection_config or VelocityProjectionConfig()
    if not isinstance(config, VelocityProjectionConfig):
        raise TypeError("projection_config must be VelocityProjectionConfig.")
    problem = build_velocity_projection_problem(
        positions,
        nominal_control,
        crowd_points,
        room_size,
        dt,
        vmax,
        safety_config,
        state_tolerance=config.state_tolerance,
    )
    nominal_shape = problem.positions.shape
    zero = np.zeros(nominal_shape, dtype=float)
    nominal = problem.u_nom.reshape(nominal_shape).copy()
    nominal_residuals = projection_residual_certificate(
        problem,
        problem.u_nom,
        active_tolerance=config.active_tolerance,
    )

    if not safety_config.enabled:
        certificate = _certificate(
            problem,
            config,
            "DISABLED",
            problem.u_nom,
            nominal_residuals,
            success=True,
            message="safety_layer_disabled",
            iterations=0,
            runtime_ms=0.0,
            zoh=None,
        )
        return VelocitySafetyV2Result(nominal, nominal.copy(), nominal.copy(), "DISABLED", True, False, certificate)
    if config.reject_unsafe_initial_state and problem.initial_state_status == "INITIAL_STATE_UNSAFE":
        certificate = _certificate(
            problem,
            config,
            "INITIAL_STATE_UNSAFE",
            zero.reshape(-1),
            projection_residual_certificate(problem, zero.reshape(-1), active_tolerance=config.active_tolerance),
            success=False,
            message="projection_not_attempted_for_unsafe_initial_state",
            iterations=0,
            runtime_ms=0.0,
            zoh=None,
            diagnostics={
                "initial_minimum_clearance": problem.initial_minimum_clearance,
                "emergency_zero_control_repairs_initial_state": False,
            },
        )
        return VelocitySafetyV2Result(nominal, zero.copy(), zero.copy(), "INITIAL_STATE_UNSAFE", False, True, certificate)

    infeasible, evidence = _single_constraint_infeasible(problem, config.primal_tolerance)
    if infeasible:
        certificate = _certificate(
            problem,
            config,
            "PROJECTION_INFEASIBLE",
            zero.reshape(-1),
            projection_residual_certificate(problem, zero.reshape(-1), active_tolerance=config.active_tolerance),
            success=False,
            message="single_constraint_support_certificate",
            iterations=0,
            runtime_ms=0.0,
            zoh=None,
            diagnostics={**evidence, "emergency_zero_control_repairs_initial_state": False},
        )
        return VelocitySafetyV2Result(nominal, zero.copy(), zero.copy(), "PROJECTION_INFEASIBLE", False, True, certificate)

    if (
        nominal_residuals.primal_residual <= config.primal_tolerance
        and nominal_residuals.kkt_residual <= config.kkt_tolerance
    ):
        zoh = (
            zoh_dense_check(
                problem,
                problem.u_nom,
                sample_count=config.zoh_samples,
                tolerance=config.zoh_tolerance,
            )
            if config.enable_zoh_check
            else None
        )
        status = "VALID" if zoh is None or zoh.safe else "ZOH_DENSE_CHECK_FAILED"
        applied = nominal.copy() if status == "VALID" else zero.copy()
        certificate = _certificate(
            problem,
            config,
            status,
            problem.u_nom,
            nominal_residuals,
            success=status == "VALID",
            message="nominal_control_already_satisfies_projection_problem",
            iterations=0,
            runtime_ms=0.0,
            zoh=zoh,
            diagnostics={"emergency_zero_control_repairs_initial_state": False if status != "VALID" else None},
        )
        return VelocitySafetyV2Result(nominal, nominal.copy(), applied, status, status == "VALID", status != "VALID", certificate)

    backend = solve_velocity_projection(problem, config)
    candidate = backend.vector.reshape(nominal_shape)
    if not backend.success:
        status = "NUMERICAL_RESIDUAL_FAILURE"
        certificate = _certificate(
            problem,
            config,
            status,
            backend.vector,
            backend.residuals,
            success=False,
            message=backend.message,
            iterations=backend.iterations,
            runtime_ms=backend.runtime_ms,
            zoh=None,
            diagnostics={"mathematical_infeasibility_claimed": False},
        )
        return VelocitySafetyV2Result(nominal, candidate, zero.copy(), status, False, True, certificate)

    zoh = (
        zoh_dense_check(
            problem,
            backend.vector,
            sample_count=config.zoh_samples,
            tolerance=config.zoh_tolerance,
        )
        if config.enable_zoh_check
        else None
    )
    status = "PROJECTED" if zoh is None or zoh.safe else "ZOH_DENSE_CHECK_FAILED"
    applied = candidate.copy() if status == "PROJECTED" else zero.copy()
    certificate = _certificate(
        problem,
        config,
        status,
        backend.vector,
        backend.residuals,
        success=status == "PROJECTED",
        message=backend.message,
        iterations=backend.iterations,
        runtime_ms=backend.runtime_ms,
        zoh=zoh,
        diagnostics={
            "mathematical_infeasibility_claimed": False,
            "emergency_zero_control_repairs_initial_state": False if status != "PROJECTED" else None,
        },
    )
    return VelocitySafetyV2Result(nominal, candidate, applied, status, status == "PROJECTED", status != "PROJECTED", certificate)


__all__ = [
    "ProjectionResidualCertificate",
    "VelocityProjectionCertificate",
    "VelocityProjectionConfig",
    "VelocityProjectionProblem",
    "VelocitySafetyV2Result",
    "ZOHDenseCheckCertificate",
    "build_velocity_projection_problem",
    "project_velocity_safety_v2",
    "projection_residual_certificate",
    "solve_velocity_projection",
    "zoh_dense_check",
]
