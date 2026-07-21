"""Top-level G6 formal evaluation orchestration."""
from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np

from ...controllers import ABCGv2Controller
from ...reporting import repository_snapshot as _repository_snapshot
from ...reporting import write_json as _write_json
from ...runtime import run_tasks
from .ablations import (
    _ablation_summary,
    _failure_fixtures,
    _robustness_summary,
    _run_ablations,
    _run_robustness,
)
from .aggregate import _aggregate, _paired_comparisons
from .config import ABLATION_VARIANTS, G6EvaluationConfig, PRIMARY_METHODS, PRIMARY_SCENARIOS
from .preflight import _preflight_is_valid, _process_peak_memory_bytes
from .report import _save_failure_gallery, _write_records_csv, _write_report
from .run_case import _run_primary_case


def run_g6_evaluation(
    output_dir: str | Path,
    config: G6EvaluationConfig,
    run_root: str | Path | None = None,
    *,
    preflight_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run formal G6 evidence and return explicit gate status."""
    if not isinstance(config, G6EvaluationConfig):
        raise TypeError("config must be G6EvaluationConfig.")
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    runs = Path(run_root) if run_root is not None else output / "run_artifacts"
    runs.mkdir(parents=True, exist_ok=True)
    repo = Path(__file__).resolve().parents[4]
    source_paths = [
        Path(__file__).resolve(),
        Path(__file__).resolve().parent / "config.py",
        Path(__file__).resolve().parent / "cases.py",
        Path(__file__).resolve().parent / "run_case.py",
        Path(__file__).resolve().parent / "aggregate.py",
        Path(__file__).resolve().parent / "ablations.py",
        Path(__file__).resolve().parent / "preflight.py",
        Path(__file__).resolve().parent / "report.py",
        Path(__file__).resolve().parent / "__init__.py",
        repo / "scripts" / "run_step1_g6_compliance.py",
        repo / "src" / "crowd_management" / "controllers" / "abcg_v2.py",
        repo / "src" / "crowd_management" / "controllers" / "assignment.py",
        repo / "src" / "crowd_management" / "estimation" / "boundary_v2.py",
    ]
    snapshot = _repository_snapshot(repo, source_paths)
    _write_json(output / "evaluation_config.json", asdict(config))
    _write_json(output / "evaluation_snapshot.json", snapshot)
    _write_json(
        output / "preflight_evidence.json",
        preflight_evidence
        if preflight_evidence is not None
        else {
            "schema": "abcg-v2-step1-preflight-v1",
            "evaluated_commit": snapshot["commit"],
            "all_passed": False,
            "status": "NOT_RUN",
        },
    )

    started = time.perf_counter()
    cases = [(scenario, seed) for scenario in config.scenarios for seed in config.seeds]
    case_records = run_tasks(
        _run_primary_case,
        [(scenario, seed, config, runs, snapshot) for scenario, seed in cases],
        config.workers,
    )
    records = [record for group in case_records for record in group]
    records.sort(key=lambda record: (str(record["scenario"]), int(record["seed"]), str(record["method"])))
    aggregate = _aggregate(records, config)
    paired = _paired_comparisons(records, config)
    ablations = _run_ablations(config, records)
    ablation_aggregate = _ablation_summary(ablations, config)
    robustness = _run_robustness(config)
    robustness_aggregate = _robustness_summary(robustness, config)
    stress_fixtures = _failure_fixtures(config)
    _write_json(
        output / "stress_cases.json",
        [
            {
                "fixture": fixture["fixture"],
                "status": fixture["status"],
                "reason": fixture["reason"],
                "selection_role": "stress_case",
            }
            for fixture in stress_fixtures
        ],
    )
    gallery = _save_failure_gallery(output, stress_fixtures)
    peak_memory = _process_peak_memory_bytes()
    wall_time_s = time.perf_counter() - started

    _write_json(output / "records.json", records)
    _write_records_csv(output / "records.csv", records)
    _write_json(output / "aggregate.json", aggregate)
    _write_json(output / "paired_comparisons.json", paired)
    _write_json(output / "ablation_records.json", ablations)
    _write_json(output / "ablation_aggregate.json", ablation_aggregate)
    _write_json(output / "robustness_records.json", robustness)
    _write_json(output / "robustness_aggregate.json", robustness_aggregate)
    performance = {
        "wall_time_s": wall_time_s,
        "peak_process_resident_memory_bytes": int(peak_memory),
        "primary_runtime_ms": _aggregate_summary(
            [float(record["total_runtime_ms"]) for record in records],
            config,
        ),
    }
    _write_json(output / "performance.json", performance)

    expected = len(config.seeds) * len(config.scenarios) * len(config.methods)
    preflight_valid = _preflight_is_valid(preflight_evidence, snapshot)
    checks = {
        "formal_preflight": preflight_valid,
        "research_dependencies": all(name in snapshot["packages"] for name in ("scipy", "shapely")),
        "reset_step_api": all(hasattr(ABCGv2Controller, name) for name in ("reset", "step")),
        "primary_scenarios": set(config.scenarios) == set(PRIMARY_SCENARIOS),
        "required_methods": set(config.methods) == set(PRIMARY_METHODS),
        "paired_seed_count_at_least_30": len(config.seeds) >= 30,
        "bootstrap_samples_at_least_30": config.bootstrap_samples >= 30,
        "all_primary_records_accounted_for": len(records) == expected,
        "all_failures_in_denominator": sum(item["run_count"] for scenario in aggregate.values() for item in scenario.values()) == expected,
        "ablations_present": {record["variant"] for record in ablations} == set(ABLATION_VARIANTS),
        "robustness_noise_dropout_scale": {record["dimension"] for record in robustness} == {"noise", "dropout", "scale"},
        "statistics_mean_median_ci_effect_worst5_failure": bool(paired) and all(
            {"mean", "median", "ci95_low", "ci95_high", "worst_5_percent_mean"}.issubset(summary)
            for scenario in aggregate.values()
            for method in scenario.values()
            for summary in method["metrics"].values()
        ),
        "actual_failure_gallery": len(gallery) >= 1 and (output / "failure_gallery.png").is_file(),
        "stress_double_cluster_and_narrow_neck": {fixture["fixture"] for fixture in stress_fixtures}.issuperset(
            {"double_cluster", "narrow_neck"}
        ),
        "runtime_p95_memory": performance["primary_runtime_ms"]["p95"] is not None and peak_memory > 0,
        "run_artifact_contract": all(
            (runs / record["scenario"] / record["method"] / f"seed_{record['seed']:03d}" / name).is_file()
            for record in records
            for name in (
                "config_resolved.json",
                "manifest.json",
                "observations.npz",
                "boundary_versions.npz",
                "plan_trace.npz",
                "trajectory.npz",
                "events.jsonl",
                "metrics.json",
            )
        ),
        "independent_truth_evidence": all(
            json.loads(
                (runs / record["scenario"] / record["method"] / f"seed_{record['seed']:03d}" / "manifest.json").read_text(
                    encoding="utf-8"
                )
            ).get("truth_access")
            == "evaluator_only"
            for record in records
        ),
        "frozen_commit": snapshot["frozen_commit"],
    }
    compliance_without_freeze = all(
        value for key, value in checks.items() if key not in {"formal_preflight", "frozen_commit"}
    )
    g0_to_g5_status = "PASS" if preflight_valid else "UNMET_PREFLIGHT"
    if preflight_valid and compliance_without_freeze and checks["frozen_commit"]:
        status = "PASS"
    elif preflight_valid and compliance_without_freeze:
        status = "UNMET_FROZEN_COMMIT"
    elif not preflight_valid and compliance_without_freeze and checks["frozen_commit"]:
        status = "UNMET_PREFLIGHT"
    elif not preflight_valid and compliance_without_freeze:
        status = "UNMET_PREFLIGHT_AND_FROZEN_COMMIT"
    else:
        status = "UNMET_COMPLIANCE_AND_FROZEN_COMMIT" if not checks["frozen_commit"] else "UNMET_COMPLIANCE"
    gates = {f"G{index}": g0_to_g5_status for index in range(6)}
    gates["G6"] = status
    status_counts = {
        item_status: int(sum(record["status"] == item_status for record in records))
        for item_status in sorted({str(record["status"]) for record in records})
    }
    gate = {
        "schema": "abcg-v2-step1-gates-v2",
        "overall_status": "PASS" if all(value == "PASS" for value in gates.values()) else status,
        "g6_status": status,
        "evaluated_commit": snapshot["commit"],
        "code_freeze_commit": snapshot["commit"],
        "frozen_commit": "PASS" if snapshot["frozen_commit"] else "FAIL",
        "gates": gates,
        "gate_basis": {
            "G0-G5": "commit-bound pytest, compileall, and pip check preflight",
            "G6": "formal paired evaluation checks plus a clean frozen checkout",
        },
        "checks": checks,
        "primary_record_count": len(records),
        "expected_primary_record_count": expected,
        "success_count": int(sum(record["success"] for record in records)),
        "failure_count": int(sum(not record["success"] for record in records)),
        "status_counts": status_counts,
        "actual_failure_gallery_count": len(gallery),
    }
    _write_json(output / "gate_evidence.json", gate)
    _write_report(output, config, aggregate, snapshot, gate)
    return gate


def _aggregate_summary(values: list[float], config: G6EvaluationConfig) -> dict[str, Any]:
    from ..shared import bootstrap_metric_summary

    return bootstrap_metric_summary(
        values,
        np.random.default_rng(700_007),
        config.confidence_interval_resamples,
        "lower",
    )
