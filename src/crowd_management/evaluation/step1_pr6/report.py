"""PR6 report and failure-gallery writers."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import numpy as np

from ...types import Array
from .config import PR6EvaluationConfig


def _save_failure_gallery(
    output: Path,
    records: list[dict[str, Any]],
    visuals: dict[tuple[str, int, str], tuple[Array, Array, Array | None]],
) -> list[dict[str, Any]]:
    selected = [record for record in records if not record["valid"]]
    selected.sort(key=lambda record: (str(record["shape"]), int(record["seed"]), str(record["variant"])))
    if len(selected) < 6:
        valid_worst = [record for record in records if record["valid"]]
        valid_worst.sort(key=lambda record: float(record["curve_hausdorff"]), reverse=True)
        selected.extend(valid_worst[: 6 - len(selected)])
    selected = selected[:6]

    gallery_records: list[dict[str, Any]] = []
    for record in selected:
        gallery_records.append(
            {
                "shape": record["shape"],
                "seed": record["seed"],
                "variant": record["variant"],
                "selection_role": "failure" if not record["valid"] else "worst_valid_case",
                "boundary_status": record["boundary_status"],
                "boundary_reason": record["boundary_reason"],
                "curve_hausdorff": record["curve_hausdorff"],
            }
        )

    os.environ.setdefault("MPLCONFIGDIR", str((output / ".mplconfig").resolve()))
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(2, 3, figsize=(13, 8))
    for axis, record in zip(axes.ravel(), selected, strict=False):
        observation, truth, estimate = visuals[(record["shape"], record["seed"], record["variant"])]
        axis.scatter(observation[:, 0], observation[:, 1], s=5, alpha=0.25, label="observation")
        axis.plot(*np.vstack((truth, truth[0])).T, color="black", linewidth=1.5, label="truth")
        if estimate is not None:
            axis.plot(*np.vstack((estimate, estimate[0])).T, color="tab:red", linewidth=1.2, label="estimate")
        axis.set_title(
            f"{record['shape']} seed={record['seed']}\n{record['variant']} {record['boundary_status']}"
        )
        axis.set_aspect("equal")
    for axis in axes.ravel()[len(selected) :]:
        axis.axis("off")
    handles, labels = axes.ravel()[0].get_legend_handles_labels()
    figure.legend(handles, labels, loc="lower center", ncol=3)
    figure.tight_layout(rect=(0.0, 0.05, 1.0, 1.0))
    figure.savefig(output / "failure_gallery.png", dpi=150)
    plt.close(figure)
    return gallery_records


def _write_markdown_report(
    output: Path,
    config: PR6EvaluationConfig,
    aggregate: dict[str, Any],
    paired: dict[str, Any],
    snapshot: dict[str, Any],
    gallery: list[dict[str, Any]],
) -> None:
    lines = [
        "# ABCG-v2 Step 1 PR6 Paired Robust Evaluation",
        "",
        f"- Paired seeds: {len(config.seeds)} (`{min(config.seeds)}` through `{max(config.seeds)}`)",
        f"- Held-out shapes: {', '.join(config.shapes)}",
        f"- Variants: radial neutral, alpha neutral, alpha bootstrap gain, alpha bootstrap gain ablated",
        f"- Repository freeze status: `{snapshot['freeze_status']}`",
        f"- Source SHA-256: `{snapshot['source_sha256']}`",
        "",
        "## Aggregate boundary error",
        "",
        "| Shape | Variant | Valid/total | Chamfer mean [95% CI] | Hausdorff mean [95% CI] |",
        "| --- | --- | --- | --- | --- |",
    ]
    for shape in config.shapes:
        for variant, values in aggregate[shape].items():
            chamfer = values["curve_chamfer"]
            hausdorff = values["curve_hausdorff"]
            lines.append(
                f"| {shape} | {variant} | {values['valid_count']}/{values['run_count']} | "
                f"{chamfer['mean']} [{chamfer['ci95_low']}, {chamfer['ci95_high']}] | "
                f"{hausdorff['mean']} [{hausdorff['ci95_low']}, {hausdorff['ci95_high']}] |"
            )
    lines.extend(
        [
            "",
            "## Evidence boundary",
            "",
            "Results are paired synthetic boundary-reconstruction evidence. They do not prove continuous-time safety,",
            "human containment efficacy, or performance on real sensor data. Invalid runs remain in the denominator.",
            "Confidence gates Lloyd step size only; it is not treated as risk density.",
            "The radial geometry baseline uses a relaxed 0.60 observation-coverage validity threshold versus 0.80",
            "for alpha variants so its non-star reconstruction error remains measurable; failure rates are not compared",
            "as though those thresholds were identical.",
            "",
            f"Failure gallery entries: {len(gallery)}.",
            "",
            "The complete paired differences and bootstrap confidence intervals are in `paired_comparisons.json`.",
            "G6 cannot be called fully frozen while the repository snapshot reports `UNFROZEN_DIRTY_WORKTREE`.",
        ]
    )
    (output / "PR6_EVALUATION_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
