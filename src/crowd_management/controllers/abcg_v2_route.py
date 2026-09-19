"""Route-aware ABCG-v2: waypoint nominal motion, frozen PR5 safety filter.

ROLE: CORE MATH — wrap ABCG-v2 so guides follow a safe path instead of
commanding a straight line through the crowd.  ``abcg_v2.py`` remains the
frozen baseline and is not modified.

Control chain:

    z_i  →  geodesic / dual-ring planner  →  w_i  →  sat(k_p (w_i - p_i))  →  PR5  →  u_i
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
from .safe_geodesic import (
    ROUTE_FINAL_TARGET,
    ROUTE_FOLLOW_WAYPOINT,
    ROUTE_GEODESIC_FALLBACK,
    ROUTE_WAIT,
    conflict_wait_mask,
    inflate_estimated_obstacle,
    inflate_observation_cloud,
    remaining_path_length,
    union_obstacles,
    visibility_shortest_path,
    workspace_polygon,
    build_static_visibility_graph,
)
from .safety import (
    VelocitySafetyConfig,
    minimum_guide_crowd_distance,
    minimum_guide_guide_distance,
    minimum_guide_wall_distance,
    project_velocity_safety,
)

_DETOUR_MODES = {
    ROUTE_APPROACH_RING,
    ROUTE_FOLLOW_BOUNDARY,
    ROUTE_FOLLOW_DEPLOYMENT,
    ROUTE_FOLLOW_WAYPOINT,
    ROUTE_WAIT,
    ROUTE_GEODESIC_FALLBACK,
}


def _empty_geo_stats() -> dict[str, object]:
    return {
        "geodesic_path_guide_steps": 0,
        "geodesic_fallback_steps": 0,
        "geodesic_wait_steps": 0,
        "geodesic_replan_count": 0,
        "geodesic_path_length_sum": 0.0,
        "geodesic_waypoint_count_sum": 0.0,
        "geodesic_progress_sum": 0.0,
        "crowd_projection_steps": 0,
        "guide_pair_projection_steps": 0,
        "room_projection_steps": 0,
    }


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
        self._crowd_curve: Array | None = None
        self._pending_transit: TransitCurve | None = None
        self._pending_inner: TransitCurve | None = None
        self._pending_crowd_curve: Array | None = None
        self._previous_applied: Array | None = None
        self._paths: list[Array | None] = []
        self._path_index: Array | None = None
        self._stall_count: Array | None = None
        self._obstacle = None
        self._room_polygon = None
        self._vis_graph = None
        self._geo_stats: dict[str, object] = _empty_geo_stats()
        self._last_route_diagnostics: dict[str, object] = {}

    def set_transit_curve(self, transit: TransitCurve | None) -> None:
        """Install the movement curve used by the dual-ring fallback planner."""
        if transit is not None and not isinstance(transit, TransitCurve):
            raise TypeError("transit must be TransitCurve or None.")
        self._transit = transit

    def set_inner_curve(self, inner: TransitCurve | None) -> None:
        """Install the deployment ring used by the dual-ring fallback planner."""
        if inner is not None and not isinstance(inner, TransitCurve):
            raise TypeError("inner must be TransitCurve or None.")
        self._inner = inner

    def set_estimated_crowd_curve(self, crowd_curve: Array | None) -> None:
        """Install the estimated crowd polygon. Never a spawn/truth contour."""
        if crowd_curve is None:
            self._crowd_curve = None
            self._obstacle = None
            self._vis_graph = None
            return
        curve = np.asarray(crowd_curve, dtype=float)
        if curve.ndim != 2 or curve.shape[1] != 2:
            raise ValueError("crowd_curve must have shape (K, 2).")
        self._crowd_curve = curve.copy()
        self._obstacle = None
        self._vis_graph = None

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
        if self._pending_crowd_curve is not None:
            self.set_estimated_crowd_curve(self._pending_crowd_curve)
        self._previous_applied = None
        count = len(np.asarray(guide_state, dtype=float))
        self._paths = [None] * count
        self._path_index = np.zeros(count, dtype=int)
        self._stall_count = np.zeros(count, dtype=int)
        self._room_polygon = None
        self._vis_graph = None
        self._geo_stats = _empty_geo_stats()
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
        waypoints, modes, geo_now = self._apply_geodesic(
            guides,
            assigned_targets,
            active_mask,
            route.waypoints,
            route.modes,
            crowd,
            crowd_clearance,
            room,
            wall_margin,
        )
        self._last_route_diagnostics = dict(route.diagnostics)
        self._last_route_diagnostics.update(geo_now)
        nominal = nominal_guide_velocity(
            guides,
            waypoints,
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
            type_residuals_before = {
                kind: safety.constraint_residuals_before[safety.constraint_kinds == kind]
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
            type_residuals_before = {
                "guide_pair": np.empty(0, dtype=float),
                "crowd": np.empty(0, dtype=float),
                "room": np.empty(0, dtype=float),
            }
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
        detouring = any(mode in _DETOUR_MODES for mode, on in zip(modes, active_mask, strict=True) if on)
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
        if int(geo_now.get("geodesic_wait_count", 0)) > 0:
            events.append("route:WAIT")

        wall_room = self._room_size if self._room_size is not None else np.array([np.inf, np.inf], dtype=float)
        clearance = {
            "minimum_guide_guide_distance": minimum_guide_guide_distance(guides),
            "minimum_guide_crowd_distance": minimum_guide_crowd_distance(guides, crowd),
            "minimum_guide_wall_distance": minimum_guide_wall_distance(guides, wall_room)
            if self._room_size is not None
            else float("inf"),
        }
        self._update_geodesic_stall(guides, waypoints, modes, active_mask, nominal, applied, safety_status)
        if int(self._last_route_diagnostics.get("geodesic_replan_now", 0)) > 0:
            events.append("route:REPLAN")
        self._record_projection_kinds(safety_status, type_residuals_before)
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
                "route_waypoints": waypoints.copy(),
                "route_modes": list(modes),
                "route_enabled": True,
                "route_detouring": bool(detouring),
                "safety_status": safety_status,
                **safety_diagnostics,
                **clearance,
                **self._last_route_diagnostics,
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
        crowd_curve: Array | None = None,
    ) -> EpisodeResult:
        self._pending_transit = transit_curve
        self._pending_inner = inner_curve
        self._pending_crowd_curve = None if crowd_curve is None else np.asarray(crowd_curve, dtype=float)
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
            self._pending_crowd_curve = None
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
        diagnostics.update(self._finalize_geo_stats())
        return replace(result, diagnostics=diagnostics)

    def _apply_geodesic(
        self,
        guides: Array,
        assigned_targets: Array,
        active_mask: Array,
        fallback_waypoints: Array,
        fallback_modes: tuple[str, ...],
        crowd_points: Array,
        clearance: float,
        room_size: Array | None,
        wall_margin: float,
    ) -> tuple[Array, list[str], dict[str, object]]:
        waypoints = np.asarray(fallback_waypoints, dtype=float).copy()
        modes = list(fallback_modes)
        stats = {
            "geodesic_enabled": bool(self.route_config.geodesic_enabled),
            "geodesic_active_count": 0,
            "geodesic_fallback_count": 0,
            "geodesic_wait_count": 0,
            "geodesic_replan_now": 0,
            "geodesic_mean_path_length": 0.0,
            "geodesic_mean_waypoint_count": 0.0,
            "geodesic_mean_progress": 0.0,
        }
        if (
            not bool(self.route_config.geodesic_enabled)
            or self._crowd_curve is None
            or room_size is None
        ):
            return waypoints, modes, stats
        if self._room_polygon is None:
            self._room_polygon = workspace_polygon(room_size, wall_margin)
        if self._obstacle is None:
            estimated = inflate_estimated_obstacle(
                self._crowd_curve,
                clearance,
                simplify=float(self.route_config.vertex_simplify),
            )
            observed = inflate_observation_cloud(
                crowd_points,
                clearance,
                simplify=float(self.route_config.vertex_simplify),
            )
            self._obstacle = union_obstacles([estimated, observed])
            self._vis_graph = None
        if self._obstacle is None:
            return waypoints, modes, stats
        if self._vis_graph is None:
            self._vis_graph = build_static_visibility_graph(self._obstacle, self._room_polygon)
        if self._path_index is None or self._stall_count is None or len(self._paths) != len(guides):
            self._paths = [None] * len(guides)
            self._path_index = np.zeros(len(guides), dtype=int)
            self._stall_count = np.zeros(len(guides), dtype=int)
        remaining = np.zeros(len(guides), dtype=float)
        epsilon = float(self.route_config.waypoint_epsilon)
        path_lengths: list[float] = []
        waypoint_counts: list[int] = []
        progress_values: list[float] = []
        for index, active in enumerate(active_mask):
            if not active:
                continue
            path = self._ensure_path(index, guides[index], assigned_targets[index])
            if path is None:
                modes[index] = ROUTE_GEODESIC_FALLBACK
                stats["geodesic_fallback_count"] = int(stats["geodesic_fallback_count"]) + 1
                self._geo_stats["geodesic_fallback_steps"] = int(self._geo_stats["geodesic_fallback_steps"]) + 1
                continue
            cursor = int(self._path_index[index])
            while cursor < len(path) - 1 and float(np.linalg.norm(path[cursor] - guides[index])) <= epsilon:
                cursor += 1
            self._path_index[index] = cursor
            waypoints[index] = path[cursor]
            last = cursor >= len(path) - 1
            modes[index] = ROUTE_FINAL_TARGET if last else ROUTE_FOLLOW_WAYPOINT
            leftover = remaining_path_length(path, cursor, guides[index])
            remaining[index] = leftover
            total = leftover + float(np.sum(np.linalg.norm(np.diff(path[: cursor + 1], axis=0), axis=1))) if cursor else leftover
            progress = 1.0 if total <= 1.0e-9 else max(0.0, min(1.0, 1.0 - leftover / total))
            path_lengths.append(float(np.sum(np.linalg.norm(np.diff(path, axis=0), axis=1))))
            waypoint_counts.append(int(len(path)))
            progress_values.append(progress)
            stats["geodesic_active_count"] = int(stats["geodesic_active_count"]) + 1
            self._geo_stats["geodesic_path_guide_steps"] = int(self._geo_stats["geodesic_path_guide_steps"]) + 1
            self._geo_stats["geodesic_path_length_sum"] = float(self._geo_stats["geodesic_path_length_sum"]) + path_lengths[-1]
            self._geo_stats["geodesic_waypoint_count_sum"] = float(self._geo_stats["geodesic_waypoint_count_sum"]) + waypoint_counts[-1]
            self._geo_stats["geodesic_progress_sum"] = float(self._geo_stats["geodesic_progress_sum"]) + progress
        wait = conflict_wait_mask(
            guides,
            waypoints,
            remaining,
            active_mask,
            float(self.safety_config.min_guide_distance),
        )
        if np.any(wait):
            waypoints[wait] = guides[wait]
            for index in np.flatnonzero(wait):
                modes[int(index)] = ROUTE_WAIT
                self._geo_stats["geodesic_wait_steps"] = int(self._geo_stats["geodesic_wait_steps"]) + 1
            stats["geodesic_wait_count"] = int(np.count_nonzero(wait))
        if path_lengths:
            stats["geodesic_mean_path_length"] = float(np.mean(path_lengths))
            stats["geodesic_mean_waypoint_count"] = float(np.mean(waypoint_counts))
            stats["geodesic_mean_progress"] = float(np.mean(progress_values))
        return waypoints, modes, stats

    def _ensure_path(self, index: int, position: Array, target: Array) -> Array | None:
        existing = self._paths[index]
        if existing is not None:
            return existing
        if self._room_polygon is None:
            return None
        planned = visibility_shortest_path(
            position,
            target,
            self._obstacle,
            self._room_polygon,
            static_graph=self._vis_graph,
        )
        if planned is None:
            self._paths[index] = None
            return None
        self._paths[index] = planned.waypoints
        if self._path_index is not None:
            self._path_index[index] = 1 if len(planned.waypoints) > 1 else 0
        return planned.waypoints

    def _update_geodesic_stall(
        self,
        guides: Array,
        waypoints: Array,
        modes: list[str],
        active_mask: Array,
        nominal: Array,
        applied: Array,
        safety_status: str,
    ) -> None:
        if self._stall_count is None or self._path_index is None:
            return
        eta = float(self.route_config.replan_speed_ratio)
        horizon = int(self.route_config.replan_stall_steps)
        replans = 0
        for index, active in enumerate(active_mask):
            if not active or modes[index] != ROUTE_FOLLOW_WAYPOINT:
                self._stall_count[index] = 0
                continue
            nom = float(np.linalg.norm(nominal[index]))
            app = float(np.linalg.norm(applied[index]))
            ratio = app / nom if nom > 1.0e-12 else 1.0
            stalled = safety_status == "PROJECTED" and ratio < eta
            if stalled:
                self._stall_count[index] += 1
            else:
                self._stall_count[index] = 0
            if int(self._stall_count[index]) >= horizon:
                self._paths[index] = None
                self._stall_count[index] = 0
                replans += 1
                self._geo_stats["geodesic_replan_count"] = int(self._geo_stats["geodesic_replan_count"]) + 1
        if replans:
            self._last_route_diagnostics["geodesic_replan_now"] = int(replans)

    def _record_projection_kinds(self, safety_status: str, type_residuals_before: dict[str, Array]) -> None:
        if safety_status != "PROJECTED":
            return
        tol = float(self.safety_config.residual_tolerance)
        for kind, key in (
            ("crowd", "crowd_projection_steps"),
            ("guide_pair", "guide_pair_projection_steps"),
            ("room", "room_projection_steps"),
        ):
            values = type_residuals_before.get(kind, np.empty(0))
            if len(values) and float(np.max(values)) > tol:
                self._geo_stats[key] = int(self._geo_stats[key]) + 1

    def _finalize_geo_stats(self) -> dict[str, object]:
        guide_steps = int(self._geo_stats["geodesic_path_guide_steps"])

        def _mean(total_key: str) -> float:
            if guide_steps <= 0:
                return 0.0
            return float(self._geo_stats[total_key]) / float(guide_steps)

        return {
            "geodesic_enabled": bool(self.route_config.geodesic_enabled),
            "geodesic_path_guide_steps": guide_steps,
            "geodesic_fallback_steps": int(self._geo_stats["geodesic_fallback_steps"]),
            "geodesic_wait_steps": int(self._geo_stats["geodesic_wait_steps"]),
            "geodesic_replan_count": int(self._geo_stats["geodesic_replan_count"]),
            "geodesic_mean_path_length": _mean("geodesic_path_length_sum"),
            "geodesic_mean_waypoint_count": _mean("geodesic_waypoint_count_sum"),
            "geodesic_mean_progress": _mean("geodesic_progress_sum"),
            "route_crowd_projection_steps": int(self._geo_stats["crowd_projection_steps"]),
            "route_guide_pair_projection_steps": int(self._geo_stats["guide_pair_projection_steps"]),
            "route_room_projection_steps": int(self._geo_stats["room_projection_steps"]),
        }


__all__ = ["RouteAwareABCGv2Controller"]
