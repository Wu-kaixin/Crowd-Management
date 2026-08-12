"""PR6 paired held-out evaluation package.

ROLE: ORCHESTRATION — diagnostic PR6 paired-seed boundary/planner evaluation.
Entry CLI: scripts/run_step1_pr6_evaluation.py → OUTPUT reports/step1_pr6_evaluation/
"""

from .config import PR6EvaluationConfig
from .orchestrate import run_pr6_evaluation

__all__ = [
    "PR6EvaluationConfig",
    "run_pr6_evaluation",
]
