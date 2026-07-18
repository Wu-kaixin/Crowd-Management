from __future__ import annotations

import json
from pathlib import Path

from crowd_management.evaluation import G6EvaluationConfig, run_g6_evaluation


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
    for name in (
        "records.json",
        "records.csv",
        "aggregate.json",
        "paired_comparisons.json",
        "ablation_records.json",
        "robustness_records.json",
        "robustness_aggregate.json",
        "failure_gallery.json",
        "failure_gallery.png",
        "stress_cases.json",
        "performance.json",
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
