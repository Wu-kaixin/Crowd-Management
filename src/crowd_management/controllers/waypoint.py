"""Finite fixed-waypoint tracking for ABCG-v2.1 routed deployment.

This runner is intentionally separate from the frozen ABCG-v2 fixed-target
episode contract.  Controller ``CONVERGED`` here still means tracking only;
deployment and truth success remain evaluator-level compositions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any, Callable, Sequence

import numpy as np

from ..types import Array
from .abcg_v2 import integrate_guide_positions, nominal_guide_velocity


PATH_SCHEMA = "abcg-v2.1-waypoint-path-v1"


@dataclass(frozen=True)
class FixedWaypointPaths:
    """Immutable ragged guide paths stored as flat points plus offsets."""

    guide_to_target: Array
    waypoint_offsets: Array
    waypoint_points: Array
    route_status: str
    route_mode: str
    clearance_margin_m: float
    diagnostics: dict[str, object] = field(default_factory=dict)
    path_schema: str = PATH_SCHEMA
    path_version: str = field(init=False)

    def __post_init__(self) -> None:
        assignment = np.asarray(self.guide_to_target)
        offsets = np.asarray(self.waypoint_offsets)
        points = np.asarray(self.waypoint_points, dtype=float)
        if assignment.ndim != 1 or not np.all(np.isfinite(assignment)):
            raise ValueError("guide_to_target must be a finite integer vector.")
        integer_assignment = assignment.astype(int)
        if not np.array_equal(assignment, integer_assignment) or np.any(integer_assignment < -1):
            raise ValueError("guide_to_target must contain integer values >= -1.")
        if offsets.shape != (len(assignment) + 1,) or not np.all(np.isfinite(offsets)):
            raise ValueError("waypoint_offsets must have shape (guide_count + 1,).")
        integer_offsets = offsets.astype(int)
        if not np.array_equal(offsets, integer_offsets):
            raise ValueError("waypoint_offsets must contain integers.")
        if integer_offsets[0] != 0 or np.any(np.diff(integer_offsets) < 0):
            raise ValueError("waypoint_offsets must begin at zero and be nondecreasing.")
        if points.ndim != 2 or points.shape[1:] != (2,) or not np.all(np.isfinite(points)):
            raise ValueError("waypoint_points must be a finite (N, 2) array.")
        if integer_offsets[-1] != len(points):
            raise ValueError("final waypoint offset must equal waypoint point count.")
        for guide_id, target_id in enumerate(integer_assignment):
            count = int(integer_offsets[guide_id + 1] - integer_offsets[guide_id])
            if target_id >= 0 and count < 1:
                raise ValueError("every active guide requires at least one waypoint.")
            if target_id < 0 and count != 0:
                raise ValueError("reserve guides must have empty waypoint paths.")
        if not np.isfinite(self.clearance_margin_m) or self.clearance_margin_m < 0.0:
            raise ValueError("clearance_margin_m must be finite and non-negative.")
        if self.path_schema != PATH_SCHEMA:
            raise ValueError(f"path_schema must be {PATH_SCHEMA!r}.")

        assignment_copy = np.asarray(integer_assignment, dtype=np.int64).copy()
        offsets_copy = np.asarray(integer_offsets, dtype=np.int64).copy()
        points_copy = np.asarray(points, dtype=np.float64).copy()
        for array in (assignment_copy, offsets_copy, points_copy):
            array.setflags(write=False)
        digest = hashlib.sha256()
        digest.update(self.path_schema.encode("utf-8"))
        digest.update(str(self.route_status).encode("utf-8"))
        digest.update(str(self.route_mode).encode("utf-8"))
        digest.update(np.asarray([self.clearance_margin_m], dtype="<f8").tobytes())
        digest.update(np.asarray(assignment_copy, dtype="<i8").tobytes())
        digest.update(np.asarray(offsets_copy, dtype="<i8").tobytes())
        digest.update(np.asarray(points_copy, dtype="<f8").tobytes())
        object.__setattr__(self, "guide_to_target", assignment_copy)
        object.__setattr__(self, "waypoint_offsets", offsets_copy)
        object.__setattr__(self, "waypoint_points", points_copy)
        object.__setattr__(self, "diagnostics", dict(self.diagnostics))
        object.__setattr__(self, "path_version", digest.hexdigest())

    @classmethod
    def from_guide_paths(
        cls,
        guide_to_target: Array,
        guide_paths: Sequence[Array | None],
        *,
        route_status: str = "ROUTE_FEASIBLE",
        route_mode: str = "visibility_graph",
        clearance_margin_m: float = 0.0,
        diagnostics: dict[str, object] | None = None,
    ) -> "FixedWaypointPaths":
        assignment = np.asarray(guide_to_target)
        if assignment.ndim != 1 or len(guide_paths) != len(assignment):
            raise ValueError("guide_paths must contain one entry per guide.")
        offsets = [0]
        points: list[Array] = []
        for path in guide_paths:
            array = np.empty((0, 2), dtype=float) if path is None else np.asarray(path, dtype=float)
            if array.ndim != 2 or array.shape[1:] != (2,) or not np.all(np.isfinite(array)):
                raise ValueError("each guide path must be a finite (N, 2) array or None.")
            points.extend(row.copy() for row in array)
            offsets.append(len(points))
        flat = np.asarray(points, dtype=float).reshape((-1, 2))
        return cls(
            guide_to_target=assignment,
            waypoint_offsets=np.asarray(offsets, dtype=int),
            waypoint_points=flat,
            route_status=str(route_status),
            route_mode=str(route_mode),
            clearance_margin_m=float(clearance_margin_m),
            diagnostics={} if diagnostics is None else dict(diagnostics),
        )

    def guide_path(self, guide_id: int) -> Array:
        start = int(self.waypoint_offsets[guide_id])
        stop = int(self.waypoint_offsets[guide_id + 1])
        return self.waypoint_points[start:stop]

    def to_jsonable(self) -> dict[str, object]:
        return {
            "path_schema": self.path_schema,
            "path_version": self.path_version,
            "guide_to_target": self.guide_to_target.tolist(),
            "waypoint_offsets": self.waypoint_offsets.tolist(),
            "waypoint_points": self.waypoint_points.tolist(),
            "route_status": self.route_status,
            "route_mode": self.route_mode,
            "clearance_margin_m": float(self.clearance_margin_m),
            "diagnostics": _jsonable(self.diagnostics),
        }


@dataclass(frozen=True)
class WaypointRunnerConfig:
    dt: float = 0.1
    k_p: float = 1.2
    v_max: float = 0.8
    waypoint_tolerance_m: float = 0.05
    final_rmse_tolerance_m: float = 0.05
    speed_tolerance_mps: float = 0.05
    hold_steps: int = 4
    max_steps: int = 240
    no_progress_window: int = 40
    min_progress_m: float = 1.0e-3
    numerical_tolerance: float = 1.0e-9

    def __post_init__(self) -> None:
        for name in (
            "dt",
            "k_p",
            "v_max",
            "waypoint_tolerance_m",
            "final_rmse_tolerance_m",
            "speed_tolerance_mps",
            "min_progress_m",
            "numerical_tolerance",
        ):
            value = float(getattr(self, name))
            if not np.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and positive.")
        for name in ("hold_steps", "max_steps", "no_progress_window"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or value < 1:
                raise ValueError(f"{name} must be a positive integer.")
        if self.dt * self.k_p > 1.0 + self.numerical_tolerance:
            raise ValueError("dt*k_p must not exceed one for the fixed-waypoint contraction contract.")


@dataclass(frozen=True)
class WaypointSafetyRequest:
    positions: Array
    nominal_control: Array
    dt: float
    step_index: int
    path_version: str
    waypoint_indices: Array


@dataclass(frozen=True)
class WaypointSafetyResponse:
    nominal_control: Array
    applied_control: Array
    status: str
    feasible: bool
    emergency_stop: bool = False
    primal_residual: float = 0.0
    kkt_residual: float = 0.0
    diagnostics: dict[str, object] = field(default_factory=dict)


SafetyCallback = Callable[[WaypointSafetyRequest], Any]


@dataclass(frozen=True)
class WaypointEvent:
    step: int
    time: float
    event: str
    guide_id: int | None = None
    waypoint_index: int | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "step": int(self.step),
            "time": float(self.time),
            "event": self.event,
            "guide_id": self.guide_id,
            "waypoint_index": self.waypoint_index,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class WaypointEpisodeResult:
    times: Array
    positions: Array
    velocities: Array
    nominal_controls: Array
    applied_controls: Array
    state_history: Array
    waypoint_index_history: Array
    remaining_path_m: Array
    total_remaining_path_m: Array
    progress_fraction: Array
    tracking_rmse_history: Array
    max_speed_history: Array
    no_progress_count_history: Array
    hold_count_history: Array
    safety_status_history: Array
    safety_diagnostics: tuple[dict[str, object], ...]
    path_schema: str
    path_version: str
    replan_count: int
    replan_reason: str
    terminal_status: str
    terminal_reason: str
    events: tuple[WaypointEvent, ...]
    diagnostics: dict[str, object] = field(default_factory=dict)

    def to_jsonable(self) -> dict[str, object]:
        return {
            "times": self.times.tolist(),
            "positions": self.positions.tolist(),
            "velocities": self.velocities.tolist(),
            "nominal_controls": self.nominal_controls.tolist(),
            "applied_controls": self.applied_controls.tolist(),
            "state_history": self.state_history.tolist(),
            "waypoint_index_history": self.waypoint_index_history.tolist(),
            "remaining_path_m": self.remaining_path_m.tolist(),
            "total_remaining_path_m": self.total_remaining_path_m.tolist(),
            "progress_fraction": self.progress_fraction.tolist(),
            "tracking_rmse_history": self.tracking_rmse_history.tolist(),
            "max_speed_history": self.max_speed_history.tolist(),
            "no_progress_count_history": self.no_progress_count_history.tolist(),
            "hold_count_history": self.hold_count_history.tolist(),
            "safety_status_history": self.safety_status_history.tolist(),
            "safety_diagnostics": _jsonable(self.safety_diagnostics),
            "path_schema": self.path_schema,
            "path_version": self.path_version,
            "replan_count": int(self.replan_count),
            "replan_reason": self.replan_reason,
            "terminal_status": self.terminal_status,
            "terminal_reason": self.terminal_reason,
            "events": [event.to_dict() for event in self.events],
            "diagnostics": _jsonable(self.diagnostics),
        }


class WaypointEpisodeRunner:
    """Run one fixed-path first-order episode with auditable progress state."""

    def __init__(self, config: WaypointRunnerConfig | None = None) -> None:
        self.config = config or WaypointRunnerConfig()
        if not isinstance(self.config, WaypointRunnerConfig):
            raise TypeError("config must be WaypointRunnerConfig.")

    def run(
        self,
        initial_positions: Array,
        paths: FixedWaypointPaths,
        *,
        safety_callback: SafetyCallback | None = None,
        precondition_status: str = "VALID",
    ) -> WaypointEpisodeResult:
        if not isinstance(paths, FixedWaypointPaths):
            raise TypeError("paths must be FixedWaypointPaths.")
        positions = np.asarray(initial_positions, dtype=float)
        if positions.ndim != 2 or positions.shape[1:] != (2,) or not np.all(np.isfinite(positions)):
            raise ValueError("initial_positions must be a finite (M, 2) array.")
        if len(positions) != len(paths.guide_to_target):
            raise ValueError("initial position count must match path guide count.")
        positions = positions.copy()
        indexes = np.where(paths.guide_to_target >= 0, 0, -1).astype(int)
        events: list[WaypointEvent] = []
        self._advance_reached(positions, paths, indexes, 0, events)
        remaining = self._remaining(positions, paths, indexes)
        initial_total = float(np.sum(remaining))
        tracking = self._final_tracking_rmse(positions, paths)
        initial_state = "HOLD" if self._all_completed(paths, indexes) else "INIT"

        if precondition_status != "VALID" or paths.route_status != "ROUTE_FEASIBLE":
            reason = (
                str(precondition_status)
                if precondition_status != "VALID"
                else str(paths.route_status)
            )
            return self._initial_only(
                positions,
                paths,
                indexes,
                remaining,
                tracking,
                initial_total,
                terminal_status=reason,
                terminal_reason=reason,
                events=events,
            )

        position_frames = [positions.copy()]
        velocity_frames = [np.zeros_like(positions)]
        nominal_frames: list[Array] = []
        applied_frames: list[Array] = []
        state_frames = [initial_state]
        index_frames = [indexes.copy()]
        remaining_frames = [remaining.copy()]
        total_frames = [initial_total]
        progress_frames = [self._progress(initial_total, initial_total)]
        tracking_frames = [tracking]
        speed_frames = [0.0]
        no_progress_frames = [0]
        hold_frames = [0]
        safety_status_frames: list[str] = []
        safety_diagnostics: list[dict[str, object]] = []

        hold_count = 0
        no_progress_count = 0
        window_start = initial_total
        window_min = initial_total
        terminal_status = "TIMEOUT"
        terminal_reason = "MAXIMUM_STEPS_REACHED"
        replan_reason = "NONE"

        for step_index in range(self.config.max_steps):
            active = np.zeros(len(positions), dtype=bool)
            current_targets = positions.copy()
            for guide_id in range(len(positions)):
                path = paths.guide_path(guide_id)
                if 0 <= indexes[guide_id] < len(path):
                    active[guide_id] = True
                    current_targets[guide_id] = path[indexes[guide_id]]
            nominal = nominal_guide_velocity(
                positions,
                current_targets,
                active,
                self.config.k_p,
                self.config.v_max,
            )
            response = self._safety_response(
                safety_callback,
                WaypointSafetyRequest(
                    positions=positions.copy(),
                    nominal_control=nominal.copy(),
                    dt=float(self.config.dt),
                    step_index=step_index,
                    path_version=paths.path_version,
                    waypoint_indices=indexes.copy(),
                ),
            )
            applied, safety_failed, safety_reason, safety_diag = self._validate_safety(
                nominal,
                response,
            )
            next_positions = integrate_guide_positions(positions, applied, self.config.dt)
            previous_indexes = indexes.copy()
            self._advance_reached(next_positions, paths, indexes, step_index + 1, events)
            advanced = bool(np.any(indexes != previous_indexes))
            next_remaining = self._remaining(next_positions, paths, indexes)
            next_total = float(np.sum(next_remaining))
            next_tracking = self._final_tracking_rmse(next_positions, paths)
            max_speed = float(np.max(np.linalg.norm(applied, axis=1))) if len(applied) else 0.0
            completed = self._all_completed(paths, indexes)

            if completed:
                no_progress_count = 0
                window_start = next_total
                window_min = next_total
            elif advanced:
                no_progress_count = 0
                window_start = next_total
                window_min = next_total
            else:
                no_progress_count += 1
                window_min = min(window_min, next_total)
                if window_start - window_min >= self.config.min_progress_m:
                    no_progress_count = 0
                    window_start = next_total
                    window_min = next_total

            criteria = bool(
                completed
                and next_tracking <= self.config.final_rmse_tolerance_m
                and max_speed <= self.config.speed_tolerance_mps
                and not safety_failed
            )
            hold_count = hold_count + 1 if criteria else 0

            if safety_failed:
                state = "SAFETY_INFEASIBLE"
                terminal_status = state
                terminal_reason = safety_reason
            elif hold_count >= self.config.hold_steps:
                state = "CONVERGED"
                terminal_status = state
                terminal_reason = "HOLD_WINDOW_SATISFIED"
            elif not completed and no_progress_count >= self.config.no_progress_window:
                state = "TIMEOUT"
                terminal_status = state
                terminal_reason = "NO_PROGRESS_REPLAN_NOT_AVAILABLE"
                replan_reason = "NO_PROGRESS_DETECTED"
                events.append(
                    WaypointEvent(
                        step=step_index + 1,
                        time=(step_index + 1) * self.config.dt,
                        event="NO_PROGRESS",
                        reason=terminal_reason,
                    )
                )
            elif step_index + 1 >= self.config.max_steps:
                state = "TIMEOUT"
                terminal_status = state
                terminal_reason = "MAXIMUM_STEPS_REACHED"
            elif completed:
                state = "HOLD"
            else:
                state = "TRACK"

            nominal_frames.append(nominal.copy())
            applied_frames.append(applied.copy())
            position_frames.append(next_positions.copy())
            velocity_frames.append(applied.copy())
            state_frames.append(state)
            index_frames.append(indexes.copy())
            remaining_frames.append(next_remaining.copy())
            total_frames.append(next_total)
            progress_frames.append(self._progress(initial_total, next_total))
            tracking_frames.append(next_tracking)
            speed_frames.append(max_speed)
            no_progress_frames.append(no_progress_count)
            hold_frames.append(hold_count)
            safety_status_frames.append(response.status)
            safety_diagnostics.append(safety_diag)
            positions = next_positions

            if state in {"CONVERGED", "TIMEOUT", "SAFETY_INFEASIBLE"}:
                break

        guide_count = len(positions)
        return WaypointEpisodeResult(
            times=np.arange(len(position_frames), dtype=float) * self.config.dt,
            positions=np.asarray(position_frames, dtype=float),
            velocities=np.asarray(velocity_frames, dtype=float),
            nominal_controls=np.asarray(nominal_frames, dtype=float).reshape((-1, guide_count, 2)),
            applied_controls=np.asarray(applied_frames, dtype=float).reshape((-1, guide_count, 2)),
            state_history=np.asarray(state_frames, dtype="U24"),
            waypoint_index_history=np.asarray(index_frames, dtype=int),
            remaining_path_m=np.asarray(remaining_frames, dtype=float),
            total_remaining_path_m=np.asarray(total_frames, dtype=float),
            progress_fraction=np.asarray(progress_frames, dtype=float),
            tracking_rmse_history=np.asarray(tracking_frames, dtype=float),
            max_speed_history=np.asarray(speed_frames, dtype=float),
            no_progress_count_history=np.asarray(no_progress_frames, dtype=int),
            hold_count_history=np.asarray(hold_frames, dtype=int),
            safety_status_history=np.asarray(safety_status_frames, dtype="U40"),
            safety_diagnostics=tuple(safety_diagnostics),
            path_schema=paths.path_schema,
            path_version=paths.path_version,
            replan_count=0,
            replan_reason=replan_reason,
            terminal_status=terminal_status,
            terminal_reason=terminal_reason,
            events=tuple(events),
            diagnostics={
                "controller_semantics": "TRACK_CONVERGED_ONLY",
                "path_fixed": True,
                "initial_total_path_m": initial_total,
                "interval_count": len(applied_frames),
                "frame_count": len(position_frames),
            },
        )

    def _initial_only(
        self,
        positions: Array,
        paths: FixedWaypointPaths,
        indexes: Array,
        remaining: Array,
        tracking: float,
        initial_total: float,
        *,
        terminal_status: str,
        terminal_reason: str,
        events: Sequence[WaypointEvent],
    ) -> WaypointEpisodeResult:
        guide_count = len(positions)
        return WaypointEpisodeResult(
            times=np.array([0.0]),
            positions=positions[None, :, :],
            velocities=np.zeros((1, guide_count, 2), dtype=float),
            nominal_controls=np.empty((0, guide_count, 2), dtype=float),
            applied_controls=np.empty((0, guide_count, 2), dtype=float),
            state_history=np.asarray([terminal_status], dtype="U40"),
            waypoint_index_history=indexes[None, :],
            remaining_path_m=remaining[None, :],
            total_remaining_path_m=np.asarray([initial_total]),
            progress_fraction=np.asarray([self._progress(initial_total, initial_total)]),
            tracking_rmse_history=np.asarray([tracking]),
            max_speed_history=np.asarray([0.0]),
            no_progress_count_history=np.asarray([0], dtype=int),
            hold_count_history=np.asarray([0], dtype=int),
            safety_status_history=np.empty(0, dtype="U40"),
            safety_diagnostics=(),
            path_schema=paths.path_schema,
            path_version=paths.path_version,
            replan_count=0,
            replan_reason="NONE",
            terminal_status=terminal_status,
            terminal_reason=terminal_reason,
            events=tuple(events),
            diagnostics={
                "controller_semantics": "TRACK_CONVERGED_ONLY",
                "path_fixed": True,
                "control_called": False,
                "interval_count": 0,
                "frame_count": 1,
            },
        )

    def _advance_reached(
        self,
        positions: Array,
        paths: FixedWaypointPaths,
        indexes: Array,
        step: int,
        events: list[WaypointEvent],
    ) -> None:
        for guide_id in range(len(positions)):
            path = paths.guide_path(guide_id)
            if indexes[guide_id] < 0:
                continue
            while (
                indexes[guide_id] < len(path)
                and np.linalg.norm(positions[guide_id] - path[indexes[guide_id]])
                <= self.config.waypoint_tolerance_m
            ):
                indexes[guide_id] += 1
                events.append(
                    WaypointEvent(
                        step=step,
                        time=step * self.config.dt,
                        event="WAYPOINT_ADVANCED",
                        guide_id=guide_id,
                        waypoint_index=int(indexes[guide_id]),
                    )
                )

    @staticmethod
    def _all_completed(paths: FixedWaypointPaths, indexes: Array) -> bool:
        for guide_id, target_id in enumerate(paths.guide_to_target):
            if target_id >= 0 and indexes[guide_id] < len(paths.guide_path(guide_id)):
                return False
        return True

    @staticmethod
    def _remaining(positions: Array, paths: FixedWaypointPaths, indexes: Array) -> Array:
        result = np.zeros(len(positions), dtype=float)
        for guide_id in range(len(positions)):
            path = paths.guide_path(guide_id)
            index = int(indexes[guide_id])
            if index < 0 or index >= len(path):
                continue
            distance = float(np.linalg.norm(positions[guide_id] - path[index]))
            if index + 1 < len(path):
                distance += float(np.sum(np.linalg.norm(np.diff(path[index:], axis=0), axis=1)))
            result[guide_id] = distance
        return result

    @staticmethod
    def _final_tracking_rmse(positions: Array, paths: FixedWaypointPaths) -> float:
        errors: list[float] = []
        for guide_id, target_id in enumerate(paths.guide_to_target):
            path = paths.guide_path(guide_id)
            if target_id >= 0 and len(path):
                errors.append(float(np.sum((positions[guide_id] - path[-1]) ** 2)))
        return float(np.sqrt(np.mean(errors))) if errors else 0.0

    @staticmethod
    def _progress(initial_total: float, current_total: float) -> float:
        if initial_total <= 0.0:
            return 1.0
        return float(np.clip(1.0 - current_total / initial_total, 0.0, 1.0))

    @staticmethod
    def _safety_response(
        callback: SafetyCallback | None,
        request: WaypointSafetyRequest,
    ) -> WaypointSafetyResponse:
        if callback is None:
            return WaypointSafetyResponse(
                nominal_control=request.nominal_control.copy(),
                applied_control=request.nominal_control.copy(),
                status="DISABLED",
                feasible=True,
            )
        raw = callback(request)
        if isinstance(raw, WaypointSafetyResponse):
            return raw
        # Adapter for the legacy and v2.1 safety projection result contracts.
        nominal = getattr(raw, "nominal_control", request.nominal_control)
        applied = getattr(raw, "applied_control", None)
        if applied is None:
            applied = getattr(raw, "projected_control", None)
        certificate = getattr(raw, "certificate", None)
        certificate_residuals = getattr(certificate, "residuals", None)
        primal_residual = getattr(raw, "primal_residual", None)
        if primal_residual is None:
            primal_residual = getattr(raw, "max_residual_after", None)
        if primal_residual is None:
            primal_residual = getattr(certificate_residuals, "primal_residual", np.inf)
        kkt_residual = getattr(raw, "kkt_residual", None)
        if kkt_residual is None:
            kkt_residual = getattr(certificate_residuals, "kkt_residual", 0.0)
        raw_diagnostics = dict(getattr(raw, "diagnostics", {}))
        if certificate is not None and hasattr(certificate, "to_dict"):
            raw_diagnostics["certificate"] = certificate.to_dict()
        return WaypointSafetyResponse(
            nominal_control=np.asarray(nominal, dtype=float),
            applied_control=np.asarray(applied, dtype=float),
            status=str(getattr(raw, "status", "INVALID_SAFETY_RESPONSE")),
            feasible=bool(getattr(raw, "feasible", False)),
            emergency_stop=bool(getattr(raw, "emergency_stop", False)),
            primal_residual=float(primal_residual),
            kkt_residual=float(kkt_residual),
            diagnostics=raw_diagnostics,
        )

    def _validate_safety(
        self,
        nominal: Array,
        response: WaypointSafetyResponse,
    ) -> tuple[Array, bool, str, dict[str, object]]:
        applied = np.asarray(response.applied_control, dtype=float)
        returned_nominal = np.asarray(response.nominal_control, dtype=float)
        valid = bool(
            applied.shape == nominal.shape
            and returned_nominal.shape == nominal.shape
            and np.all(np.isfinite(applied))
            and np.all(np.isfinite(returned_nominal))
            and np.allclose(returned_nominal, nominal, rtol=0.0, atol=self.config.numerical_tolerance)
            and np.all(np.linalg.norm(applied, axis=1) <= self.config.v_max + self.config.numerical_tolerance)
            and np.isfinite(response.primal_residual)
            and np.isfinite(response.kkt_residual)
        )
        failed = bool(
            not valid
            or not response.feasible
            or response.emergency_stop
            or "INFEASIBLE" in response.status
            or "UNSAFE" in response.status
            or "FAIL" in response.status
        )
        if not valid:
            applied = np.zeros_like(nominal)
            reason = "INVALID_SAFETY_RESPONSE"
        else:
            reason = response.status
        return applied, failed, reason, {
            "status": response.status,
            "feasible": response.feasible,
            "emergency_stop": response.emergency_stop,
            "primal_residual": response.primal_residual,
            "kkt_residual": response.kkt_residual,
            "diagnostics": _jsonable(response.diagnostics),
        }


def _jsonable(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


__all__ = [
    "FixedWaypointPaths",
    "PATH_SCHEMA",
    "SafetyCallback",
    "WaypointEpisodeResult",
    "WaypointEpisodeRunner",
    "WaypointEvent",
    "WaypointRunnerConfig",
    "WaypointSafetyRequest",
    "WaypointSafetyResponse",
]
