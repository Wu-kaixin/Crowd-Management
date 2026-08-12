"""Evaluation workflows for auditable ABCG research stages.

ROLE: ORCHESTRATION / EVIDENCE — formal G6 and diagnostic PR6 pipelines.
Writes under reports/ (and often runs/ for raw cases). Schemas live here too.
"""

from .step1_g6 import G6EvaluationConfig, run_g6_evaluation, run_g6_preflight
from .step1_pr6 import PR6EvaluationConfig, run_pr6_evaluation

__all__ = [
    "G6EvaluationConfig",
    "PR6EvaluationConfig",
    "run_g6_evaluation",
    "run_g6_preflight",
    "run_pr6_evaluation",
]
