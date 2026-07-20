"""Deterministic free-space routing for ABCG-v2.1 static deployment."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import heapq
from typing import Literal

import numpy as np
from shapely.geometry import LineString, Point, Polygon

from ..geometry.free_space import FreeSpaceFailure, FreeSpaceResult, GuideFreeSpace
from ..types import Array


RouteMethod = Literal["straight", "boundary_corridor", "visibility_graph"]
ROUTE_METHODS: tuple[RouteMethod, ...] = (
    "straight",
    "boundary_corridor",
    "visibility_graph",
)


@dataclass(frozen=True)
class RoutingConfig:
    """Numerical tolerances for deterministic point-guide routing."""

    topology_tolerance: float = 1.0e-9
    clearance_tolerance: float = 2.0e-7
    tie_tolerance: float = 1.0e-12

    def __post_init__(self) -> None:
        for name in ("topology_tolerance", "clearance_tolerance", "tie_tolerance"):
            value = float(getattr(self, name))
            if not np.isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be finite and non-negative.")


@dataclass(frozen=True)
class ClearanceCertificate:
    """Exact Shapely checks tying one polyline to the canonical geometry."""

    geometry_sha256: str
    nominal_crowd_clearance: float
    required_crowd_clearance: float
    measured_source_clearance: float
    required_room_margin: float
    measured_room_wall_clearance: float
    endpoints_covered: bool
    all_segments_covered: bool
    segment_count: int
    tolerance: float
    valid: bool
    diagnostics: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class RoutePath:
    """One guide-to-target route or one explicit reachability failure."""

    guide_id: int
    target_id: int
    method: str
    waypoints: Array
    path_length: float | None
    component_id: int | None
    status: str
    terminal_reason: str
    certificate: ClearanceCertificate | None
    diagnostics: dict[str, object] = field(default_factory=dict)

    def to_jsonable(self) -> dict[str, object]:
        """Return strict-JSON-safe route evidence."""

        return {
            "guide_id": int(self.guide_id),
            "target_id": int(self.target_id),
            "method": self.method,
            "waypoints": np.asarray(self.waypoints, dtype=float).tolist(),
            "path_length": None if self.path_length is None else float(self.path_length),
            "component_id": None if self.component_id is None else int(self.component_id),
            "status": self.status,
            "terminal_reason": self.terminal_reason,
            "certificate": None if self.certificate is None else asdict(self.certificate),
            "diagnostics": dict(self.diagnostics),
        }


@dataclass(frozen=True)
class PairwiseRouteMatrix:
    """All guide-target routes with ``inf`` confined to in-memory costs."""

    guide_positions: Array
    target_positions: Array
    paths: tuple[tuple[RoutePath, ...], ...]
    path_cost_matrix: Array
    reachable_mask: Array
    method: str
    geometry_sha256: str
    status: str
    diagnostics: dict[str, object] = field(default_factory=dict)

    def to_jsonable(self) -> dict[str, object]:
        """Serialize unreachable costs as ``null`` plus an explicit mask."""

        costs = np.asarray(self.path_cost_matrix, dtype=float)
        reachable = np.asarray(self.reachable_mask, dtype=bool)
        safe_costs: list[list[float | None]] = [
            [float(costs[i, j]) if reachable[i, j] else None for j in range(costs.shape[1])]
            for i in range(costs.shape[0])
        ]
        return {
            "guide_positions": np.asarray(self.guide_positions, dtype=float).tolist(),
            "target_positions": np.asarray(self.target_positions, dtype=float).tolist(),
            "paths": [[path.to_jsonable() for path in row] for row in self.paths],
            "path_cost_matrix": safe_costs,
            "reachable_mask": reachable.tolist(),
            "method": self.method,
            "geometry_sha256": self.geometry_sha256,
            "status": self.status,
            "diagnostics": dict(self.diagnostics),
        }


def _point(values: Array) -> Array | None:
    point = np.asarray(values, dtype=float)
    if point.shape != (2,) or not np.all(np.isfinite(point)):
        return None
    return point.copy()


def _points(values: Array, name: str) -> Array:
    points = np.asarray(values, dtype=float)
    if points.ndim != 2 or points.shape[1:] != (2,) or not np.all(np.isfinite(points)):
        raise ValueError(f"{name} must be a finite (N, 2) array.")
    return points.copy()


def _path_geometry(waypoints: Array) -> Point | LineString:
    return Point(waypoints[0]) if len(waypoints) == 1 else LineString(waypoints)


def _path_length(waypoints: Array) -> float:
    if len(waypoints) < 2:
        return 0.0
    return float(np.sum(np.linalg.norm(np.diff(waypoints, axis=0), axis=1)))


def _covering_component_ids(
    point: Array,
    free_space: GuideFreeSpace,
    tolerance: float,
) -> tuple[int, ...]:
    geometry = Point(point)
    covered: list[int] = []
    for component_id, component in enumerate(free_space.components):
        if component.covers(geometry):
            covered.append(component_id)
        elif (
            component.distance(geometry) <= tolerance
            and not free_space.forbidden_polygon.contains(geometry)
            and free_space.feasible_room.buffer(tolerance).covers(geometry)
        ):
            covered.append(component_id)
    return tuple(covered)


def _certificate(
    waypoints: Array,
    start: Array,
    target: Array,
    component: Polygon,
    free_space: GuideFreeSpace,
    config: RoutingConfig,
) -> ClearanceCertificate:
    tolerance = float(config.clearance_tolerance)
    geometry = _path_geometry(waypoints)
    endpoint_tolerance = max(float(config.topology_tolerance), tolerance)
    endpoints_covered = bool(
        np.linalg.norm(waypoints[0] - start) <= endpoint_tolerance
        and np.linalg.norm(waypoints[-1] - target) <= endpoint_tolerance
        and component.covers(Point(waypoints[0]))
        and component.covers(Point(waypoints[-1]))
    )
    segments_covered = True
    for first, second in zip(waypoints[:-1], waypoints[1:], strict=True):
        if np.linalg.norm(second - first) <= config.topology_tolerance:
            continue
        if not component.covers(LineString((first, second))):
            segments_covered = False
            break
    source_clearance = float(geometry.distance(free_space.source_polygon))
    room_clearance = float(geometry.distance(free_space.physical_room.boundary))
    required_clearance = float(free_space.certified_crowd_clearance)
    clearance_valid = source_clearance + tolerance >= required_clearance
    room_valid = room_clearance + tolerance >= free_space.room_margin
    covered = bool(component.covers(geometry) and segments_covered)
    valid = bool(
        endpoints_covered
        and covered
        and clearance_valid
        and room_valid
        and np.isfinite(source_clearance)
        and np.isfinite(room_clearance)
    )
    return ClearanceCertificate(
        geometry_sha256=free_space.geometry_sha256,
        nominal_crowd_clearance=float(free_space.nominal_crowd_clearance),
        required_crowd_clearance=required_clearance,
        measured_source_clearance=source_clearance,
        required_room_margin=float(free_space.room_margin),
        measured_room_wall_clearance=room_clearance,
        endpoints_covered=endpoints_covered,
        all_segments_covered=covered,
        segment_count=max(0, len(waypoints) - 1),
        tolerance=tolerance,
        valid=valid,
        diagnostics={
            "clearance_reference": "canonical_source_polygon",
            "room_reference": "physical_room_boundary",
            "free_space_test": "polygon_covers_each_segment",
        },
    )


def _failure_route(
    guide_id: int,
    target_id: int,
    method: str,
    reason: str,
    **diagnostics: object,
) -> RoutePath:
    return RoutePath(
        guide_id=int(guide_id),
        target_id=int(target_id),
        method=method,
        waypoints=np.empty((0, 2), dtype=float),
        path_length=None,
        component_id=None,
        status="ROUTE_INFEASIBLE",
        terminal_reason=reason,
        certificate=None,
        diagnostics={"reason": reason, **diagnostics},
    )


def _success_route(
    guide_id: int,
    target_id: int,
    method: str,
    waypoints: Array,
    component_id: int,
    certificate: ClearanceCertificate,
    **diagnostics: object,
) -> RoutePath:
    return RoutePath(
        guide_id=int(guide_id),
        target_id=int(target_id),
        method=method,
        waypoints=np.asarray(waypoints, dtype=float),
        path_length=_path_length(waypoints),
        component_id=int(component_id),
        status="ROUTE_FEASIBLE",
        terminal_reason="route_certified",
        certificate=certificate,
        diagnostics={"reason": "route_certified", **diagnostics},
    )


def _add_node(nodes: list[Array], point: Array, tolerance: float) -> int:
    for node_id, existing in enumerate(nodes):
        if np.linalg.norm(existing - point) <= tolerance:
            return node_id
    nodes.append(np.asarray(point, dtype=float).copy())
    return len(nodes) - 1


def _add_edge(adjacency: list[dict[int, float]], first: int, second: int, weight: float) -> None:
    if first == second or not np.isfinite(weight) or weight <= 0.0:
        return
    previous = adjacency[first].get(second)
    if previous is None or weight < previous:
        adjacency[first][second] = float(weight)
        adjacency[second][first] = float(weight)


def _segment_allowed(
    first: Array,
    second: Array,
    component: Polygon,
    free_space: GuideFreeSpace,
    config: RoutingConfig,
) -> bool:
    if np.linalg.norm(second - first) <= config.topology_tolerance:
        return True
    certificate = _certificate(
        np.vstack((first, second)),
        first,
        second,
        component,
        free_space,
        config,
    )
    return certificate.valid


def _dijkstra(
    adjacency: list[dict[int, float]],
    start_id: int,
    target_id: int,
    tie_tolerance: float,
) -> tuple[int, ...] | None:
    count = len(adjacency)
    distances = np.full(count, np.inf, dtype=float)
    hops = np.full(count, np.iinfo(np.int64).max, dtype=np.int64)
    predecessor = np.full(count, -1, dtype=int)
    distances[start_id] = 0.0
    hops[start_id] = 0
    queue: list[tuple[float, int, int]] = [(0.0, 0, start_id)]
    while queue:
        distance, hop_count, node = heapq.heappop(queue)
        if distance > distances[node] + tie_tolerance or hop_count > hops[node]:
            continue
        for neighbor in sorted(adjacency[node]):
            candidate = distance + adjacency[node][neighbor]
            candidate_hops = hop_count + 1
            strictly_better = candidate < distances[neighbor] - tie_tolerance
            equal_better = (
                abs(candidate - distances[neighbor]) <= tie_tolerance
                and (
                    candidate_hops < hops[neighbor]
                    or (
                        candidate_hops == hops[neighbor]
                        and (predecessor[neighbor] < 0 or node < predecessor[neighbor])
                    )
                )
            )
            if strictly_better or equal_better:
                distances[neighbor] = candidate
                hops[neighbor] = candidate_hops
                predecessor[neighbor] = node
                heapq.heappush(queue, (candidate, int(candidate_hops), neighbor))
    if not np.isfinite(distances[target_id]):
        return None
    path = [target_id]
    visited = {target_id}
    while path[-1] != start_id:
        previous = int(predecessor[path[-1]])
        if previous < 0 or previous in visited:
            return None
        path.append(previous)
        visited.add(previous)
    return tuple(reversed(path))


def _straight_on_component(
    start: Array,
    target: Array,
    component_id: int,
    free_space: GuideFreeSpace,
    config: RoutingConfig,
) -> tuple[Array, ClearanceCertificate] | None:
    waypoints = (
        start[None, :]
        if np.linalg.norm(target - start) <= config.topology_tolerance
        else np.vstack((start, target))
    )
    certificate = _certificate(
        waypoints,
        start,
        target,
        free_space.components[component_id],
        free_space,
        config,
    )
    return (waypoints, certificate) if certificate.valid else None


def _visibility_on_component(
    start: Array,
    target: Array,
    component_id: int,
    free_space: GuideFreeSpace,
    config: RoutingConfig,
) -> tuple[Array, ClearanceCertificate] | None:
    component = free_space.components[component_id]
    nodes: list[Array] = []
    start_id = _add_node(nodes, start, config.topology_tolerance)
    target_id = _add_node(nodes, target, config.topology_tolerance)
    vertices: list[tuple[float, float]] = [
        (float(x), float(y)) for x, y in np.asarray(component.exterior.coords[:-1])
    ]
    for interior in component.interiors:
        vertices.extend((float(x), float(y)) for x, y in np.asarray(interior.coords[:-1]))
    for vertex in sorted(set(vertices)):
        _add_node(nodes, np.asarray(vertex, dtype=float), config.topology_tolerance)
    adjacency: list[dict[int, float]] = [dict() for _ in nodes]
    for first_id in range(len(nodes)):
        for second_id in range(first_id + 1, len(nodes)):
            if _segment_allowed(nodes[first_id], nodes[second_id], component, free_space, config):
                _add_edge(
                    adjacency,
                    first_id,
                    second_id,
                    float(np.linalg.norm(nodes[second_id] - nodes[first_id])),
                )
    node_path = _dijkstra(adjacency, start_id, target_id, config.tie_tolerance)
    if node_path is None:
        return None
    waypoints = np.asarray([nodes[node_id] for node_id in node_path], dtype=float)
    certificate = _certificate(waypoints, start, target, component, free_space, config)
    return (waypoints, certificate) if certificate.valid else None


def _corridor_on_component(
    start: Array,
    target: Array,
    component_id: int,
    free_space: GuideFreeSpace,
    config: RoutingConfig,
) -> tuple[Array, ClearanceCertificate] | None:
    direct = _straight_on_component(start, target, component_id, free_space, config)
    if direct is not None:
        return direct
    component = free_space.components[component_id]
    nodes: list[Array] = []
    start_id = _add_node(nodes, start, config.topology_tolerance)
    target_id = _add_node(nodes, target, config.topology_tolerance)
    ring_ids = [
        _add_node(nodes, np.asarray(vertex, dtype=float), config.topology_tolerance)
        for vertex in np.asarray(free_space.forbidden_polygon.exterior.coords[:-1])
    ]
    adjacency: list[dict[int, float]] = [dict() for _ in nodes]
    for first_id, second_id in zip(ring_ids, np.roll(ring_ids, -1), strict=True):
        if _segment_allowed(nodes[first_id], nodes[int(second_id)], component, free_space, config):
            _add_edge(
                adjacency,
                first_id,
                int(second_id),
                float(np.linalg.norm(nodes[int(second_id)] - nodes[first_id])),
            )
    for endpoint_id in (start_id, target_id):
        for ring_id in sorted(set(ring_ids)):
            if _segment_allowed(nodes[endpoint_id], nodes[ring_id], component, free_space, config):
                _add_edge(
                    adjacency,
                    endpoint_id,
                    ring_id,
                    float(np.linalg.norm(nodes[ring_id] - nodes[endpoint_id])),
                )
    node_path = _dijkstra(adjacency, start_id, target_id, config.tie_tolerance)
    if node_path is None:
        return None
    waypoints = np.asarray([nodes[node_id] for node_id in node_path], dtype=float)
    certificate = _certificate(waypoints, start, target, component, free_space, config)
    return (waypoints, certificate) if certificate.valid else None


def route_guide_to_target(
    guide_position: Array,
    target_position: Array,
    free_space: FreeSpaceResult,
    method: RouteMethod,
    config: RoutingConfig | None = None,
    *,
    guide_id: int = -1,
    target_id: int = -1,
) -> RoutePath:
    """Route one pair and return an explicit certified or infeasible result."""

    cfg = config or RoutingConfig()
    if not isinstance(cfg, RoutingConfig):
        raise TypeError("config must be RoutingConfig.")
    if method not in ROUTE_METHODS:
        raise ValueError(f"method must be one of {ROUTE_METHODS}.")
    if isinstance(free_space, FreeSpaceFailure):
        return _failure_route(
            guide_id,
            target_id,
            method,
            "FREE_SPACE_INVALID",
            free_space_status=free_space.status,
            free_space_diagnostics=dict(free_space.diagnostics),
        )
    if not isinstance(free_space, GuideFreeSpace):
        raise TypeError("free_space must be a guide free-space result.")
    start = _point(guide_position)
    target = _point(target_position)
    if start is None:
        return _failure_route(guide_id, target_id, method, "INVALID_GUIDE_ENDPOINT")
    if target is None:
        return _failure_route(guide_id, target_id, method, "INVALID_TARGET_ENDPOINT")

    start_components = _covering_component_ids(start, free_space, cfg.topology_tolerance)
    target_components = _covering_component_ids(target, free_space, cfg.topology_tolerance)
    if not start_components:
        return _failure_route(guide_id, target_id, method, "GUIDE_OUTSIDE_FREE_SPACE")
    if not target_components:
        return _failure_route(guide_id, target_id, method, "TARGET_OUTSIDE_FREE_SPACE")
    common = tuple(sorted(set(start_components).intersection(target_components)))
    if not common:
        return _failure_route(
            guide_id,
            target_id,
            method,
            "DISCONNECTED_FREE_SPACE",
            guide_components=start_components,
            target_components=target_components,
        )

    candidates: list[tuple[Array, ClearanceCertificate, int]] = []
    for component_id in common:
        if method == "straight":
            candidate = _straight_on_component(start, target, component_id, free_space, cfg)
        elif method == "boundary_corridor":
            candidate = _corridor_on_component(start, target, component_id, free_space, cfg)
        else:
            candidate = _visibility_on_component(start, target, component_id, free_space, cfg)
        if candidate is not None:
            candidates.append((candidate[0], candidate[1], component_id))
    if not candidates:
        reason = "STRAIGHT_PATH_BLOCKED" if method == "straight" else "NO_CERTIFIED_GRAPH_PATH"
        return _failure_route(
            guide_id,
            target_id,
            method,
            reason,
            common_components=common,
        )

    candidates.sort(
        key=lambda item: (
            _path_length(item[0]),
            item[2],
            tuple(float(value) for value in item[0].ravel()),
        )
    )
    waypoints, certificate, component_id = candidates[0]
    return _success_route(
        guide_id,
        target_id,
        method,
        waypoints,
        component_id,
        certificate,
        candidate_component_count=len(candidates),
    )


def route_straight(
    guide_position: Array,
    target_position: Array,
    free_space: FreeSpaceResult,
    config: RoutingConfig | None = None,
    **ids: int,
) -> RoutePath:
    return route_guide_to_target(
        guide_position, target_position, free_space, "straight", config, **ids
    )


def route_boundary_corridor(
    guide_position: Array,
    target_position: Array,
    free_space: FreeSpaceResult,
    config: RoutingConfig | None = None,
    **ids: int,
) -> RoutePath:
    return route_guide_to_target(
        guide_position, target_position, free_space, "boundary_corridor", config, **ids
    )


def route_visibility_graph(
    guide_position: Array,
    target_position: Array,
    free_space: FreeSpaceResult,
    config: RoutingConfig | None = None,
    **ids: int,
) -> RoutePath:
    return route_guide_to_target(
        guide_position, target_position, free_space, "visibility_graph", config, **ids
    )


def build_pairwise_route_matrix(
    guide_positions: Array,
    target_positions: Array,
    free_space: FreeSpaceResult,
    method: RouteMethod,
    config: RoutingConfig | None = None,
) -> PairwiseRouteMatrix:
    """Build every route independently, preserving partial reachability."""

    guides = _points(guide_positions, "guide_positions")
    targets = _points(target_positions, "target_positions")
    paths: list[tuple[RoutePath, ...]] = []
    costs = np.full((len(guides), len(targets)), np.inf, dtype=float)
    reachable = np.zeros((len(guides), len(targets)), dtype=bool)
    for guide_id, guide in enumerate(guides):
        row: list[RoutePath] = []
        for target_id, target in enumerate(targets):
            route = route_guide_to_target(
                guide,
                target,
                free_space,
                method,
                config,
                guide_id=guide_id,
                target_id=target_id,
            )
            row.append(route)
            if route.status == "ROUTE_FEASIBLE":
                assert route.path_length is not None and np.isfinite(route.path_length)
                costs[guide_id, target_id] = route.path_length
                reachable[guide_id, target_id] = True
        paths.append(tuple(row))
    geometry_hash = free_space.geometry_sha256 if isinstance(free_space, GuideFreeSpace) else ""
    return PairwiseRouteMatrix(
        guide_positions=guides,
        target_positions=targets,
        paths=tuple(paths),
        path_cost_matrix=costs,
        reachable_mask=reachable,
        method=method,
        geometry_sha256=geometry_hash,
        status=(
            "ROUTE_MATRIX_READY"
            if isinstance(free_space, GuideFreeSpace)
            else "ROUTE_MATRIX_INVALID_FREE_SPACE"
        ),
        diagnostics={
            "reason": "all_pairs_evaluated",
            "guide_count": len(guides),
            "target_count": len(targets),
            "reachable_pair_count": int(np.count_nonzero(reachable)),
            "infeasible_pair_count": int(reachable.size - np.count_nonzero(reachable)),
            "partial_reachability_preserved": True,
            "unreachable_internal_cost": "positive_infinity",
            "unreachable_json_cost": None,
        },
    )


__all__ = [
    "ClearanceCertificate",
    "PairwiseRouteMatrix",
    "ROUTE_METHODS",
    "RouteMethod",
    "RoutePath",
    "RoutingConfig",
    "build_pairwise_route_matrix",
    "route_boundary_corridor",
    "route_guide_to_target",
    "route_straight",
    "route_visibility_graph",
]
