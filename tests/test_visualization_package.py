import csv
import json
import os
import subprocess
import sys
from pathlib import Path


def test_visualization_package_cli_generates_lightweight_outputs(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    output = tmp_path / "viz_package"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo / "src")
    env["MPLCONFIGDIR"] = str(tmp_path / "mplconfig")

    result = subprocess.run(
        [
            sys.executable,
            str(repo / "scripts" / "run_visualization_package.py"),
            "--config",
            str(repo / "configs" / "simple_room.yaml"),
            "--modes",
            "baseline",
            "dbact",
            "--steps",
            "5",
            "--seed",
            "0",
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
    assert (output / "baseline" / "metrics.json").is_file()
    assert (output / "dbact" / "replay.npz").is_file()
    assert (output / "summary" / "metrics_summary.csv").is_file()
    assert (output / "summary" / "metrics_summary.json").is_file()
    assert (output / "summary" / "VISUALIZATION_PACKAGE_REPORT.md").is_file()
    assert (output / "comparison" / "final_metrics_bar.png").is_file()
    assert (output / "comparison" / "four_modes_dashboard.png").is_file()

    with open(output / "summary" / "metrics_summary.csv", "r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert [row["mode"] for row in rows] == ["baseline", "dbact"]
    assert "final_evacuation_rate" in rows[0]

    with open(output / "summary" / "metrics_summary.json", "r", encoding="utf-8") as f:
        summary = json.load(f)
    assert summary["modes"] == ["baseline", "dbact"]
