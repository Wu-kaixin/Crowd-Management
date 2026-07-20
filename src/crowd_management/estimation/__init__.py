"""State and boundary estimation for unknown crowds."""

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
from .boundary_v3 import (
    AlignedBoundaryReplica,
    BoundaryCalibrationCase,
    BoundaryStabilityConfig,
    BoundaryStabilityEstimate,
    BoundaryStabilityFailure,
    BoundaryStabilityResult,
    RegisteredBoundaryCurve,
    align_boundary_replica,
    estimate_boundary_stability,
    estimate_boundary_uncertainty_v3,
    normalize_boundary_curve,
)

__all__ = [
    "BoundaryEstimate",
    "BoundaryEstimateFailure",
    "BoundaryEstimateV2",
    "BoundaryEstimateV2Result",
    "BoundaryV2Config",
    "AlignedBoundaryReplica",
    "BoundaryCalibrationCase",
    "BoundaryStabilityConfig",
    "BoundaryStabilityEstimate",
    "BoundaryStabilityFailure",
    "BoundaryStabilityResult",
    "RegisteredBoundaryCurve",
    "adapt_radial_boundary",
    "boundary_v2_from_curve",
    "estimate_crowd_center",
    "estimate_radial_boundary",
    "estimate_boundary_v2",
    "align_boundary_replica",
    "estimate_boundary_stability",
    "estimate_boundary_uncertainty_v3",
    "normalize_boundary_curve",
    "offset_boundary",
    "smooth_radii",
]
