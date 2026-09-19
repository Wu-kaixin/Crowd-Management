from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
from shapely.geometry import LineString, Point, Polygon

from crowd_management.controllers.safe_geodesic import (
    conflict_wait_mask,
    inflate_estimated_obstacle,
    inflate_observation_cloud,
    remaining_path_length,
    segment_in_free_space,
    union_obstacles,
    visibility_shortest_path,
    workspace_polygon,
)


def _u_curve() -> np.ndarray:
    return np.array(
        [
            [5.0, 5.0],
            [15.0, 5.0],
            [15.0, 7.0],
            [8.0, 7.0],
            [8.0, 13.0],
            [15.0, 13.0],
            [15.0, 15.0],
            [5.0, 15.0],
        ],
        dtype=float,
    )


def test_direct_line_when_segment_is_free() -> None:
    room = workspace_polygon(np.array([20.0, 20.0]), 0.25)
    obstacle = inflate_estimated_obstacle(
        np.array([[9.0, 9.0], [11.0, 9.0], [11.0, 11.0], [9.0, 11.0]], dtype=float),
        0.4,
        simplify=0.05,
    )
    planned = visibility_shortest_path(np.array([2.0, 2.0]), np.array([3.5, 2.5]), obstacle, room)
    assert planned is not None
    assert planned.diagnostics["status"] == "DIRECT"
    assert len(planned.waypoints) == 2


def test_u_obstacle_path_goes_around_not_through() -> None:
    room = workspace_polygon(np.array([20.0, 20.0]), 0.25)
    obstacle = inflate_estimated_obstacle(_u_curve(), 0.5, simplify=0.05)
    assert obstacle is not None
    start = np.array([16.5, 10.0])
    goal = np.array([3.5, 10.0])
    assert not segment_in_free_space(start, goal, obstacle, room)
    planned = visibility_shortest_path(start, goal, obstacle, room)
    assert planned is not None
    assert planned.diagnostics["status"] == "VISIBLE"
    assert len(planned.waypoints) >= 3
    for a, b in zip(planned.waypoints[:-1], planned.waypoints[1:], strict=True):
        assert segment_in_free_space(a, b, obstacle, room)
    path = LineString([(float(x), float(y)) for x, y in planned.waypoints])
    interior = obstacle.buffer(-1.0e-6)
    assert not interior.intersects(path)
    assert float(np.max(np.abs(planned.waypoints[:, 1] - 10.0))) > 2.0


def test_longer_remaining_path_waits_on_opposing_pair() -> None:
    wait = conflict_wait_mask(
        np.array([[0.0, 0.0], [0.5, 0.0]]),
        np.array([[2.0, 0.0], [-2.0, 0.0]]),
        np.array([5.0, 1.0]),
        np.array([True, True]),
        min_guide_distance=0.6,
    )
    assert wait.tolist() == [True, False]


def test_higher_id_waits_on_remaining_length_tie() -> None:
    wait = conflict_wait_mask(
        np.array([[0.0, 0.0], [0.4, 0.0]]),
        np.array([[2.0, 0.0], [-2.0, 0.0]]),
        np.array([3.0, 3.0]),
        np.array([True, True]),
        min_guide_distance=0.6,
    )
    assert wait.tolist() == [False, True]


def test_remaining_path_length_includes_unfinished_vertices() -> None:
    path = np.array([[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]], dtype=float)
    assert remaining_path_length(path, 1, np.array([0.5, 0.0])) == 1.5


def test_geodesic_module_has_no_spawn_or_truth_imports() -> None:
    source = Path("src/crowd_management/controllers/safe_geodesic.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    joined = " ".join(imported)
    assert "jupedsim" not in joined
    assert "known_boundary" not in joined
    assert "spawn" not in joined
    assert "truth" not in joined


def test_leaky_estimate_still_blocks_observation_cloud() -> None:
    room = workspace_polygon(np.array([20.0, 20.0]), 0.25)
    leaky_curve = np.array(
        [[9.9, 9.9], [10.1, 9.9], [10.1, 10.1], [9.9, 10.1]],
        dtype=float,
    )
    crowd = np.column_stack((np.full(25, 10.0), np.linspace(4.0, 16.0, 25)))
    estimated = inflate_estimated_obstacle(leaky_curve, 0.85, simplify=0.05)
    observed = inflate_observation_cloud(crowd, 0.85, simplify=0.05)
    obstacle = union_obstacles([estimated, observed])
    start = np.array([7.5, 10.0])
    goal = np.array([15.0, 10.0])
    assert not segment_in_free_space(start, goal, obstacle, room)
    planned = visibility_shortest_path(start, goal, obstacle, room)
    assert planned is not None
    assert planned.diagnostics["status"] == "VISIBLE"
    assert float(np.max(np.abs(planned.waypoints[:, 1] - 10.0))) > 2.0


def test_inflate_uses_estimated_polygon_not_a_point_cloud_hull_of_truth() -> None:
    curve = _u_curve()
    obstacle = inflate_estimated_obstacle(curve, 0.5, simplify=0.0)
    assert isinstance(obstacle, Polygon)
    assert obstacle.area > Polygon(curve).area
    assert obstacle.contains(Point(6.0, 10.0))
    # A point deep in the concavity stays outside the estimated obstacle.
    assert not obstacle.contains(Point(12.0, 10.0))
