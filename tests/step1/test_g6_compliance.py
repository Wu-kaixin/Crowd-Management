from __future__ import annotations

import json
from pathlib import Path

from crowd_management.evaluation import G6EvaluationConfig, run_g6_evaluation
from crowd_management.evaluation.step1_g6 import _preflight_is_valid


def test_g6_writes_closed_loop_contract_and_explicit_unmet_gate(tmp_path: Path) -> None:
    report = tmp_path / "report"
    runs = tmp_path / "runs"
    gate = run_g6_evaluation(
        report,
        G6EvaluationConfig(
            seeds=(0, 1),
            observation_count=70,
            bootstrap_samples=2,
            confidence_interval_resamples=50,
            max_steps=25,
            workers=2,
        ),
        run_root=runs,
    )

    assert gate["primary_record_count"] == 2 * 4 * 5
    assert gate["checks"]["all_primary_records_accounted_for"]
    assert gate["checks"]["all_failures_in_denominator"]
    assert not gate["checks"]["paired_seed_count_at_least_30"]
    assert not gate["checks"]["bootstrap_samples_at_least_30"]
    assert gate["g6_status"].startswith("UNMET_")
    assert gate["overall_status"].startswith("UNMET_")
    assert gate["frozen_commit"] in {"PASS", "FAIL"}
    assert gate["evaluated_commit"]
    assert gate["gates"] == {
        "G0": "UNMET_PREFLIGHT",
        "G1": "UNMET_PREFLIGHT",
        "G2": "UNMET_PREFLIGHT",
        "G3": "UNMET_PREFLIGHT",
        "G4": "UNMET_PREFLIGHT",
        "G5": "UNMET_PREFLIGHT",
        "G6": gate["g6_status"],
    }
    for name in (
        "records.json",
        "records.csv",
        "aggregate.json",
        "paired_comparisons.json",
        "ablation_records.json",
        "ablation_aggregate.json",
        "robustness_records.json",
        "robustness_aggregate.json",
        "failure_gallery.json",
        "failure_gallery.png",
        "stress_cases.json",
        "performance.json",
        "preflight_evidence.json",
        "gate_evidence.json",
        "G6_COMPLIANCE_REPORT.md",
    ):
        assert (report / name).is_file()

    manifest = json.loads((runs / "u_shape" / "abcg_v2" / "seed_000" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["truth_access"] == "evaluator_only"
    assert len(manifest["artifacts"]) == 8
    for name in manifest["artifacts"]:
        assert (runs / "u_shape" / "abcg_v2" / "seed_000" / name).is_file()

    gallery = json.loads((report / "failure_gallery.json").read_text(encoding="utf-8"))
    assert gallery
    assert all(item["selection_role"] == "actual_failure" for item in gallery)
    stress = json.loads((report / "stress_cases.json").read_text(encoding="utf-8"))
    assert {item["fixture"] for item in stress}.issuperset({"double_cluster", "narrow_neck"})
    aggregate = json.loads((report / "aggregate.json").read_text(encoding="utf-8"))
    metric = aggregate["u_shape"]["abcg_v2"]["metrics"]["total_runtime_ms"]
    assert {"mean", "median", "ci95_low", "ci95_high", "p95", "worst_5_percent_mean"}.issubset(metric)
    ablation = json.loads((report / "ablation_aggregate.json").read_text(encoding="utf-8"))
    assert set(ablation["u_shape"]) == {
        "radial_no_bootstrap",
        "alpha_no_bootstrap",
        "alpha_bootstrap_no_gain",
        "abcg_v2_full",
    }


def test_g6_defaults_match_formal_seed_and_bootstrap_floor() -> None:
    config = G6EvaluationConfig()
    assert len(config.seeds) == 30
    assert config.bootstrap_samples == 30
    assert set(config.scenarios) == {"circle", "ellipse", "u_shape", "c_shape"}
    assert set(config.methods) == {
        "endpoint_abcg",
        "uniform_angular",
        "uniform_arc",
        "fixed_m_periodic",
        "abcg_v2",
    }


def test_preflight_evidence_is_commit_bound_and_requires_all_commands() -> None:
    snapshot = {"commit": "abc123"}
    evidence = {
        "schema": "abcg-v2-step1-preflight-v1",
        "evaluated_commit": "abc123",
        "repository_clean_before": True,
        "repository_clean_after": True,
        "all_passed": True,
        "commands": [
            {"name": "pytest", "return_code": 0},
            {"name": "compileall", "return_code": 0},
            {"name": "pip_check", "return_code": 0},
        ],
    }

    assert _preflight_is_valid(evidence, snapshot)
    assert not _preflight_is_valid({**evidence, "evaluated_commit": "other"}, snapshot)
    assert not _preflight_is_valid(
        {**evidence, "commands": [*evidence["commands"][:-1], {"name": "pip_check", "return_code": 1}]},
        snapshot,
    )
