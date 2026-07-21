"""Scientific equivalence characterization across workers and reruns."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from dataclasses import replace

from crowd_management.evaluation import G6EvaluationConfig, run_g6_evaluation
from crowd_management.experiments.static_containment import run_static_containment


STABLE_SUMMARY_KEYS = (
    "coverage_ratio",
    "max_euclidean_boundary_distance",
    "evaluation_status",
    "boundary_v2_status",
    "periodic_plan_status",
    "resource_status",
    "assignment_status",
    "episode_status",
    "safety_filter_status",
    "safety_projected_steps",
    "method_status",
    "active_guide_count",
    "reserve_guide_count",
    "truth_component_count",
)


def _stable_summary(path: Path) -> dict:
    summary = json.loads((path / "summary.json").read_text(encoding="utf-8"))
    method = next(iter(summary))
    return {key: summary[method][key] for key in STABLE_SUMMARY_KEYS}


def test_static_containment_is_seed_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "a"
    second = tmp_path / "b"
    run_static_containment("configs/ci_smoke.yaml", first, methods=["abcg"], save_plots=False)
    run_static_containment("configs/ci_smoke.yaml", second, methods=["abcg"], save_plots=False)
    assert _stable_summary(first) == _stable_summary(second)


def test_tiny_g6_workers_one_matches_auto_scientific_fields(tmp_path: Path) -> None:
    config = G6EvaluationConfig(
        seeds=(0, 1),
        scenarios=("circle",),
        methods=("abcg_v2", "uniform_arc"),
        observation_count=60,
        bootstrap_samples=2,
        confidence_interval_resamples=40,
        max_steps=20,
        workers=1,
    )
    one = tmp_path / "workers1"
    auto = tmp_path / "workers_auto"
    run_g6_evaluation(one, config, run_root=tmp_path / "runs1")
    run_g6_evaluation(auto, replace(config, workers=2), run_root=tmp_path / "runs2")

    comparator = Path("scripts/compare_results.py")
    result = subprocess.run(
        [
            sys.executable,
            str(comparator),
            "--reference",
            str(one),
            "--candidate",
            str(auto),
            "--files",
            "records.json",
            "aggregate.json",
            "paired_comparisons.json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "IDENTICAL" in result.stdout


def test_compare_results_ignores_runtime_metadata_keys(tmp_path: Path) -> None:
    reference = {
        "coverage_ratio": 0.5,
        "total_runtime_ms": 12.0,
        "commit": "aaa",
    }
    candidate = {
        "coverage_ratio": 0.5,
        "total_runtime_ms": 99.0,
        "commit": "bbb",
    }
    ref_dir = tmp_path / "ref"
    cand_dir = tmp_path / "cand"
    ref_dir.mkdir()
    cand_dir.mkdir()
    (ref_dir / "summary.json").write_text(json.dumps(reference), encoding="utf-8")
    (cand_dir / "summary.json").write_text(json.dumps(candidate), encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            "scripts/compare_results.py",
            "--reference",
            str(ref_dir),
            "--candidate",
            str(cand_dir),
            "--files",
            "summary.json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
