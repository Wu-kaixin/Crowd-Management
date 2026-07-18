"""PR2 periodic arc-length coverage planning for one valid closed boundary.

The optimizer uses uniform density ``phi(s) = 1``.  Boundary confidence gates
the relaxed Lloyd update only; it is deliberately not used as a risk or
coverage-density weight.  Resource allocation, persistent guide identities,
velocity control, and bootstrap confidence estimation belong to later PRs.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np

from ..estimation import BoundaryEstimateV2
from ..geometry import max_consecutive_arc_gap
from ..types import Array

PlanDiagnostics = dict[str, object]


@dataclass(frozen=True)
class PeriodicArcCVTConfig:
    """Numerical configuration for deterministic relaxed periodic Lloyd steps."""

    max_iterations: int = 80
    h_tolerance: float = 1.0e-10
    target_tolerance: float = 1.0e-8
    eta_min: float = 0.15
    monotonic_tolerance: float = 1.0e-10
    duplicate_tolerance: float = 1.0e-9
    confidence_quadrature_samples: int = 16

    def __post_init__(self) -> None:
        if isinstance(self.max_iterations, bool) or not isinstance(self.max_iterations, (int, np.integer)) or self.max_iterations < 1:
            raise ValueError("max_iterations must be at least one.")
        for name in ("h_tolerance", "target_tolerance", "monotonic_tolerance", "duplicate_tolerance"):
            value = float(getattr(self, name))
            if not np.isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be finite and non-negative.")
        if not np.isfinite(self.eta_min) or not 0.0 <= self.eta_min <= 1.0:
            raise ValueError("eta_min must be in [0, 1].")
        if (
            isinstance(self.confidence_quadrature_samples, bool)
            or not isinstance(self.confidence_quadrature_samples, (int, np.integer))
            or self.confidence_quadrature_samples < 1
        ):
            raise ValueError("confidence_quadrature_samples must be at least one.")


@dataclass(frozen=True)
class CoveragePlan:
    """Auditable output of periodic arc coverage planning.

    ``cell_bounds`` are unwrapped periodic Voronoi bounds associated with the
    sorted ``target_s`` values.  Bounds may cross zero or ``length``.
    """

    target_s: Array
    target_xy: Array
    cell_bounds: Array
    cell_mass: Array
    h_history: Array
    max_arc_gap: float
    active_count: int
    converged: bool
    status: str
    gain_history: Array = field(default_factory=lambda: np.empty((0, 0), dtype=float))
    diagnostics: PlanDiagnostics = field(default_factory=dict)


@dataclass(frozen=True)
class PeriodicArcCVT:
    """Small state-free planner facade around the stable PR2 function API."""

    config: PeriodicArcCVTConfig = field(default_factory=PeriodicArcCVTConfig)

    def __post_init__(self) -> None:
        if not isinstance(self.config, PeriodicArcCVTConfig):
            raise TypeError("config must be PeriodicArcCVTConfig.")

    def plan(self, boundary: BoundaryEstimateV2, m: int, init: Array | None = None) -> CoveragePlan:
        return plan_periodic_arc_coverage(boundary, m, self.config, init=init)


def _validate_agent_count(agent_count: int) -> int:
    if isinstance(agent_count, bool) or int(agent_count) != agent_count or int(agent_count) < 1:
        raise ValueError("m must be a positive integer.")
    return int(agent_count)


def _boundary_contract_valid(boundary: BoundaryEstimateV2) -> bool:
    if not isinstance(boundary, BoundaryEstimateV2):
        return False
    point_count = len(boundary.arc_s)
    arrays_valid = (
        np.asarray(boundary.arc_s).shape == (point_count,)
        and np.asarray(boundary.offset_points).shape == (point_count, 2)
        and np.asarray(boundary.confidence).shape == (point_count,)
    )
    if not arrays_valid or point_count < 3:
        return False
    arc_s = np.asarray(boundary.arc_s, dtype=float)
    confidence = np.asarray(boundary.confidence, dtype=float)
    points = np.asarray(boundary.offset_points, dtype=float)
    return bool(
        boundary.topology_valid
        and boundary.component_count == 1
        and np.isfinite(boundary.length)
        and boundary.length > 0.0
        and np.all(np.isfinite(arc_s))
        and np.all(np.isfinite(points))
        and np.all(np.isfinite(confidence))
        and np.all((confidence >= 0.0) & (confidence <= 1.0))
        and arc_s[0] == 0.0
        and np.all(np.diff(arc_s) > 0.0)
        and arc_s[-1] < boundary.length
    )


def _interpolate_periodic(values: Array, arc_s: Array, length: float, target_s: Array) -> Array:
    samples = np.asarray(values, dtype=float)
    coordinates = np.asarray(arc_s, dtype=float)
    targets = np.mod(np.asarray(target_s, dtype=float), length)
    extended_s = np.r_[coordinates, length]
    if samples.ndim == 1:
        return np.interp(targets, extended_s, np.r_[samples, samples[0]])
    return np.column_stack(
        [np.interp(targets, extended_s, np.r_[samples[:, column], samples[0, column]]) for column in range(samples.shape[1])]
    )


def _target_xy(boundary: BoundaryEstimateV2, target_s: Array) -> Array:
    return _interpolate_periodic(boundary.offset_points, boundary.arc_s, boundary.length, target_s)


def _periodic_cells(ordered_sites: Array, length: float) -> tuple[Array, Array, Array]:
    sites = np.asarray(ordered_sites, dtype=float)
    previous = np.roll(sites, 1)
    previous[0] -= length
    following = np.roll(sites, -1)
    following[-1] += length
    left = 0.5 * (previous + sites)
    right = 0.5 * (sites + following)
    bounds = np.column_stack((left, right))
    mass = right - left
    centroids = 0.5 * (left + right)
    return bounds, mass, centroids


def _uniform_cost_from_cells(sites: Array, bounds: Array) -> float:
    left_delta = bounds[:, 0] - sites
    right_delta = bounds[:, 1] - sites
    return float(np.sum((right_delta**3 - left_delta**3) / 3.0))


def _active_site_count(sites: Array, length: float, tolerance: float) -> int:
    if len(sites) == 0:
        return 0
    ordered = np.sort(np.mod(sites, length))
    gaps = np.diff(np.r_[ordered, ordered[0] + length])
    return int(len(sites) - np.count_nonzero(gaps <= tolerance))


def equal_arc_target_s(length: float, m: int, phase: float = 0.0) -> Array:
    """Return ``m`` sorted, equally spaced coordinates on ``[0, length)``."""
    period = float(length)
    count = _validate_agent_count(m)
    if not np.isfinite(period) or period <= 0.0:
        raise ValueError("length must be finite and positive.")
    if not np.isfinite(phase):
        raise ValueError("phase must be finite.")
    return np.sort(np.mod(float(phase) + period * np.arange(count, dtype=float) / count, period))


def periodic_uniform_coverage_cost(target_s: Array, length: float) -> float:
    """Evaluate ``H = integral min_i d_L(s, s_i)^2 ds`` exactly for ``phi=1``."""
    period = float(length)
    sites = np.asarray(target_s, dtype=float)
    if not np.isfinite(period) or period <= 0.0:
        raise ValueError("length must be finite and positive.")
    if sites.ndim != 1 or len(sites) == 0 or not np.all(np.isfinite(sites)):
        raise ValueError("target_s must be a non-empty finite one-dimensional array.")
    ordered = np.sort(np.mod(sites, period))
    bounds, mass, _ = _periodic_cells(ordered, period)
    if np.any(mass <= 0.0):
        raise ValueError("periodic cells must have positive mass.")
    return _uniform_cost_from_cells(ordered, bounds)


def _invalid_plan(
    boundary: BoundaryEstimateV2,
    status: str,
    reason: str,
    target_s: Array | None = None,
    active_count: int = 0,
) -> CoveragePlan:
    sites = np.asarray(target_s if target_s is not None else np.empty(0), dtype=float)
    if _boundary_contract_valid(boundary) and len(sites):
        xy = _target_xy(boundary, sites)
        gap = max_consecutive_arc_gap(sites, boundary.length)
    else:
        xy = np.empty((len(sites), 2), dtype=float)
        gap = 0.0
    return CoveragePlan(
        target_s=sites.copy(),
        target_xy=xy,
        cell_bounds=np.zeros((len(sites), 2), dtype=float),
        cell_mass=np.zeros(len(sites), dtype=float),
        h_history=np.array([0.0], dtype=float),
        max_arc_gap=float(gap),
        active_count=int(active_count),
        converged=False,
        status=status,
        gain_history=np.empty((0, len(sites)), dtype=float),
        diagnostics={
            "reason": reason,
            "density_model": "uniform_phi_1",
            "confidence_role": "lloyd_gain_only",
        },
    )


def _cell_confidence_gain(
    boundary: BoundaryEstimateV2,
    bounds: Array,
    config: PeriodicArcCVTConfig,
) -> Array:
    fraction = (np.arange(config.confidence_quadrature_samples, dtype=float) + 0.5) / config.confidence_quadrature_samples
    samples = bounds[:, 0, None] + (bounds[:, 1] - bounds[:, 0])[:, None] * fraction[None, :]
    confidence = _interpolate_periodic(
        boundary.confidence,
        boundary.arc_s,
        boundary.length,
        samples.ravel(),
    ).reshape(samples.shape)
    return np.clip(np.mean(confidence, axis=1), config.eta_min, 1.0)


def plan_equal_arc_coverage(boundary: BoundaryEstimateV2, m: int, phase: float = 0.0) -> CoveragePlan:
    """Construct the deterministic equal-arc PR2 baseline without iteration."""
    count = _validate_agent_count(m)
    if not _boundary_contract_valid(boundary):
        return _invalid_plan(boundary, "PLAN_INVALID_BOUNDARY", "invalid_boundary_contract")
    sites = equal_arc_target_s(boundary.length, count, phase)
    bounds, mass, _ = _periodic_cells(sites, boundary.length)
    cost = _uniform_cost_from_cells(sites, bounds)
    return CoveragePlan(
        target_s=sites,
        target_xy=_target_xy(boundary, sites),
        cell_bounds=bounds,
        cell_mass=mass,
        h_history=np.array([cost], dtype=float),
        max_arc_gap=max_consecutive_arc_gap(sites, boundary.length),
        active_count=count,
        converged=True,
        status="VALID",
        gain_history=np.empty((0, count), dtype=float),
        diagnostics={
            "planner": "equal_arc_baseline",
            "density_model": "uniform_phi_1",
            "confidence_role": "not_used_by_baseline",
            "analytic_optimum": boundary.length**3 / (12.0 * count**2),
        },
    )


def plan_periodic_arc_coverage(
    boundary: BoundaryEstimateV2,
    m: int,
    config: PeriodicArcCVTConfig,
    init: Array | None = None,
) -> CoveragePlan:
    """Plan coverage on a valid periodic boundary with confidence-gated Lloyd steps."""
    count = _validate_agent_count(m)
    if not isinstance(config, PeriodicArcCVTConfig):
        raise TypeError("config must be PeriodicArcCVTConfig.")
    if not _boundary_contract_valid(boundary):
        return _invalid_plan(boundary, "PLAN_INVALID_BOUNDARY", "invalid_boundary_contract")

    if init is None:
        sites = equal_arc_target_s(boundary.length, count)
        initialization = "equal_arc_deterministic"
    else:
        raw_sites = np.asarray(init, dtype=float)
        if raw_sites.shape != (count,) or not np.all(np.isfinite(raw_sites)):
            return _invalid_plan(boundary, "PLAN_INVALID_INITIALIZATION", "init_must_be_finite_shape_m")
        sites = np.sort(np.mod(raw_sites, boundary.length))
        initialization = "provided"

    active_count = _active_site_count(sites, boundary.length, config.duplicate_tolerance)
    if active_count != count:
        return _invalid_plan(
            boundary,
            "PLAN_INVALID_EMPTY_CELL",
            "duplicate_periodic_sites",
            target_s=sites,
            active_count=active_count,
        )

    bounds, mass, centroids = _periodic_cells(sites, boundary.length)
    if np.any(mass <= config.duplicate_tolerance) or not np.all(np.isfinite(mass)):
        return _invalid_plan(
            boundary,
            "PLAN_INVALID_EMPTY_CELL",
            "nonpositive_periodic_cell_mass",
            target_s=sites,
            active_count=active_count,
        )

    cost_history = [_uniform_cost_from_cells(sites, bounds)]
    gain_history: list[Array] = []
    converged = False
    status = "PLAN_MAX_ITERATIONS"
    reason = "maximum_iterations_reached"

    for _ in range(config.max_iterations):
        gains = _cell_confidence_gain(boundary, bounds, config)
        gain_history.append(gains.copy())
        displacement = gains * (centroids - sites)
        proposed = np.sort(np.mod(sites + displacement, boundary.length))
        next_bounds, next_mass, next_centroids = _periodic_cells(proposed, boundary.length)
        if np.any(next_mass <= config.duplicate_tolerance) or not np.all(np.isfinite(next_mass)):
            return _invalid_plan(
                boundary,
                "PLAN_INVALID_EMPTY_CELL",
                "update_created_nonpositive_cell_mass",
                target_s=sites,
                active_count=_active_site_count(sites, boundary.length, config.duplicate_tolerance),
            )
        next_cost = _uniform_cost_from_cells(proposed, next_bounds)
        previous_cost = cost_history[-1]
        if next_cost - previous_cost > config.monotonic_tolerance:
            return CoveragePlan(
                target_s=sites,
                target_xy=_target_xy(boundary, sites),
                cell_bounds=bounds,
                cell_mass=mass,
                h_history=np.asarray(cost_history, dtype=float),
                max_arc_gap=max_consecutive_arc_gap(sites, boundary.length),
                active_count=count,
                converged=False,
                status="PLAN_INVALID_H_INCREASE",
                gain_history=np.asarray(gain_history, dtype=float),
                diagnostics={
                    "reason": "uniform_coverage_cost_increased",
                    "attempted_cost": next_cost,
                    "density_model": "uniform_phi_1",
                    "confidence_role": "lloyd_gain_only",
                },
            )

        sites, bounds, mass, centroids = proposed, next_bounds, next_mass, next_centroids
        cost_history.append(next_cost)
        cost_change = previous_cost - next_cost
        if np.max(np.abs(displacement)) <= config.target_tolerance or cost_change <= config.h_tolerance * max(1.0, abs(previous_cost)):
            converged = True
            status = "VALID"
            reason = "converged"
            break

    gains_array = np.asarray(gain_history, dtype=float).reshape((-1, count))
    return CoveragePlan(
        target_s=sites,
        target_xy=_target_xy(boundary, sites),
        cell_bounds=bounds,
        cell_mass=mass,
        h_history=np.asarray(cost_history, dtype=float),
        max_arc_gap=max_consecutive_arc_gap(sites, boundary.length),
        active_count=count,
        converged=converged,
        status=status,
        gain_history=gains_array,
        diagnostics={
            "reason": reason,
            "planner": "periodic_ca_alcc",
            "initialization": initialization,
            "iterations": len(gain_history),
            "density_model": "uniform_phi_1",
            "confidence_role": "lloyd_gain_only",
            "confidence_source": boundary.diagnostics.get("confidence_status", "unspecified"),
            "analytic_optimum": boundary.length**3 / (12.0 * count**2),
            "config": asdict(config),
        },
    )
