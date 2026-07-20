"""Closed-curve geometry used by ABCG-v2 Step 1."""

from .arclength import (
    has_self_intersections,
    max_consecutive_arc_gap,
    periodic_arclength_distance,
    resample_closed_curve_by_arclength,
    signed_area,
)
from .buffer import (
    BufferedPolygonGeometry,
    PolygonBufferConfig,
    PolygonBufferFailure,
    PolygonBufferResult,
    build_polygon_buffer,
)
from .free_space import (
    FreeSpaceConfig,
    FreeSpaceFailure,
    FreeSpaceResult,
    GuideFreeSpace,
    build_guide_free_space,
)

__all__ = [
    "has_self_intersections",
    "max_consecutive_arc_gap",
    "periodic_arclength_distance",
    "resample_closed_curve_by_arclength",
    "signed_area",
    "BufferedPolygonGeometry",
    "PolygonBufferConfig",
    "PolygonBufferFailure",
    "PolygonBufferResult",
    "build_polygon_buffer",
    "FreeSpaceConfig",
    "FreeSpaceFailure",
    "FreeSpaceResult",
    "GuideFreeSpace",
    "build_guide_free_space",
]
