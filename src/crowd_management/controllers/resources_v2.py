"""Robust-envelope guide resource decisions for ABCG-v2.1.

The robust count is deliberately scoped to the perimeter of an explicitly
constructed calibrated envelope.  A positional uncertainty tube alone does
not bound the perimeter of every possible high-frequency truth curve, and this
module never claims that stronger result.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np


@dataclass(frozen=True)
class RobustResourceConfig:
    required_arc_gap: float = 2.2
    m_min: int = 4
    increase_hysteresis: float = 0.1
    decrease_hysteresis: float = 0.1
    count_tolerance: float = 1.0e-12

    def __post_init__(self) -> None:
        if not np.isfinite(self.required_arc_gap) or self.required_arc_gap <= 0.0:
            raise ValueError("required_arc_gap must be finite and positive.")
        if isinstance(self.m_min, bool) or not isinstance(self.m_min, (int, np.integer)) or self.m_min < 1:
            raise ValueError("m_min must be a positive integer.")
        for name in ("increase_hysteresis", "decrease_hysteresis", "count_tolerance"):
            value = float(getattr(self, name))
            if not np.isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be finite and non-negative.")


@dataclass(frozen=True)
class RobustResourceDecision:
    nominal_count: int
    robust_count: int | None
    required_count: int
    desired_count: int
    active_count: int
    reserve_count: int
    unmet_target_count: int
    previous_active_count: int | None
    hysteresis_applied: bool
    nominal_gap: float
    selected_envelope_gap: float | None
    uncertainty_mode: str
    status: str
    conditions: tuple[str, ...]
    diagnostics: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "nominal_count": self.nominal_count,
            "robust_count": self.robust_count,
            "required_count": self.required_count,
            "desired_count": self.desired_count,
            "active_count": self.active_count,
            "reserve_count": self.reserve_count,
            "unmet_target_count": self.unmet_target_count,
            "previous_active_count": self.previous_active_count,
            "hysteresis_applied": self.hysteresis_applied,
            "nominal_gap": self.nominal_gap,
            "selected_envelope_gap": self.selected_envelope_gap,
            "uncertainty_mode": self.uncertainty_mode,
            "status": self.status,
            "conditions": list(self.conditions),
            "diagnostics": dict(self.diagnostics),
        }


def allocate_robust_resources(
    nominal_length: float,
    available_count: int,
    config: RobustResourceConfig,
    *,
    uncertainty_mode: str = "none",
    uncertainty_status: str | None = None,
    robust_envelope_length: float | None = None,
    previous_active_count: int | None = None,
) -> RobustResourceDecision:
    """Return nominal and, when calibrated, robust-envelope resource counts.

    Modes are ``none`` (nominal ablation), ``stability`` (uncalibrated evidence)
    and ``calibrated_tube``.  Only the last mode with status
    ``CALIBRATED_TUBE`` and a valid envelope length can produce a robust count.
    """

    if not isinstance(config, RobustResourceConfig):
        raise TypeError("config must be RobustResourceConfig.")
    length = _positive_finite(nominal_length, "nominal_length")
    available = _nonnegative_integer(available_count, "available_count")
    previous = (
        None
        if previous_active_count is None
        else _nonnegative_integer(previous_active_count, "previous_active_count")
    )
    mode = str(uncertainty_mode).lower()
    if mode not in {"none", "stability", "calibrated_tube"}:
        raise ValueError("uncertainty_mode must be none, stability, or calibrated_tube.")

    nominal_count = max(config.m_min, _ceil_ratio(length, config.required_arc_gap, config.count_tolerance))
    robust_count: int | None = None
    resource_uncertain = False
    envelope_length: float | None = None
    uncertainty_reason = "nominal_ablation_selected"
    if mode == "stability":
        resource_uncertain = True
        uncertainty_reason = "stability_score_is_not_a_calibrated_tube"
    elif mode == "calibrated_tube":
        if uncertainty_status != "CALIBRATED_TUBE":
            resource_uncertain = True
            uncertainty_reason = "independent_tube_calibration_not_passed"
        elif robust_envelope_length is None:
            resource_uncertain = True
            uncertainty_reason = "robust_envelope_length_missing"
        else:
            candidate = float(robust_envelope_length)
            if not np.isfinite(candidate) or candidate <= 0.0 or candidate + config.count_tolerance < length:
                resource_uncertain = True
                uncertainty_reason = "robust_envelope_length_invalid"
            else:
                envelope_length = candidate
                robust_count = max(
                    nominal_count,
                    config.m_min,
                    _ceil_ratio(candidate, config.required_arc_gap, config.count_tolerance),
                )
                uncertainty_reason = "calibrated_explicit_envelope_selected"

    basis_count = robust_count if robust_count is not None else nominal_count
    basis_length = envelope_length if envelope_length is not None else length
    desired = basis_count
    if previous is not None:
        desired = max(previous, config.m_min)
        if basis_count > desired:
            while (
                desired < basis_count
                and basis_length > desired * config.required_arc_gap + config.increase_hysteresis
            ):
                desired += 1
        elif basis_count < desired:
            while (
                desired > basis_count
                and basis_length
                < (desired - 1) * config.required_arc_gap - config.decrease_hysteresis
            ):
                desired -= 1

    required_count = basis_count
    active = min(desired, available)
    reserve = max(available - active, 0)
    required_unmet = max(required_count - available, 0)
    policy_unmet = max(desired - available, 0)
    hysteresis_applied = desired != basis_count
    selected_gap = None if active == 0 else float(basis_length / active)
    gap_degraded = bool(
        hysteresis_applied
        and active == desired
        and selected_gap is not None
        and selected_gap > config.required_arc_gap + config.count_tolerance
    )

    conditions: list[str] = []
    if required_unmet:
        conditions.append("CAPACITY_SHORTFALL")
    if resource_uncertain:
        conditions.append("RESOURCE_UNCERTAIN")
    if gap_degraded:
        conditions.append("HYSTERESIS_GAP_DEGRADED")
    if not conditions:
        conditions.append("VALID")
    for candidate in (
        "CAPACITY_SHORTFALL",
        "RESOURCE_UNCERTAIN",
        "HYSTERESIS_GAP_DEGRADED",
        "VALID",
    ):
        if candidate in conditions:
            status = candidate
            break

    return RobustResourceDecision(
        nominal_count=nominal_count,
        robust_count=robust_count,
        required_count=required_count,
        desired_count=desired,
        active_count=active,
        reserve_count=reserve,
        unmet_target_count=required_unmet,
        previous_active_count=previous,
        hysteresis_applied=hysteresis_applied,
        nominal_gap=float(length / nominal_count),
        selected_envelope_gap=selected_gap,
        uncertainty_mode=mode,
        status=status,
        conditions=tuple(conditions),
        diagnostics={
            "reason": (
                "insufficient_available_guides_for_required_count"
                if required_unmet
                else uncertainty_reason
                if resource_uncertain
                else "hysteresis_retained_gap_above_requirement"
                if gap_degraded
                else "resource_requirement_satisfied"
            ),
            "uncertainty_reason": uncertainty_reason,
            "nominal_length": length,
            "robust_envelope_length": envelope_length,
            "selected_basis": "robust_envelope" if envelope_length is not None else "nominal_boundary",
            "policy_desired_count": desired,
            "policy_unmet_count": policy_unmet,
            "required_unmet_count": required_unmet,
            "formula": "max(m_min, ceil_tolerant(L/g_req))",
            "status_precedence": [
                "CAPACITY_SHORTFALL",
                "RESOURCE_UNCERTAIN",
                "HYSTERESIS_GAP_DEGRADED",
                "VALID",
            ],
            "scope_limitation": (
                "Robust count controls equal-arc gap on the explicit calibrated envelope only; "
                "a positional tube alone does not bound arbitrary high-frequency truth perimeter."
            ),
            "config": asdict(config),
        },
    )


def _ceil_ratio(numerator: float, denominator: float, tolerance: float) -> int:
    ratio = float(numerator / denominator)
    adjusted = ratio - float(tolerance) * max(1.0, abs(ratio))
    return max(1, int(np.ceil(adjusted)))


def _positive_finite(value: float, name: str) -> float:
    result = float(value)
    if not np.isfinite(result) or result <= 0.0:
        raise ValueError(f"{name} must be finite and positive.")
    return result


def _nonnegative_integer(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer.")
    return int(value)


__all__ = [
    "RobustResourceConfig",
    "RobustResourceDecision",
    "allocate_robust_resources",
]
