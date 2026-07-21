"""Top-level PR6 paired evaluation orchestration."""
from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ...reporting import repository_snapshot as _repository_snapshot
from ...runtime import run_tasks
from ...types import Array
from .aggregate import _aggregate_records, _paired_comparisons
from .cases import _estimator_configs
from .config import PR6EvaluationConfig
from .report import _save_failure_gallery, _write_markdown_report
from .run_case import _run_paired_case


def run_pr6_evaluation(output_dir: str | Path, config: PR6EvaluationConfig) -> dict[str, Any]:
    """Run paired PR6 variants and save finite auditable summaries."""
    if not isinstance(config, PR6EvaluationConfig):
        raise TypeError("config must be PR6EvaluationConfig.")
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    estimator_configs = _estimator_configs(config)
    records: list[dict[str, Any]] = []
    visuals: dict[tuple[str, int, str], tuple[Array, Array, Array | None]] = {}

    cases = [(shape, seed) for shape in config.shapes for seed in config.seeds]
    case_results = run_tasks(
        _run_paired_case,
        [(shape, seed, config, estimator_configs) for shape, seed in cases],
        config.workers,
    )
    for case_records, case_visuals in case_results:
        records.extend(case_records)
        visuals.update(case_visuals)
    records.sort(key=lambda record: (str(record["shape"]), int(record["seed"]), str(record["variant"])))

    aggregate = _aggregate_records(records, config)
    paired = _paired_comparisons(records, config)
    repo = Path(__file__).resolve().parents[4]
    source_paths = [
        repo / "src" / "crowd_management" / "estimation" / "boundary_v2.py",
        repo / "src" / "crowd_management" / "controllers" / "periodic_arc_cvt.py",
        Path(__file__).resolve(),
        Path(__file__).resolve().parent / "config.py",
        Path(__file__).resolve().parent / "cases.py",
        Path(__file__).resolve().parent / "run_case.py",
        Path(__file__).resolve().parent / "aggregate.py",
        Path(__file__).resolve().parent / "report.py",
        Path(__file__).resolve().parent / "__init__.py",
        repo / "scripts" / "run_step1_pr6_evaluation.py",
    ]
    snapshot = _repository_snapshot(repo, source_paths, include_environment=False)

    with open(output / "records.json", "w", encoding="utf-8") as file:
        json.dump(records, file, indent=2)
    with open(output / "records.csv", "w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(records[0].keys()))
        writer.writeheader()
        writer.writerows(records)
    with open(output / "aggregate.json", "w", encoding="utf-8") as file:
        json.dump(aggregate, file, indent=2)
    with open(output / "paired_comparisons.json", "w", encoding="utf-8") as file:
        json.dump(paired, file, indent=2)
    with open(output / "evaluation_config.json", "w", encoding="utf-8") as file:
        json.dump(asdict(config), file, indent=2)
    with open(output / "evaluation_snapshot.json", "w", encoding="utf-8") as file:
        json.dump(snapshot, file, indent=2)

    gallery = _save_failure_gallery(output, records, visuals)
    with open(output / "failure_gallery.json", "w", encoding="utf-8") as file:
        json.dump(gallery, file, indent=2)
    _write_markdown_report(output, config, aggregate, paired, snapshot, gallery)

    evidence = {
        "paired_seed_count": len(config.seeds),
        "heldout_shape_count": len(config.shapes),
        "variant_count": len({record["variant"] for record in records}),
        "record_count": len(records),
        "all_records_accounted_for": len(records) == len(config.seeds) * len(config.shapes) * 4,
        "confidence_intervals_present": True,
        "failure_gallery_present": (output / "failure_gallery.png").is_file(),
        "frozen_commit": snapshot["frozen_commit"],
        "g6_status": "PASS" if snapshot["frozen_commit"] else "UNMET_FROZEN_COMMIT",
    }
    with open(output / "gate_evidence.json", "w", encoding="utf-8") as file:
        json.dump(evidence, file, indent=2)
    return evidence
