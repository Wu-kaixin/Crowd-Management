import csv
import json
import os
import subprocess
import sys
from pathlib import Path


def test_multi_seed_eval_cli_generates_summary_and_aggregate(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    output = tmp_path / "multi_seed"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo / "src")

    result = subprocess.run(
        [
            sys.executable,
            str(repo / "scripts" / "run_multi_seed_eval.py"),
            "--config",
            str(repo / "configs" / "simple_room.yaml"),
            "--modes",
            "baseline",
            "static",
            "--seeds",
            "0",
            "1",
            "--steps",
            "5",
            "--output",
            str(output),
        ],
        cwd=repo,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert (output / "baseline_seed_0" / "metrics.json").is_file()
    assert (output / "static_seed_1" / "metrics.json").is_file()
    assert (output / "summary.csv").is_file()
    assert (output / "aggregate_metrics.csv").is_file()
    assert (output / "summary.json").is_file()
    assert (output / "aggregate_metrics.json").is_file()
    assert (output / "evacuation_rate_mean_std.png").is_file()

    with open(output / "summary.csv", "r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 4
    assert {"mode", "seed", "final_evacuation_rate", "final_evacuated_count"}.issubset(rows[0])

    with open(output / "aggregate_metrics.csv", "r", encoding="utf-8", newline="") as f:
        aggregate_rows = list(csv.DictReader(f))
    assert len(aggregate_rows) == 2
    assert "final_evacuation_rate_mean" in aggregate_rows[0]
    assert "final_evacuation_rate_std" in aggregate_rows[0]

    with open(output / "aggregate_metrics.json", "r", encoding="utf-8") as f:
        aggregate = json.load(f)
    assert "mean" in aggregate["baseline"]["final_evacuation_rate"]
    assert "std" in aggregate["baseline"]["final_evacuation_rate"]
