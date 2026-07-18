"""PR3 adaptive guide-resource policy with explicit hysteresis and capacity state."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np


@dataclass(frozen=True)
class ResourcePolicyConfig:
    """Configuration for ``m_req = ceil(L / g_req)`` resource selection."""

    g_req: float = 2.5
    m_min: int = 3
    increase_hysteresis: float = 0.1
    decrease_hysteresis: float = 0.1

    def __post_init__(self) -> None:
        if not np.isfinite(self.g_req) or self.g_req <= 0.0:
            raise ValueError("g_req must be finite and positive.")
        if isinstance(self.m_min, bool) or not isinstance(self.m_min, (int, np.integer)) or self.m_min < 1:
            raise ValueError("m_min must be a positive integer.")
        for name in ("increase_hysteresis", "decrease_hysteresis"):
            value = float(getattr(self, name))
            if not np.isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be finite and non-negative.")


@dataclass(frozen=True)
class ResourceDecision:
    """Auditable PR3 resource decision before guide-target assignment."""

    requested_count: int
    desired_count: int
    active_count: int
    reserve_count: int
    unmet_target_count: int
    previous_active_count: int | None
    hysteresis_applied: bool
    status: str
    diagnostics: dict[str, object] = field(default_factory=dict)


class ResourcePolicy:
    """State-free policy; callers pass the prior active count explicitly."""

    def __init__(self, config: ResourcePolicyConfig | None = None) -> None:
        self.config = config or ResourcePolicyConfig()
        if not isinstance(self.config, ResourcePolicyConfig):
            raise TypeError("config must be ResourcePolicyConfig.")

    def decide(
        self,
        boundary_length: float,
        available_count: int,
        previous_active_count: int | None = None,
    ) -> ResourceDecision:
        length = float(boundary_length)
        if not np.isfinite(length) or length <= 0.0:
            raise ValueError("boundary_length must be finite and positive.")
        available = _nonnegative_integer(available_count, "available_count")
        previous = (
            None
            if previous_active_count is None
            else _nonnegative_integer(previous_active_count, "previous_active_count")
        )

        requested = int(np.ceil(length / self.config.g_req))
        baseline_desired = max(requested, int(self.config.m_min))
        desired = baseline_desired
        if previous is not None:
            desired = max(previous, int(self.config.m_min))
            if baseline_desired > desired:
                while (
                    desired < baseline_desired
                    and length > desired * self.config.g_req + self.config.increase_hysteresis
                ):
                    desired += 1
            elif baseline_desired < desired:
                while (
                    desired > baseline_desired
                    and length < (desired - 1) * self.config.g_req - self.config.decrease_hysteresis
                ):
                    desired -= 1

        active = min(desired, available)
        reserve = max(available - active, 0)
        unmet = max(desired - available, 0)
        status = "CAPACITY_SHORTFALL" if unmet else "VALID"
        reason = "insufficient_available_guides" if unmet else "resource_requirement_satisfied"
        return ResourceDecision(
            requested_count=requested,
            desired_count=desired,
            active_count=active,
            reserve_count=reserve,
            unmet_target_count=unmet,
            previous_active_count=previous,
            hysteresis_applied=desired != baseline_desired,
            status=status,
            diagnostics={
                "reason": reason,
                "formula": "ceil_length_over_g_req_then_hysteresis_and_clip",
                "baseline_desired_count": baseline_desired,
                "config": asdict(self.config),
            },
        )


def allocate_guide_resources(
    boundary_length: float,
    available_count: int,
    config: ResourcePolicyConfig,
    previous_active_count: int | None = None,
) -> ResourceDecision:
    """Functional API for deterministic PR3 resource selection."""
    return ResourcePolicy(config).decide(boundary_length, available_count, previous_active_count)


def _nonnegative_integer(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer.")
    return int(value)
