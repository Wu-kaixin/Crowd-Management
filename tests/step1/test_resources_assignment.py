from __future__ import annotations

import numpy as np
import pytest

from crowd_management.controllers import (
    AssignmentConfig,
    IdentityPreservingAssigner,
    ResourcePolicy,
    ResourcePolicyConfig,
    assign_guides_to_targets,
)


@pytest.mark.parametrize(
    ("length", "expected_requested", "expected_active"),
    [
        (0.01, 1, 2),
        (4.0, 2, 2),
        (4.000001, 3, 3),
        (12.0, 6, 6),
    ],
)
def test_resource_formula_handles_length_boundaries(
    length: float,
    expected_requested: int,
    expected_active: int,
) -> None:
    policy = ResourcePolicy(ResourcePolicyConfig(g_req=2.0, m_min=2))

    decision = policy.decide(length, available_count=8)

    assert decision.status == "VALID"
    assert decision.requested_count == expected_requested
    assert decision.desired_count == expected_active
    assert decision.active_count == expected_active
    assert decision.reserve_count == 8 - expected_active
    assert decision.unmet_target_count == 0


def test_resource_policy_reports_reserve_semantics() -> None:
    policy = ResourcePolicy(ResourcePolicyConfig(g_req=2.5, m_min=3))

    decision = policy.decide(boundary_length=10.0, available_count=7)

    assert decision.status == "VALID"
    assert decision.requested_count == 4
    assert decision.active_count == 4
    assert decision.reserve_count == 3
    assert decision.unmet_target_count == 0


def test_resource_policy_reports_capacity_shortfall_instead_of_clipping_silently() -> None:
    policy = ResourcePolicy(ResourcePolicyConfig(g_req=2.0, m_min=3))

    decision = policy.decide(boundary_length=10.1, available_count=4)

    assert decision.status == "CAPACITY_SHORTFALL"
    assert decision.requested_count == 6
    assert decision.desired_count == 6
    assert decision.active_count == 4
    assert decision.reserve_count == 0
    assert decision.unmet_target_count == 2
    assert decision.diagnostics["reason"] == "insufficient_available_guides"


def test_resource_hysteresis_prevents_threshold_chatter() -> None:
    policy = ResourcePolicy(
        ResourcePolicyConfig(
            g_req=2.0,
            m_min=2,
            increase_hysteresis=0.2,
            decrease_hysteresis=0.2,
        )
    )

    below_up_margin = policy.decide(8.05, available_count=8, previous_active_count=4)
    above_up_margin = policy.decide(8.25, available_count=8, previous_active_count=4)
    above_down_margin = policy.decide(7.95, available_count=8, previous_active_count=5)
    below_down_margin = policy.decide(7.75, available_count=8, previous_active_count=5)

    assert below_up_margin.requested_count == 5
    assert below_up_margin.desired_count == 4
    assert below_up_margin.hysteresis_applied
    assert above_up_margin.desired_count == 5
    assert above_down_margin.requested_count == 4
    assert above_down_margin.desired_count == 5
    assert above_down_margin.hysteresis_applied
    assert below_down_margin.desired_count == 4


def test_assignment_is_deterministic_and_marks_reserve_guides() -> None:
    guides = np.array([[0.0, 0.0], [10.0, 0.0], [20.0, 0.0]])
    targets = np.array([[0.1, 0.0], [19.9, 0.0]])
    config = AssignmentConfig(lambda_switch=0.0, reserve_cost=0.5)

    first = assign_guides_to_targets(guides, targets, config)
    second = IdentityPreservingAssigner(config).assign(guides, targets)

    assert first.status == "VALID"
    assert np.array_equal(first.guide_to_target, np.array([0, -1, 1]))
    assert np.array_equal(first.target_to_guide, np.array([0, 2]))
    assert np.array_equal(first.reserve_guide_ids, np.array([1]))
    assert len(first.unmet_target_ids) == 0
    assert np.array_equal(first.guide_to_target, second.guide_to_target)
    assert first.total_cost == second.total_cost


def test_switch_penalty_preserves_previous_identity_when_justified() -> None:
    guides = np.array([[9.0, 0.0], [1.0, 0.0]])
    targets = np.array([[0.0, 0.0], [10.0, 0.0]])
    previous = np.array([0, 1])

    nearest = assign_guides_to_targets(guides, targets, AssignmentConfig(lambda_switch=0.0), previous)
    stable = assign_guides_to_targets(guides, targets, AssignmentConfig(lambda_switch=100.0), previous)

    assert np.array_equal(nearest.guide_to_target, np.array([1, 0]))
    assert nearest.switch_count == 2
    assert np.array_equal(stable.guide_to_target, previous)
    assert stable.switch_count == 0


def test_assignment_exposes_unmet_targets_under_capacity_shortfall() -> None:
    guides = np.array([[0.0, 0.0], [10.0, 0.0]])
    targets = np.array([[0.0, 0.0], [5.0, 0.0], [10.0, 0.0]])

    result = assign_guides_to_targets(guides, targets, AssignmentConfig())

    assert result.status == "CAPACITY_SHORTFALL"
    assert len(result.unmet_target_ids) == 1
    assert result.unmet_target_ids[0] == 1
    assert result.target_to_guide[1] == -1
    assert len(result.reserve_guide_ids) == 0
    assert np.all(result.guide_to_target >= 0)


def test_invalid_assignment_input_is_explicit_and_contains_no_nan() -> None:
    guides = np.array([[0.0, 0.0], [np.nan, 1.0]])
    targets = np.array([[1.0, 0.0]])

    result = assign_guides_to_targets(guides, targets, AssignmentConfig())

    assert result.status == "ASSIGNMENT_INFEASIBLE"
    assert result.diagnostics["reason"] == "invalid_guide_positions"
    assert np.all(np.isfinite(result.guide_to_target))
    assert np.all(np.isfinite(result.target_to_guide))
    assert np.all(np.isfinite(result.cost_matrix))
