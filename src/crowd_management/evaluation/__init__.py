"""Evaluation workflows for auditable ABCG research stages."""

from .step1_g6 import G6EvaluationConfig, run_g6_evaluation, run_g6_preflight
from .step1_g7 import (
    G6_BASE_SHA,
    IMPLEMENTATION_FREEZE_SHA,
    audit_frozen_g6_evidence,
    failure_rate_composition,
    matched_same_resource_pairs,
    paired_bootstrap_interval,
    split_resource_regimes,
)
from .step1_pr6 import PR6EvaluationConfig, run_pr6_evaluation
from .schemas import (
    DeploymentMetrics,
    G7Record,
    LayeredOutcome,
    LayerState,
    ResourceRegime,
    compose_layered_outcome,
    resource_normalized_metrics,
)

__all__ = [
    "G6EvaluationConfig",
    "G6_BASE_SHA",
    "IMPLEMENTATION_FREEZE_SHA",
    "PR6EvaluationConfig",
    "DeploymentMetrics",
    "G7Record",
    "LayeredOutcome",
    "LayerState",
    "ResourceRegime",
    "audit_frozen_g6_evidence",
    "compose_layered_outcome",
    "failure_rate_composition",
    "matched_same_resource_pairs",
    "paired_bootstrap_interval",
    "resource_normalized_metrics",
    "run_g6_evaluation",
    "run_g6_preflight",
    "run_pr6_evaluation",
    "split_resource_regimes",
]
