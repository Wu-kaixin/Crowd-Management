"""Result schema regression for formal and smoke outputs."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from crowd_management.evaluation import G6EvaluationConfig, PR6EvaluationConfig, run_g6_evaluation, run_pr6_evaluation
from crowd_management.evaluation.schema_validation import (
    SchemaValidationError,
    validate_evaluation_directory,
    validate_g6_gate_evidence,
    validate_runtime_metadata,
)
from crowd_management.experiments.static_containment import run_static_containment


def test_frozen_g6_gate_evidence_schema() -> None:
    gate = json.loads(Path("reports/step1_g6_compliance/gate_evidence.json").read_text(encoding="utf-8"))
    validate_g6_gate_evidence(gate)


def test_frozen_pr6_gate_directory_schema() -> None:
    # records.json is gitignored for the formal tree; validate available committed artifacts.
    gate = json.loads(Path("reports/step1_pr6_evaluation/gate_evidence.json").read_text(encoding="utf-8"))
    from crowd_management.evaluation.schema_validation import validate_pr6_gate_evidence, validate_paired_comparisons

    validate_pr6_gate_evidence(gate)
    paired = json.loads(Path("reports/step1_pr6_evaluation/paired_comparisons.json").read_text(encoding="utf-8"))
    validate_paired_comparisons(paired)


def test_tiny_g6_directory_schema(tmp_path: Path) -> None:
    report = tmp_path / "report"
    run_g6_evaluation(
        report,
        G6EvaluationConfig(
            seeds=(0,),
            scenarios=("circle",),
            methods=("abcg_v2", "uniform_arc"),
            observation_count=60,
            bootstrap_samples=2,
            confidence_interval_resamples=40,
            max_steps=20,
            workers=1,
        ),
        run_root=tmp_path / "runs",
    )
    checked = validate_evaluation_directory(report, kind="g6")
    assert "records.json" in checked
    assert "gate_evidence.json" in checked


def test_tiny_pr6_directory_schema(tmp_path: Path) -> None:
    run_pr6_evaluation(
        tmp_path,
        PR6EvaluationConfig(
            seeds=(0,),
            shapes=("u_shape",),
            observation_count=120,
            bootstrap_samples=2,
            confidence_interval_resamples=40,
            workers=1,
        ),
    )
    checked = validate_evaluation_directory(tmp_path, kind="pr6")
    assert "records.json" in checked


def test_static_summary_schema(tmp_path: Path) -> None:
    run_static_containment(
        "configs/ci_smoke.yaml",
        tmp_path,
        methods=["abcg"],
        save_plots=False,
    )
    checked = validate_evaluation_directory(tmp_path, kind="static")
    assert set(checked) >= {"summary.json", "manifest.json"}


def test_runtime_metadata_rejects_privacy_keys() -> None:
    with pytest.raises(SchemaValidationError):
        validate_runtime_metadata(
            {
                "schema": "abcg-runtime-metadata-v1",
                "hardware": {"username": "alice"},
                "parallel_plan": {"workers": 1},
            }
        )
