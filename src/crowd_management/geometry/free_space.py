"""Canonical guide free space derived from the shared ABCG-v2.1 buffer.

The source :class:`~crowd_management.geometry.buffer.BufferedPolygonGeometry`
is authoritative: routing never rebuilds an obstacle from observations or a
second offset.  Disconnected free-space components are retained so reachability
can be decided per guide/target pair.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json

import numpy as np
from shapely import to_wkb
from shapely.geometry import MultiPolygon, Polygon, box

from .buffer import BufferedPolygonGeometry, PolygonBufferFailure, PolygonBufferResult


FreeSpaceDiagnostics = dict[str, object]


@dataclass(frozen=True)
class FreeSpaceConfig:
    """Room and numerical contract for point-guide configuration space."""

    room_size: tuple[float, float]
    room_margin: float = 0.0
    topology_tolerance: float = 1.0e-9
    clearance_tolerance: float = 1.0e-7

    def __post_init__(self) -> None:
        room = np.asarray(self.room_size, dtype=float)
        if room.shape != (2,) or not np.all(np.isfinite(room)) or np.any(room <= 0.0):
            raise ValueError("room_size must contain two finite positive dimensions.")
        if not np.isfinite(self.room_margin) or self.room_margin < 0.0:
            raise ValueError("room_margin must be finite and non-negative.")
        if np.any(room <= 2.0 * self.room_margin):
            raise ValueError("room_size must exceed twice room_margin on each axis.")
        for name in ("topology_tolerance", "clearance_tolerance"):
            value = float(getattr(self, name))
            if not np.isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be finite and non-negative.")


@dataclass(frozen=True)
class GuideFreeSpace:
    """One canonical room-minus-buffer domain with every component retained."""

    physical_room: Polygon
    feasible_room: Polygon
    source_polygon: Polygon
    forbidden_polygon: Polygon
    free_space: Polygon | MultiPolygon
    components: tuple[Polygon, ...]
    nominal_crowd_clearance: float
    certified_crowd_clearance: float
    room_margin: float
    geometry_sha256: str
    source_buffer_sha256: str
    status: str = "VALID"
    diagnostics: FreeSpaceDiagnostics = field(default_factory=dict)


@dataclass(frozen=True)
class FreeSpaceFailure:
    """Explicit free-space construction failure with no partial geometry."""

    status: str
    diagnostics: FreeSpaceDiagnostics = field(default_factory=dict)


FreeSpaceResult = GuideFreeSpace | FreeSpaceFailure


def _failure(status: str, reason: str, **diagnostics: object) -> FreeSpaceFailure:
    return FreeSpaceFailure(status=status, diagnostics={"reason": reason, **diagnostics})


def _polygon_components(geometry: object) -> tuple[Polygon, ...] | None:
    if isinstance(geometry, Polygon):
        candidates = (geometry,)
    elif isinstance(geometry, MultiPolygon):
        candidates = tuple(geometry.geoms)
    else:
        return None
    valid = tuple(
        polygon
        for polygon in candidates
        if not polygon.is_empty and polygon.is_valid and polygon.area > 0.0
    )
    if len(valid) != len(candidates):
        return None
    return tuple(
        sorted(
            valid,
            key=lambda polygon: (
                tuple(float(value) for value in polygon.bounds),
                float(polygon.area),
                bytes(to_wkb(polygon, byte_order=1, include_srid=False, output_dimension=2)),
            ),
        )
    )


def build_guide_free_space(
    buffered_geometry: PolygonBufferResult,
    config: FreeSpaceConfig,
) -> FreeSpaceResult:
    """Subtract the exact shared forbidden buffer from the inward room.

    A ``MultiPolygon`` result is valid and retained.  It represents disconnected
    guide configuration-space components, not a geometry error.
    """

    if not isinstance(config, FreeSpaceConfig):
        raise TypeError("config must be FreeSpaceConfig.")
    if isinstance(buffered_geometry, PolygonBufferFailure):
        return _failure(
            buffered_geometry.status,
            "source_buffer_is_invalid",
            source_buffer_diagnostics=dict(buffered_geometry.diagnostics),
        )
    if not isinstance(buffered_geometry, BufferedPolygonGeometry):
        raise TypeError("buffered_geometry must be a polygon buffer result.")

    width, height = (float(value) for value in config.room_size)
    margin = float(config.room_margin)
    physical_room = box(0.0, 0.0, width, height)
    feasible_room = box(margin, margin, width - margin, height - margin)
    forbidden = buffered_geometry.forbidden_polygon
    tolerance = float(config.topology_tolerance)
    if not feasible_room.buffer(tolerance).covers(forbidden):
        return _failure(
            "ROOM_INFEASIBLE",
            "canonical_forbidden_polygon_is_not_covered_by_inward_room",
            forbidden_bounds=tuple(float(value) for value in forbidden.bounds),
            room_size=(width, height),
            room_margin=margin,
            source_buffer_sha256=buffered_geometry.sha256,
        )

    free = feasible_room.difference(forbidden)
    if free.is_empty:
        return _failure(
            "ROOM_INFEASIBLE",
            "room_minus_forbidden_is_empty",
            room_size=(width, height),
            room_margin=margin,
            source_buffer_sha256=buffered_geometry.sha256,
        )
    components = _polygon_components(free)
    if not components:
        return _failure(
            "FREE_SPACE_INVALID",
            "room_minus_forbidden_is_not_a_valid_polygonal_domain",
            geometry_type=free.geom_type,
            source_buffer_sha256=buffered_geometry.sha256,
        )
    canonical_free: Polygon | MultiPolygon = (
        components[0] if len(components) == 1 else MultiPolygon(components)
    )

    hash_payload = json.dumps(
        {
            "source_buffer_sha256": buffered_geometry.sha256,
            "room_size": [width, height],
            "room_margin": margin,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.sha256()
    digest.update(hash_payload)
    digest.update(
        bytes(
            to_wkb(
                canonical_free,
                byte_order=1,
                include_srid=False,
                output_dimension=2,
            )
        )
    )
    certified_clearance = min(
        float(buffered_geometry.clearance),
        float(buffered_geometry.measured_exterior_clearance),
    )
    return GuideFreeSpace(
        physical_room=physical_room,
        feasible_room=feasible_room,
        source_polygon=buffered_geometry.source_polygon,
        forbidden_polygon=forbidden,
        free_space=canonical_free,
        components=components,
        nominal_crowd_clearance=float(buffered_geometry.clearance),
        certified_crowd_clearance=certified_clearance,
        room_margin=margin,
        geometry_sha256=digest.hexdigest(),
        source_buffer_sha256=buffered_geometry.sha256,
        diagnostics={
            "reason": "canonical_room_minus_shared_buffer",
            "component_count": len(components),
            "disconnected": len(components) > 1,
            "free_space_area": float(canonical_free.area),
            "room_size": (width, height),
            "room_margin": margin,
            "nominal_crowd_clearance": float(buffered_geometry.clearance),
            "certified_crowd_clearance": certified_clearance,
            "clearance_basis": "minimum_of_requested_and_measured_buffer_exterior_clearance",
            "source_buffer_sha256": buffered_geometry.sha256,
        },
    )


__all__ = [
    "FreeSpaceConfig",
    "FreeSpaceFailure",
    "FreeSpaceResult",
    "GuideFreeSpace",
    "build_guide_free_space",
]
