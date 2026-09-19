r"""Step 1 known-environment scenario contract.

ROLE: CORE GEOMETRY — known venue \(\Omega_{\mathrm{env}}\), not crowd geometry.

CURRENT implementations: closed square / rectangle via ``RectangularScenario``.
Register additional venue types with ``scenarios.register_scenario`` (Step 2+).
"""

from __future__ import annotations

from typing import Protocol

from ..types import Array


class Scenario(Protocol):
    """Closed known environment used for wall safety and workspace feasibility."""

    name: str
    width: float
    height: float
    openings: tuple[object, ...]

    @property
    def closed(self) -> bool:
        """Step 1 requires a closed venue; openings are reserved for Step 2."""

    def boundary_vertices(self) -> Array:
        """Return the closed environment polygon vertices, shape ``(N, 2)``."""

    def contains(self, points: Array, margin: float = 0.0) -> Array:
        """Return a boolean mask: points inside the inset workspace."""

    def wall_clearance(self, points: Array) -> Array:
        """Return per-point distance to the nearest environment wall."""

    def feasible_workspace_bounds(self, margin: float) -> tuple[Array, Array]:
        """Return ``(lower, upper)`` inclusive AABB of the inset workspace."""
