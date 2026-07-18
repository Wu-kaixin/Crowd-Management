from __future__ import annotations

import numpy as np

from crowd_management.controllers import (
    ABCGv2Config,
    ABCGv2Controller,
    AssignmentConfig,
    ConvergenceStateMachine,
    ControlOutput,
    assign_guides_to_targets,
    integrate_guide_positions,
    nominal_guide_velocity,
)


def _assignment(guides: np.ndarray, targets: np.ndarray):
    return assign_guides_to_targets(guides, targets, AssignmentConfig(lambda_switch=0.0))


def test_nominal_velocity_is_proportional_and_individually_saturated() -> None:
    positions = np.array([[0.0, 0.0], [0.0, 0.0], [2.0, 2.0]])
    assigned_targets = np.array([[10.0, 0.0], [0.1, 0.0], [2.0, 2.0]])
    active = np.array([True, True, False])

    velocity = nominal_guide_velocity(positions, assigned_targets, active, k_p=2.0, v_max=1.0)

    assert np.allclose(velocity[0], [1.0, 0.0])
    assert np.allclose(velocity[1], [0.2, 0.0])
    assert np.allclose(velocity[2], [0.0, 0.0])
    assert np.all(np.linalg.norm(velocity, axis=1) <= 1.0)


def test_integrator_implements_p_dot_equals_u_without_mutating_input() -> None:
    positions = np.array([[1.0, 2.0], [3.0, 4.0]])
    original = positions.copy()
    controls = np.array([[0.5, -0.25], [-1.0, 2.0]])

    updated = integrate_guide_positions(positions, controls, dt=0.2)

    assert np.allclose(updated, positions + 0.2 * controls)
    assert np.array_equal(positions, original)


def test_reset_step_contract_uses_measured_guide_feedback_and_explicit_output() -> None:
    guides = np.array([[0.0, 0.0], [2.0, 0.0], [5.0, 5.0]])
    targets = np.array([[1.0, 0.0], [3.0, 0.0]])
    assignment = _assignment(guides, targets)
    controller = ABCGv2Controller(ABCGv2Config(dt=0.1, k_p=1.5, v_max=0.5))

    controller.reset(targets, assignment, guides)
    first = controller.step(np.empty((0, 2)), guides, dt=0.1)
    next_guides = integrate_guide_positions(guides, first.safe_velocity, 0.1)
    second = controller.step(np.empty((0, 2)), next_guides, dt=0.1)

    assert isinstance(first, ControlOutput)
    assert first.preferred_velocity.shape == guides.shape
    assert first.safe_velocity.shape == guides.shape
    assert first.targets.shape == targets.shape
    assert first.active_ids == (0, 1)
    assert first.reserve_ids == (2,)
    assert np.array_equal(first.assignment, assignment.guide_to_target)
    assert first.state == "TRACK"
    assert first.events == ("state:INIT->TRACK",)
    assert second.diagnostics["tracking_rmse"] < first.diagnostics["tracking_rmse"]
    assert np.allclose(second.diagnostics["measured_guide_state"], next_guides)


def test_reset_step_propagates_precondition_failure_without_motion() -> None:
    guides = np.array([[0.0, 0.0]])
    targets = np.array([[1.0, 0.0]])
    controller = ABCGv2Controller()
    controller.reset(
        targets,
        _assignment(guides, targets),
        guides,
        precondition_status="CAPACITY_SHORTFALL",
    )

    output = controller.step(np.empty((0, 2)), guides, dt=0.1)

    assert output.state == "CAPACITY_SHORTFALL"
    assert np.array_equal(output.preferred_velocity, np.zeros_like(guides))
    assert np.array_equal(output.safe_velocity, np.zeros_like(guides))
    assert output.events == ("terminal:CAPACITY_SHORTFALL",)


def test_step_contract_times_out_at_configured_control_horizon() -> None:
    guides = np.array([[0.0, 0.0]])
    targets = np.array([[100.0, 0.0]])
    controller = ABCGv2Controller(ABCGv2Config(max_steps=2, v_max=0.1))
    controller.reset(targets, _assignment(guides, targets), guides)

    first = controller.step(np.empty((0, 2)), guides, dt=0.1)
    guides = integrate_guide_positions(guides, first.safe_velocity, 0.1)
    second = controller.step(np.empty((0, 2)), guides, dt=0.1)

    assert first.state == "TRACK"
    assert second.state == "TIMEOUT"
    assert "state:TRACK->TIMEOUT" in second.events


def test_fixed_target_episode_converges_with_complete_monotone_trace() -> None:
    guides = np.array([[0.0, 0.0], [2.0, 0.0], [5.0, 5.0]])
    targets = np.array([[1.0, 0.0], [3.0, 0.0]])
    assignment = _assignment(guides, targets)
    config = ABCGv2Config(
        dt=0.1,
        k_p=2.0,
        v_max=0.6,
        tracking_rmse_tolerance=1.0e-3,
        speed_tolerance=1.0e-3,
        hold_steps=3,
        max_steps=200,
    )

    episode = ABCGv2Controller(config).run_fixed_target_episode(guides, targets, assignment)

    assert episode.status == "CONVERGED"
    assert episode.converged
    assert episode.positions.shape[0] == episode.nominal_controls.shape[0] + 1
    assert episode.positions.shape == episode.velocities.shape
    assert episode.applied_controls.shape == episode.nominal_controls.shape
    assert len(episode.times) == len(episode.positions)
    assert len(episode.state_history) == len(episode.positions)
    assert len(episode.tracking_rmse) == len(episode.positions)
    assert len(episode.hold_count_history) == len(episode.positions)
    assert np.all(np.diff(episode.tracking_rmse) <= config.error_increase_tolerance)
    assert episode.tracking_rmse[-1] < episode.tracking_rmse[0]
    assert np.max(np.linalg.norm(episode.applied_controls, axis=2)) <= config.v_max
    assert np.array_equal(episode.reserve_guide_ids, np.array([2]))
    assert episode.diagnostics["safety_filter_status"] == "DISABLED_PR5"


def test_hold_requires_consecutive_full_window() -> None:
    machine = ConvergenceStateMachine(hold_steps=3)

    states = [
        machine.update(True),
        machine.update(True),
        machine.update(False),
        machine.update(True),
        machine.update(True),
        machine.update(True),
    ]

    assert states == ["HOLD", "HOLD", "TRACK", "HOLD", "HOLD", "CONVERGED"]
    assert machine.hold_count == 3


def test_episode_at_target_still_waits_for_hold_window() -> None:
    guides = np.array([[1.0, 0.0], [3.0, 0.0]])
    targets = guides.copy()
    assignment = _assignment(guides, targets)
    config = ABCGv2Config(hold_steps=4, max_steps=10)

    episode = ABCGv2Controller(config).run_fixed_target_episode(guides, targets, assignment)

    assert episode.status == "CONVERGED"
    assert episode.state_history.tolist() == ["INIT", "HOLD", "HOLD", "HOLD", "CONVERGED"]
    assert len(episode.applied_controls) == 4


def test_timeout_is_explicit_and_trace_is_not_dropped() -> None:
    guides = np.array([[0.0, 0.0]])
    targets = np.array([[100.0, 0.0]])
    assignment = _assignment(guides, targets)
    config = ABCGv2Config(dt=0.1, k_p=1.0, v_max=0.1, hold_steps=2, max_steps=2)

    episode = ABCGv2Controller(config).run_fixed_target_episode(guides, targets, assignment)

    assert episode.status == "TIMEOUT"
    assert not episode.converged
    assert episode.stop_reason == "maximum_steps_reached"
    assert episode.positions.shape == (3, 1, 2)
    assert episode.applied_controls.shape == (2, 1, 2)
    assert episode.state_history[-1] == "TIMEOUT"


def test_capacity_shortfall_precondition_stops_before_motion() -> None:
    guides = np.array([[0.0, 0.0]])
    targets = np.array([[1.0, 0.0]])
    assignment = _assignment(guides, targets)

    episode = ABCGv2Controller().run_fixed_target_episode(
        guides,
        targets,
        assignment,
        precondition_status="CAPACITY_SHORTFALL",
    )

    assert episode.status == "CAPACITY_SHORTFALL"
    assert episode.positions.shape == (1, 1, 2)
    assert episode.applied_controls.shape == (0, 1, 2)
    assert episode.state_history.tolist() == ["CAPACITY_SHORTFALL"]


def test_assignment_infeasible_propagates_without_nan() -> None:
    guides = np.array([[0.0, 0.0]])
    targets = np.array([[1.0, 0.0]])
    invalid_assignment = assign_guides_to_targets(
        np.array([[np.nan, 0.0]]),
        targets,
        AssignmentConfig(),
    )

    episode = ABCGv2Controller().run_fixed_target_episode(guides, targets, invalid_assignment)

    assert episode.status == "ASSIGNMENT_INFEASIBLE"
    assert not episode.converged
    assert np.all(np.isfinite(episode.positions))
    assert np.all(np.isfinite(episode.applied_controls))
