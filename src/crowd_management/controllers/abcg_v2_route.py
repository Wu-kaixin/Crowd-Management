"""Route-aware ABCG-v2: waypoint nominal motion, frozen PR5 safety filter.

ROLE: CORE MATH — wrap ABCG-v2 so guides follow a safe transit curve instead of
commanding a straight line through the crowd.  ``abcg_v2.py`` remains the
frozen baseline and is not modified.

Control chain:

    z_i  →  route planner  →  w_i  →  sat(k_p (w_i - p_i))  →  PR5  →  u_i
"""
from __future__ import annotations

from dataclasses import asdict, replace

import numpy as np

from ..crowd.observation import CrowdObservation, as_controller_observation
from ..types import Array
from .abcg_v2 import (
    ABCGv2Config,
    ABCGv2Controller,
    AssignmentResult,
    ControlOutput,
    EpisodeResult,
    _points,
    _tracking_rmse,
    nominal_guide_velocity,
)
from .boundary_route import (
    ROUTE_APPROACH_RING,
    ROUTE_FOLLOW_BOUNDARY,
    ROUTE_FOLLOW_DEPLOYMENT,
    BoundaryRouteConfig,
    TransitCurve,
    plan_route_waypoints,
)
from .safety import (
    VelocitySafetyConfig,
    minimum_guide_crowd_distance,
    minimum_guide_guide_distance,
    minimum_guide_wall_distance,
    project_velocity_safety,
)

_DETOUR_MODES = {ROUTE_APPROACH_RING, ROUTE_FOLLOW_BOUNDARY, ROUTE_FOLLOW_DEPLOYMENT}


class RouteAwareABCGv2Controller(ABCGv2Controller):
    """ABCG-v2 with boundary-aware nominal motion. Assignment and PR5 are unchanged."""

    def __init__(
        self,
        config: ABCGv2Config | None = None,
        safety_config: VelocitySafetyConfig | None = None,
        route_config: BoundaryRouteConfig | None = None,
    ) -> None:
        super().__init__(config=config, safety_config=safety_config)
        self.route_config = route_config or BoundaryRouteConfig()
        if not isinstance(self.route_config, BoundaryRouteConfig):
            raise TypeError("route_config must be BoundaryRouteConfig.")
        self._transit: TransitCurve | None = None
        self._inner: TransitCurve | None = None
        self._pending_transit: TransitCurve | None = None
        self._pending_inner: TransitCurve | None = None
        self._previous_applied: Array | None = None
        self._last_route_diagnostics: dict[str, object] = {}

    def set_transit_curve(self, transit: TransitCurve | None) -> None:
        """Install the movement curve used by the route planner."""
        if transit is not None and not isinstance(transit, TransitCurve):
            raise TypeError("transit must be TransitCurve or None.")
        self._transit = transit

    def set_inner_curve(self, inner: TransitCurve | None) -> None:
        """Install the deployment ring used to enter bays after the outer transit."""
        if inner is not None and not isinstance(inner, TransitCurve):
            raise TypeError("inner must be TransitCurve or None.")
        self._inner = inner

    def reset(
        self,
        target_positions: Array,
        assignment: AssignmentResult,
        guide_state: Array,
        room_size: Array | None = None,
        precondition_status: str = "VALID",
    ) -> None:
        super().reset(
            target_positions,
            assignment,
            guide_state,
            room_size=room_size,
            precondition_status=precondition_status,
        )
        if self._pending_transit is not None:
            self._transit = self._pending_transit
        if self._pending_inner is not None:
            self._inner = self._pending_inner
        self._previous_applied = None
        self._last_route_diagnostics = {}

    def step(self, observation: Array | CrowdObservation, guide_state: Array, dt: float) -> ControlOutput:
        """Same measured-feedback contract as ABCG-v2, with routed nominal velocity."""
        if self._targets is None or self._guide_to_target is None or self._machine is None:
            raise RuntimeError("reset must be called before step.")
        crowd_observation = as_controller_observation(observation)
        crowd = crowd_observation.controller_points()
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
                    "route_enabled": True,
                },
            )

        room = self._room_size
        wall_margin = float(self.safety_config.room_margin)
        crowd_clearance = float(self.safety_config.min_crowd_distance)
        route = plan_route_waypoints(
            guides,
            assigned_targets,
            active_mask,
            self._transit,
            crowd,
            self.route_config,
            clearance=crowd_clearance,
            room_size=room,
            wall_margin=wall_margin,
            previous_applied=self._previous_applied,
            tracking_tolerance=self.config.tracking_rmse_tolerance,
            inner=self._inner,
        )
        self._last_route_diagnostics = dict(route.diagnostics)
        nominal = nominal_guide_velocity(
            guides,
            route.waypoints,
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
            type_residuals = {
                kind: safety.constraint_residuals_after[safety.constraint_kinds == kind]
                for kind in ("guide_pair", "crowd", "room")
            }
            safety_diagnostics: dict[str, object] = {
                "safety_constraint_count": safety.constraint_count,
                "safety_violated_constraint_count": safety.violated_constraint_count,
                "safety_projection_sweeps": safety.projection_sweeps,
                "safety_max_residual_before": safety.max_residual_before,
                "safety_max_residual_after": safety.max_residual_after,
                "safety_max_guide_pair_residual_after": max(
                    0.0,
                    float(np.max(type_residuals["guide_pair"])) if len(type_residuals["guide_pair"]) else 0.0,
                ),
                "safety_max_crowd_residual_after": max(
                    0.0,
                    float(np.max(type_residuals["crowd"])) if len(type_residuals["crowd"]) else 0.0,
                ),
                "safety_max_room_residual_after": max(
                    0.0,
                    float(np.max(type_residuals["room"])) if len(type_residuals["room"]) else 0.0,
                ),
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
                "safety_max_guide_pair_residual_after": 0.0,
                "safety_max_crowd_residual_after": 0.0,
                "safety_max_room_residual_after": 0.0,
                "safety_control_adjustment_norm": 0.0,
                "safety_emergency_stop": False,
                "safety_constraint_type_counts": {"guide_pair": 0, "crowd": 0, "room": 0},
            }

        state_before = self._machine.state
        max_speed = float(np.max(np.linalg.norm(applied, axis=1))) if len(applied) else 0.0
        detouring = any(mode in _DETOUR_MODES for mode, on in zip(route.modes, active_mask, strict=True) if on)
        if safety_status == "SAFETY_INFEASIBLE":
            state = self._machine.stop("SAFETY_INFEASIBLE")
        elif (
            (not detouring)
            and safety_status != "PROJECTED"
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
        if detouring:
            events.append("route:DETOUR")

        wall_room = self._room_size if self._room_size is not None else np.array([np.inf, np.inf], dtype=float)
        clearance = {
            "minimum_guide_guide_distance": minimum_guide_guide_distance(guides),
            "minimum_guide_crowd_distance": minimum_guide_crowd_distance(guides, crowd),
            "minimum_guide_wall_distance": minimum_guide_wall_distance(guides, wall_room)
            if self._room_size is not None
            else float("inf"),
        }
        self._previous_tracking_rmse = tracking_rmse
        self._previous_applied = applied.copy()
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
                "route_waypoints": route.waypoints.copy(),
                "route_modes": list(route.modes),
                "route_enabled": True,
                "route_detouring": bool(detouring),
                "safety_status": safety_status,
                **safety_diagnostics,
                **clearance,
                **route.diagnostics,
            },
        )

    def run_fixed_target_episode(
        self,
        initial_positions: Array,
        target_positions: Array,
        assignment: AssignmentResult,
        precondition_status: str = "VALID",
        crowd_points: Array | CrowdObservation | None = None,
        room_size: Array | None = None,
        on_frame: object | None = None,
        transit_curve: TransitCurve | None = None,
        inner_curve: TransitCurve | None = None,
    ) -> EpisodeResult:
        self._pending_transit = transit_curve
        self._pending_inner = inner_curve
        try:
            result = super().run_fixed_target_episode(
                initial_positions,
                target_positions,
                assignment,
                precondition_status=precondition_status,
                crowd_points=crowd_points,
                room_size=room_size,
                on_frame=on_frame,
            )
        finally:
            self._pending_transit = None
            self._pending_inner = None
        diagnostics = dict(result.diagnostics)
        diagnostics["control_law"] = "sat_vmax_kp_route_waypoint"
        diagnostics["route_enabled"] = True
        diagnostics["route_config"] = asdict(self.route_config)
        diagnostics["transit_clearance_used"] = (
            None if self._transit is None else float(self._transit.clearance)
        )
        diagnostics["inner_clearance_used"] = (
            None if self._inner is None else float(self._inner.clearance)
        )
        diagnostics["transit_status"] = (
            "NONE" if self._transit is None else str(self._transit.diagnostics.get("status", "VALID"))
        )
        diagnostics.update(self._last_route_diagnostics)
        return replace(result, diagnostics=diagnostics)


__all__ = ["RouteAwareABCGv2Controller"]
