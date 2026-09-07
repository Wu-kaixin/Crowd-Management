"""Adaptive guide-agent deployment around unknown crowds.

Package roles (see docs/CODEMAP.zh.md):
  CORE:        crowd/, estimation/, geometry/, controllers/
  ORCHESTRATE: experiments/, evaluation/, runtime/, reporting/
  METRICS/IO:  containment_metrics.py, containment_visualization.py
  DO NOT USE:  legacy/ on this branch (archive: archive/legacy-evacuation-2026-07-21)
"""

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
