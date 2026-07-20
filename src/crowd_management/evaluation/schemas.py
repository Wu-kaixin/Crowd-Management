"""ABCG-v2.1 evaluation schemas with explicit layered success semantics.

The legacy controller terminal state ``CONVERGED`` describes target tracking
only.  This module deliberately keeps deployment and truth validation outside
the controller so callers cannot silently promote tracking to overall success.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping

import numpy as np


class LayerState(StrEnum):
    """Positive evidence layers required by the proof-strengthened evaluator."""

    PLAN_OPTIMAL = "PLAN_OPTIMAL"
    ROUTE_FEASIBLE = "ROUTE_FEASIBLE"
    TRACK_CONVERGED = "TRACK_CONVERGED"
    SAMPLED_SAFE = "SAMPLED_SAFE"
    ESTIMATED_DEPLOYMENT_SUCCESS = "ESTIMATED_DEPLOYMENT_SUCCESS"
    TRUTH_VALIDATED_SUCCESS = "TRUTH_VALIDATED_SUCCESS"


class ResourceRegime(StrEnum):
    """Comparison regimes that must never be pooled without a label."""

    SAME_RESOURCE = "same_resource"
    ADAPTIVE_RESOURCE = "adaptive_resource"


@dataclass(frozen=True)
class LayeredOutcome:
    """Layered episode evidence; derived success fields are not user-settable."""

    plan_optimal: bool
    route_feasible: bool
    track_converged: bool
    sampled_safe: bool
    truth_criteria_met: bool
    controller_terminal_state: str
    terminal_reason: str
    failure_reason: str | None = None
    diagnostics: Mapping[str, Any] = field(default_factory=dict)

    @property
    def estimated_deployment_success(self) -> bool:
        return bool(
            self.plan_optimal
            and self.route_feasible
            and self.track_converged
            and self.sampled_safe
        )

    @property
    def truth_validated_success(self) -> bool:
        return bool(self.estimated_deployment_success and self.truth_criteria_met)

    @property
    def passed_layers(self) -> tuple[str, ...]:
        layers: list[str] = []
        for state, passed in (
            (LayerState.PLAN_OPTIMAL, self.plan_optimal),
            (LayerState.ROUTE_FEASIBLE, self.route_feasible),
            (LayerState.TRACK_CONVERGED, self.track_converged),
            (LayerState.SAMPLED_SAFE, self.sampled_safe),
            (LayerState.ESTIMATED_DEPLOYMENT_SUCCESS, self.estimated_deployment_success),
            (LayerState.TRUTH_VALIDATED_SUCCESS, self.truth_validated_success),
        ):
            if passed:
                layers.append(str(state))
        return tuple(layers)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe record with explicit uppercase layer fields."""
        return {
            str(LayerState.PLAN_OPTIMAL): self.plan_optimal,
            str(LayerState.ROUTE_FEASIBLE): self.route_feasible,
            str(LayerState.TRACK_CONVERGED): self.track_converged,
            str(LayerState.SAMPLED_SAFE): self.sampled_safe,
            str(LayerState.ESTIMATED_DEPLOYMENT_SUCCESS): self.estimated_deployment_success,
            str(LayerState.TRUTH_VALIDATED_SUCCESS): self.truth_validated_success,
            "controller_terminal_state": self.controller_terminal_state,
            "terminal_reason": self.terminal_reason,
            "failure_reason": self.failure_reason,
            "passed_layers": list(self.passed_layers),
            "diagnostics": _jsonable(dict(self.diagnostics)),
        }


@dataclass(frozen=True)
class DeploymentMetrics:
    """Primary G7 endpoints; ``None`` keeps failed episodes in the denominator."""

    truth_coverage: float | None
    maximum_consecutive_arc_gap: float | None
    tracking_rmse: float | None
    minimum_intersample_clearance: float | None
    active_guide_count: int
    path_length: float | None
    control_energy: float | None
    runtime_ms: float | None
    peak_memory_bytes: int | None = None

    def __post_init__(self) -> None:
        if (
            isinstance(self.active_guide_count, bool)
            or not isinstance(self.active_guide_count, (int, np.integer))
            or self.active_guide_count < 0
        ):
            raise ValueError("active_guide_count must be a non-negative integer.")
        for name in (
            "truth_coverage",
            "maximum_consecutive_arc_gap",
            "tracking_rmse",
            "minimum_intersample_clearance",
            "path_length",
            "control_energy",
            "runtime_ms",
        ):
            value = getattr(self, name)
            if value is not None and not np.isfinite(float(value)):
                raise ValueError(f"{name} must be finite or None.")
        if self.peak_memory_bytes is not None and (
            isinstance(self.peak_memory_bytes, bool)
            or not isinstance(self.peak_memory_bytes, (int, np.integer))
            or self.peak_memory_bytes < 0
        ):
            raise ValueError("peak_memory_bytes must be a non-negative integer or None.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "truth_coverage": self.truth_coverage,
            "maximum_consecutive_arc_gap": self.maximum_consecutive_arc_gap,
            "tracking_rmse": self.tracking_rmse,
            "minimum_intersample_clearance": self.minimum_intersample_clearance,
            "active_guide_count": int(self.active_guide_count),
            "path_length": self.path_length,
            "control_energy": self.control_energy,
            "runtime_ms": self.runtime_ms,
            "peak_memory_bytes": (
                None if self.peak_memory_bytes is None else int(self.peak_memory_bytes)
            ),
        }


@dataclass(frozen=True)
class G7Record:
    """One paired G7 record with a mandatory resource-comparison regime."""

    scenario: str
    method: str
    seed: int
    resource_regime: ResourceRegime
    outcome: LayeredOutcome
    metrics: DeploymentMetrics
    config_hash: str
    base_sha: str
    branch_sha: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario": self.scenario,
            "method": self.method,
            "seed": int(self.seed),
            "resource_regime": str(self.resource_regime),
            "outcome": self.outcome.to_dict(),
            "metrics": self.metrics.to_dict(),
            "resource_normalized_metrics": resource_normalized_metrics(self.metrics),
            "config_hash": self.config_hash,
            "base_sha": self.base_sha,
            "branch_sha": self.branch_sha,
            "metadata": _jsonable(dict(self.metadata)),
        }


def compose_layered_outcome(
    *,
    plan_optimal: bool,
    route_feasible: bool,
    controller_terminal_state: str,
    sampled_safe: bool,
    truth_criteria_met: bool,
    terminal_reason: str,
    failure_reason: str | None = None,
    diagnostics: Mapping[str, Any] | None = None,
) -> LayeredOutcome:
    """Map controller convergence to tracking only and compose evaluator success."""
    track_converged = str(controller_terminal_state) == "CONVERGED"
    if failure_reason is None:
        if not plan_optimal:
            failure_reason = "PLAN_NOT_OPTIMAL"
        elif not route_feasible:
            failure_reason = "ROUTE_INFEASIBLE"
        elif not track_converged:
            failure_reason = str(controller_terminal_state)
        elif not sampled_safe:
            failure_reason = "SAMPLED_UNSAFE"
        elif not truth_criteria_met:
            failure_reason = "TRUTH_VALIDATION_FAILED"
    outcome = LayeredOutcome(
        plan_optimal=bool(plan_optimal),
        route_feasible=bool(route_feasible),
        track_converged=track_converged,
        sampled_safe=bool(sampled_safe),
        truth_criteria_met=bool(truth_criteria_met),
        controller_terminal_state=str(controller_terminal_state),
        terminal_reason=str(terminal_reason),
        failure_reason=failure_reason,
        diagnostics={} if diagnostics is None else dict(diagnostics),
    )
    if outcome.truth_validated_success and outcome.failure_reason is not None:
        raise ValueError("A truth-validated success cannot carry a failure_reason.")
    return outcome


def resource_normalized_metrics(metrics: DeploymentMetrics) -> dict[str, float | None]:
    """Return clearly named efficiency metrics without hiding guide count."""
    count = int(metrics.active_guide_count)
    if count <= 0:
        return {
            "truth_coverage_per_active_guide": None,
            "arc_gap_times_active_guide_count": None,
            "path_length_per_active_guide": None,
            "control_energy_per_active_guide": None,
            "runtime_ms_per_active_guide": None,
        }

    def per_guide(value: float | None) -> float | None:
        return None if value is None else float(value) / count

    return {
        "truth_coverage_per_active_guide": per_guide(metrics.truth_coverage),
        "arc_gap_times_active_guide_count": (
            None
            if metrics.maximum_consecutive_arc_gap is None
            else float(metrics.maximum_consecutive_arc_gap) * count
        ),
        "path_length_per_active_guide": per_guide(metrics.path_length),
        "control_energy_per_active_guide": per_guide(metrics.control_energy),
        "runtime_ms_per_active_guide": per_guide(metrics.runtime_ms),
    }


def _jsonable(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return _jsonable(value.tolist())
    if isinstance(value, np.generic):
        return _jsonable(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        return None
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value
