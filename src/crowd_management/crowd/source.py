"""Simulator-independent static crowd source interface."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..types import Array
from .jupedsim_static import (
    generate_jupedsim_static_crowd,
    generate_jupedsim_static_truth,
)
from .static_crowd import (
    StaticCrowdConfig,
    generate_static_crowd,
)
from .truth import (
    StaticCrowdTruth,
    generate_static_crowd_truth,
)


class StaticCrowdSource(
    Protocol
):
    """Minimal Step-1 crowd-source contract."""

    def observe(self) -> Array:
        """Return N x 2 observed crowd positions."""
        ...

    def truth(
        self,
        safety_distance: float,
    ) -> StaticCrowdTruth:
        """Return evaluator-only truth."""
        ...


@dataclass(frozen=True)
class SyntheticStaticCrowdSource:
    config: StaticCrowdConfig

    def observe(self) -> Array:
        return generate_static_crowd(
            self.config
        )

    def truth(
        self,
        safety_distance: float,
    ) -> StaticCrowdTruth:
        return generate_static_crowd_truth(
            self.config,
            safety_distance=safety_distance,
        )


@dataclass(frozen=True)
class JuPedSimStaticCrowdSource:
    config: StaticCrowdConfig

    def observe(self) -> Array:
        return (
            generate_jupedsim_static_crowd(
                self.config
            )
        )

    def truth(
        self,
        safety_distance: float,
    ) -> StaticCrowdTruth:
        return (
            generate_jupedsim_static_truth(
                self.config,
                safety_distance=(
                    safety_distance
                ),
            )
        )


def build_crowd_source(
    config: StaticCrowdConfig,
) -> StaticCrowdSource:
    """Construct the configured Step-1 crowd source."""

    source = (
        config.source
        .strip()
        .lower()
        .replace("-", "_")
    )

    if source == "synthetic":
        return (
            SyntheticStaticCrowdSource(
                config
            )
        )

    if source == "jupedsim":
        return (
            JuPedSimStaticCrowdSource(
                config
            )
        )

    raise ValueError(
        f"Unsupported crowd source: "
        f"{config.source}"
    )