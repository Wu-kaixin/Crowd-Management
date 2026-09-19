"""Truth-leakage contract: ABCG never sees spawn or evaluator geometry."""

from __future__ import annotations

import inspect

import numpy as np
import pytest

from crowd_management.controllers import ABCGv2Config, ABCGv2Controller, AssignmentConfig, assign_guides_to_targets
from crowd_management.crowd.observation import (
    FORBIDDEN_OBSERVATION_FIELDS,
    CrowdObservation,
    as_controller_observation,
    crowd_observation_from_points,
)
from crowd_management.experiments.static_containment.config import StaticContainmentConfig
from crowd_management.experiments.static_containment.known_boundary import estimate_known_boundary_pipeline


def _controller() -> ABCGv2Controller:
    guides = np.array([[0.5, 0.5], [1.5, 0.5]])
    targets = np.array([[1.0, 1.0], [2.0, 1.0]])
    assignment = assign_guides_to_targets(guides, targets, AssignmentConfig(lambda_switch=0.0))
    controller = ABCGv2Controller(ABCGv2Config(dt=0.1, k_p=1.0, v_max=0.5, max_steps=3))
    controller.reset(targets, assignment, guides, room_size=np.array([20.0, 20.0]))
    return controller, guides


def test_controller_cannot_access_spawn_polygon() -> None:
    signature = inspect.signature(ABCGv2Controller.step)
    for name in signature.parameters:
        assert name not in FORBIDDEN_OBSERVATION_FIELDS
    with pytest.raises(TypeError):
        as_controller_observation({"positions": np.ones((4, 2)), "spawn_polygon": [[0.0, 0.0]]})
    with pytest.raises(ValueError):
        crowd_observation_from_points(np.ones((4, 2)), {"spawn_vertices": np.ones((4, 2))})


def test_controller_cannot_access_truth_boundary() -> None:
    controller, guides = _controller()
    observation = CrowdObservation(positions=np.array([[4.0, 4.0], [5.0, 5.0], [6.0, 4.0], [5.0, 3.0]]))
    output = controller.step(observation, guides, dt=0.1)
    assert "spawn" not in output.diagnostics
    assert "truth" not in output.diagnostics
    with pytest.raises((TypeError, ValueError)):
        CrowdObservation(
            positions=observation.positions,
            diagnostics={"truth_boundary": "secret"},
        )


def test_mutating_evaluator_truth_does_not_change_controller_output() -> None:
    controller, guides = _controller()
    points = np.array([[4.0, 4.0], [5.0, 5.0], [6.0, 4.0], [5.0, 3.0], [4.5, 4.5]])
    first = controller.step(CrowdObservation(positions=points), guides, dt=0.1)
    truth = points * 10.0
    second_controller, _ = _controller()
    second = second_controller.step(CrowdObservation(positions=points.copy()), guides, dt=0.1)
    assert np.allclose(first.safe_velocity, second.safe_velocity)
    assert not np.allclose(truth, points)


def test_private_spawn_metadata_does_not_change_abcg_output() -> None:
    points = np.array([[8.0, 8.0], [9.0, 9.0], [10.0, 8.5], [9.5, 7.5], [8.5, 8.8], [9.2, 8.1]])
    first = CrowdObservation(positions=points)
    second = CrowdObservation(positions=points.copy())
    controller_a, guides = _controller()
    out_a = controller_a.step(first, guides, dt=0.1)
    controller_b, _ = _controller()
    out_b = controller_b.step(second, guides, dt=0.1)
    assert np.allclose(out_a.preferred_velocity, out_b.preferred_velocity)
    assert np.allclose(out_a.safe_velocity, out_b.safe_velocity)


def test_known_boundary_pipeline_does_not_read_spawn(tmp_path) -> None:
    del tmp_path
    from pathlib import Path

    cfg = StaticContainmentConfig.from_yaml(Path("configs/step1_known_boundary/square_circle.yaml"))
    spawn = np.asarray(cfg.crowd.region_vertices, dtype=float)
    points = np.array(
        [
            [9.0, 10.0],
            [10.0, 10.5],
            [11.0, 10.0],
            [10.0, 9.4],
            [9.5, 9.8],
            [10.4, 10.2],
            [10.7, 9.7],
            [9.3, 10.3],
        ]
    )
    observation = CrowdObservation(positions=points)
    estimate, _deployment = estimate_known_boundary_pipeline(observation, cfg)
    if hasattr(estimate, "diagnostics"):
        assert "spawn" not in estimate.diagnostics
        assert "region_vertices" not in estimate.diagnostics
    assert spawn.shape[0] >= 3
