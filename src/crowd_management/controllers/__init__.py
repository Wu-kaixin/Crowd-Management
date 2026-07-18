"""Guide-agent deployment controllers."""

from .abcg import ABCGController
from .abcg_v2 import (
    ABCGv2Config,
    ABCGv2Controller,
    ConvergenceStateMachine,
    ControlOutput,
    EpisodeResult,
    integrate_guide_positions,
    nominal_guide_velocity,
)
from .assignment import (
    AssignmentConfig,
    AssignmentResult,
    IdentityPreservingAssigner,
    assign_guides_to_targets,
)
from .coverage_cvt import BoundaryCVTController
from .legacy_center_radius import LegacyCenterRadiusController
from .periodic_arc_cvt import (
    CoveragePlan,
    PeriodicArcCVT,
    PeriodicArcCVTConfig,
    equal_arc_target_s,
    plan_equal_arc_coverage,
    plan_periodic_arc_coverage,
    periodic_uniform_coverage_cost,
)
from .random_deployment import RandomDeploymentController
from .resources import ResourceDecision, ResourcePolicy, ResourcePolicyConfig, allocate_guide_resources
from .safety import SafetyProjectionResult, VelocitySafetyConfig, project_velocity_safety
from .static_circle import StaticCircleController

__all__ = [
    "ABCGController",
    "ABCGv2Config",
    "ABCGv2Controller",
    "AssignmentConfig",
    "AssignmentResult",
    "BoundaryCVTController",
    "LegacyCenterRadiusController",
    "IdentityPreservingAssigner",
    "CoveragePlan",
    "ConvergenceStateMachine",
    "ControlOutput",
    "EpisodeResult",
    "PeriodicArcCVT",
    "PeriodicArcCVTConfig",
    "RandomDeploymentController",
    "ResourceDecision",
    "ResourcePolicy",
    "ResourcePolicyConfig",
    "StaticCircleController",
    "SafetyProjectionResult",
    "VelocitySafetyConfig",
    "equal_arc_target_s",
    "allocate_guide_resources",
    "assign_guides_to_targets",
    "plan_equal_arc_coverage",
    "plan_periodic_arc_coverage",
    "periodic_uniform_coverage_cost",
    "project_velocity_safety",
    "integrate_guide_positions",
    "nominal_guide_velocity",
]
