"""Formal G6 evaluation package."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .ablations import (
    _ablation_summary,
    _failure_fixtures,
    _robustness_summary,
    _run_ablation_case,
    _run_ablations,
    _run_robustness,
    _run_robustness_case,
)
from .aggregate import _aggregate, _paired_comparisons, _summary
from .cases import (
    _base_case,
    _boundary_config,
    _inside_polygon,
    _initial_guides,
    _neutralize_confidence,
    _observed_case,
    _polygon_for_shape,
)
from .config import (
    ABLATION_VARIANTS,
    G6EvaluationConfig,
    METRIC_DIRECTIONS,
    NONCONVEX_SCENARIOS,
    PRIMARY_METHODS,
    PRIMARY_SCENARIOS,
)
from .orchestrate import run_g6_evaluation
from .preflight import _preflight_is_valid, _process_peak_memory_bytes
from . import preflight as _preflight_module
from .report import _save_failure_gallery, _write_records_csv, _write_report
from .run_case import (
    _curve_errors,
    _empty_trace,
    _make_targets,
    _minimum_pair_distance,
    _nearest_arc_coordinates,
    _plan_metrics,
    _run_feedback_episode,
    _run_method,
    _run_primary_case,
    _save_run_artifacts,
    _trajectory_crossings,
)

_run_preflight_command = _preflight_module._run_preflight_command


def run_g6_preflight(repo: str | Path | None = None) -> dict[str, Any]:
    """Run G6 preflight while preserving package-level monkeypatch hooks."""
    _preflight_module._run_preflight_command = _run_preflight_command
    return _preflight_module.run_g6_preflight(repo)


__all__ = [
    "ABLATION_VARIANTS",
    "G6EvaluationConfig",
    "METRIC_DIRECTIONS",
    "NONCONVEX_SCENARIOS",
    "PRIMARY_METHODS",
    "PRIMARY_SCENARIOS",
    "run_g6_evaluation",
    "run_g6_preflight",
]
