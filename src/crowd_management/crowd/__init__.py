"""Crowd representations for adaptive guide-agent deployment.

Step 1 supports simulator-independent static crowd observations.

Truth objects are evaluation-only and must never be passed to
controllers or estimators.
"""

from .jupedsim_static import (
    build_center_support_polygon,
    build_spawn_polygon,
    generate_jupedsim_static_crowd,
    generate_jupedsim_static_truth,
)
from .source import (
    JuPedSimStaticCrowdSource,
    StaticCrowdSource,
    SyntheticStaticCrowdSource,
    build_crowd_source,
)
from .static_crowd import (
    StaticCrowdConfig,
    generate_circle_crowd,
    generate_ellipse_crowd,
    generate_nonconvex_crowd,
    generate_static_crowd,
    generate_two_cluster_crowd,
)
from .truth import (
    StaticCrowdTruth,
    generate_static_crowd_truth,
)
from .heterogeneity import (
    StaticHeterogeneityConfig,
    generate_static_agent_attributes,
)

__all__ = [
    "JuPedSimStaticCrowdSource",
    "StaticCrowdConfig",
    "StaticCrowdSource",
    "StaticCrowdTruth",
    "SyntheticStaticCrowdSource",
    "build_center_support_polygon",
    "build_crowd_source",
    "build_spawn_polygon",
    "generate_circle_crowd",
    "generate_ellipse_crowd",
    "generate_jupedsim_static_crowd",
    "generate_jupedsim_static_truth",
    "generate_nonconvex_crowd",
    "generate_static_crowd",
    "generate_static_crowd_truth",
    "generate_two_cluster_crowd",
    "StaticHeterogeneityConfig",
    "generate_static_agent_attributes",
]