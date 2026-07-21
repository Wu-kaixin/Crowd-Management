"""G6 report and gallery writers."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import numpy as np

from ...reporting import write_json as _write_json
from ...reporting import write_records_csv as _write_records_csv  # noqa: F401
from .config import G6EvaluationConfig


def _save_failure_gallery(output: Path, fixtures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actual = [fixture for fixture in fixtures if fixture["status"] not in {"VALID", "CONVERGED", "UNEXPECTED_VALID"}]
    os.environ.setdefault("MPLCONFIGDIR", str((output / ".mplconfig").resolve()))
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(1, max(1, len(actual)), figsize=(6 * max(1, len(actual)), 5), squeeze=False)
    for axis, fixture in zip(axes.ravel(), actual, strict=False):
        observation = fixture["observation"]
        truth = fixture["truth"]
        estimate = fixture["estimate"]
        axis.scatter(observation[:, 0], observation[:, 1], s=8, alpha=0.35, label="observation")
        if len(truth):
            axis.plot(*np.vstack((truth, truth[0])).T, color="black", linewidth=1.3, label="independent truth")
        if len(estimate):
            axis.plot(*np.vstack((estimate, estimate[0])).T, color="tab:red", linewidth=1.2, label="estimate")
        axis.set_title(f"{fixture['fixture']}\n{fixture['status']}")
        axis.set_aspect("equal")
        axis.legend(loc="best")
    for axis in axes.ravel()[len(actual) :]:
        axis.axis("off")
    figure.tight_layout()
    figure.savefig(output / "failure_gallery.png", dpi=150)
    plt.close(figure)
    serializable = [
        {"fixture": fixture["fixture"], "status": fixture["status"], "reason": fixture["reason"], "selection_role": "actual_failure"}
        for fixture in actual
    ]
    _write_json(output / "failure_gallery.json", serializable)
    return serializable


def _write_report(
    output: Path,
    config: G6EvaluationConfig,
    aggregate: dict[str, Any],
    snapshot: dict[str, Any],
    gate: dict[str, Any],
) -> None:
    lines = [
        "# ABCG-v2 Step 1 G6 formal compliance report",
        "",
        f"- Primary matrix: {len(config.scenarios)} scenarios × {len(config.methods)} methods × {len(config.seeds)} paired seeds",
        f"- Bootstrap boundary samples: {config.bootstrap_samples}",
        "- Initial layouts: balanced perimeter, one-sided, opposed sides",
        f"- Freeze status: `{snapshot['freeze_status']}`",
        f"- Overall status: `{gate['overall_status']}`",
        f"- G6 status: `{gate['g6_status']}`",
        f"- Evaluated commit: `{gate['evaluated_commit']}`",
        "",
        "## Primary closed-loop outcomes",
        "",
        "| Scenario | Method | Success/total | Failure rate | Arc gap mean | Coverage mean | Runtime P95 ms |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for scenario in config.scenarios:
        for method in config.methods:
            values = aggregate[scenario][method]
            metrics = values["metrics"]
            lines.append(
                f"| {scenario} | {method} | {values['success_count']}/{values['run_count']} | "
                f"{values['failure_rate']:.3f} | {metrics['plan_max_arc_gap_m']['mean']} | "
                f"{metrics['coverage_ratio']['mean']} | {metrics['total_runtime_ms']['p95']} |"
            )
    lines.extend(
        [
            "",
            "## Evidence boundary",
            "",
            "Analytic truth is used only by the evaluator. Each method receives the same paired observation and initial guide state.",
            "Invalid boundary, capacity, assignment, safety, degraded, and timeout states remain in the denominator.",
            "The report is synthetic Step 1 evidence; it does not claim human-crowd interaction or decentralized Step 2/3 performance.",
            (
                "The evaluator recorded a clean frozen commit."
                if snapshot["frozen_commit"]
                else "The evaluator recorded a dirty checkout, so frozen-commit compliance remains unmet."
            ),
        ]
    )
    (output / "G6_COMPLIANCE_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
