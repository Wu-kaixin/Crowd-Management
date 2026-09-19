"""Visibility-graph geodesic around an estimated crowd obstacle.

ROLE: CORE MATH — shortest path in ``Omega_env \\ (O_hat_crowd ⊕ B(d_safe))``.
Never reads spawn polygons or evaluator truth.  PR5 remains the last filter.
"""
from __future__ import annotations

from dataclasses import dataclass
import heapq

import numpy as np
from shapely.geometry import LineString, MultiPoint, MultiPolygon, Point, Polygon, box
from shapely.ops import nearest_points, unary_union

from ..types import Array

ROUTE_FOLLOW_WAYPOINT = "FOLLOW_WAYPOINT"
ROUTE_FINAL_TARGET = "FINAL_TARGET"
ROUTE_WAIT = "WAIT"
ROUTE_GEODESIC_FALLBACK = "GEODESIC_FALLBACK"

_SNAP_EPS = 1.0e-3
_INTERIOR_SHRINK = 1.0e-8


@dataclass(frozen=True)
class GeodesicPath:
    """One guide's polyline from the current pose to its CVT target."""

    waypoints: Array
    length: float
    diagnostics: dict[str, object]


def inflate_estimated_obstacle(crowd_curve: Array, clearance: float, *, simplify: float = 0.12):
    """Return ``O_hat ⊕ B(d_safe)`` from the estimated crowd polygon only."""
    vertices = np.asarray(crowd_curve, dtype=float)
    if vertices.ndim != 2 or vertices.shape[1] != 2 or len(vertices) < 3 or not np.all(np.isfinite(vertices)):
        return None
    radius = float(clearance)
    if not np.isfinite(radius) or radius < 0.0:
        raise ValueError("clearance must be finite and non-negative.")
    polygon = Polygon(vertices)
    if polygon.is_empty:
        return None
    if not polygon.is_valid:
        polygon = polygon.buffer(0)
    if polygon.is_empty:
        return None
    inflated = polygon.buffer(radius, join_style=1, cap_style=1)
    if inflated.is_empty:
        return None
    if simplify > 0.0:
        inflated = inflated.simplify(float(simplify), preserve_topology=True)
    if inflated.is_empty:
        return None
    return inflated


def inflate_observation_cloud(crowd_points: Array, clearance: float, *, simplify: float = 0.12):
    """Return ``{p_j} ⊕ B(d_safe)`` from the controller observation, never spawn/truth."""
    points = np.asarray(crowd_points, dtype=float)
    if points.ndim != 2 or points.shape[1] != 2 or len(points) == 0 or not np.all(np.isfinite(points)):
        return None
    radius = float(clearance)
    if not np.isfinite(radius) or radius < 0.0:
        raise ValueError("clearance must be finite and non-negative.")
    cloud = MultiPoint([(float(row[0]), float(row[1])) for row in points])
    inflated = cloud.buffer(radius, join_style=1, cap_style=1)
    if inflated.is_empty:
        return None
    if simplify > 0.0:
        inflated = inflated.simplify(float(simplify), preserve_topology=True)
    if inflated.is_empty:
        return None
    return inflated


def workspace_polygon(room_size: Array, wall_margin: float) -> Polygon:
    room = np.asarray(room_size, dtype=float)
    margin = float(wall_margin)
    if room.shape != (2,) or not np.all(np.isfinite(room)) or not np.isfinite(margin) or margin < 0.0:
        raise ValueError("room_size and wall_margin must be finite.")
    return box(margin, margin, float(room[0]) - margin, float(room[1]) - margin)


def segment_in_free_space(start: Array, end: Array, obstacle, room: Polygon) -> bool:
    """True iff the open segment stays in the room and out of the obstacle interior."""
    origin = np.asarray(start, dtype=float)
    finish = np.asarray(end, dtype=float)
    if origin.shape != (2,) or finish.shape != (2,):
        raise ValueError("segment endpoints must be length-2.")
    if float(np.linalg.norm(finish - origin)) <= 1.0e-12:
        return True
    line = LineString([(float(origin[0]), float(origin[1])), (float(finish[0]), float(finish[1]))])
    if not room.covers(line):
        return False
    if obstacle is None or obstacle.is_empty:
        return True
    interior = obstacle.buffer(-_INTERIOR_SHRINK)
    if interior.is_empty:
        return True
    return not interior.intersects(line)


def snap_to_free_space(point: Array, obstacle, room: Polygon) -> Array:
    """Project an interior pose onto the obstacle boundary, slightly outward."""
    pose = np.asarray(point, dtype=float)
    if pose.shape != (2,):
        raise ValueError("point must be length-2.")
    if obstacle is None or obstacle.is_empty:
        return pose.copy()
    location = Point(float(pose[0]), float(pose[1]))
    if not obstacle.contains(location):
        return pose.copy()
    _, boundary = nearest_points(location, obstacle.boundary)
    snapped = np.array(boundary.coords[0], dtype=float)
    outward = snapped - pose
    norm = float(np.linalg.norm(outward))
    if norm <= 1.0e-12:
        centroid = np.array(obstacle.centroid.coords[0], dtype=float)
        outward = snapped - centroid
        norm = float(np.linalg.norm(outward))
    if norm > 1.0e-12:
        snapped = snapped + (_SNAP_EPS / norm) * outward
    if not room.covers(Point(float(snapped[0]), float(snapped[1]))):
        return np.array(boundary.coords[0], dtype=float)
    return snapped


def _polygon_vertices(geometry) -> Array:
    parts: list[Array] = []
    geoms = geometry.geoms if isinstance(geometry, MultiPolygon) else (geometry,)
    for geom in geoms:
        if geom.is_empty or geom.geom_type != "Polygon":
            continue
        coords = np.asarray(geom.exterior.coords, dtype=float)
        if len(coords) >= 2 and np.allclose(coords[0], coords[-1]):
            coords = coords[:-1]
        if len(coords):
            parts.append(coords)
        for interior in geom.interiors:
            hole = np.asarray(interior.coords, dtype=float)
            if len(hole) >= 2 and np.allclose(hole[0], hole[-1]):
                hole = hole[:-1]
            if len(hole):
                parts.append(hole)
    if not parts:
        return np.empty((0, 2), dtype=float)
    return np.vstack(parts)


def _unique_nodes(points: Array, *, tol: float = 1.0e-8) -> Array:
    nodes: list[Array] = []
    for row in np.asarray(points, dtype=float):
        if not np.all(np.isfinite(row)):
            continue
        if any(float(np.linalg.norm(row - existing)) <= tol for existing in nodes):
            continue
        nodes.append(row.copy())
    if not nodes:
        return np.empty((0, 2), dtype=float)
    return np.vstack(nodes)


@dataclass(frozen=True)
class StaticVisibilityGraph:
    """Obstacle + workspace vertices and their mutual visibility edges."""

    nodes: Array
    adjacency: list[list[tuple[int, float]]]


def build_static_visibility_graph(obstacle, room: Polygon) -> StaticVisibilityGraph:
    candidates: list[Array] = []
    if obstacle is not None and not obstacle.is_empty:
        vertices = _polygon_vertices(obstacle)
        if len(vertices):
            candidates.append(vertices)
    room_vertices = _polygon_vertices(room)
    if len(room_vertices):
        candidates.append(room_vertices)
    if not candidates:
        return StaticVisibilityGraph(nodes=np.empty((0, 2), dtype=float), adjacency=[])
    nodes = _unique_nodes(np.vstack(candidates))
    adjacency: list[list[tuple[int, float]]] = [[] for _ in range(len(nodes))]
    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            if not segment_in_free_space(nodes[i], nodes[j], obstacle, room):
                continue
            weight = float(np.linalg.norm(nodes[j] - nodes[i]))
            adjacency[i].append((j, weight))
            adjacency[j].append((i, weight))
    return StaticVisibilityGraph(nodes=nodes, adjacency=adjacency)


def _dijkstra(nodes: Array, adjacency: list[list[tuple[int, float]]], start: int, goal: int) -> Array | None:
    count = len(nodes)
    distance = np.full(count, np.inf, dtype=float)
    previous = np.full(count, -1, dtype=int)
    distance[start] = 0.0
    heap: list[tuple[float, int]] = [(0.0, start)]
    while heap:
        cost, index = heapq.heappop(heap)
        if cost > float(distance[index]) + 1.0e-12:
            continue
        if index == goal:
            break
        for neighbor, weight in adjacency[index]:
            candidate = cost + float(weight)
            if candidate + 1.0e-12 < float(distance[neighbor]):
                distance[neighbor] = candidate
                previous[neighbor] = index
                heapq.heappush(heap, (candidate, neighbor))
    if not np.isfinite(distance[goal]):
        return None
    chain: list[int] = []
    cursor = goal
    while cursor >= 0:
        chain.append(cursor)
        cursor = int(previous[cursor])
    chain.reverse()
    return nodes[np.asarray(chain, dtype=int)].copy()


def _connect_query_nodes(
    origin: Array,
    target: Array,
    static: StaticVisibilityGraph,
    obstacle,
    room: Polygon,
) -> tuple[Array, list[list[tuple[int, float]]], int, int]:
    extra = [origin]
    if float(np.linalg.norm(target - origin)) > 1.0e-12:
        extra.append(target)
    nodes = static.nodes if len(static.nodes) else np.empty((0, 2), dtype=float)
    if len(nodes):
        nodes = np.vstack((nodes, np.asarray(extra, dtype=float)))
    else:
        nodes = np.asarray(extra, dtype=float)
    adjacency: list[list[tuple[int, float]]] = [list(neighbors) for neighbors in static.adjacency]
    while len(adjacency) < len(nodes):
        adjacency.append([])
    start_id = len(static.nodes)
    goal_id = start_id if len(extra) == 1 else start_id + 1
    query_ids = (start_id,) if goal_id == start_id else (start_id, goal_id)
    for query in query_ids:
        for index in range(len(static.nodes)):
            if not segment_in_free_space(nodes[query], nodes[index], obstacle, room):
                continue
            weight = float(np.linalg.norm(nodes[query] - nodes[index]))
            adjacency[query].append((index, weight))
            adjacency[index].append((query, weight))
    if goal_id != start_id and segment_in_free_space(origin, target, obstacle, room):
        weight = float(np.linalg.norm(target - origin))
        adjacency[start_id].append((goal_id, weight))
        adjacency[goal_id].append((start_id, weight))
    return nodes, adjacency, start_id, goal_id


def visibility_shortest_path(
    start: Array,
    goal: Array,
    obstacle,
    room: Polygon,
    static_graph: StaticVisibilityGraph | None = None,
) -> GeodesicPath | None:
    """Return the Euclidean shortest path on the polygon visibility graph."""
    origin = snap_to_free_space(start, obstacle, room)
    raw_goal = np.asarray(goal, dtype=float)
    target = snap_to_free_space(raw_goal, obstacle, room)
    planned: GeodesicPath | None
    if segment_in_free_space(origin, target, obstacle, room):
        waypoints = np.vstack((origin, target))
        planned = GeodesicPath(
            waypoints=waypoints,
            length=float(np.linalg.norm(target - origin)),
            diagnostics={"status": "DIRECT", "node_count": 2, "edge_count": 1},
        )
    else:
        graph = static_graph if static_graph is not None else build_static_visibility_graph(obstacle, room)
        nodes, adjacency, start_id, goal_id = _connect_query_nodes(origin, target, graph, obstacle, room)
        if len(nodes) < 2:
            planned = None
        else:
            polyline = _dijkstra(nodes, adjacency, start_id, goal_id)
            if polyline is None or len(polyline) < 2:
                planned = None
            else:
                length = float(np.sum(np.linalg.norm(np.diff(polyline, axis=0), axis=1)))
                edges = sum(len(neighbors) for neighbors in adjacency) // 2
                planned = GeodesicPath(
                    waypoints=polyline,
                    length=length,
                    diagnostics={"status": "VISIBLE", "node_count": int(len(nodes)), "edge_count": int(edges)},
                )
    if planned is None:
        return None
    if float(np.linalg.norm(planned.waypoints[-1] - raw_goal)) > 1.0e-9:
        planned = GeodesicPath(
            waypoints=np.vstack((planned.waypoints, raw_goal)),
            length=float(planned.length + np.linalg.norm(raw_goal - planned.waypoints[-1])),
            diagnostics=dict(planned.diagnostics) | {"terminal": "TRUE_TARGET"},
        )
    return planned


def remaining_path_length(path: Array, index: int, position: Array) -> float:
    samples = np.asarray(path, dtype=float)
    pose = np.asarray(position, dtype=float)
    cursor = min(max(int(index), 0), max(len(samples) - 1, 0))
    if len(samples) == 0:
        return 0.0
    length = float(np.linalg.norm(samples[cursor] - pose))
    if cursor + 1 < len(samples):
        length += float(np.sum(np.linalg.norm(np.diff(samples[cursor:], axis=0), axis=1)))
    return length


def conflict_wait_mask(
    positions: Array,
    waypoints: Array,
    remaining: Array,
    active_mask: Array,
    min_guide_distance: float,
) -> Array:
    """Deterministic wait: longer remaining path yields; higher id breaks ties."""
    current = np.asarray(positions, dtype=float)
    goals = np.asarray(waypoints, dtype=float)
    left = np.asarray(remaining, dtype=float)
    active = np.asarray(active_mask, dtype=bool)
    wait = np.zeros(len(current), dtype=bool)
    threshold = 1.5 * float(min_guide_distance)
    ids = np.flatnonzero(active)
    for a_pos, i in enumerate(ids):
        for j in ids[a_pos + 1 :]:
            gap = float(np.linalg.norm(current[j] - current[i]))
            if gap > threshold:
                continue
            ui = goals[i] - current[i]
            uj = goals[j] - current[j]
            ni = float(np.linalg.norm(ui))
            nj = float(np.linalg.norm(uj))
            if ni <= 1.0e-9 or nj <= 1.0e-9:
                continue
            toward = float(np.dot(current[j] - current[i], ui)) > 0.0 and float(
                np.dot(current[i] - current[j], uj)
            ) > 0.0
            opposing = float(np.dot(ui, uj)) / (ni * nj) < -0.2
            if not (toward or opposing):
                continue
            if float(left[i]) > float(left[j]) + 1.0e-9:
                wait[i] = True
            elif float(left[j]) > float(left[i]) + 1.0e-9:
                wait[j] = True
            elif int(i) > int(j):
                wait[i] = True
            else:
                wait[j] = True
    return wait


def union_obstacles(parts: list[object]):
    valid = [item for item in parts if item is not None and not getattr(item, "is_empty", True)]
    if not valid:
        return None
    return unary_union(valid)


__all__ = [
    "ROUTE_FINAL_TARGET",
    "ROUTE_FOLLOW_WAYPOINT",
    "ROUTE_GEODESIC_FALLBACK",
    "ROUTE_WAIT",
    "GeodesicPath",
    "StaticVisibilityGraph",
    "build_static_visibility_graph",
    "conflict_wait_mask",
    "inflate_estimated_obstacle",
    "inflate_observation_cloud",
    "remaining_path_length",
    "segment_in_free_space",
    "snap_to_free_space",
    "union_obstacles",
    "visibility_shortest_path",
    "workspace_polygon",
]
