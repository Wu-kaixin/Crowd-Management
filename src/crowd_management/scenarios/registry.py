r"""Extensible known-environment scenario registry.

CURRENT: closed ``square`` and ``rectangle`` factories.
FUTURE: register additional venue types (L-shape, arenas, openings) without
changing the Step 1 runner contract.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import numpy as np

from .base import Scenario
from .rectangular import BoundaryOpening, RectangularScenario

ScenarioFactory = Callable[..., Scenario]

_REGISTRY: dict[str, ScenarioFactory] = {}


def register_scenario(name: str, factory: ScenarioFactory, *, replace: bool = False) -> None:
    """Register a scenario factory under a lowercase type name."""
    key = str(name).strip().lower()
    if not key:
        raise ValueError("scenario name must be non-empty.")
    if key in _REGISTRY and not replace:
        raise ValueError(f"scenario type {key!r} is already registered.")
    _REGISTRY[key] = factory


def registered_scenario_types() -> tuple[str, ...]:
    return tuple(sorted(_REGISTRY))


def build_scenario(raw: Mapping[str, Any] | None = None, *, room_size: object | None = None) -> Scenario:
    """Build a Step 1 scenario from YAML ``scene`` (or legacy ``room.size``)."""
    data = dict(raw or {})
    if room_size is not None and not data:
        size = np.asarray(room_size, dtype=float)
        if size.shape != (2,):
            raise ValueError("room_size must contain two dimensions.")
        scene_type = "square" if np.isclose(size[0], size[1]) else "rectangle"
        return _REGISTRY[scene_type](width=float(size[0]), height=float(size[1]))

    width = float(data.get("width", 20.0))
    height = float(data.get("height", 14.0))
    scene_type = str(data.get("type", "square" if np.isclose(width, height) else "rectangle")).strip().lower()
    closed = bool(data.get("closed", True))
    openings_raw = data.get("openings") or []
    if not closed:
        raise ValueError("Step 1 requires a closed environment (scene.closed: true).")
    if openings_raw:
        raise ValueError("Step 1 does not implement environment openings (reserved for Step 2).")
    if scene_type not in _REGISTRY:
        known = ", ".join(registered_scenario_types()) or "(none)"
        raise ValueError(f"Unknown scene.type {scene_type!r}. Registered Step 1 types: {known}.")
    return _REGISTRY[scene_type](
        width=width,
        height=height,
        openings=tuple(
            BoundaryOpening(wall=str(item["wall"]), start=float(item["start"]), end=float(item["end"]))
            for item in openings_raw
        ),
    )


def _rectangular_factory(*, name: str) -> ScenarioFactory:
    def factory(
        *,
        width: float,
        height: float,
        openings: tuple[BoundaryOpening, ...] = (),
        origin: tuple[float, float] = (0.0, 0.0),
    ) -> RectangularScenario:
        return RectangularScenario(name=name, width=width, height=height, openings=openings, origin=origin)

    return factory


register_scenario("square", _rectangular_factory(name="square"))
register_scenario("rectangle", _rectangular_factory(name="rectangle"))
