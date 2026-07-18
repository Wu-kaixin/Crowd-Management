"""PR4 kinematics plus PR5 velocity safety and auditable episode states.

The nominal fixed-target controller is separated from the applied control.  An
optional PR5 filter projects the latter onto sampled-data safety constraints
and records every projection or finite emergency stop.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np

from ..types import Array
from .assignment import AssignmentResult
from .safety import VelocitySafetyConfig, project_velocity_safety


@dataclass(frozen=True)
class ABCGv2Config:
    """PR4 proportional velocity, Euler integration, and stop configuration."""

    dt: float = 0.1
    k_p: float = 1.5
    v_max: float = 1.0
    tracking_rmse_tolerance: float = 0.03
    speed_tolerance: float = 0.03
    hold_steps: int = 10
    max_steps: int = 400
    error_increase_tolerance: float = 1.0e-12

    def __post_init__(self) -> None:
        for name in (
            "dt",
            "k_p",
            "v_max",
            "tracking_rmse_tolerance",
            "speed_tolerance",
        ):
            value = float(getattr(self, name))
            if not np.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and positive.")
        if self.dt * self.k_p > 1.0:
            raise ValueError("dt * k_p must not exceed one for monotone fixed-target integration.")
        for name in ("hold_steps", "max_steps"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or value < 1:
                raise ValueError(f"{name} must be a positive integer.")
        if not np.isfinite(self.error_increase_tolerance) or self.error_increase_tolerance < 0.0:
            raise ValueError("error_increase_tolerance must be finite and non-negative.")


@dataclass(frozen=True)
class EpisodeResult:
    """Complete PR4/PR5 state, control, and safety trace for one episode."""

    times: Array
    positions: Array
    velocities: Array
    nominal_controls: Array
    applied_controls: Array
    state_history: Array
    tracking_rmse: Array
    max_speed_history: Array
    hold_count_history: Array
    target_positions: Array
    guide_to_target: Array
    reserve_guide_ids: Array
    safety_status_history: Array
    safety_constraint_count: Array
    safety_guide_pair_constraint_count: Array
    safety_crowd_constraint_count: Array
    safety_room_constraint_count: Array
    safety_violated_constraint_count: Array
    safety_projection_sweeps: Array
    safety_max_residual_before: Array
    safety_max_residual_after: Array
    safety_max_guide_pair_residual_after: Array
    safety_max_crowd_residual_after: Array
    safety_max_room_residual_after: Array
    safety_control_adjustment_norm: Array
    safety_emergency_stop_history: Array
    status: str
    converged: bool
    stop_reason: str
    diagnostics: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ControlOutput:
    """One feedback-control output for measured guide state.

    Velocity and target arrays use metres and seconds: the two velocity arrays
    have shape ``(M, 2)`` in m/s, ``targets`` has shape ``(K, 2)`` in metres,
    and ``assignment`` has shape ``(M,)`` with ``-1`` denoting reserve guides.
    Failure states return finite zero velocities and explicit events.
    """

    preferred_velocity: Array
    safe_velocity: Array
    targets: Array
    active_ids: tuple[int, ...]
    reserve_ids: tuple[int, ...]
    assignment: Array
    state: str
    events: tuple[str, ...]
    diagnostics: dict[str, object] = field(default_factory=dict)


class ConvergenceStateMachine:
    """PR4 INIT/TRACK/HOLD/CONVERGED/TIMEOUT transition logic."""

    def __init__(self, hold_steps: int) -> None:
        if isinstance(hold_steps, bool) or not isinstance(hold_steps, (int, np.integer)) or hold_steps < 1:
            raise ValueError("hold_steps must be a positive integer.")
        self.hold_steps = int(hold_steps)
        self.state = "INIT"
        self.hold_count = 0

    @property
    def terminal(self) -> bool:
        return self.state in {
            "CONVERGED",
            "DEGRADED",
            "BOUNDARY_INVALID",
            "OFFSET_INVALID",
            "CAPACITY_SHORTFALL",
            "ASSIGNMENT_INFEASIBLE",
            "SAFETY_INFEASIBLE",
            "TIMEOUT",
        }

    def update(self, criteria_met: bool) -> str:
        if self.terminal:
            return self.state
        if criteria_met:
            self.hold_count += 1
            self.state = "CONVERGED" if self.hold_count >= self.hold_steps else "HOLD"
        else:
            self.hold_count = 0
            self.state = "TRACK"
        return self.state

    def stop(self, status: str) -> str:
        self.state = str(status)
        return self.state

    def timeout(self) -> str:
        if self.state != "CONVERGED":
            self.state = "TIMEOUT"
        return self.state


def _points(values: Array, name: str) -> Array:
    array = np.asarray(values, dtype=float)
    if array.ndim != 2 or array.shape[1:] != (2,) or not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must be a finite (N, 2) array.")
    return array.copy()


def nominal_guide_velocity(
    positions: Array,
    assigned_targets: Array,
    active_mask: Array,
    k_p: float,
    v_max: float,
) -> Array:
    """Return per-guide ``sat_vmax(k_p (z_i - p_i))``; reserves receive zero."""
    current = _points(positions, "positions")
    targets = _points(assigned_targets, "assigned_targets")
    active = np.asarray(active_mask, dtype=bool)
    gain = float(k_p)
    speed_limit = float(v_max)
    if targets.shape != current.shape or active.shape != (len(current),):
        raise ValueError("assigned_targets and active_mask must match positions.")
    if not np.isfinite(gain) or gain <= 0.0 or not np.isfinite(speed_limit) or speed_limit <= 0.0:
        raise ValueError("k_p and v_max must be finite and positive.")
    velocity = gain * (targets - current)
    velocity[~active] = 0.0
    speed = np.linalg.norm(velocity, axis=1)
    scale = np.ones(len(velocity), dtype=float)
    moving_fast = speed > speed_limit
    # Scale to the next representable value below the limit so recomputing a
    # vector norm cannot exceed v_max by one floating-point rounding unit.
    strict_limit = np.nextafter(speed_limit, 0.0)
    scale[moving_fast] = strict_limit / speed[moving_fast]
    return velocity * scale[:, None]


def integrate_guide_positions(positions: Array, controls: Array, dt: float) -> Array:
    """Apply one explicit-Euler step of ``p_dot = u`` without hidden clipping."""
    current = _points(positions, "positions")
    applied = _points(controls, "controls")
    step = float(dt)
    if current.shape != applied.shape:
        raise ValueError("controls must match positions.")
    if not np.isfinite(step) or step <= 0.0:
        raise ValueError("dt must be finite and positive.")
    return current + step * applied


def _tracking_rmse(positions: Array, assigned_targets: Array, active_mask: Array) -> float:
    if not np.any(active_mask):
        return 0.0
    squared = np.sum((positions[active_mask] - assigned_targets[active_mask]) ** 2, axis=1)
    return float(np.sqrt(np.mean(squared)))


class ABCGv2Controller:
    """Stateful measured-feedback controller plus fixed-target episode facade."""

    def __init__(
        self,
        config: ABCGv2Config | None = None,
        safety_config: VelocitySafetyConfig | None = None,
    ) -> None:
        self.config = config or ABCGv2Config()
        if not isinstance(self.config, ABCGv2Config):
            raise TypeError("config must be ABCGv2Config.")
        self.safety_config = safety_config or VelocitySafetyConfig(
            enabled=False,
            min_guide_distance=0.0,
            min_crowd_distance=0.0,
            room_margin=0.0,
        )
        if not isinstance(self.safety_config, VelocitySafetyConfig):
            raise TypeError("safety_config must be VelocitySafetyConfig.")
        self._targets: Array | None = None
        self._guide_to_target: Array | None = None
        self._guide_count = 0
        self._room_size: Array | None = None
        self._machine: ConvergenceStateMachine | None = None
        self._previous_tracking_rmse: float | None = None
        self._step_index = 0

    def reset(
        self,
        target_positions: Array,
        assignment: AssignmentResult,
        guide_state: Array,
        room_size: Array | None = None,
        precondition_status: str = "VALID",
    ) -> None:
        """Reset instance state for one fixed-plan feedback episode.

        ``guide_state`` and ``target_positions`` are finite metre-valued
        ``(M, 2)`` and ``(K, 2)`` arrays.  The assignment remains explicit and
        identity preserving; no module-level or process-global state is used.
        """
        guides = _points(guide_state, "guide_state")
        targets = _points(target_positions, "target_positions")
        if not isinstance(assignment, AssignmentResult):
            raise TypeError("assignment must be AssignmentResult.")
        guide_to_target = np.asarray(assignment.guide_to_target, dtype=int)
        if guide_to_target.shape != (len(guides),):
            raise ValueError("assignment.guide_to_target must match guide_state rows.")
        active = guide_to_target >= 0
        if np.any(guide_to_target[active] >= len(targets)):
            raise ValueError("assignment contains an out-of-range target index.")

        room: Array | None = None
        if room_size is not None:
            room = np.asarray(room_size, dtype=float)
            if room.shape != (2,) or not np.all(np.isfinite(room)) or np.any(room <= 0.0):
                raise ValueError("room_size must contain two finite positive dimensions.")

        self._targets = targets
        self._guide_to_target = guide_to_target.copy()
        self._guide_count = len(guides)
        self._room_size = room.copy() if room is not None else None
        self._machine = ConvergenceStateMachine(self.config.hold_steps)
        self._previous_tracking_rmse = None
        self._step_index = 0

        if precondition_status != "VALID":
            allowed = {
                "DEGRADED",
                "BOUNDARY_INVALID",
                "OFFSET_INVALID",
                "CAPACITY_SHORTFALL",
                "ASSIGNMENT_INFEASIBLE",
                "SAFETY_INFEASIBLE",
            }
            self._machine.stop(precondition_status if precondition_status in allowed else "DEGRADED")
        elif assignment.status != "VALID":
            status = "CAPACITY_SHORTFALL" if assignment.status == "CAPACITY_SHORTFALL" else "ASSIGNMENT_INFEASIBLE"
            self._machine.stop(status)
        elif not np.any(active):
            self._machine.stop("DEGRADED")
        elif self.safety_config.enabled and room is None:
            self._machine.stop("SAFETY_INFEASIBLE")

    def step(self, observation: Array, guide_state: Array, dt: float) -> ControlOutput:
        """Return one velocity command from the current measured state.

        ``observation`` is the finite global crowd point set ``(N, 2)`` in
        metres and ``guide_state`` is the measured ``(M, 2)`` guide position
        array. ``dt`` is the positive control period in seconds.  The caller is
        responsible for applying ``safe_velocity`` to the plant and feeding the
        next measured guide state back into this method.
        """
        if self._targets is None or self._guide_to_target is None or self._machine is None:
            raise RuntimeError("reset must be called before step.")
        crowd = _points(observation, "observation")
        guides = _points(guide_state, "guide_state")
        control_dt = float(dt)
        if len(guides) != self._guide_count:
            raise ValueError("guide_state row count changed after reset.")
        if not np.isfinite(control_dt) or control_dt <= 0.0:
            raise ValueError("dt must be finite and positive.")

        mapping = self._guide_to_target
        active_mask = mapping >= 0
        assigned_targets = guides.copy()
        assigned_targets[active_mask] = self._targets[mapping[active_mask]]
        active_ids = tuple(int(item) for item in np.flatnonzero(active_mask))
        reserve_ids = tuple(int(item) for item in np.flatnonzero(~active_mask))
        tracking_rmse = _tracking_rmse(guides, assigned_targets, active_mask)

        if self._machine.terminal:
            zeros = np.zeros_like(guides)
            return ControlOutput(
                preferred_velocity=zeros.copy(),
                safe_velocity=zeros.copy(),
                targets=self._targets.copy(),
                active_ids=active_ids,
                reserve_ids=reserve_ids,
                assignment=mapping.copy(),
                state=self._machine.state,
                events=(f"terminal:{self._machine.state}",),
                diagnostics={
                    "step_index": self._step_index,
                    "dt_seconds": control_dt,
                    "tracking_rmse": tracking_rmse,
                    "measured_guide_state": guides.copy(),
                    "safety_status": "NOT_EVALUATED_TERMINAL",
                },
            )

        nominal = nominal_guide_velocity(
            guides,
            assigned_targets,
            active_mask,
            self.config.k_p,
            self.config.v_max,
        )
        if self.safety_config.enabled:
            assert self._room_size is not None
            safety = project_velocity_safety(
                guides,
                nominal,
                crowd,
                self._room_size,
                control_dt,
                self.config.v_max,
                self.safety_config,
            )
            applied = safety.applied_control
            safety_status = safety.status
            safety_residual = safety.max_residual_after
            safety_emergency = safety.emergency_stop
            safety_diagnostics: dict[str, object] = {
                "safety_constraint_count": safety.constraint_count,
                "safety_violated_constraint_count": safety.violated_constraint_count,
                "safety_projection_sweeps": safety.projection_sweeps,
                "safety_max_residual_before": safety.max_residual_before,
                "safety_max_residual_after": safety.max_residual_after,
                "safety_control_adjustment_norm": safety.control_adjustment_norm,
                "safety_emergency_stop": safety.emergency_stop,
                "safety_constraint_type_counts": dict(safety.constraint_type_counts),
            }
        else:
            applied = nominal.copy()
            safety_status = "DISABLED"
            safety_residual = 0.0
            safety_emergency = False
            safety_diagnostics = {
                "safety_constraint_count": 0,
                "safety_violated_constraint_count": 0,
                "safety_projection_sweeps": 0,
                "safety_max_residual_before": 0.0,
                "safety_max_residual_after": 0.0,
                "safety_control_adjustment_norm": 0.0,
                "safety_emergency_stop": False,
                "safety_constraint_type_counts": {"guide_pair": 0, "crowd": 0, "room": 0},
            }

        state_before = self._machine.state
        max_speed = float(np.max(np.linalg.norm(applied, axis=1))) if len(applied) else 0.0
        if safety_status == "SAFETY_INFEASIBLE":
            state = self._machine.stop("SAFETY_INFEASIBLE")
        elif (
            safety_status != "PROJECTED"
            and self._previous_tracking_rmse is not None
            and tracking_rmse > self._previous_tracking_rmse + self.config.error_increase_tolerance
        ):
            state = self._machine.stop("DEGRADED")
        else:
            criteria_met = (
                tracking_rmse <= self.config.tracking_rmse_tolerance
                and max_speed <= self.config.speed_tolerance
                and (
                    not self.safety_config.enabled
                    or (not safety_emergency and safety_residual <= self.safety_config.residual_tolerance)
                )
            )
            state = self._machine.update(criteria_met)

        if not self._machine.terminal and self._step_index + 1 >= self.config.max_steps:
            state = self._machine.timeout()

        events: list[str] = []
        if state != state_before:
            events.append(f"state:{state_before}->{state}")
        if safety_status == "PROJECTED":
            events.append("safety:PROJECTED")
        elif safety_status == "SAFETY_INFEASIBLE":
            events.append("safety:SAFETY_INFEASIBLE")

        self._previous_tracking_rmse = tracking_rmse
        self._step_index += 1
        return ControlOutput(
            preferred_velocity=nominal,
            safe_velocity=applied,
            targets=self._targets.copy(),
            active_ids=active_ids,
            reserve_ids=reserve_ids,
            assignment=mapping.copy(),
            state=state,
            events=tuple(events),
            diagnostics={
                "step_index": self._step_index - 1,
                "dt_seconds": control_dt,
                "tracking_rmse": tracking_rmse,
                "max_speed": max_speed,
                "hold_count": self._machine.hold_count,
                "measured_guide_state": guides.copy(),
                "assigned_targets": assigned_targets.copy(),
                "safety_status": safety_status,
                **safety_diagnostics,
            },
        )

    def _terminal_episode(
        self,
        positions: Array,
        targets: Array,
        guide_to_target: Array,
        assigned_targets: Array,
        active_mask: Array,
        status: str,
        reason: str,
    ) -> EpisodeResult:
        guide_count = len(positions)
        return EpisodeResult(
            times=np.array([0.0], dtype=float),
            positions=positions[None, :, :],
            velocities=np.zeros((1, guide_count, 2), dtype=float),
            nominal_controls=np.empty((0, guide_count, 2), dtype=float),
            applied_controls=np.empty((0, guide_count, 2), dtype=float),
            state_history=np.array([status]),
            tracking_rmse=np.array([_tracking_rmse(positions, assigned_targets, active_mask)]),
            max_speed_history=np.array([0.0], dtype=float),
            hold_count_history=np.array([0], dtype=int),
            target_positions=targets,
            guide_to_target=guide_to_target,
            reserve_guide_ids=np.flatnonzero(~active_mask).astype(int),
            safety_status_history=np.empty(0, dtype="U24"),
            safety_constraint_count=np.empty(0, dtype=int),
            safety_guide_pair_constraint_count=np.empty(0, dtype=int),
            safety_crowd_constraint_count=np.empty(0, dtype=int),
            safety_room_constraint_count=np.empty(0, dtype=int),
            safety_violated_constraint_count=np.empty(0, dtype=int),
            safety_projection_sweeps=np.empty(0, dtype=int),
            safety_max_residual_before=np.empty(0, dtype=float),
            safety_max_residual_after=np.empty(0, dtype=float),
            safety_max_guide_pair_residual_after=np.empty(0, dtype=float),
            safety_max_crowd_residual_after=np.empty(0, dtype=float),
            safety_max_room_residual_after=np.empty(0, dtype=float),
            safety_control_adjustment_norm=np.empty(0, dtype=float),
            safety_emergency_stop_history=np.empty(0, dtype=bool),
            status=status,
            converged=False,
            stop_reason=reason,
            diagnostics={
                "motion_model": "p_dot_equals_u_explicit_euler",
                "safety_filter_status": "ENABLED_PR5" if self.safety_config.enabled else "DISABLED_PR5",
                "safety_config": asdict(self.safety_config),
                "config": asdict(self.config),
            },
        )

    def run_fixed_target_episode(
        self,
        initial_positions: Array,
        target_positions: Array,
        assignment: AssignmentResult,
        precondition_status: str = "VALID",
        crowd_points: Array | None = None,
        room_size: Array | None = None,
    ) -> EpisodeResult:
        positions = _points(initial_positions, "initial_positions")
        targets = _points(target_positions, "target_positions")
        if not isinstance(assignment, AssignmentResult):
            raise TypeError("assignment must be AssignmentResult.")

        guide_to_target = np.asarray(assignment.guide_to_target, dtype=int)
        if guide_to_target.shape != (len(positions),):
            active_mask = np.zeros(len(positions), dtype=bool)
            return self._terminal_episode(
                positions,
                targets,
                np.full(len(positions), -1, dtype=int),
                positions.copy(),
                active_mask,
                "ASSIGNMENT_INFEASIBLE",
                "assignment_shape_mismatch",
            )
        active_mask = guide_to_target >= 0
        if np.any(guide_to_target[active_mask] >= len(targets)):
            return self._terminal_episode(
                positions,
                targets,
                guide_to_target,
                positions.copy(),
                np.zeros(len(positions), dtype=bool),
                "ASSIGNMENT_INFEASIBLE",
                "assignment_target_index_out_of_range",
            )
        assigned_targets = positions.copy()
        assigned_targets[active_mask] = targets[guide_to_target[active_mask]]

        if precondition_status != "VALID":
            allowed = {
                "DEGRADED",
                "BOUNDARY_INVALID",
                "OFFSET_INVALID",
                "CAPACITY_SHORTFALL",
                "ASSIGNMENT_INFEASIBLE",
            }
            status = precondition_status if precondition_status in allowed else "DEGRADED"
            return self._terminal_episode(
                positions,
                targets,
                guide_to_target,
                assigned_targets,
                active_mask,
                status,
                f"precondition_{precondition_status.lower()}",
            )
        if assignment.status != "VALID":
            status = "CAPACITY_SHORTFALL" if assignment.status == "CAPACITY_SHORTFALL" else "ASSIGNMENT_INFEASIBLE"
            return self._terminal_episode(
                positions,
                targets,
                guide_to_target,
                assigned_targets,
                active_mask,
                status,
                f"assignment_{assignment.status.lower()}",
            )
        if not np.any(active_mask):
            return self._terminal_episode(
                positions,
                targets,
                guide_to_target,
                assigned_targets,
                active_mask,
                "DEGRADED",
                "no_active_assignments",
            )
        if self.safety_config.enabled and (crowd_points is None or room_size is None):
            return self._terminal_episode(
                positions,
                targets,
                guide_to_target,
                assigned_targets,
                active_mask,
                "SAFETY_INFEASIBLE",
                "safety_context_missing",
            )

        safety_crowd = (
            np.asarray(crowd_points, dtype=float)
            if crowd_points is not None
            else np.empty((0, 2), dtype=float)
        )
        safety_room = (
            np.asarray(room_size, dtype=float)
            if room_size is not None
            else np.array([1.0, 1.0], dtype=float)
        )

        machine = ConvergenceStateMachine(self.config.hold_steps)
        position_frames = [positions.copy()]
        velocity_frames = [np.zeros_like(positions)]
        nominal_frames: list[Array] = []
        applied_frames: list[Array] = []
        state_frames = ["INIT"]
        error_frames = [_tracking_rmse(positions, assigned_targets, active_mask)]
        speed_frames = [0.0]
        hold_frames = [0]
        safety_status_frames: list[str] = []
        safety_constraint_frames: list[int] = []
        safety_guide_pair_constraint_frames: list[int] = []
        safety_crowd_constraint_frames: list[int] = []
        safety_room_constraint_frames: list[int] = []
        safety_violated_frames: list[int] = []
        safety_sweep_frames: list[int] = []
        safety_residual_before_frames: list[float] = []
        safety_residual_after_frames: list[float] = []
        safety_guide_pair_residual_after_frames: list[float] = []
        safety_crowd_residual_after_frames: list[float] = []
        safety_room_residual_after_frames: list[float] = []
        safety_adjustment_frames: list[float] = []
        safety_emergency_frames: list[bool] = []
        stop_reason = "maximum_steps_reached"

        for _ in range(self.config.max_steps):
            nominal = nominal_guide_velocity(
                positions,
                assigned_targets,
                active_mask,
                self.config.k_p,
                self.config.v_max,
            )
            if self.safety_config.enabled:
                safety = project_velocity_safety(
                    positions,
                    nominal,
                    safety_crowd,
                    safety_room,
                    self.config.dt,
                    self.config.v_max,
                    self.safety_config,
                )
                applied = safety.applied_control
                safety_status = safety.status
                safety_constraint_count = safety.constraint_count
                safety_guide_pair_constraint_count = safety.constraint_type_counts["guide_pair"]
                safety_crowd_constraint_count = safety.constraint_type_counts["crowd"]
                safety_room_constraint_count = safety.constraint_type_counts["room"]
                safety_violated_count = safety.violated_constraint_count
                safety_sweeps = safety.projection_sweeps
                safety_residual_before = safety.max_residual_before
                safety_residual_after = safety.max_residual_after
                type_residuals = {
                    kind: safety.constraint_residuals_after[safety.constraint_kinds == kind]
                    for kind in ("guide_pair", "crowd", "room")
                }
                safety_guide_pair_residual_after = max(
                    0.0,
                    float(np.max(type_residuals["guide_pair"]))
                    if len(type_residuals["guide_pair"])
                    else 0.0,
                )
                safety_crowd_residual_after = max(
                    0.0,
                    float(np.max(type_residuals["crowd"])) if len(type_residuals["crowd"]) else 0.0,
                )
                safety_room_residual_after = max(
                    0.0,
                    float(np.max(type_residuals["room"])) if len(type_residuals["room"]) else 0.0,
                )
                safety_adjustment = safety.control_adjustment_norm
                safety_emergency = safety.emergency_stop
            else:
                applied = nominal.copy()
                safety_status = "DISABLED"
                safety_constraint_count = 0
                safety_guide_pair_constraint_count = 0
                safety_crowd_constraint_count = 0
                safety_room_constraint_count = 0
                safety_violated_count = 0
                safety_sweeps = 0
                safety_residual_before = 0.0
                safety_residual_after = 0.0
                safety_guide_pair_residual_after = 0.0
                safety_crowd_residual_after = 0.0
                safety_room_residual_after = 0.0
                safety_adjustment = 0.0
                safety_emergency = False
            next_positions = integrate_guide_positions(positions, applied, self.config.dt)
            next_error = _tracking_rmse(next_positions, assigned_targets, active_mask)
            max_speed = float(np.max(np.linalg.norm(applied, axis=1))) if len(applied) else 0.0

            if safety_status == "SAFETY_INFEASIBLE":
                state = machine.stop("SAFETY_INFEASIBLE")
                stop_reason = "velocity_safety_projection_infeasible"
            elif (
                safety_status != "PROJECTED"
                and next_error > error_frames[-1] + self.config.error_increase_tolerance
            ):
                state = machine.stop("DEGRADED")
                stop_reason = "tracking_error_increased"
            else:
                criteria_met = (
                    next_error <= self.config.tracking_rmse_tolerance
                    and max_speed <= self.config.speed_tolerance
                    and (
                        not self.safety_config.enabled
                        or (
                            not safety_emergency
                            and safety_residual_after <= self.safety_config.residual_tolerance
                        )
                    )
                )
                state = machine.update(criteria_met)

            nominal_frames.append(nominal)
            applied_frames.append(applied)
            position_frames.append(next_positions.copy())
            velocity_frames.append(applied.copy())
            state_frames.append(state)
            error_frames.append(next_error)
            speed_frames.append(max_speed)
            hold_frames.append(machine.hold_count)
            safety_status_frames.append(safety_status)
            safety_constraint_frames.append(safety_constraint_count)
            safety_guide_pair_constraint_frames.append(safety_guide_pair_constraint_count)
            safety_crowd_constraint_frames.append(safety_crowd_constraint_count)
            safety_room_constraint_frames.append(safety_room_constraint_count)
            safety_violated_frames.append(safety_violated_count)
            safety_sweep_frames.append(safety_sweeps)
            safety_residual_before_frames.append(safety_residual_before)
            safety_residual_after_frames.append(safety_residual_after)
            safety_guide_pair_residual_after_frames.append(safety_guide_pair_residual_after)
            safety_crowd_residual_after_frames.append(safety_crowd_residual_after)
            safety_room_residual_after_frames.append(safety_room_residual_after)
            safety_adjustment_frames.append(safety_adjustment)
            safety_emergency_frames.append(safety_emergency)
            positions = next_positions

            if machine.terminal:
                stop_reason = "hold_window_satisfied" if state == "CONVERGED" else stop_reason
                break

        if not machine.terminal:
            machine.timeout()
            state_frames[-1] = "TIMEOUT"

        status = machine.state
        guide_count = len(positions)
        return EpisodeResult(
            times=np.arange(len(position_frames), dtype=float) * self.config.dt,
            positions=np.asarray(position_frames, dtype=float),
            velocities=np.asarray(velocity_frames, dtype=float),
            nominal_controls=np.asarray(nominal_frames, dtype=float).reshape((-1, guide_count, 2)),
            applied_controls=np.asarray(applied_frames, dtype=float).reshape((-1, guide_count, 2)),
            state_history=np.asarray(state_frames),
            tracking_rmse=np.asarray(error_frames, dtype=float),
            max_speed_history=np.asarray(speed_frames, dtype=float),
            hold_count_history=np.asarray(hold_frames, dtype=int),
            target_positions=targets,
            guide_to_target=guide_to_target,
            reserve_guide_ids=np.flatnonzero(~active_mask).astype(int),
            safety_status_history=np.asarray(safety_status_frames, dtype="U24"),
            safety_constraint_count=np.asarray(safety_constraint_frames, dtype=int),
            safety_guide_pair_constraint_count=np.asarray(safety_guide_pair_constraint_frames, dtype=int),
            safety_crowd_constraint_count=np.asarray(safety_crowd_constraint_frames, dtype=int),
            safety_room_constraint_count=np.asarray(safety_room_constraint_frames, dtype=int),
            safety_violated_constraint_count=np.asarray(safety_violated_frames, dtype=int),
            safety_projection_sweeps=np.asarray(safety_sweep_frames, dtype=int),
            safety_max_residual_before=np.asarray(safety_residual_before_frames, dtype=float),
            safety_max_residual_after=np.asarray(safety_residual_after_frames, dtype=float),
            safety_max_guide_pair_residual_after=np.asarray(
                safety_guide_pair_residual_after_frames,
                dtype=float,
            ),
            safety_max_crowd_residual_after=np.asarray(safety_crowd_residual_after_frames, dtype=float),
            safety_max_room_residual_after=np.asarray(safety_room_residual_after_frames, dtype=float),
            safety_control_adjustment_norm=np.asarray(safety_adjustment_frames, dtype=float),
            safety_emergency_stop_history=np.asarray(safety_emergency_frames, dtype=bool),
            status=status,
            converged=status == "CONVERGED",
            stop_reason=stop_reason,
            diagnostics={
                "motion_model": "p_dot_equals_u_explicit_euler",
                "control_law": "sat_vmax_kp_target_error",
                "applied_control_role": (
                    "pr5_projected_or_emergency_control"
                    if self.safety_config.enabled
                    else "nominal_with_safety_disabled"
                ),
                "safety_filter_status": "ENABLED_PR5" if self.safety_config.enabled else "DISABLED_PR5",
                "safety_projected_steps": int(np.count_nonzero(np.asarray(safety_status_frames) == "PROJECTED")),
                "safety_infeasible_steps": int(
                    np.count_nonzero(np.asarray(safety_status_frames) == "SAFETY_INFEASIBLE")
                ),
                "safety_max_residual_after": float(max(safety_residual_after_frames, default=0.0)),
                "safety_config": asdict(self.safety_config),
                "tracking_error_nonincreasing": bool(
                    np.all(np.diff(np.asarray(error_frames)) <= self.config.error_increase_tolerance)
                ),
                "config": asdict(self.config),
            },
        )
