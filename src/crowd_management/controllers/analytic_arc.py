"""Analytic periodic equal-arc coverage and deterministic phase selection.

For uniform density ``phi(s)=1`` on one closed curve of length ``L``, the
global optimum with ``m`` sites is the equal-arc family.  Its exact continuous
coverage objective and maximum consecutive gap are

``H* = L**3 / (12*m**2)`` and ``G = L/m``.

The coverage objective is invariant to the phase.  Phase is therefore selected
only to reduce an external deployment cost (normally a routed assignment cost)
while preserving equal-arc spacing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np
from scipy.optimize import linear_sum_assignment

from ..types import Array
from .periodic_arc_cvt import equal_arc_target_s, periodic_uniform_coverage_cost


PhaseCostEvaluator = Callable[[Array], float | Array]


@dataclass(frozen=True)
class AnalyticArcPlan:
    """One member of the uniform-density analytic optimum family."""

    length: float
    active_count: int
    phase: float
    phase_period: float
    target_s: Array
    h_star: float
    max_arc_gap: float
    status: str = "PLAN_OPTIMAL"
    diagnostics: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class PhaseOptimizationResult:
    """Deterministic grid search over the fundamental phase interval [0, G)."""

    plan: AnalyticArcPlan | None
    status: str
    phase_zero_cost: float | None
    optimized_cost: float | None
    candidate_phases: Array
    candidate_costs: Array
    candidate_feasible: Array
    selected_candidate_index: int | None
    diagnostics: dict[str, object] = field(default_factory=dict)


def analytic_uniform_cost(length: float, m: int) -> float:
    """Return the exact continuous equal-arc optimum ``L^3/(12m^2)``."""

    period, count = _validate_length_count(length, m)
    return float(period**3 / (12.0 * count**2))


def analytic_equal_arc_gap(length: float, m: int) -> float:
    """Return the exact maximum consecutive arc gap ``L/m``."""

    period, count = _validate_length_count(length, m)
    return float(period / count)


def plan_analytic_equal_arc(
    length: float,
    m: int,
    *,
    phase: float = 0.0,
    verification_tolerance: float = 1.0e-11,
) -> AnalyticArcPlan:
    """Construct and independently verify an analytic ``phi=1`` plan.

    ``phase`` is canonicalized modulo ``G=L/m`` because adding one gap merely
    cyclically relabels the same target set.
    """

    period, count = _validate_length_count(length, m)
    if not np.isfinite(phase):
        raise ValueError("phase must be finite.")
    if not np.isfinite(verification_tolerance) or verification_tolerance < 0.0:
        raise ValueError("verification_tolerance must be finite and non-negative.")
    gap = period / count
    canonical_phase = float(np.mod(float(phase), gap))
    sites = equal_arc_target_s(period, count, canonical_phase)
    exact = analytic_uniform_cost(period, count)
    independently_evaluated = periodic_uniform_coverage_cost(sites, period)
    error = abs(independently_evaluated - exact)
    scale = max(1.0, abs(exact))
    if error > float(verification_tolerance) * scale:
        return AnalyticArcPlan(
            length=period,
            active_count=count,
            phase=canonical_phase,
            phase_period=gap,
            target_s=sites,
            h_star=exact,
            max_arc_gap=gap,
            status="PLAN_ANALYTIC_VERIFICATION_FAILED",
            diagnostics={
                "reason": "continuous_cost_does_not_match_closed_form",
                "evaluated_h": independently_evaluated,
                "formula_error": error,
                "verification_tolerance": float(verification_tolerance),
            },
        )
    return AnalyticArcPlan(
        length=period,
        active_count=count,
        phase=canonical_phase,
        phase_period=gap,
        target_s=sites,
        h_star=exact,
        max_arc_gap=gap,
        diagnostics={
            "planner": "analytic_equal_arc_phi_1",
            "formula_h": "L^3/(12*m^2)",
            "formula_gap": "L/m",
            "evaluated_h": independently_evaluated,
            "formula_error": error,
            "phase_domain": "[0,L/m)",
            "phase_role": "external_deployment_cost_only",
            "lloyd_role": "nonuniform_weight_or_ablation_only",
        },
    )


def optimize_equal_arc_phase(
    length: float,
    m: int,
    cost_evaluator: PhaseCostEvaluator,
    *,
    grid_size: int = 64,
    tie_tolerance: float = 1.0e-12,
) -> PhaseOptimizationResult:
    """Minimize external cost without changing the equal-arc optimum.

    The evaluator may return a scalar total cost or a two-dimensional pairwise
    cost matrix.  Matrices are reduced by a finite Hungarian assignment.  A
    phase with no finite assignment is retained as an infeasible candidate;
    if every phase is infeasible the function returns ``ROUTE_INFEASIBLE``.
    """

    period, count = _validate_length_count(length, m)
    if not callable(cost_evaluator):
        raise TypeError("cost_evaluator must be callable.")
    if isinstance(grid_size, bool) or not isinstance(grid_size, (int, np.integer)) or grid_size < 1:
        raise ValueError("grid_size must be a positive integer.")
    if not np.isfinite(tie_tolerance) or tie_tolerance < 0.0:
        raise ValueError("tie_tolerance must be finite and non-negative.")

    gap = period / count
    phases = gap * np.arange(int(grid_size), dtype=float) / int(grid_size)
    costs = np.full(len(phases), np.inf, dtype=float)
    feasible = np.zeros(len(phases), dtype=bool)
    evaluation_kind: str | None = None
    for index, phase in enumerate(phases):
        plan = plan_analytic_equal_arc(period, count, phase=float(phase))
        value = cost_evaluator(plan.target_s.copy())
        if np.isscalar(value):
            evaluation_kind = evaluation_kind or "scalar_total_cost"
            candidate = float(value)
            if np.isfinite(candidate) and candidate >= 0.0:
                costs[index] = candidate
                feasible[index] = True
        else:
            evaluation_kind = evaluation_kind or "hungarian_pairwise_cost_matrix"
            candidate = _finite_assignment_cost(np.asarray(value, dtype=float), count)
            if candidate is not None:
                costs[index] = candidate
                feasible[index] = True

    if not np.any(feasible):
        return PhaseOptimizationResult(
            plan=None,
            status="ROUTE_INFEASIBLE",
            phase_zero_cost=None,
            optimized_cost=None,
            candidate_phases=phases,
            candidate_costs=costs,
            candidate_feasible=feasible,
            selected_candidate_index=None,
            diagnostics={
                "reason": "no_phase_has_a_finite_complete_assignment",
                "grid_size": int(grid_size),
                "phase_domain": "[0,L/m)",
                "evaluation_kind": evaluation_kind,
            },
        )

    best_cost = float(np.min(costs[feasible]))
    tolerance = float(tie_tolerance) * max(1.0, abs(best_cost))
    tied = np.flatnonzero(feasible & (costs <= best_cost + tolerance))
    selected = int(tied[0])
    selected_plan = plan_analytic_equal_arc(period, count, phase=float(phases[selected]))
    zero_cost = float(costs[0]) if feasible[0] else None
    return PhaseOptimizationResult(
        plan=selected_plan,
            status="PHASE_GRID_SELECTED",
        phase_zero_cost=zero_cost,
        optimized_cost=float(costs[selected]),
        candidate_phases=phases,
        candidate_costs=costs,
        candidate_feasible=feasible,
        selected_candidate_index=selected,
        diagnostics={
            "reason": "minimum_evaluated_external_deployment_cost",
            "grid_size": int(grid_size),
            "tie_break": "smallest_canonical_phase",
            "tie_tolerance": float(tie_tolerance),
            "phase_domain": "[0,L/m)",
            "evaluation_kind": evaluation_kind,
            "search_guarantee": "deterministic_grid_only_not_continuous_global_optimum",
            "coverage_h_invariant": selected_plan.h_star,
            "coverage_gap_invariant": selected_plan.max_arc_gap,
        },
    )


def periodic_site_sets_equal(first: Array, second: Array, length: float, *, atol: float = 1.0e-10) -> bool:
    """Compare periodic site sets without relying on target identities."""

    period = float(length)
    a = np.sort(np.mod(np.asarray(first, dtype=float), period))
    b = np.sort(np.mod(np.asarray(second, dtype=float), period))
    if a.shape != b.shape or a.ndim != 1 or not np.all(np.isfinite(a)) or not np.all(np.isfinite(b)):
        return False
    if len(a) == 0:
        return True
    # Try every cyclic relabelling because a site may cross the zero seam.
    for shift in range(len(b)):
        delta = np.mod(np.roll(b, shift) - a + 0.5 * period, period) - 0.5 * period
        if np.all(np.abs(delta) <= atol):
            return True
    return False


def _finite_assignment_cost(matrix: Array, target_count: int) -> float | None:
    if matrix.ndim != 2 or matrix.shape[1] != target_count or matrix.shape[0] < target_count:
        return None
    if np.any(np.isnan(matrix)) or np.any(matrix < 0.0):
        return None
    finite = np.isfinite(matrix)
    if not np.any(finite):
        return None
    maximum = float(np.max(matrix[finite])) if np.any(finite) else 0.0
    sentinel = max(1.0, maximum) * (matrix.shape[0] + matrix.shape[1] + 1.0) * 1.0e6
    safe = np.where(finite, matrix, sentinel)
    rows, columns = linear_sum_assignment(safe)
    if len(columns) != target_count or not np.all(finite[rows, columns]):
        return None
    return float(np.sum(matrix[rows, columns]))


def _validate_length_count(length: float, m: int) -> tuple[float, int]:
    period = float(length)
    if not np.isfinite(period) or period <= 0.0:
        raise ValueError("length must be finite and positive.")
    if isinstance(m, bool) or not isinstance(m, (int, np.integer)) or m < 1:
        raise ValueError("m must be a positive integer.")
    return period, int(m)


__all__ = [
    "AnalyticArcPlan",
    "PhaseCostEvaluator",
    "PhaseOptimizationResult",
    "analytic_equal_arc_gap",
    "analytic_uniform_cost",
    "optimize_equal_arc_phase",
    "periodic_site_sets_equal",
    "plan_analytic_equal_arc",
]
