"""Known closed square/rectangle environment contract."""

from __future__ import annotations

import numpy as np
import pytest

from crowd_management.scenarios import RectangularScenario


def test_square_scene_contract() -> None:
    scene = RectangularScenario(name="square", width=20.0, height=20.0)
    vertices = scene.boundary_vertices()
    assert scene.closed
    assert scene.step1_contract_valid()
    assert vertices.shape == (4, 2)
    assert np.allclose(vertices[0], [0.0, 0.0])
    assert np.allclose(vertices[2], [20.0, 20.0])
    inside = np.array([[10.0, 10.0], [0.2, 0.2], [19.8, 19.8]])
    assert np.all(scene.contains(inside, margin=0.0))
    assert np.all(scene.contains(np.array([[10.0, 10.0]]), margin=0.25))
    assert not scene.contains(np.array([[0.1, 10.0]]), margin=0.25)[0]
    clearance = scene.wall_clearance(np.array([[1.0, 10.0]]))
    assert clearance[0] == pytest.approx(1.0)


def test_rectangle_scene_contract() -> None:
    scene = RectangularScenario(name="rectangle", width=28.0, height=16.0)
    assert scene.closed
    assert scene.width == 28.0
    assert scene.height == 16.0
    lower, upper = scene.feasible_workspace_bounds(0.25)
    assert np.allclose(lower, [0.25, 0.25])
    assert np.allclose(upper, [27.75, 15.75])
    workspace = scene.feasible_workspace_polygon(0.25)
    assert workspace.is_valid
    assert not workspace.is_empty


def test_environment_boundary_is_not_crowd_boundary() -> None:
    scene = RectangularScenario(name="square", width=20.0, height=20.0)
    crowd = np.array([[8.0, 8.0], [12.0, 8.0], [12.0, 12.0], [8.0, 12.0]])
    env = scene.boundary_vertices()
    assert not np.allclose(env, crowd)
    assert scene.polygon().area == pytest.approx(400.0)
    from shapely.geometry import Polygon

    assert Polygon(crowd).area == pytest.approx(16.0)
