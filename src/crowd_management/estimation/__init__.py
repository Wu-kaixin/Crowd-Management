"""State and boundary estimation for unknown crowds.

ROLE: CORE MATH — boundary from observed points only (unknown crowd).
v1: boundary.py (radial). PR6 current: boundary_v2.py (alpha-shape + bootstrap).
"""

from .boundary import BoundaryEstimate, estimate_crowd_center, estimate_radial_boundary, offset_boundary, smooth_radii
from .boundary_v2 import (
    BoundaryEstimateFailure,
    BoundaryEstimateV2,
    BoundaryEstimateV2Result,
    BoundaryV2Config,
    adapt_radial_boundary,
    boundary_v2_from_curve,
    estimate_boundary_v2,
)

__all__ = [
    "BoundaryEstimate",
    "BoundaryEstimateFailure",
    "BoundaryEstimateV2",
    "BoundaryEstimateV2Result",
    "BoundaryV2Config",
    "adapt_radial_boundary",
    "boundary_v2_from_curve",
    "estimate_crowd_center",
    "estimate_radial_boundary",
    "estimate_boundary_v2",
    "offset_boundary",
    "smooth_radii",
]
