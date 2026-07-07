import csv
import json
import os
import subprocess
import sys
from pathlib import Path

from crowd_management.crowd_model import run_simulation
from crowd_management.types import SimulationConfig


def test_two_exit_bottleneck_config_loads_with_multiple_exits():
    cfg = SimulationConfig.from_yaml(Path(__file__).resolve().parents[1] / "legacy" / "evacuation_guidance" / "configs" / "two_exit_bottleneck.yaml")
    assert cfg.room.width == 24.0
    assert len(cfg.room.all_exits) >= 2
    assert cfg.room.all_exits[0].id == "main_exit"
    assert cfg.room.all_exits[1].id == "alternate_exit"


def test_density_dbact_runs_short_multi_exit_simulation():
    cfg = SimulationConfig.from_yaml(Path(__file__).resolve().parents[1] / "legacy" / "evacuation_guidance" / "configs" / "two_exit_bottleneck.yaml")
    history = run_simulation(cfg, guided=True, steps=6, guidance_mode="density_dbact")
    data = history.as_arrays()
    assert data["positions"].shape[0] == 7
    assert "target_exit_ids" in data
    assert data["target_exit_ids"].shape[1] == cfg.pedestrians.count
    assert data["target_exit_ids"].max() >= 1


def test_density_dbact_experiment_cli_generates_lightweight_outputs(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    output = tmp_path / "density_dbact"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo / "src")
    env["MPLCONFIGDIR"] = str(tmp_path / "mplconfig")

    result = subprocess.run(
        [
            sys.executable,
            str(repo / "scripts" / "run_density_dbact_experiment.py"),
            "--config",
            str(repo / "legacy" / "evacuation_guidance" / "configs" / "two_exit_bottleneck.yaml"),
            "--modes",
            "baseline",
            "density_dbact",
            "--steps",
            "6",
            "--seed",
            "0",
            "--output",
            str(output),
            "--skip-video",
            "--fast-test",
        ],
        cwd=repo,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert (output / "summary" / "metrics_summary.csv").is_file()
    assert (output / "summary" / "metrics_summary.json").is_file()
    assert (output / "comparison" / "final_metrics_bar.png").is_file()
    assert (output / "comparison" / "exit_usage_curve.png").is_file()

    with open(output / "summary" / "metrics_summary.csv", "r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert [row["mode"] for row in rows] == ["baseline", "density_dbact"]
    assert "exit_1_usage_count" in rows[0]

    with open(output / "summary" / "metrics_summary.json", "r", encoding="utf-8") as f:
        summary = json.load(f)
    assert summary["modes"] == ["baseline", "density_dbact"]
