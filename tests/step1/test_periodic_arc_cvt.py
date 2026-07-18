from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from crowd_management.controllers import (
    PeriodicArcCVTConfig,
    PeriodicArcCVT,
    equal_arc_target_s,
    plan_equal_arc_coverage,
    plan_periodic_arc_coverage,
    periodic_uniform_coverage_cost,
)
from crowd_management.estimation import BoundaryEstimateV2


def _circle_boundary(*, confidence: float = 1.0, count: int = 240) -> BoundaryEstimateV2:
    radius = 2.0
    safety_distance = 0.4
    theta = np.linspace(0.0, 2.0 * np.pi, count, endpoint=False)
    normals = np.column_stack((np.cos(theta), np.sin(theta)))
    tangents = np.column_stack((-np.sin(theta), np.cos(theta)))
    curve = radius * normals
    offset = (radius + safety_distance) * normals
    length = 2.0 * np.pi * radius
    return BoundaryEstimateV2(
        curve_points=curve,
        offset_points=offset,
        arc_s=length * np.arange(count, dtype=float) / count,
        length=length,
        tangents=tangents,
        outward_normals=normals,
        uncertainty=np.zeros(count, dtype=float),
        confidence=np.full(count, confidence, dtype=float),
        component_count=1,
        topology_valid=True,
        method="analytic_test_circle",
        version=2,
        diagnostics={"confidence_status": "injected_test_value"},
    )


def test_equal_arc_circle_matches_uniform_optimum_and_true_periodic_gap() -> None:
    boundary = _circle_boundary()
    agent_count = 8

    plan = plan_equal_arc_coverage(boundary, agent_count, phase=0.37)

    expected_h = boundary.length**3 / (12.0 * agent_count**2)
    assert plan.status == "VALID"
    assert plan.converged
    assert plan.h_history[-1] == pytest.approx(expected_h, rel=1.0e-12)
    assert plan.max_arc_gap == pytest.approx(boundary.length / agent_count, rel=1.0e-12)
    assert np.allclose(np.linalg.norm(plan.target_xy, axis=1), 2.4, atol=2.0e-4)


def test_periodic_lloyd_cost_is_nonincreasing_and_converges_toward_equal_arcs() -> None:
    boundary = _circle_boundary()
    initial = boundary.length * np.array([0.01, 0.08, 0.31, 0.72])
    config = PeriodicArcCVTConfig(max_iterations=500, h_tolerance=1.0e-12, target_tolerance=1.0e-9)

    plan = plan_periodic_arc_coverage(boundary, 4, config, init=initial)

    assert plan.status == "VALID"
    assert plan.converged
    assert np.all(np.diff(plan.h_history) <= config.monotonic_tolerance)
    assert plan.h_history[-1] < plan.h_history[0]
    assert plan.max_arc_gap == pytest.approx(boundary.length / 4.0, rel=2.0e-5)


def test_periodic_seam_is_rotation_invariant() -> None:
    length = 10.0
    sites = np.array([0.1, 2.7, 5.4, 9.8])
    shift = 3.75

    first = periodic_uniform_coverage_cost(sites, length)
    second = periodic_uniform_coverage_cost(np.mod(sites + shift, length), length)
    wrapped_equal = equal_arc_target_s(length, 4, phase=9.5)

    assert first == pytest.approx(second, rel=1.0e-12)
    assert np.all((wrapped_equal >= 0.0) & (wrapped_equal < length))
    gaps = np.diff(np.r_[np.sort(wrapped_equal), np.sort(wrapped_equal)[0] + length])
    assert np.allclose(gaps, length / 4.0)


def test_confidence_gates_update_gain_without_becoming_a_density_weight() -> None:
    high_boundary = _circle_boundary(confidence=1.0)
    low_boundary = replace(high_boundary, confidence=np.zeros_like(high_boundary.confidence))
    # Keep this gain-isolation case away from the coordinate seam.  Identity
    # matching across that seam is deliberately deferred to PR3.
    initial = high_boundary.length * np.array([0.10, 0.18, 0.42, 0.75])
    config = PeriodicArcCVTConfig(max_iterations=1, eta_min=0.2)

    high = plan_periodic_arc_coverage(high_boundary, 4, config, init=initial)
    low = plan_periodic_arc_coverage(low_boundary, 4, config, init=initial)

    high_move = np.linalg.norm(np.sort(high.target_s) - np.sort(initial))
    low_move = np.linalg.norm(np.sort(low.target_s) - np.sort(initial))
    assert np.allclose(high.gain_history[0], 1.0)
    assert np.allclose(low.gain_history[0], config.eta_min)
    assert low_move == pytest.approx(config.eta_min * high_move, rel=1.0e-10)
    assert high.diagnostics["density_model"] == "uniform_phi_1"
    assert low.diagnostics["density_model"] == "uniform_phi_1"


def test_duplicate_sites_return_explicit_empty_cell_failure_without_nan() -> None:
    boundary = _circle_boundary()
    initial = np.array([0.0, 0.0, boundary.length / 2.0])

    plan = plan_periodic_arc_coverage(boundary, 3, PeriodicArcCVTConfig(), init=initial)

    assert plan.status == "PLAN_INVALID_EMPTY_CELL"
    assert not plan.converged
    assert plan.active_count == 2
    assert np.all(np.isfinite(plan.target_s))
    assert np.all(np.isfinite(plan.target_xy))
    assert np.all(np.isfinite(plan.h_history))


def test_invalid_boundary_returns_explicit_plan_failure() -> None:
    boundary = replace(_circle_boundary(), topology_valid=False)

    plan = plan_periodic_arc_coverage(boundary, 4, PeriodicArcCVTConfig())

    assert plan.status == "PLAN_INVALID_BOUNDARY"
    assert not plan.converged
    assert plan.active_count == 0
    assert plan.diagnostics["reason"] == "invalid_boundary_contract"


def test_periodic_plan_is_deterministic() -> None:
    boundary = _circle_boundary()
    initial = boundary.length * np.array([0.03, 0.23, 0.44, 0.91])
    config = PeriodicArcCVTConfig(max_iterations=40)

    first = plan_periodic_arc_coverage(boundary, 4, config, init=initial)
    second = plan_periodic_arc_coverage(boundary, 4, config, init=initial)
    facade = PeriodicArcCVT(config).plan(boundary, 4, init=initial)

    assert np.array_equal(first.target_s, second.target_s)
    assert np.array_equal(first.target_xy, second.target_xy)
    assert np.array_equal(first.h_history, second.h_history)
    assert np.array_equal(first.gain_history, second.gain_history)
    assert np.array_equal(first.target_s, facade.target_s)
