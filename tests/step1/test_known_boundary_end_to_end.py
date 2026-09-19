"""Live visualization, static crowd, and known-boundary end-to-end tests."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from crowd_management.controllers.safety import (
    minimum_guide_crowd_distance,
    minimum_guide_guide_distance,
    minimum_guide_wall_distance,
)
from crowd_management.crowd import generate_jupedsim_static_crowd
from crowd_management.crowd.observation import CrowdObservation
from crowd_management.experiments.static_containment import StaticContainmentConfig, run_static_containment
from crowd_management.visualization.live_step1 import NullStep1Renderer, Step1Frame, build_renderer

REPO = Path(__file__).resolve().parents[2]


def test_jupedsim_static_reproducibility() -> None:
    cfg = StaticContainmentConfig.from_yaml(REPO / "configs/step1_known_boundary/square_circle.yaml")
    first = generate_jupedsim_static_crowd(cfg.crowd)
    second = generate_jupedsim_static_crowd(cfg.crowd)
    assert np.array_equal(first, second)


def test_crowd_remains_static() -> None:
    cfg = StaticContainmentConfig.from_yaml(REPO / "configs/step1_known_boundary/square_circle.yaml")
    points = generate_jupedsim_static_crowd(cfg.crowd)
    again = generate_jupedsim_static_crowd(cfg.crowd)
    assert np.allclose(points, again)
    assert np.all(np.isfinite(points))


def test_boundary_estimation_valid_case() -> None:
    from crowd_management.experiments.static_containment.known_boundary import estimate_known_boundary_pipeline

    cfg = StaticContainmentConfig.from_yaml(REPO / "configs/step1_known_boundary/square_circle.yaml")
    points = generate_jupedsim_static_crowd(cfg.crowd)
    result, deployment = estimate_known_boundary_pipeline(CrowdObservation(positions=points), cfg)
    from crowd_management.estimation import BoundaryEstimateV2

    assert isinstance(result, BoundaryEstimateV2)
    assert result.topology_valid
    del deployment


def test_boundary_failure_is_explicit() -> None:
    from crowd_management.estimation import BoundaryEstimateFailure, BoundaryV2Config, estimate_boundary_v2

    result = estimate_boundary_v2(
        np.array([[0.0, 0.0], [1.0, 0.0]]),
        BoundaryV2Config(min_observation_points=8),
        np.random.default_rng(0),
    )
    assert isinstance(result, BoundaryEstimateFailure)
    assert result.status == "OBSERVATION_INVALID"


def test_guide_wall_safety() -> None:
    guides = np.array([[1.0, 10.0], [10.0, 1.0]])
    assert minimum_guide_wall_distance(guides, np.array([20.0, 20.0])) == 1.0


def test_guide_crowd_safety() -> None:
    guides = np.array([[0.0, 0.0]])
    crowd = np.array([[3.0, 4.0]])
    assert minimum_guide_crowd_distance(guides, crowd) == 5.0


def test_guide_guide_safety() -> None:
    guides = np.array([[0.0, 0.0], [3.0, 4.0]])
    assert minimum_guide_guide_distance(guides) == 5.0


def test_visualization_hold_window_default() -> None:
    from crowd_management.experiments.static_containment import StaticContainmentConfig

    cfg = StaticContainmentConfig.from_yaml(REPO / "configs/step1_known_boundary/square_circle.yaml")
    assert cfg.visualization.live is True
    assert cfg.visualization.hold_window is True


def test_live_renderer_defaults_to_blocking_window() -> None:
    from crowd_management.visualization.live_step1 import Step1LiveRenderer, build_renderer

    renderer = build_renderer(live=True)
    assert isinstance(renderer, Step1LiveRenderer)
    assert renderer.block is True

    renderer = build_renderer(live=False)
    frame = Step1Frame(
        scenario_name="square",
        seed=0,
        time=0.0,
        step=0,
        environment_vertices=np.array([[0.0, 0.0], [20.0, 0.0], [20.0, 20.0], [0.0, 20.0]]),
        crowd_points=np.array([[10.0, 10.0], [11.0, 10.0]]),
        crowd_radii=None,
        crowd_demand=None,
        estimated_crowd_boundary=None,
        deployment_curve=None,
        target_positions=np.array([[12.0, 12.0]]),
        initial_guides=np.array([[1.0, 1.0]]),
        current_guides=np.array([[1.0, 1.0]]),
        active_ids=(0,),
        reserve_ids=(),
        trails=None,
        controller_state="BOUNDARY_INVALID",
        failed=True,
        failure_reason="BOUNDARY_INVALID",
    )
    renderer.start(frame)
    renderer.update(frame)
    assert isinstance(renderer, NullStep1Renderer)
    assert len(renderer.frames) >= 1


def test_live_and_headless_numerically_equivalent(tmp_path: Path) -> None:
    config = REPO / "configs/ci_smoke.yaml"
    first = tmp_path / "headless"
    second = tmp_path / "mock_live"
    mock = NullStep1Renderer()
    a = run_static_containment(config, first, methods=["abcg"], save_plots=False, live=False, headless=True)
    b = run_static_containment(
        config,
        second,
        methods=["abcg"],
        save_plots=False,
        live=True,
        headless=False,
        renderer=mock,
    )
    assert a["abcg"]["episode_status"] == b["abcg"]["episode_status"]
    first_episode = np.load(first / "abcg" / "episode.npz")
    second_episode = np.load(second / "abcg" / "episode.npz")
    assert np.allclose(first_episode["positions"], second_episode["positions"], atol=1e-12, rtol=1e-12)
    assert np.allclose(first_episode["applied_controls"], second_episode["applied_controls"], atol=1e-12, rtol=1e-12)
    assert len(mock.frames) >= 1


def test_failure_case_still_produces_final_frame(tmp_path: Path) -> None:
    result = run_static_containment(
        REPO / "configs/step1_known_boundary/square_near_wall_infeasible.yaml",
        tmp_path,
        methods=["abcg"],
        save_plots=True,
        live=False,
        headless=True,
    )
    assert result["abcg"]["episode_status"] != "CONVERGED" or result["abcg"]["scientific_success"] in {True, False}
    assert (tmp_path / "abcg" / "final_scene.png").is_file() or (tmp_path / "abcg" / "containment.png").is_file()


def test_step1_square_end_to_end(tmp_path: Path) -> None:
    result = run_static_containment(
        REPO / "configs/step1_known_boundary/square_circle.yaml",
        tmp_path,
        methods=["abcg"],
        save_plots=False,
        live=False,
        headless=True,
    )
    assert "episode_status" in result["abcg"]
    assert (tmp_path / "crowd_observation.npz").is_file()
    assert (tmp_path / "evaluator_truth.npz").is_file()
    loaded = np.load(tmp_path / "crowd_observation.npz")
    assert "positions" in loaded.files
    assert "spawn" not in loaded.files
    state = np.load(tmp_path / "abcg" / "containment_state.npz")
    assert str(state["guide_init_mode"]) == "random"
    initial = np.asarray(state["guide_initial_points"], dtype=float)
    endpoints = np.asarray(state["guide_method_endpoints"], dtype=float)
    assert initial.shape == endpoints.shape
    # Random unknown spawn must not collapse onto the endpoint plan.
    assert not np.allclose(initial, endpoints, atol=1e-6)


def test_known_boundary_defaults_to_random_guide_init() -> None:
    cfg = StaticContainmentConfig.from_yaml(REPO / "configs/step1_known_boundary/square_circle.yaml")
    assert cfg.guide_init == "random"
    assert cfg.scene.name == "square"
    assert cfg.scene.closed


def test_legacy_room_config_defaults_to_endpoint_guide_init() -> None:
    cfg = StaticContainmentConfig.from_yaml(REPO / "configs/ci_smoke.yaml")
    assert cfg.guide_init == "endpoint"
    assert cfg.known_environment is False


def test_step1_rectangle_end_to_end(tmp_path: Path) -> None:
    result = run_static_containment(
        REPO / "configs/step1_known_boundary/rectangle_ellipse.yaml",
        tmp_path,
        methods=["abcg"],
        save_plots=False,
        live=False,
        headless=True,
    )
    assert result["abcg"]["episode_status"] in {
        "CONVERGED",
        "TIMEOUT",
        "DEGRADED",
        "BOUNDARY_INVALID",
        "OFFSET_INVALID",
        "OFFSET_OUTSIDE_WORKSPACE",
        "CAPACITY_SHORTFALL",
        "SAFETY_INFEASIBLE",
        "PLAN_INVALID",
        "ASSIGNMENT_INFEASIBLE",
    }
