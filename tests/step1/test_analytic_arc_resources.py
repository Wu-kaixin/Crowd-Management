from __future__ import annotations

import json

import numpy as np
import pytest

from crowd_management.controllers import (
    RobustResourceConfig,
    allocate_robust_resources,
    analytic_equal_arc_gap,
    analytic_uniform_cost,
    optimize_equal_arc_phase,
    periodic_site_sets_equal,
    plan_analytic_equal_arc,
)


@pytest.mark.parametrize("seed", range(20))
def test_analytic_equal_arc_property(seed: int) -> None:
    rng = np.random.default_rng(seed)
    length = float(rng.uniform(0.1, 100.0))
    count = int(rng.integers(1, 33))
    phase = float(rng.uniform(-3.0 * length, 3.0 * length))

    plan = plan_analytic_equal_arc(length, count, phase=phase)

    assert plan.status == "PLAN_OPTIMAL"
    assert plan.h_star == pytest.approx(length**3 / (12.0 * count**2), rel=2.0e-12)
    assert plan.max_arc_gap == pytest.approx(length / count, rel=2.0e-12)
    assert analytic_uniform_cost(length, count) == plan.h_star
    assert analytic_equal_arc_gap(length, count) == plan.max_arc_gap
    gaps = np.diff(np.r_[plan.target_s, plan.target_s[0] + length])
    assert np.allclose(gaps, length / count, rtol=2.0e-12, atol=2.0e-12)


def test_phase_plus_one_gap_is_the_same_periodic_set() -> None:
    length = 17.3
    count = 7
    phase = 0.419
    first = plan_analytic_equal_arc(length, count, phase=phase)
    second = plan_analytic_equal_arc(length, count, phase=phase + length / count)

    assert periodic_site_sets_equal(first.target_s, second.target_s, length)
    assert first.h_star == second.h_star
    assert first.max_arc_gap == second.max_arc_gap


def test_phase_optimizer_preserves_coverage_and_never_worsens_phase_zero() -> None:
    length = 12.0
    count = 4
    desired_phase = 0.75

    def cost(sites: np.ndarray) -> float:
        first = float(np.min(sites))
        periodic_error = abs(((first - desired_phase + 1.5) % 3.0) - 1.5)
        return periodic_error**2

    result = optimize_equal_arc_phase(length, count, cost, grid_size=16)

    assert result.status == "PHASE_GRID_SELECTED"
    assert result.plan is not None
    assert result.phase_zero_cost is not None
    assert result.optimized_cost is not None
    assert result.optimized_cost <= result.phase_zero_cost + 1.0e-15
    assert result.plan.h_star == pytest.approx(length**3 / (12.0 * count**2))
    assert result.plan.max_arc_gap == pytest.approx(length / count)


def test_phase_optimizer_accepts_geodesic_cost_matrix_and_reports_no_route() -> None:
    feasible = optimize_equal_arc_phase(
        8.0,
        2,
        lambda sites: np.array([[sites[0] + 1.0, sites[1] + 4.0], [sites[0] + 3.0, sites[1] + 1.0]]),
        grid_size=8,
    )
    blocked = optimize_equal_arc_phase(
        8.0,
        2,
        lambda sites: np.full((2, len(sites)), np.inf),
        grid_size=8,
    )

    assert feasible.status == "PHASE_GRID_SELECTED"
    assert feasible.diagnostics["evaluation_kind"] == "hungarian_pairwise_cost_matrix"
    assert blocked.status == "ROUTE_INFEASIBLE"
    assert blocked.plan is None
    assert not np.any(blocked.candidate_feasible)


def test_nominal_and_calibrated_robust_resource_counts() -> None:
    config = RobustResourceConfig(required_arc_gap=2.0, m_min=3)
    decision = allocate_robust_resources(
        10.0,
        12,
        config,
        uncertainty_mode="calibrated_tube",
        uncertainty_status="CALIBRATED_TUBE",
        robust_envelope_length=13.0,
    )

    assert decision.status == "VALID"
    assert decision.nominal_count == 5
    assert decision.robust_count == 7
    assert decision.active_count == 7
    assert decision.nominal_gap == pytest.approx(2.0)
    assert decision.selected_envelope_gap == pytest.approx(13.0 / 7.0)
    assert "explicit calibrated envelope only" in str(decision.diagnostics["scope_limitation"])


def test_uncalibrated_stability_is_resource_uncertain_and_serializable() -> None:
    decision = allocate_robust_resources(
        10.0,
        8,
        RobustResourceConfig(required_arc_gap=2.0, m_min=3),
        uncertainty_mode="stability",
        uncertainty_status="UNCALIBRATED_STABILITY",
    )

    assert decision.status == "RESOURCE_UNCERTAIN"
    assert decision.robust_count is None
    assert decision.active_count == decision.nominal_count
    assert "RESOURCE_UNCERTAIN" in decision.conditions
    json.dumps(decision.to_dict())


def test_resource_status_precedence_and_hysteresis_gap_failure() -> None:
    config = RobustResourceConfig(
        required_arc_gap=2.0,
        m_min=2,
        increase_hysteresis=0.2,
    )
    degraded = allocate_robust_resources(
        8.05,
        8,
        config,
        uncertainty_mode="none",
        previous_active_count=4,
    )
    uncertain_shortfall = allocate_robust_resources(
        10.0,
        2,
        config,
        uncertainty_mode="stability",
    )

    assert degraded.status == "HYSTERESIS_GAP_DEGRADED"
    assert degraded.active_count == 4
    assert degraded.selected_envelope_gap == pytest.approx(8.05 / 4.0)
    assert uncertain_shortfall.status == "CAPACITY_SHORTFALL"
    assert uncertain_shortfall.conditions[:2] == (
        "CAPACITY_SHORTFALL",
        "RESOURCE_UNCERTAIN",
    )


def test_count_tolerance_avoids_spurious_extra_guide_at_exact_threshold() -> None:
    decision = allocate_robust_resources(
        4.0 + 1.0e-14,
        8,
        RobustResourceConfig(required_arc_gap=2.0, m_min=1, count_tolerance=1.0e-12),
    )

    assert decision.nominal_count == 2
    assert decision.status == "VALID"


def test_phase_grid_selection_does_not_claim_continuous_global_optimum() -> None:
    result = optimize_equal_arc_phase(
        4.0,
        4,
        lambda sites: (float(np.min(sites)) - 0.1) ** 2,
        grid_size=4,
    )

    assert result.status == "PHASE_GRID_SELECTED"
    assert result.optimized_cost == pytest.approx(0.01)
    assert result.diagnostics["search_guarantee"] == (
        "deterministic_grid_only_not_continuous_global_optimum"
    )
    assert result.plan is not None and result.plan.status == "PLAN_OPTIMAL"


def test_capacity_shortfall_uses_required_count_not_hysteresis_policy_count() -> None:
    held_low = allocate_robust_resources(
        10.0,
        4,
        RobustResourceConfig(required_arc_gap=2.0, m_min=1, increase_hysteresis=100.0),
        previous_active_count=4,
    )
    held_high = allocate_robust_resources(
        10.0,
        6,
        RobustResourceConfig(required_arc_gap=2.0, m_min=1, decrease_hysteresis=100.0),
        previous_active_count=8,
    )

    assert held_low.required_count == 5
    assert held_low.status == "CAPACITY_SHORTFALL"
    assert held_low.unmet_target_count == 1
    assert held_high.required_count == 5
    assert held_high.status != "CAPACITY_SHORTFALL"
    assert held_high.unmet_target_count == 0
    assert held_high.diagnostics["policy_unmet_count"] == 2
