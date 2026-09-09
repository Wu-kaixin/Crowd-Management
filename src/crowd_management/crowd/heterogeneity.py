"""Moderate pedestrian heterogeneity for Step 1.

Step 1 remains STATIC:
    dx_i^c / dt = 0

The heterogeneous parameters are therefore population attributes only.
They are not yet used to evolve pedestrian dynamics or model guide-crowd
interaction.

The selected attributes map naturally to JuPedSim pedestrian models and
are reserved for Step 2:
    - radius
    - desired_speed
    - time_gap
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from ..types import Array


@dataclass(frozen=True)
class StaticHeterogeneityConfig:
    enabled: bool = False

    radius_mean: float = 0.20
    radius_std: float = 0.015
    radius_min: float = 0.17
    radius_max: float = 0.23

    desired_speed_mean: float = 1.25
    desired_speed_std: float = 0.10
    desired_speed_min: float = 0.95
    desired_speed_max: float = 1.55

    time_gap_mean: float = 1.00
    time_gap_std: float = 0.08
    time_gap_min: float = 0.80
    time_gap_max: float = 1.20

    @classmethod
    def from_dict(
        cls,
        raw: dict[str, Any] | None,
    ) -> "StaticHeterogeneityConfig":
        raw = raw or {}

        cfg = cls(
            enabled=bool(raw.get("enabled", False)),
            radius_mean=float(raw.get("radius_mean", 0.20)),
            radius_std=float(raw.get("radius_std", 0.015)),
            radius_min=float(raw.get("radius_min", 0.17)),
            radius_max=float(raw.get("radius_max", 0.23)),
            desired_speed_mean=float(
                raw.get("desired_speed_mean", 1.25)
            ),
            desired_speed_std=float(
                raw.get("desired_speed_std", 0.10)
            ),
            desired_speed_min=float(
                raw.get("desired_speed_min", 0.95)
            ),
            desired_speed_max=float(
                raw.get("desired_speed_max", 1.55)
            ),
            time_gap_mean=float(raw.get("time_gap_mean", 1.00)),
            time_gap_std=float(raw.get("time_gap_std", 0.08)),
            time_gap_min=float(raw.get("time_gap_min", 0.80)),
            time_gap_max=float(raw.get("time_gap_max", 1.20)),
        )

        cfg.validate()
        return cfg

    def validate(self) -> None:
        _validate_range(
            "radius",
            self.radius_mean,
            self.radius_std,
            self.radius_min,
            self.radius_max,
        )

        _validate_range(
            "desired_speed",
            self.desired_speed_mean,
            self.desired_speed_std,
            self.desired_speed_min,
            self.desired_speed_max,
        )

        _validate_range(
            "time_gap",
            self.time_gap_mean,
            self.time_gap_std,
            self.time_gap_min,
            self.time_gap_max,
        )


def _validate_range(
    name: str,
    mean: float,
    std: float,
    lower: float,
    upper: float,
) -> None:
    if std < 0.0:
        raise ValueError(f"{name}_std must be non-negative.")

    if lower <= 0.0:
        raise ValueError(f"{name}_min must be positive.")

    if upper <= lower:
        raise ValueError(
            f"{name}_max must be greater than {name}_min."
        )

    if not lower <= mean <= upper:
        raise ValueError(
            f"{name}_mean must lie inside [{lower}, {upper}]."
        )


def _bounded_normal(
    rng: np.random.Generator,
    count: int,
    mean: float,
    std: float,
    lower: float,
    upper: float,
) -> Array:
    if std == 0.0:
        return np.full(count, mean, dtype=float)

    values = rng.normal(
        loc=mean,
        scale=std,
        size=count,
    )

    return np.clip(
        values,
        lower,
        upper,
    ).astype(float)


def generate_static_agent_attributes(
    count: int,
    config: StaticHeterogeneityConfig,
    seed: int,
) -> dict[str, Array]:
    """Generate reproducible Step-1 pedestrian attributes."""

    if count <= 0:
        raise ValueError("count must be positive.")

    rng = np.random.default_rng(seed)

    if config.enabled:
        radius = _bounded_normal(
            rng,
            count,
            config.radius_mean,
            config.radius_std,
            config.radius_min,
            config.radius_max,
        )

        desired_speed = _bounded_normal(
            rng,
            count,
            config.desired_speed_mean,
            config.desired_speed_std,
            config.desired_speed_min,
            config.desired_speed_max,
        )

        time_gap = _bounded_normal(
            rng,
            count,
            config.time_gap_mean,
            config.time_gap_std,
            config.time_gap_min,
            config.time_gap_max,
        )
    else:
        radius = np.full(
            count,
            config.radius_mean,
            dtype=float,
        )

        desired_speed = np.full(
            count,
            config.desired_speed_mean,
            dtype=float,
        )

        time_gap = np.full(
            count,
            config.time_gap_mean,
            dtype=float,
        )

    return {
        "agent_id": np.arange(count, dtype=int),
        "radius": radius,
        "desired_speed": desired_speed,
        "time_gap": time_gap,
        "heterogeneity_enabled": np.full(
            count,
            config.enabled,
            dtype=bool,
        ),
    }