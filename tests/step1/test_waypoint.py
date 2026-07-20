from __future__ import annotations

import json

import numpy as np
import pytest

from crowd_management.controllers.safety import VelocitySafetyConfig
from crowd_management.controllers.safety_v2 import (
    VelocityProjectionConfig,
    project_velocity_safety_v2,
)
from crowd_management.controllers.waypoint import (
    FixedWaypointPaths,
    WaypointEpisodeRunner,
    WaypointRunnerConfig,
    WaypointSafetyResponse,
)


def _paths(paths: list[np.ndarray | None], assignment: list[int] | None = None) -> FixedWaypointPaths:
    mapping = np.asarray(assignment if assignment is not None else list(range(len(paths))), dtype=int)
    return FixedWaypointPaths.from_guide_paths(mapping, paths, clearance_margin_m=0.5)


def test_fixed_path_version_is_content_deterministic_and_validated() -> None:
    first = _paths([np.array([[0.0, 0.0], [1.0, 0.0]])])
    second = _paths([np.array([[0.0, 0.0], [1.0, 0.0]])])
    changed = _paths([np.array([[0.0, 0.0], [1.01, 0.0]])])

    assert first.path_version == second.path_version
    assert first.path_version != changed.path_version
    assert len(first.path_version) == 64
    assert not first.waypoint_points.flags.writeable
    with pytest.raises(ValueError):
        _paths([None], assignment=[0])
    with pytest.raises(ValueError):
        _paths([np.array([[np.nan, 0.0]])])


def test_single_segment_contracts_and_integrates_applied_controls_exactly() -> None:
    config = WaypointRunnerConfig(
        dt=0.1,
        k_p=1.0,
        v_max=2.0,
        waypoint_tolerance_m=0.01,
        final_rmse_tolerance_m=0.02,
        hold_steps=2,
        max_steps=100,
        no_progress_window=30,
    )
    result = WaypointEpisodeRunner(config).run(
        np.array([[0.0, 0.0]]),
        _paths([np.array([[1.0, 0.0]])]),
    )

    assert result.terminal_status == "CONVERGED"
    assert np.all(np.diff(result.total_remaining_path_m) <= 1.0e-12)
    assert np.allclose(
        result.positions[1:],
        result.positions[:-1] + config.dt * result.applied_controls,
    )
    assert np.array_equal(result.velocities[1:], result.applied_controls)
    assert np.array_equal(result.velocities[0], np.zeros((1, 2)))
    assert len(result.positions) == len(result.applied_controls) + 1


def test_multi_segment_advances_after_integration_and_records_progress() -> None:
    config = WaypointRunnerConfig(
        dt=0.5,
        k_p=2.0,
        v_max=1.0,
        waypoint_tolerance_m=1.0e-6,
        final_rmse_tolerance_m=1.0e-6,
        speed_tolerance_mps=0.01,
        hold_steps=1,
        max_steps=10,
        no_progress_window=5,
    )
    result = WaypointEpisodeRunner(config).run(
        np.array([[0.0, 0.0]]),
        _paths([np.array([[0.5, 0.0], [1.0, 0.0]])]),
    )

    assert result.waypoint_index_history[0, 0] == 0
    assert result.waypoint_index_history[1, 0] == 1
    assert any(event.step == 1 and event.waypoint_index == 1 for event in result.events)
    assert np.all(np.diff(result.waypoint_index_history[:, 0]) >= 0)
    assert np.all((result.progress_fraction >= 0.0) & (result.progress_fraction <= 1.0))


def test_initial_waypoint_skip_reserve_semantics_and_final_hold() -> None:
    config = WaypointRunnerConfig(
        dt=0.1,
        k_p=1.0,
        v_max=1.0,
        waypoint_tolerance_m=0.02,
        final_rmse_tolerance_m=0.02,
        speed_tolerance_mps=0.02,
        hold_steps=3,
        max_steps=80,
    )
    paths = _paths(
        [np.array([[0.0, 0.0], [0.2, 0.0]]), None],
        assignment=[0, -1],
    )
    result = WaypointEpisodeRunner(config).run(np.array([[0.0, 0.0], [5.0, 5.0]]), paths)

    assert result.waypoint_index_history[0].tolist() == [1, -1]
    assert np.all(result.applied_controls[:, 1] == 0.0)
    assert result.terminal_status == "CONVERGED"
    assert result.hold_count_history[-1] == 3
    assert np.count_nonzero(result.state_history == "HOLD") >= 2


def test_timeout_retains_t_plus_one_frames() -> None:
    config = WaypointRunnerConfig(
        dt=0.1,
        k_p=0.5,
        v_max=0.2,
        max_steps=3,
        no_progress_window=3,
        min_progress_m=1.0e-8,
    )
    result = WaypointEpisodeRunner(config).run(
        np.array([[0.0, 0.0]]),
        _paths([np.array([[10.0, 0.0]])]),
    )

    assert result.terminal_status == "TIMEOUT"
    assert result.terminal_reason == "MAXIMUM_STEPS_REACHED"
    assert result.positions.shape == (4, 1, 2)
    assert result.applied_controls.shape == (3, 1, 2)
    assert result.safety_status_history.shape == (3,)


def test_zero_applied_control_triggers_exact_no_progress_reason() -> None:
    calls: list[int] = []

    def stopped(request):
        calls.append(request.step_index)
        return WaypointSafetyResponse(
            nominal_control=request.nominal_control,
            applied_control=np.zeros_like(request.nominal_control),
            status="PROJECTED",
            feasible=True,
        )

    config = WaypointRunnerConfig(
        max_steps=20,
        no_progress_window=4,
        min_progress_m=0.01,
    )
    result = WaypointEpisodeRunner(config).run(
        np.array([[0.0, 0.0]]),
        _paths([np.array([[1.0, 0.0]])]),
        safety_callback=stopped,
    )

    assert result.terminal_status == "TIMEOUT"
    assert result.terminal_reason == "NO_PROGRESS_REPLAN_NOT_AVAILABLE"
    assert result.replan_reason == "NO_PROGRESS_DETECTED"
    assert len(calls) == config.no_progress_window
    assert result.no_progress_count_history[-1] == config.no_progress_window


def test_safety_callback_applied_control_is_the_only_integrated_control() -> None:
    def half_speed(request):
        return WaypointSafetyResponse(
            nominal_control=request.nominal_control,
            applied_control=0.5 * request.nominal_control,
            status="PROJECTED",
            feasible=True,
        )

    config = WaypointRunnerConfig(max_steps=2, no_progress_window=10)
    result = WaypointEpisodeRunner(config).run(
        np.array([[0.0, 0.0]]),
        _paths([np.array([[1.0, 0.0]])]),
        safety_callback=half_speed,
    )

    assert np.allclose(result.applied_controls, 0.5 * result.nominal_controls)
    assert np.allclose(
        result.positions[1:],
        result.positions[:-1] + config.dt * result.applied_controls,
    )


def test_route_infeasible_is_initial_only_and_never_calls_safety() -> None:
    calls = 0

    def callback(request):
        nonlocal calls
        calls += 1
        raise AssertionError("callback must not be called")

    paths = FixedWaypointPaths.from_guide_paths(
        np.array([0]),
        [np.array([[1.0, 0.0]])],
        route_status="ROUTE_INFEASIBLE",
    )
    result = WaypointEpisodeRunner().run(
        np.array([[0.0, 0.0]]),
        paths,
        safety_callback=callback,
    )

    assert calls == 0
    assert result.terminal_status == "ROUTE_INFEASIBLE"
    assert result.positions.shape == (1, 1, 2)
    assert result.applied_controls.shape == (0, 1, 2)
    assert result.diagnostics["control_called"] is False


def test_safety_failure_records_one_finite_emergency_interval() -> None:
    def infeasible(request):
        return WaypointSafetyResponse(
            nominal_control=request.nominal_control,
            applied_control=np.zeros_like(request.nominal_control),
            status="PROJECTION_INFEASIBLE",
            feasible=False,
            emergency_stop=True,
        )

    result = WaypointEpisodeRunner().run(
        np.array([[0.0, 0.0]]),
        _paths([np.array([[1.0, 0.0]])]),
        safety_callback=infeasible,
    )

    assert result.terminal_status == "SAFETY_INFEASIBLE"
    assert len(result.positions) == 2
    assert len(result.applied_controls) == 1
    assert np.all(np.isfinite(result.positions))
    assert np.all(result.applied_controls == 0.0)


def test_waypoint_episode_is_bitwise_reproducible_and_strict_json_safe() -> None:
    runner = WaypointEpisodeRunner(WaypointRunnerConfig(max_steps=6, no_progress_window=6))
    paths = _paths([np.array([[0.2, 0.0], [0.5, 0.1]])])
    first = runner.run(np.array([[0.0, 0.0]]), paths)
    second = runner.run(np.array([[0.0, 0.0]]), paths)

    for name in (
        "times",
        "positions",
        "velocities",
        "nominal_controls",
        "applied_controls",
        "state_history",
        "waypoint_index_history",
        "remaining_path_m",
        "progress_fraction",
    ):
        assert np.array_equal(getattr(first, name), getattr(second, name))
    assert first.events == second.events
    assert first.path_version == second.path_version
    payload = first.to_jsonable()
    text = json.dumps(payload, allow_nan=False, sort_keys=True)
    restored = json.loads(text)
    assert restored["path_version"] == paths.path_version
    assert len(restored["positions"]) == len(restored["applied_controls"]) + 1


def test_waypoint_runner_consumes_v2_safety_certificate_response() -> None:
    safety_config = VelocitySafetyConfig(
        min_guide_distance=0.0,
        min_crowd_distance=0.0,
        room_margin=0.1,
    )

    def callback(request):
        return project_velocity_safety_v2(
            request.positions,
            request.nominal_control,
            np.empty((0, 2)),
            np.array([10.0, 10.0]),
            request.dt,
            0.8,
            safety_config,
            VelocityProjectionConfig(backend="dykstra"),
        )

    result = WaypointEpisodeRunner(WaypointRunnerConfig(max_steps=2)).run(
        np.array([[1.0, 1.0]]),
        _paths([np.array([[1.2, 1.0]])]),
        safety_callback=callback,
    )

    assert result.terminal_status != "SAFETY_INFEASIBLE"
    assert result.safety_diagnostics[0]["primal_residual"] <= 1.0e-8
    assert "certificate" in result.safety_diagnostics[0]["diagnostics"]
