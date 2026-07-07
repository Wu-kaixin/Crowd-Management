import csv
import json
import os
import subprocess
import sys
from pathlib import Path


def test_stage4_density_eval_smoke_outputs(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    output = tmp_path / "stage4"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo / "src")
    env["MPLCONFIGDIR"] = str(tmp_path / "mplconfig")

    result = subprocess.run(
        [
            sys.executable,
            str(repo / "scripts" / "run_stage4_density_eval.py"),
            "--config",
            str(repo / "legacy" / "evacuation_guidance" / "configs" / "two_exit_bottleneck.yaml"),
            "--modes",
            "baseline",
            "density_dbact",
            "nearest_exit",
            "balanced_exit_static",
            "--seeds",
            "0",
            "1",
            "--steps",
            "6",
            "--output",
            str(output),
            "--skip-video",
            "--skip-heavy-plots",
        ],
        cwd=repo,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert (output / "summary" / "run_metrics.csv").is_file()
    assert (output / "summary" / "run_metrics.json").is_file()
    assert (output / "summary" / "aggregate_metrics.csv").is_file()
    assert (output / "summary" / "aggregate_metrics.json").is_file()
    assert (output / "summary" / "composite_scores.csv").is_file()
    assert (output / "summary" / "STAGE4_DENSITY_EVAL_REPORT.md").is_file()
    assert (output / "summary" / "TEAMS_CHANNEL_REPORT.md").is_file()
    assert (output / "comparison" / "robust_metrics_dashboard.png").is_file()
    assert (output / "comparison" / "composite_score_mean_std.png").is_file()

    with open(output / "summary" / "aggregate_metrics.csv", "r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert {row["mode"] for row in rows} == {"baseline", "density_dbact", "nearest_exit", "balanced_exit_static"}
    for key in ["final_evacuation_rate_mean", "congestion_index_mean", "cumulative_congestion_mean", "exit_imbalance_mean"]:
        assert key in rows[0]

    with open(output / "summary" / "run_metrics.json", "r", encoding="utf-8") as f:
        summary = json.load(f)
    assert summary["seeds"] == [0, 1]
