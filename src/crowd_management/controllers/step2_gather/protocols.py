"""Step 2: gather dispersed pedestrians, then surround.

Step 1 keeps pedestrians static (``dx^c/dt = 0``). Step 2 implements
gather-then-surround on dispersed scenes. The ``NotImplemented*`` stub remains
for callers that must not silently claim dynamics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from ...types import Array


@dataclass(frozen=True)
class GatherTarget:
    """Rendezvous / assembly region for a crowd group."""

    group_id: int
    center: Array
    radius: float
    status: str = "ACTIVE"


@dataclass(frozen=True)
class GatherThenSurroundPlan:
    """Two-phase plan: gather phase then containment phase."""

    phase: str  # "gather" | "surround" | "done"
    gather_targets: tuple[GatherTarget, ...] = ()
    surround_targets: Array | None = None
    active_guide_targets: Array | None = None
    gather_disk_polyline: Array | None = None
    diagnostics: dict[str, object] = field(default_factory=dict)
    status: str = "INIT"


class CrowdMotionModel(Protocol):
    """Pedestrian response to nearby guides (Step 2 dynamics)."""

    def step(
        self,
        crowd_positions: Array,
        guide_positions: Array,
        dt: float,
    ) -> Array:
        """Return next crowd positions, shape ``(N, 2)``."""


class GatherThenSurroundController(Protocol):
    """Step 2 pipeline on top of dispersed Step 1 scenes."""

    def reset(self, crowd_positions: Array, guide_positions: Array) -> GatherThenSurroundPlan:
        """Initialize gather targets from a dispersed observation."""

    def step(
        self,
        crowd_positions: Array,
        guide_positions: Array,
        dt: float,
    ) -> tuple[Array, GatherThenSurroundPlan]:
        """Return guide velocities ``(M, 2)`` and the updated phase plan."""


class NotImplementedGatherThenSurroundController:
    """Explicit stub so Step 1 cannot silently claim gather dynamics."""

    def reset(self, crowd_positions: Array, guide_positions: Array) -> GatherThenSurroundPlan:
        del crowd_positions, guide_positions
        raise NotImplementedError(
            "Use CentralGatherThenSurroundController for Step 2 gather-then-surround; "
            "Step 1 only surrounds a static envelope."
        )

    def step(
        self,
        crowd_positions: Array,
        guide_positions: Array,
        dt: float,
    ) -> tuple[Array, GatherThenSurroundPlan]:
        del crowd_positions, guide_positions, dt
        raise NotImplementedError(
            "Use CentralGatherThenSurroundController for Step 2 gather-then-surround; "
            "Step 1 only surrounds a static envelope."
        )
