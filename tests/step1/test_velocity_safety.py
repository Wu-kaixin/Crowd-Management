from __future__ import annotations

import numpy as np

from crowd_management.controllers import (
    ABCGv2Config,
    ABCGv2Controller,
    AssignmentResult,
    VelocitySafetyConfig,
    project_velocity_safety,
)


def _identity_assignment(count: int) -> AssignmentResult:
    ids = np.arange(count, dtype=int)
    return AssignmentResult(
        guide_to_target=ids,
        target_to_guide=ids,
        reserve_guide_ids=np.empty(0, dtype=int),
        unmet_target_ids=np.empty(0, dtype=int),
        cost_matrix=np.zeros((count, count), dtype=float),
        total_cost=0.0,
        switch_count=0,
        status="VALID",
    )


def test_pair_projection_prevents_one_step_guide_conflict() -> None:
    positions = np.array([[2.0, 2.0], [3.0, 2.0]])
    nominal = np.array([[1.0, 0.0], [-1.0, 0.0]])
    config = VelocitySafetyConfig(min_guide_distance=1.0, min_crowd_distance=0.0)

    result = project_velocity_safety(
        positions,
        nominal,
        crowd_points=np.empty((0, 2)),
        room_size=np.array([10.0, 10.0]),
        dt=0.1,
        v_max=2.0,
        config=config,
    )

    predicted = positions + 0.1 * result.applied_control
    assert result.status == "PROJECTED"
    assert result.feasible
    assert result.violated_constraint_count > 0
    assert np.linalg.norm(predicted[0] - predicted[1]) >= 1.0 - config.residual_tolerance
    assert result.max_residual_after <= config.residual_tolerance


def test_crowd_and_room_halfspaces_are_enforced() -> None:
    positions = np.array([[1.0, 1.0], [9.0, 5.0]])
    nominal = np.array([[-1.0, 0.0], [2.0, 0.0]])
    crowd = np.array([[0.0, 1.0]])
    config = VelocitySafetyConfig(
        min_guide_distance=0.0,
        min_crowd_distance=1.0,
        room_margin=1.0,
    )

    result = project_velocity_safety(
        positions,
        nominal,
        crowd_points=crowd,
        room_size=np.array([10.0, 10.0]),
        dt=0.1,
        v_max=2.0,
        config=config,
    )

    predicted = positions + 0.1 * result.applied_control
    assert result.status == "PROJECTED"
    assert result.constraint_type_counts["crowd"] == 1
    assert result.constraint_type_counts["room"] == 3
    assert np.linalg.norm(predicted[0] - crowd[0]) >= 1.0 - config.residual_tolerance
    assert predicted[1, 0] <= 9.0 + config.residual_tolerance


def test_safe_nominal_control_is_left_unchanged() -> None:
    positions = np.array([[2.0, 2.0], [4.0, 2.0]])
    nominal = np.array([[0.1, 0.0], [0.1, 0.0]])
    config = VelocitySafetyConfig(min_guide_distance=1.0, min_crowd_distance=0.5)

    result = project_velocity_safety(
        positions,
        nominal,
        crowd_points=np.array([[2.0, 0.0]]),
        room_size=np.array([8.0, 6.0]),
        dt=0.1,
        v_max=1.0,
        config=config,
    )

    assert result.status == "VALID"
    assert result.feasible
    assert np.array_equal(result.applied_control, nominal)
    assert result.projection_sweeps == 0


def test_infeasible_recovery_returns_finite_emergency_stop() -> None:
    positions = np.array([[2.0, 2.0], [2.0, 2.0]])
    nominal = np.zeros((2, 2), dtype=float)
    config = VelocitySafetyConfig(
        min_guide_distance=1.0,
        min_crowd_distance=0.0,
        max_projection_sweeps=60,
    )

    result = project_velocity_safety(
        positions,
        nominal,
        crowd_points=np.empty((0, 2)),
        room_size=np.array([5.0, 5.0]),
        dt=0.1,
        v_max=0.1,
        config=config,
    )

    assert result.status == "SAFETY_INFEASIBLE"
    assert not result.feasible
    assert result.emergency_stop
    assert np.array_equal(result.applied_control, np.zeros_like(nominal))
    assert result.max_residual_after > config.residual_tolerance
    assert np.all(np.isfinite(result.projected_control))
    assert np.all(np.isfinite(result.constraint_residuals_after))


def test_episode_uses_applied_safety_control_and_records_every_projection() -> None:
    guides = np.array([[2.0, 2.0], [3.0, 2.0]])
    targets = np.array([[3.0, 2.0], [2.0, 2.0]])
    controller = ABCGv2Controller(
        ABCGv2Config(dt=0.1, k_p=1.0, v_max=1.0, hold_steps=2, max_steps=2),
        VelocitySafetyConfig(min_guide_distance=1.0, min_crowd_distance=0.0),
    )

    episode = controller.run_fixed_target_episode(
        guides,
        targets,
        _identity_assignment(2),
        crowd_points=np.empty((0, 2)),
        room_size=np.array([5.0, 5.0]),
    )

    assert episode.status == "TIMEOUT"
    assert len(episode.safety_status_history) == len(episode.applied_controls)
    assert episode.safety_status_history[0] == "PROJECTED"
    assert not np.array_equal(episode.nominal_controls[0], episode.applied_controls[0])
    assert np.all(episode.safety_max_residual_after <= controller.safety_config.residual_tolerance)
    assert len(episode.safety_max_guide_pair_residual_after) == len(episode.applied_controls)
    assert np.all(np.isfinite(episode.safety_control_adjustment_norm))


def test_episode_propagates_safety_infeasible_without_nan() -> None:
    guides = np.array([[2.0, 2.0], [2.0, 2.0]])
    targets = np.array([[3.0, 2.0], [1.0, 2.0]])
    controller = ABCGv2Controller(
        ABCGv2Config(dt=0.1, k_p=1.0, v_max=0.1, hold_steps=2, max_steps=10),
        VelocitySafetyConfig(
            min_guide_distance=1.0,
            min_crowd_distance=0.0,
            max_projection_sweeps=60,
        ),
    )

    episode = controller.run_fixed_target_episode(
        guides,
        targets,
        _identity_assignment(2),
        crowd_points=np.empty((0, 2)),
        room_size=np.array([5.0, 5.0]),
    )

    assert episode.status == "SAFETY_INFEASIBLE"
    assert episode.stop_reason == "velocity_safety_projection_infeasible"
    assert len(episode.applied_controls) == 1
    assert episode.safety_emergency_stop_history.tolist() == [True]
    assert np.all(np.isfinite(episode.positions))
    assert np.all(np.isfinite(episode.safety_max_residual_after))


def test_safety_enabled_episode_can_converge_when_target_is_feasible() -> None:
    guides = np.array([[2.0, 2.0]])
    targets = np.array([[3.0, 2.0]])
    controller = ABCGv2Controller(
        ABCGv2Config(
            dt=0.1,
            k_p=2.0,
            v_max=1.0,
            tracking_rmse_tolerance=1.0e-3,
            speed_tolerance=1.0e-3,
            hold_steps=2,
            max_steps=100,
        ),
        VelocitySafetyConfig(min_guide_distance=0.5, min_crowd_distance=0.5),
    )

    episode = controller.run_fixed_target_episode(
        guides,
        targets,
        _identity_assignment(1),
        crowd_points=np.array([[0.0, 0.0]]),
        room_size=np.array([6.0, 6.0]),
    )

    assert episode.status == "CONVERGED"
    assert np.all(episode.safety_status_history == "VALID")
    assert episode.diagnostics["safety_filter_status"] == "ENABLED_PR5"
    assert episode.tracking_rmse[-1] < episode.tracking_rmse[0]
