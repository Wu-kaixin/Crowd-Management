"""Adaptive guide-agent deployment around unknown crowds."""

from .containment_metrics import containment_summary
from .controllers import ABCGController, BoundaryCVTController, LegacyCenterRadiusController
from .crowd import StaticCrowdConfig, StaticCrowdTruth, generate_static_crowd, generate_static_crowd_truth
from .estimation import BoundaryEstimate, estimate_radial_boundary

__all__ = [
    "ABCGController",
    "BoundaryCVTController",
    "BoundaryEstimate",
    "LegacyCenterRadiusController",
    "StaticCrowdConfig",
    "StaticCrowdTruth",
    "containment_summary",
    "estimate_radial_boundary",
    "generate_static_crowd",
    "generate_static_crowd_truth",
]
