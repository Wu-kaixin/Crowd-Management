from __future__ import annotations

import numpy as np

from crowd_management.controllers.boundary_route import (
    ROUTE_DIRECT,
    ROUTE_FINAL_APPROACH,
    ROUTE_FOLLOW_BOUNDARY,
    ROUTE_FOLLOW_DEPLOYMENT,
    BoundaryRouteConfig,
    TransitCurve,
    build_transit_curve,
    line_of_sight_clear,
    plan_route_waypoints,
    project_onto_curve,
    shorter_arc_direction,
)
from crowd_management.geometry.arclength import resample_closed_curve_by_arclength
from crowd_management.geometry.deployment_curve import DeploymentCurve, build_deployment_curve


def _rectangle_transit() -> TransitCurve:
    vertices = np.array(
        [
            [8.0, 5.0],
            [12.0, 5.0],
            [12.0, 15.0],
            [8.0, 15.0],
        ],
        dtype=float,
    )
    curve, arc_s, length, tangents, _normals = resample_closed_curve_by_arclength(vertices, spacing=0.2)
    return TransitCurve(
        curve_points=curve,
        arc_s=arc_s,
        length=float(length),
        tangents=tangents,
        clearance=0.25,
        diagnostics={"status": "VALID"},
    )


def test_line_of_sight_rejects_chord_through_crowd() -> None:
    crowd = np.column_stack((np.full(25, 10.0), np.linspace(6.0, 14.0, 25)))
    assert line_of_sight_clear(
        np.array([5.0, 10.0]),
        np.array([15.0, 10.0]),
        crowd,
        clearance=0.85,
        room_size=np.array([20.0, 20.0]),
        wall_margin=0.25,
    ) is False
    assert line_of_sight_clear(
        np.array([5.0, 10.0]),
        np.array([5.0, 16.0]),
        crowd,
        clearance=0.85,
        room_size=np.array([20.0, 20.0]),
        wall_margin=0.25,
    ) is True


def test_shorter_arc_picks_the_minor_periodic_direction() -> None:
    direction, remaining = shorter_arc_direction(
        np.array([0.0, 0.0]),
        np.array([3.0, 8.0]),
        length=10.0,
    )
    assert np.allclose(direction, [1.0, -1.0])
    assert np.allclose(remaining, [3.0, 2.0])


def test_blocked_guide_is_sent_along_transit_not_through_crowd() -> None:
    transit = _rectangle_transit()
    crowd = np.column_stack((np.full(30, 10.0), np.linspace(6.0, 14.0, 30)))
    positions = np.array([[5.0, 10.0]])
    targets = np.array([[15.0, 10.0]])
    plan = plan_route_waypoints(
        positions,
        targets,
        np.array([True]),
        transit,
        crowd,
        BoundaryRouteConfig(),
        clearance=0.85,
        room_size=np.array([20.0, 20.0]),
        wall_margin=0.25,
    )
    assert plan.modes[0] in {ROUTE_FOLLOW_BOUNDARY, "APPROACH_RING"}
    assert plan.modes[0] != ROUTE_DIRECT
    waypoint = plan.waypoints[0]
    # The commanded waypoint must not sit on the far side of the crowd strip.
    assert waypoint[0] < 12.5
    chord_hits_crowd = not line_of_sight_clear(
        positions[0],
        waypoint,
        crowd,
        clearance=0.85,
        room_size=np.array([20.0, 20.0]),
        wall_margin=0.25,
    )
    assert chord_hits_crowd is False


def test_clear_line_of_sight_stays_direct() -> None:
    transit = _rectangle_transit()
    crowd = np.array([[10.0, 10.0]])
    positions = np.array([[8.0, 2.0]])
    targets = np.array([[12.0, 2.0]])
    plan = plan_route_waypoints(
        positions,
        targets,
        np.array([True]),
        transit,
        crowd,
        BoundaryRouteConfig(),
        clearance=0.85,
        room_size=np.array([20.0, 20.0]),
        wall_margin=0.25,
    )
    assert plan.modes == (ROUTE_DIRECT,)
    assert np.allclose(plan.waypoints, targets)


def test_near_target_foot_commands_final_approach_not_outer_ring() -> None:
    angles = np.linspace(0.0, 2.0 * np.pi, 180, endpoint=False)
    curve = np.column_stack((10.0 + 4.0 * np.cos(angles), 10.0 + 4.0 * np.sin(angles)))
    resampled, arc_s, length, tangents, _normals = resample_closed_curve_by_arclength(curve, spacing=0.12)
    transit = TransitCurve(
        curve_points=resampled,
        arc_s=arc_s,
        length=float(length),
        tangents=tangents,
        clearance=0.0,
        diagnostics={"status": "VALID"},
    )
    crowd_angles = np.linspace(0.0, 2.0 * np.pi, 80, endpoint=False)
    crowd = np.column_stack((10.0 + 3.15 * np.cos(crowd_angles), 10.0 + 3.15 * np.sin(crowd_angles)))
    positions = np.array([[6.0, 10.0]])
    targets = np.array([[6.20, 10.0]])
    plan = plan_route_waypoints(
        positions,
        targets,
        np.array([True]),
        transit,
        crowd,
        BoundaryRouteConfig(),
        clearance=0.85,
        room_size=np.array([20.0, 20.0]),
        wall_margin=0.25,
    )
    assert plan.modes == (ROUTE_FINAL_APPROACH,)
    assert np.allclose(plan.waypoints, targets)


def test_follow_waypoint_does_not_use_inward_chord_on_a_circle() -> None:
    angles = np.linspace(0.0, 2.0 * np.pi, 180, endpoint=False)
    curve = np.column_stack((10.0 + 4.0 * np.cos(angles), 10.0 + 4.0 * np.sin(angles)))
    resampled, arc_s, length, tangents, _normals = resample_closed_curve_by_arclength(curve, spacing=0.12)
    transit = TransitCurve(
        curve_points=resampled,
        arc_s=arc_s,
        length=float(length),
        tangents=tangents,
        clearance=0.0,
        diagnostics={"status": "FALLBACK_DEPLOYMENT_CURVE"},
    )
    crowd_angles = np.linspace(0.0, 2.0 * np.pi, 80, endpoint=False)
    crowd = np.column_stack((10.0 + 3.15 * np.cos(crowd_angles), 10.0 + 3.15 * np.sin(crowd_angles)))
    positions = np.array([[6.0, 10.0]])
    targets = np.array([[14.0, 10.0]])
    plan = plan_route_waypoints(
        positions,
        targets,
        np.array([True]),
        transit,
        crowd,
        BoundaryRouteConfig(lookahead=0.8, approach_radius=0.40),
        clearance=0.85,
        room_size=np.array([20.0, 20.0]),
        wall_margin=0.25,
    )
    assert plan.modes[0] == ROUTE_FOLLOW_BOUNDARY
    assert line_of_sight_clear(
        positions[0],
        plan.waypoints[0],
        crowd,
        clearance=0.85,
        room_size=np.array([20.0, 20.0]),
        wall_margin=0.25,
    )
    assert float(np.linalg.norm(plan.waypoints[0] - np.array([10.0, 10.0]))) >= 3.95


def test_leaky_estimate_uses_covering_hull_for_transit() -> None:
    inner = np.array([[9.0, 9.0], [11.0, 9.0], [11.0, 11.0], [9.0, 11.0]], dtype=float)
    angles = np.linspace(0.0, 2.0 * np.pi, 36, endpoint=False)
    crowd = np.vstack(
        (
            np.column_stack((10.0 + 0.55 * np.cos(angles), 10.0 + 0.55 * np.sin(angles))),
            np.array([[12.6, 10.0]]),
        )
    )
    fallback = build_deployment_curve(inner, 0.85, crowd_points=crowd, min_crowd_clearance=None)
    assert isinstance(fallback, DeploymentCurve)
    transit = build_transit_curve(
        inner,
        0.85,
        0.25,
        crowd_points=crowd,
        fallback=fallback,
    )
    assert transit is not None
    assert transit.diagnostics.get("construction") == "crowd_hull_buffer"
    assert float(transit.clearance) >= 0.0
    distances = np.linalg.norm(transit.curve_points[:, None, :] - crowd[None, :, :], axis=2)
    assert float(np.min(distances)) + 1.0e-9 >= 0.85


def test_blocked_outer_foot_follows_inner_deployment_not_chord() -> None:
    outer = _rectangle_transit()
    inner_vertices = np.array(
        [
            [8.4, 5.4],
            [11.6, 5.4],
            [11.6, 14.6],
            [8.4, 14.6],
        ],
        dtype=float,
    )
    curve, arc_s, length, tangents, _normals = resample_closed_curve_by_arclength(
        inner_vertices, spacing=0.2
    )
    inner = TransitCurve(
        curve_points=curve,
        arc_s=arc_s,
        length=float(length),
        tangents=tangents,
        clearance=0.0,
        diagnostics={"status": "DEPLOYMENT_INNER"},
    )
    crowd = np.column_stack((np.full(30, 10.0), np.linspace(6.0, 14.0, 30)))
    positions = np.array([[12.0, 10.0]])
    targets = np.array([[10.2, 10.0]])
    plan = plan_route_waypoints(
        positions,
        targets,
        np.array([True]),
        outer,
        crowd,
        BoundaryRouteConfig(),
        clearance=0.85,
        room_size=np.array([20.0, 20.0]),
        wall_margin=0.25,
        inner=inner,
    )
    assert plan.modes == (ROUTE_FOLLOW_DEPLOYMENT,)
    assert not np.allclose(plan.waypoints, targets)
    assert line_of_sight_clear(
        positions[0],
        plan.waypoints[0],
        crowd,
        clearance=0.85,
        room_size=np.array([20.0, 20.0]),
        wall_margin=0.25,
    )
    assert plan.waypoints[0, 0] > 10.5


def test_project_onto_curve_returns_nearest_sample() -> None:
    transit = _rectangle_transit()
    projected, arc_s, distance = project_onto_curve(
        np.array([[7.0, 10.0]]),
        transit.curve_points,
        transit.arc_s,
    )
    assert projected.shape == (1, 2)
    assert np.isfinite(arc_s[0])
    assert distance[0] < 1.5
    assert projected[0, 0] == np.min(transit.curve_points[:, 0]) or abs(
        projected[0, 0] - 8.0
    ) < 0.3
