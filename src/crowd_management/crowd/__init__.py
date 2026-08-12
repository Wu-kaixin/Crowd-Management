"""Crowd representations for the adaptive guide-agent deployment line.

ROLE: CORE DATA GENERATORS — synthetic static point clouds + independent analytic truth.
Truth is for evaluation only; controllers must not depend on it at runtime.
"""

from .static_crowd import (
    StaticCrowdConfig,
    generate_circle_crowd,
    generate_ellipse_crowd,
    generate_nonconvex_crowd,
    generate_static_crowd,
    generate_two_cluster_crowd,
)
from .truth import StaticCrowdTruth, generate_static_crowd_truth

__all__ = [
    "StaticCrowdConfig",
    "StaticCrowdTruth",
    "generate_circle_crowd",
    "generate_ellipse_crowd",
    "generate_nonconvex_crowd",
    "generate_static_crowd",
    "generate_static_crowd_truth",
    "generate_two_cluster_crowd",
]
