"""Scenario registry, random guide init, and DESIGNED decentralization stubs."""

from __future__ import annotations

import numpy as np
import pytest

from crowd_management.controllers.decentralized import (
    LocalObservation,
    NotImplementedDecentralizedController,
)
from crowd_management.controllers.guide_initialization import sample_random_guide_positions
from crowd_management.scenarios import (
    RectangularScenario,
    build_scenario,
    register_scenario,
    registered_scenario_types,
)


def test_registered_square_and_rectangle() -> None:
    assert "square" in registered_scenario_types()
    assert "rectangle" in registered_scenario_types()
    square = build_scenario({"type": "square", "width": 20.0, "height": 20.0, "closed": True})
    rect = build_scenario({"type": "rectangle", "width": 28.0, "height": 16.0, "closed": True})
    assert isinstance(square, RectangularScenario)
    assert isinstance(rect, RectangularScenario)
    assert square.closed and rect.closed


def test_step1_rejects_openings_and_unknown_type() -> None:
    with pytest.raises(ValueError, match="closed"):
        build_scenario({"type": "square", "width": 10.0, "height": 10.0, "closed": False})
    with pytest.raises(ValueError, match="openings"):
        build_scenario(
            {
                "type": "square",
                "width": 10.0,
                "height": 10.0,
                "closed": True,
                "openings": [{"wall": "south", "start": 1.0, "end": 2.0}],
            }
        )
    with pytest.raises(ValueError, match="Unknown scene.type"):
        build_scenario({"type": "L_shape", "width": 10.0, "height": 10.0, "closed": True})


def test_register_scenario_extension_hook() -> None:
    def factory(*, width: float, height: float, openings=(), origin=(0.0, 0.0)):
        del openings, origin
        return RectangularScenario(name="square", width=width, height=height)

    register_scenario("_test_alias", factory, replace=True)
    scene = build_scenario({"type": "_test_alias", "width": 12.0, "height": 12.0, "closed": True})
    assert scene.width == 12.0


def test_random_guide_init_in_workspace() -> None:
    scene = RectangularScenario(name="square", width=20.0, height=20.0)
    crowd = np.array([[10.0, 10.0], [10.5, 10.0], [10.0, 10.5]])
    guides = sample_random_guide_positions(
        scene,
        8,
        seed=0,
        wall_margin=0.25,
        min_guide_distance=0.5,
        crowd_points=crowd,
        min_crowd_distance=0.85,
    )
    assert guides.shape == (8, 2)
    assert np.all(scene.contains(guides, margin=0.25))
    assert np.all(np.linalg.norm(guides[:, None, :] - crowd[None, :, :], axis=2) >= 0.85 - 1e-9)


def test_decentralized_stub_is_explicit() -> None:
    controller = NotImplementedDecentralizedController()
    with pytest.raises(NotImplementedError, match="Step 3"):
        controller.reset((0, 1))
    obs = LocalObservation(
        guide_id=0,
        ego_position=np.array([1.0, 1.0]),
        neighbor_guide_ids=(),
        neighbor_guide_positions=np.zeros((0, 2)),
        local_crowd_positions=np.zeros((0, 2)),
    )
    with pytest.raises(NotImplementedError, match="Step 3"):
        controller.step(0, obs, (), 0.1)
