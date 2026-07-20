from __future__ import annotations

import json

import numpy as np
from shapely.geometry import LineString

from crowd_management.controllers.routing import (
    RoutingConfig,
    build_pairwise_route_matrix,
    route_boundary_corridor,
    route_straight,
    route_visibility_graph,
)
from crowd_management.geometry.buffer import (
    BufferedPolygonGeometry,
    PolygonBufferConfig,
    build_polygon_buffer,
)
from crowd_management.geometry.free_space import (
    FreeSpaceConfig,
    GuideFreeSpace,
    build_guide_free_space,
)


def _square_free_space() -> tuple[BufferedPolygonGeometry, GuideFreeSpace]:
    source = np.array(
        [[4.0, 4.0], [6.0, 4.0], [6.0, 6.0], [4.0, 6.0]],
        dtype=float,
    )
    buffered = build_polygon_buffer(
        source,
        PolygonBufferConfig(
            clearance=0.5,
            join_style="mitre",
            room_size=(10.0, 10.0),
            room_margin=0.25,
        ),
    )
    assert isinstance(buffered, BufferedPolygonGeometry)
    free_space = build_guide_free_space(
        buffered,
        FreeSpaceConfig(room_size=(10.0, 10.0), room_margin=0.25),
    )
    assert isinstance(free_space, GuideFreeSpace)
    return buffered, free_space


def test_straight_route_reports_blocked_canonical_obstacle() -> None:
    _, free_space = _square_free_space()

    route = route_straight(np.array([1.0, 5.0]), np.array([6.5, 5.0]), free_space)

    assert route.status == "ROUTE_INFEASIBLE"
    assert route.terminal_reason == "STRAIGHT_PATH_BLOCKED"
    assert route.path_length is None
    assert route.waypoints.shape == (0, 2)


def test_visibility_graph_detours_and_is_deterministic() -> None:
    _, free_space = _square_free_space()
    start = np.array([1.0, 5.0])
    target = np.array([6.5, 5.0])

    first = route_visibility_graph(start, target, free_space)
    second = route_visibility_graph(start, target, free_space)

    assert first.status == "ROUTE_FEASIBLE"
    assert first.certificate is not None and first.certificate.valid
    assert first.path_length is not None
    assert first.path_length > np.linalg.norm(target - start)
    assert len(first.waypoints) >= 4
    assert np.array_equal(first.waypoints, second.waypoints)
    assert first.path_length == second.path_length


def test_u_shape_one_sided_start_reaches_inner_notch_only_with_visibility() -> None:
    source = np.array(
        [
            [2.0, 2.0],
            [8.0, 2.0],
            [8.0, 7.5],
            [6.6, 7.5],
            [6.6, 3.7],
            [3.4, 3.7],
            [3.4, 7.5],
            [2.0, 7.5],
        ],
        dtype=float,
    )
    buffered = build_polygon_buffer(
        source,
        PolygonBufferConfig(
            clearance=0.3,
            join_style="mitre",
            room_size=(10.0, 10.0),
            room_margin=0.2,
        ),
    )
    assert isinstance(buffered, BufferedPolygonGeometry)
    free_space = build_guide_free_space(
        buffered,
        FreeSpaceConfig(room_size=(10.0, 10.0), room_margin=0.2),
    )
    assert isinstance(free_space, GuideFreeSpace)
    one_sided_start = np.array([0.75, 6.0])
    inner_notch_target = np.array([6.3, 6.0])

    straight = route_straight(one_sided_start, inner_notch_target, free_space)
    visibility = route_visibility_graph(one_sided_start, inner_notch_target, free_space)

    assert buffered.forbidden_polygon.boundary.distance(
        LineString([inner_notch_target, inner_notch_target])
    ) <= 1.0e-12
    assert straight.status == "ROUTE_INFEASIBLE"
    assert visibility.status == "ROUTE_FEASIBLE"
    assert visibility.certificate is not None and visibility.certificate.valid
    assert visibility.path_length is not None
    assert visibility.path_length > np.linalg.norm(inner_notch_target - one_sided_start)


def test_boundary_corridor_follows_buffer_and_is_not_better_than_visibility() -> None:
    _, free_space = _square_free_space()
    start = np.array([1.0, 5.0])
    target = np.array([6.5, 5.0])

    corridor = route_boundary_corridor(start, target, free_space)
    visibility = route_visibility_graph(start, target, free_space)

    assert corridor.status == "ROUTE_FEASIBLE"
    assert corridor.certificate is not None and corridor.certificate.valid
    assert corridor.path_length is not None and visibility.path_length is not None
    assert corridor.path_length >= visibility.path_length - 1.0e-12
    assert any(
        free_space.forbidden_polygon.exterior.distance(LineString((first, second)))
        <= 1.0e-12
        for first, second in zip(corridor.waypoints[:-1], corridor.waypoints[1:], strict=True)
    )


def test_disconnected_free_space_is_retained_and_route_is_infeasible() -> None:
    wall = np.array(
        [[4.5, 0.0], [5.5, 0.0], [5.5, 10.0], [4.5, 10.0]],
        dtype=float,
    )
    buffered = build_polygon_buffer(
        wall,
        PolygonBufferConfig(clearance=0.0, join_style="mitre", room_size=(10.0, 10.0)),
    )
    assert isinstance(buffered, BufferedPolygonGeometry)
    free_space = build_guide_free_space(buffered, FreeSpaceConfig(room_size=(10.0, 10.0)))
    assert isinstance(free_space, GuideFreeSpace)

    route = route_visibility_graph(np.array([2.0, 5.0]), np.array([8.0, 5.0]), free_space)

    assert len(free_space.components) == 2
    assert free_space.diagnostics["disconnected"] is True
    assert route.status == "ROUTE_INFEASIBLE"
    assert route.terminal_reason == "DISCONNECTED_FREE_SPACE"


def test_target_on_buffer_boundary_is_legal_and_clearance_is_certified() -> None:
    buffered, free_space = _square_free_space()
    start = np.array([1.0, 5.0])
    target = np.array([3.5, 5.0])

    route = route_straight(start, target, free_space)

    assert buffered.forbidden_polygon.boundary.distance(LineString([target, target])) == 0.0
    assert route.status == "ROUTE_FEASIBLE"
    assert route.certificate is not None and route.certificate.valid
    assert route.certificate.geometry_sha256 == free_space.geometry_sha256
    assert route.certificate.measured_source_clearance >= (
        free_space.certified_crowd_clearance - route.certificate.tolerance
    )
    assert route.certificate.measured_room_wall_clearance >= (
        free_space.room_margin - route.certificate.tolerance
    )


def test_visibility_segments_satisfy_free_space_and_clearance_properties() -> None:
    _, free_space = _square_free_space()
    route = route_visibility_graph(
        np.array([1.0, 5.0]),
        np.array([6.5, 5.0]),
        free_space,
        RoutingConfig(clearance_tolerance=1.0e-7),
    )

    assert route.status == "ROUTE_FEASIBLE"
    assert route.component_id is not None
    component = free_space.components[route.component_id]
    for first, second in zip(route.waypoints[:-1], route.waypoints[1:], strict=True):
        segment = LineString((first, second))
        assert component.covers(segment)
        assert segment.distance(free_space.source_polygon) >= (
            free_space.certified_crowd_clearance - 1.0e-7
        )


def test_endpoint_inside_forbidden_polygon_fails_explicitly() -> None:
    _, free_space = _square_free_space()

    route = route_visibility_graph(np.array([5.0, 5.0]), np.array([3.5, 5.0]), free_space)

    assert route.status == "ROUTE_INFEASIBLE"
    assert route.terminal_reason == "GUIDE_OUTSIDE_FREE_SPACE"


def test_pairwise_route_matrix_preserves_partial_reachability_and_serializes_null() -> None:
    _, free_space = _square_free_space()
    result = build_pairwise_route_matrix(
        np.array([[1.0, 5.0]]),
        np.array([[3.5, 5.0], [6.5, 5.0]]),
        free_space,
        "straight",
    )

    assert result.status == "ROUTE_MATRIX_READY"
    assert result.reachable_mask.tolist() == [[True, False]]
    assert np.isfinite(result.path_cost_matrix[0, 0])
    assert np.isinf(result.path_cost_matrix[0, 1])
    payload = result.to_jsonable()
    assert payload["path_cost_matrix"][0][1] is None
    assert payload["reachable_mask"] == [[True, False]]
    json.dumps(payload, allow_nan=False)
