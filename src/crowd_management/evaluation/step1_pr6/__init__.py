"""PR6 paired held-out evaluation package."""

from .aggregate import _aggregate_records, _paired_comparisons, _percentile_interval
from .cases import (
    _estimator_configs,
    _heldout_case,
    _neutralize_confidence,
    _points_inside_polygon,
    _polygon_for_shape,
    _truth_length,
)
from .config import PR6EvaluationConfig
from .orchestrate import run_pr6_evaluation
from .report import _save_failure_gallery, _write_markdown_report
from .run_case import _evaluate_boundary, _run_paired_case, _symmetric_curve_errors

__all__ = [
    "PR6EvaluationConfig",
    "run_pr6_evaluation",
]
