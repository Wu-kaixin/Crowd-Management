r"""DESIGNED Step 3 decentralized interfaces.

These protocols reserve the public surface for limited-communication,
local-perception containment. Step 1 remains centralized ABCG-v2 and must
not call the stub implementations below.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from ...types import Array


@dataclass(frozen=True)
class LocalObservation:
    """What one guide can sense within its local range (DESIGNED)."""

    guide_id: int
    ego_position: Array
    neighbor_guide_ids: tuple[int, ...]
    neighbor_guide_positions: Array
    local_crowd_positions: Array
    local_crowd_attributes: dict[str, Array] = field(default_factory=dict)
    wall_clearance: float | None = None


@dataclass(frozen=True)
class LocalMessage:
    """Peer-to-peer payload under limited communication (DESIGNED)."""

    sender_id: int
    receiver_id: int
    topic: str
    payload: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class CrowdGroupHypothesis:
    """Local estimate of a crowd group identity (DESIGNED Step 2/3)."""

    group_id: int
    member_indices: tuple[int, ...]
    centroid: Array | None = None
    status: str = "DESIGNED_NOT_IMPLEMENTED"


@dataclass(frozen=True)
class DecentralizedAssignment:
    """Local guide-to-group / guide-to-role decision (DESIGNED)."""

    guide_id: int
    group_id: int | None
    role: str
    status: str = "DESIGNED_NOT_IMPLEMENTED"


class LocalPerception(Protocol):
    """DESIGNED: local sensing of crowd points and nearby guides."""

    sensing_radius: float

    def observe(self, guide_id: int, ego_position: Array) -> LocalObservation:
        """Return only entities inside the sensing radius."""


class LocalCommunication(Protocol):
    """DESIGNED: limited-range or bandwidth-constrained messaging."""

    comm_radius: float
    max_messages_per_step: int

    def send(self, message: LocalMessage) -> None:
        """Enqueue an outbound peer message."""

    def receive(self, guide_id: int) -> tuple[LocalMessage, ...]:
        """Drain inbox for one guide."""


class CrowdGroupIdentifier(Protocol):
    """DESIGNED: cluster / split / merge recognition from local evidence."""

    def identify(self, observation: LocalObservation, inbox: tuple[LocalMessage, ...]) -> tuple[CrowdGroupHypothesis, ...]:
        """Propose crowd groups visible to this guide."""


class DecentralizedAssigner(Protocol):
    """DESIGNED: local role / target allocation without a global planner."""

    def assign(
        self,
        guide_id: int,
        observation: LocalObservation,
        groups: tuple[CrowdGroupHypothesis, ...],
        inbox: tuple[LocalMessage, ...],
    ) -> DecentralizedAssignment:
        """Return this guide's local assignment decision."""


class DecentralizedContainmentController(Protocol):
    """DESIGNED Step 3 pipeline: search → identify → assign → contain."""

    def reset(self, guide_ids: tuple[int, ...]) -> None:
        """Initialize per-guide local state."""

    def step(
        self,
        guide_id: int,
        observation: LocalObservation,
        inbox: tuple[LocalMessage, ...],
        dt: float,
    ) -> Array:
        """Return a local velocity command for one guide, shape ``(2,)``."""


class NotImplementedDecentralizedController:
    """Explicit stub so Step 1 cannot silently pretend decentralization exists."""

    def reset(self, guide_ids: tuple[int, ...]) -> None:
        del guide_ids
        raise NotImplementedError(
            "Decentralized containment is DESIGNED for Step 3; Step 1 uses centralized ABCG-v2."
        )

    def step(
        self,
        guide_id: int,
        observation: LocalObservation,
        inbox: tuple[LocalMessage, ...],
        dt: float,
    ) -> Array:
        del guide_id, observation, inbox, dt
        raise NotImplementedError(
            "Decentralized containment is DESIGNED for Step 3; Step 1 uses centralized ABCG-v2."
        )
