"""Controller-visible crowd observation for Step 1.

ROLE: INPUT CONTRACT — observed pedestrian points and attributes only.

Private simulator data (spawn polygon, region vertices, evaluator truth,
crowd shape labels, true centre/radius) must never appear here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..types import Array

FORBIDDEN_OBSERVATION_FIELDS = frozenset(
    {
        "spawn",
        "spawn_polygon",
        "spawn_vertices",
        "region_vertices",
        "support_polygon",
        "truth",
        "truth_boundary",
        "true_crowd_boundary",
        "true_safety_boundary",
        "crowd_shape",
        "shape_label",
        "crowd_center",
        "crowd_radius",
        "component_ids",
        "crowd_component_ids",
        "group_labels",
        "group_id",
        "evaluator_truth",
    }
)


def _finite_vector(values: Array | None, count: int, name: str) -> Array | None:
    if values is None:
        return None
    array = np.asarray(values, dtype=float)
    if array.shape != (count,) or not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must be a finite length-{count} vector.")
    return array.copy()


@dataclass(frozen=True)
class CrowdObservation:
    """Global Step 1 observation visible to ABCG.

    ``positions`` are pedestrian centres in metres, shape ``(N, 2)``.
    Optional attributes are copies of observed scalars. Desired speed and
    time gap are metadata/future interface: Step 1 pedestrians remain static.
    """

    positions: Array
    radii: Array | None = None
    demand: Array | None = None
    desired_speed: Array | None = None
    time_gap: Array | None = None
    diagnostics: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        points = np.asarray(self.positions, dtype=float)
        if points.ndim != 2 or points.shape[1:] != (2,) or not np.all(np.isfinite(points)):
            raise ValueError("positions must be a finite (N, 2) array.")
        object.__setattr__(self, "positions", points.copy())
        count = len(points)
        object.__setattr__(self, "radii", _finite_vector(self.radii, count, "radii"))
        object.__setattr__(self, "demand", _finite_vector(self.demand, count, "demand"))
        object.__setattr__(self, "desired_speed", _finite_vector(self.desired_speed, count, "desired_speed"))
        object.__setattr__(self, "time_gap", _finite_vector(self.time_gap, count, "time_gap"))
        leaked = FORBIDDEN_OBSERVATION_FIELDS.intersection(self.diagnostics)
        if leaked:
            raise ValueError(f"CrowdObservation diagnostics must not contain {sorted(leaked)}.")

    @property
    def observable_attributes(self) -> dict[str, Array]:
        attributes: dict[str, Array] = {}
        if self.radii is not None:
            attributes["radii"] = self.radii.copy()
        if self.demand is not None:
            attributes["demand"] = self.demand.copy()
        if self.desired_speed is not None:
            attributes["desired_speed"] = self.desired_speed.copy()
        if self.time_gap is not None:
            attributes["time_gap"] = self.time_gap.copy()
        return attributes

    def controller_points(self) -> Array:
        """Return the point cloud ABCG may use for estimation and safety."""
        return self.positions.copy()


def crowd_observation_from_points(
    positions: Array,
    attributes: dict[str, Array] | None = None,
) -> CrowdObservation:
    """Build a controller observation from points plus optional attributes."""
    raw = attributes or {}
    leaked = FORBIDDEN_OBSERVATION_FIELDS.intersection(raw)
    if leaked:
        raise ValueError(f"CrowdObservation must not include private fields {sorted(leaked)}.")
    return CrowdObservation(
        positions=positions,
        radii=raw.get("radius", raw.get("radii")),
        demand=raw.get("demand", raw.get("demand_weight")),
        desired_speed=raw.get("desired_speed"),
        time_gap=raw.get("time_gap"),
        diagnostics={"attribute_keys": tuple(sorted(raw))},
    )


def as_controller_observation(observation: Array | CrowdObservation) -> CrowdObservation:
    """Accept the controller input union and reject private geometry objects."""
    if isinstance(observation, CrowdObservation):
        return observation
    if isinstance(observation, dict):
        leaked = FORBIDDEN_OBSERVATION_FIELDS.intersection(observation)
        if leaked:
            raise TypeError(f"controller observation must not contain {sorted(leaked)}.")
        raise TypeError("controller observation must be CrowdObservation or an (N, 2) array.")
    return CrowdObservation(positions=np.asarray(observation, dtype=float))
