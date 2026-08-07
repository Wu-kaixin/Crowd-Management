"""Formal G6 evaluation package.

ROLE: ORCHESTRATION — formal G6 compliance pipeline (preflight, cases, ablations, reports).
Entry CLI: scripts/run_step1_g6_compliance.py → OUTPUT reports/step1_g6_compliance/
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import preflight as _preflight_module
from .config import (
    ABLATION_VARIANTS,
    METRIC_DIRECTIONS,
    NONCONVEX_SCENARIOS,
    PRIMARY_METHODS,
    PRIMARY_SCENARIOS,
    G6EvaluationConfig,
)
from .orchestrate import run_g6_evaluation
from .preflight import _preflight_is_valid

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
    "_preflight_is_valid",
    "run_g6_evaluation",
    "run_g6_preflight",
]
