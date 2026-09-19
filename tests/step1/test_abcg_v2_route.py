from __future__ import annotations

import numpy as np

from crowd_management.controllers import (
    ABCGv2Config,
    ABCGv2Controller,
    AssignmentResult,
    BoundaryRouteConfig,
    RouteAwareABCGv2Controller,
    VelocitySafetyConfig,
    integrate_guide_positions,
)
from crowd_management.controllers.boundary_route import TransitCurve
from crowd_management.geometry.arclength import resample_closed_curve_by_arclength


def _identity_assignment(count: int) -> AssignmentResult:
    ids = np.arange(count, dtype=int)
    return AssignmentResult(
        guide_to_target=ids,
        target_to_guide=ids,
        reserve_guide_ids=np.empty(0, dtype=int),
        unmet_target_ids=np.empty(0, dtype=int),
        cost_matrix=np.zeros((count, count), dtype=float),
        total_cost=0.0,
        switch_count=0,
        status="VALID",
    )


def _crowd_wall() -> np.ndarray:
    xs = np.linspace(9.55, 10.45, 8)
    ys = np.linspace(4.0, 16.0, 49)
    grid_x, grid_y = np.meshgrid(xs, ys)
    return np.column_stack((grid_x.ravel(), grid_y.ravel()))


def _pinned_guides() -> np.ndarray:
    return np.array([[8.70, 10.0]])


def _transit() -> TransitCurve:
    vertices = np.array(
        [
            [7.5, 4.0],
            [12.5, 4.0],
            [12.5, 16.0],
            [7.5, 16.0],
        ],
        dtype=float,
    )
    curve, arc_s, length, tangents, _normals = resample_closed_curve_by_arclength(vertices, spacing=0.15)
    return TransitCurve(
        curve_points=curve,
        arc_s=arc_s,
        length=float(length),
        tangents=tangents,
        clearance=0.25,
        diagnostics={"status": "VALID"},
    )


def _safety() -> VelocitySafetyConfig:
    return VelocitySafetyConfig(
        enabled=True,
        min_guide_distance=0.6,
        min_crowd_distance=0.85,
        room_margin=0.25,
    )


def test_frozen_abcg_v2_pins_when_nominal_aims_through_crowd() -> None:
    guides = _pinned_guides()
    targets = np.array([[15.0, 10.0]])
    crowd = _crowd_wall()
    controller = ABCGv2Controller(ABCGv2Config(max_steps=25, v_max=1.0, k_p=1.5), _safety())
    controller.reset(targets, _identity_assignment(1), guides, room_size=np.array([20.0, 20.0]))
    positions = guides.copy()
    speeds = []
    for _ in range(20):
        output = controller.step(crowd, positions, dt=0.1)
        speeds.append(float(np.linalg.norm(output.safe_velocity[0])))
        positions = integrate_guide_positions(positions, output.safe_velocity, 0.1)
    assert float(np.mean(speeds[-10:])) < 0.25
    assert positions[0, 0] < 9.2
    assert abs(positions[0, 1] - 10.0) < 0.30


def test_route_aware_controller_creates_tangential_escape() -> None:
    guides = _pinned_guides()
    targets = np.array([[15.0, 10.0]])
    crowd = _crowd_wall()
    controller = RouteAwareABCGv2Controller(
        ABCGv2Config(max_steps=80, v_max=1.0, k_p=1.5),
        _safety(),
        BoundaryRouteConfig(transit_clearance=0.25, lookahead=0.8),
    )
    controller.set_transit_curve(_transit())
    controller.reset(targets, _identity_assignment(1), guides, room_size=np.array([20.0, 20.0]))
    positions = guides.copy()
    modes = []
    for _ in range(40):
        output = controller.step(crowd, positions, dt=0.1)
        modes.append(str(output.diagnostics.get("route_modes", ["DIRECT"])[0]))
        positions = integrate_guide_positions(positions, output.safe_velocity, 0.1)
    assert any(mode in {"APPROACH_RING", "FOLLOW_BOUNDARY"} for mode in modes)
    assert abs(positions[0, 1] - 10.0) > 0.35
    assert float(np.linalg.norm(positions[0] - guides[0])) > 0.4


def test_route_aware_episode_uses_pr5_and_does_not_cross_crowd() -> None:
    guides = np.array([[8.70, 10.0]])
    targets = np.array([[15.0, 10.0]])
    crowd = _crowd_wall()
    controller = RouteAwareABCGv2Controller(
        ABCGv2Config(max_steps=350, v_max=1.0, k_p=1.5, hold_steps=5),
        _safety(),
        BoundaryRouteConfig(),
    )
    episode = controller.run_fixed_target_episode(
        guides,
        targets,
        _identity_assignment(1),
        crowd_points=crowd,
        room_size=np.array([20.0, 20.0]),
        transit_curve=_transit(),
    )
    min_crowd = float(episode.diagnostics["minimum_guide_crowd_distance"])
    assert min_crowd + 1.0e-9 >= 0.85
    assert episode.diagnostics["safety_filter_status"] == "ENABLED_PR5"
    assert episode.diagnostics["control_law"] == "sat_vmax_kp_route_waypoint"
    # Must not tunnel through x=10 at y≈10 while still west of the wall.
    path = episode.positions[:, 0, :]
    mid_crossings = path[(np.abs(path[:, 0] - 10.0) < 0.4) & (np.abs(path[:, 1] - 10.0) < 1.0)]
    assert len(mid_crossings) == 0
