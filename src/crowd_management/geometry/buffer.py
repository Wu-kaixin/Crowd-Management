"""Canonical polygon-buffer geometry for ABCG-v2.1 static deployment.

The module deliberately treats a single Shapely buffer result as the source of
the target curve, configuration-space forbidden set, and sampled-safety
geometry.  It never selects the largest component, drops holes, or repairs an
invalid polygon silently.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib

import numpy as np
from shapely import to_wkb
from shapely.geometry import LinearRing, MultiPolygon, Polygon, box

from ..types import Array


BufferDiagnostics = dict[str, object]


@dataclass(frozen=True)
class PolygonBufferConfig:
    """Deterministic controls for a two-dimensional Minkowski expansion."""

    clearance: float
    quad_segs: int = 16
    join_style: str = "round"
    mitre_limit: float = 5.0
    allow_holes: bool = False
    allow_topology_change: bool = False
    room_size: tuple[float, float] | None = None
    room_margin: float = 0.0

    def __post_init__(self) -> None:
        if not np.isfinite(self.clearance) or self.clearance < 0.0:
            raise ValueError("clearance must be finite and non-negative.")
        if (
            isinstance(self.quad_segs, bool)
            or not isinstance(self.quad_segs, (int, np.integer))
            or self.quad_segs < 1
        ):
            raise ValueError("quad_segs must be a positive integer.")
        if self.join_style not in {"round", "mitre", "bevel"}:
            raise ValueError("join_style must be 'round', 'mitre', or 'bevel'.")
        if not np.isfinite(self.mitre_limit) or self.mitre_limit <= 0.0:
            raise ValueError("mitre_limit must be finite and positive.")
        if not np.isfinite(self.room_margin) or self.room_margin < 0.0:
            raise ValueError("room_margin must be finite and non-negative.")
        if self.room_size is not None:
            room = np.asarray(self.room_size, dtype=float)
            if room.shape != (2,) or not np.all(np.isfinite(room)) or np.any(room <= 0.0):
                raise ValueError("room_size must contain two finite positive dimensions.")


@dataclass(frozen=True)
class BufferedPolygonGeometry:
    """One valid canonical buffer shared by planning and safety consumers."""

    source_polygon: Polygon
    buffered_polygon: Polygon
    exterior: Array
    holes: tuple[Array, ...]
    clearance: float
    measured_exterior_clearance: float
    wkb: bytes
    sha256: str
    topology_changed: bool
    diagnostics: BufferDiagnostics = field(default_factory=dict)

    @property
    def target_polygon(self) -> Polygon:
        """Return the exact polygon whose exterior defines deployment targets."""

        return self.buffered_polygon

    @property
    def forbidden_polygon(self) -> Polygon:
        """Return the same buffer as the guide configuration-space obstacle."""

        return self.buffered_polygon

    @property
    def safety_polygon(self) -> Polygon:
        """Return the same buffer used for geometry-level clearance checks."""

        return self.buffered_polygon

    @property
    def target_wkb(self) -> bytes:
        return self.wkb

    @property
    def forbidden_wkb(self) -> bytes:
        return self.wkb

    @property
    def safety_wkb(self) -> bytes:
        return self.wkb


@dataclass(frozen=True)
class PolygonBufferFailure:
    """Explicit geometry failure; no repaired or partial polygon is returned."""

    status: str
    diagnostics: BufferDiagnostics = field(default_factory=dict)


PolygonBufferResult = BufferedPolygonGeometry | PolygonBufferFailure


def _failure(status: str, reason: str, **diagnostics: object) -> PolygonBufferFailure:
    return PolygonBufferFailure(status=status, diagnostics={"reason": reason, **diagnostics})


def _ring_area(points: Array) -> float:
    successor = np.roll(points, -1, axis=0)
    return 0.5 * float(
        np.sum(points[:, 0] * successor[:, 1] - successor[:, 0] * points[:, 1])
    )


def _canonical_ring(coordinates: Array, *, counter_clockwise: bool) -> Array:
    points = np.asarray(coordinates, dtype=float)
    if points.ndim != 2 or points.shape[1:] != (2,) or not np.all(np.isfinite(points)):
        raise ValueError("ring coordinates must be a finite (N, 2) array.")
    if len(points) >= 2 and np.array_equal(points[0], points[-1]):
        points = points[:-1]
    if len(points) < 3:
        raise ValueError("a ring requires at least three vertices.")
    area = _ring_area(points)
    if abs(area) <= 1.0e-14:
        raise ValueError("ring area must be non-zero.")
    if (area > 0.0) != counter_clockwise:
        points = points[::-1].copy()
    # A stable start vertex makes WKB/hash and serialized arrays independent of
    # Shapely's internal ring start choice.
    order = np.lexsort((points[:, 1], points[:, 0]))
    start = int(order[0])
    points = np.roll(points, -start, axis=0)
    return np.vstack((points, points[0]))


def _canonical_polygon(polygon: Polygon) -> Polygon:
    exterior = _canonical_ring(np.asarray(polygon.exterior.coords), counter_clockwise=True)
    holes = [
        _canonical_ring(np.asarray(interior.coords), counter_clockwise=False)
        for interior in polygon.interiors
    ]
    holes.sort(key=lambda ring: tuple(ring[0]))
    return Polygon(exterior, holes)


def _source_polygon(source: Array | Polygon | MultiPolygon) -> PolygonBufferResult | Polygon:
    if isinstance(source, MultiPolygon):
        return _failure(
            "MULTIPOLYGON",
            "source_geometry_has_multiple_polygon_components",
            component_count=len(source.geoms),
        )
    if isinstance(source, Polygon):
        polygon = source
    else:
        points = np.asarray(source, dtype=float)
        if points.ndim != 2 or points.shape[1:] != (2,) or not np.all(np.isfinite(points)):
            return _failure("INVALID", "source_curve_must_be_finite_N_by_2")
        if len(points) >= 2 and np.linalg.norm(points[-1] - points[0]) <= 1.0e-12:
            points = points[:-1]
        if len(points) < 3:
            return _failure("EMPTY", "source_curve_has_fewer_than_three_vertices")
        polygon = Polygon(points)
    if polygon.is_empty:
        return _failure("EMPTY", "source_polygon_is_empty")
    if not polygon.is_valid or polygon.area <= 1.0e-14:
        return _failure("INVALID", "source_polygon_is_invalid", area=float(polygon.area))
    try:
        canonical = _canonical_polygon(polygon)
    except ValueError as error:
        return _failure("INVALID", str(error))
    if not canonical.is_valid or canonical.is_empty:
        return _failure("INVALID", "canonical_source_polygon_is_invalid")
    return canonical


def build_polygon_buffer(
    source: Array | Polygon | MultiPolygon,
    config: PolygonBufferConfig,
) -> PolygonBufferResult:
    """Expand one polygon and classify every unsupported topology explicitly.

    ``source`` may be one ordered exterior curve or one Shapely ``Polygon``.
    ``MultiPolygon`` inputs and outputs are never reduced to a selected member.
    The returned canonical buffer is the sole geometry exposed through the
    target/forbidden/safety properties.
    """

    if not isinstance(config, PolygonBufferConfig):
        raise TypeError("config must be PolygonBufferConfig.")
    source_result = _source_polygon(source)
    if isinstance(source_result, PolygonBufferFailure):
        return source_result
    source_polygon = source_result
    source_hole_count = len(source_polygon.interiors)
    if source_hole_count and not config.allow_holes:
        return _failure(
            "HOLES",
            "source_polygon_contains_holes",
            source_hole_count=source_hole_count,
        )

    buffered = source_polygon.buffer(
        float(config.clearance),
        quad_segs=int(config.quad_segs),
        join_style=config.join_style,
        mitre_limit=float(config.mitre_limit),
    )
    if buffered.is_empty:
        return _failure("EMPTY", "polygon_buffer_is_empty", clearance=float(config.clearance))
    if isinstance(buffered, MultiPolygon):
        return _failure(
            "MULTIPOLYGON",
            "polygon_buffer_has_multiple_components",
            component_count=len(buffered.geoms),
            clearance=float(config.clearance),
        )
    if not isinstance(buffered, Polygon) or not buffered.is_valid or buffered.area <= 1.0e-14:
        return _failure(
            "INVALID",
            "polygon_buffer_is_invalid",
            geometry_type=buffered.geom_type,
            clearance=float(config.clearance),
        )

    try:
        canonical_buffer = _canonical_polygon(buffered)
    except ValueError as error:
        return _failure("INVALID", str(error), clearance=float(config.clearance))
    result_hole_count = len(canonical_buffer.interiors)
    if result_hole_count and not config.allow_holes:
        return _failure(
            "HOLES",
            "polygon_buffer_contains_holes",
            source_hole_count=source_hole_count,
            result_hole_count=result_hole_count,
        )

    topology_changed = source_hole_count != result_hole_count
    if topology_changed and not config.allow_topology_change:
        return _failure(
            "OFFSET_TOPOLOGY_CHANGED",
            "polygon_buffer_changed_hole_topology",
            source_hole_count=source_hole_count,
            result_hole_count=result_hole_count,
            clearance=float(config.clearance),
        )

    if config.room_size is not None:
        width, height = (float(value) for value in config.room_size)
        margin = float(config.room_margin)
        if width <= 2.0 * margin or height <= 2.0 * margin:
            return _failure(
                "ROOM_INFEASIBLE",
                "room_margin_leaves_no_positive_free_area",
                room_width=width,
                room_height=height,
                room_margin=margin,
            )
        feasible_room = box(margin, margin, width - margin, height - margin)
        if not feasible_room.covers(canonical_buffer):
            return _failure(
                "ROOM_INFEASIBLE",
                "buffered_polygon_is_not_covered_by_room",
                room_width=width,
                room_height=height,
                room_margin=margin,
                buffered_bounds=tuple(float(value) for value in canonical_buffer.bounds),
            )

    exterior = np.asarray(canonical_buffer.exterior.coords[:-1], dtype=float)
    holes = tuple(
        np.asarray(interior.coords[:-1], dtype=float)
        for interior in canonical_buffer.interiors
    )
    canonical_wkb = to_wkb(
        canonical_buffer,
        byte_order=1,
        include_srid=False,
        output_dimension=2,
    )
    assert isinstance(canonical_wkb, bytes)
    measured_clearance = float(LinearRing(canonical_buffer.exterior.coords).distance(source_polygon))
    return BufferedPolygonGeometry(
        source_polygon=source_polygon,
        buffered_polygon=canonical_buffer,
        exterior=exterior,
        holes=holes,
        clearance=float(config.clearance),
        measured_exterior_clearance=measured_clearance,
        wkb=canonical_wkb,
        sha256=hashlib.sha256(canonical_wkb).hexdigest(),
        topology_changed=topology_changed,
        diagnostics={
            "status": "VALID",
            "geometry_model": "single_canonical_polygon_buffer",
            "shared_geometry_roles": "target,forbidden,safety",
            "source_hole_count": source_hole_count,
            "result_hole_count": result_hole_count,
            "quad_segs": int(config.quad_segs),
            "join_style": config.join_style,
            "mitre_limit": float(config.mitre_limit),
            "room_checked": config.room_size is not None,
        },
    )


__all__ = [
    "BufferedPolygonGeometry",
    "PolygonBufferConfig",
    "PolygonBufferFailure",
    "PolygonBufferResult",
    "build_polygon_buffer",
]
