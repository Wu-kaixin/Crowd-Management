from __future__ import annotations

import json
from pathlib import Path

from crowd_management.evaluation import PR6EvaluationConfig, run_pr6_evaluation


def test_pr6_evaluation_writes_paired_ablations_intervals_and_gallery(tmp_path: Path) -> None:
    evidence = run_pr6_evaluation(
        tmp_path,
        PR6EvaluationConfig(
            seeds=(0, 1),
            observation_count=180,
            bootstrap_samples=3,
            confidence_interval_resamples=100,
        ),
    )

    assert evidence["paired_seed_count"] == 2
    assert evidence["heldout_shape_count"] == 2
    assert evidence["variant_count"] == 4
    assert evidence["record_count"] == 16
    assert evidence["all_records_accounted_for"]
    assert evidence["g6_status"] in {"PASS", "UNMET_FROZEN_COMMIT"}
    for name in (
        "records.json",
        "records.csv",
        "aggregate.json",
        "paired_comparisons.json",
        "evaluation_config.json",
        "evaluation_snapshot.json",
        "failure_gallery.json",
        "failure_gallery.png",
        "gate_evidence.json",
        "PR6_EVALUATION_REPORT.md",
    ):
        assert (tmp_path / name).is_file()

    records = json.loads((tmp_path / "records.json").read_text(encoding="utf-8"))
    assert len(records) == 16
    assert {record["seed"] for record in records} == {0, 1}
    assert {record["shape"] for record in records} == {"u_shape", "c_shape"}
    assert {record["variant"] for record in records} == {
        "radial_neutral",
        "alpha_neutral",
        "alpha_bootstrap_gain",
        "alpha_bootstrap_no_gain",
    }
    paired = json.loads((tmp_path / "paired_comparisons.json").read_text(encoding="utf-8"))
    comparison = paired["u_shape"]["alpha_bootstrap_gain_minus_radial_neutral"]["curve_chamfer"]
    assert comparison["n"] <= 2
    assert {"mean", "ci95_low", "ci95_high", "win_rate_lower_is_better"}.issubset(comparison)


def test_pr6_requires_unique_paired_seeds() -> None:
    try:
        PR6EvaluationConfig(seeds=(0, 0))
    except ValueError as error:
        assert "unique" in str(error)
    else:
        raise AssertionError("duplicate paired seeds must fail")
