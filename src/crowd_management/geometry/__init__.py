"""Closed-curve geometry used by ABCG-v2 Step 1."""

from .arclength import (
    has_self_intersections,
    max_consecutive_arc_gap,
    periodic_arclength_distance,
    resample_closed_curve_by_arclength,
    signed_area,
)

__all__ = [
    "has_self_intersections",
    "max_consecutive_arc_gap",
    "periodic_arclength_distance",
    "resample_closed_curve_by_arclength",
    "signed_area",
]
