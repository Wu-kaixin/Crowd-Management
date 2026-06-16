from pathlib import Path
import os
import subprocess
import sys

import numpy as np
import pytest

from crowd_management.crowd_model import CrowdEnvironment, run_simulation
from crowd_management.dbact_transfer import DBACTTransferController
from crowd_management.guider_model import initialize_guiders
from crowd_management.metrics import save_metrics, summary_metrics, time_series_metrics
from crowd_management.types import SimulationConfig, as_vec2, limit_norm, unit


def _config() -> SimulationConfig:
    return SimulationConfig.from_yaml(Path(__file__).resolve().parents[1] / "configs" / "simple_room.yaml")


def test_config_loads_and_vector_helpers():
    cfg = _config()
    assert cfg.pedestrians.count == 160
    assert cfg.guiders.count == 5
    assert cfg.room.width == 20.0
    assert np.allclose(unit(np.array([3.0, 4.0])), np.array([0.6, 0.8]))
    assert np.linalg.norm(limit_norm(np.array([3.0, 4.0]), 2.0)) <= 2.0 + 1e-9
    with pytest.raises(ValueError):
        as_vec2([1.0, 2.0, 3.0])


def test_baseline_simulation_runs_without_nan():
    cfg = _config()
    history = run_simulation(cfg, guided=False, steps=8)
    data = history.as_arrays()
    assert data["positions"].shape[0] == 9
    assert data["positions"].shape[1] == cfg.pedestrians.count
    assert np.isfinite(data["positions"]).all()


def test_dbact_transfer_generates_guider_targets():
    cfg = _config()
    controller = DBACTTransferController(cfg.room, cfg.guiders)
    positions = np.array([[3.0, 5.0], [4.0, 6.0], [3.5, 7.0]])
    evacuated = np.array([False, False, False])
    estimate = controller.estimate_crowd_state(positions, evacuated)
    targets, directions = controller.compute_guider_target_positions(estimate, cfg.guiders.count)
    assert targets.shape == (cfg.guiders.count, 2)
    assert directions.shape == (cfg.guiders.count, 2)
    assert np.all(np.isfinite(targets))
    assert np.all(np.linalg.norm(directions, axis=1) > 0.99)


def test_update_guiders_assigns_distinct_targets():
    cfg = _config()
    guiders = initialize_guiders(cfg.guiders, cfg.room)
    controller = DBACTTransferController(cfg.room, cfg.guiders)
    positions = np.array([[3.0, 5.0], [4.0, 6.0], [3.5, 7.0]])
    evacuated = np.array([False, False, False])
    controller.update_guiders(guiders, positions, evacuated)
    assert len(guiders) == cfg.guiders.count
    assert not np.allclose(guiders[0].target_position, guiders[-1].target_position)


def test_guided_simulation_runs_and_records_guiders():
    cfg = _config()
    env = CrowdEnvironment(cfg, guided=True)
    history = env.run(steps=8)
    data = history.as_arrays()
    assert "guider_positions" in data
    assert data["guider_positions"].shape[1] == cfg.guiders.count
    assert np.isfinite(data["positions"]).all()


def test_metrics_include_required_fields_and_save_outputs(tmp_path):
    cfg = _config()
    history = run_simulation(cfg, guided=True, steps=8)
    metrics = summary_metrics(history, cfg.metrics)
    for key in ["evacuation_rate", "final_evacuated", "mean_speed", "congestion_index", "near_collision_count", "mean_path_length"]:
        assert key in metrics
    series = time_series_metrics(history, cfg.metrics)
    assert "evacuation_rate" in series
    save_metrics(history, cfg.metrics, tmp_path)
    assert (tmp_path / "metrics.json").is_file()
    assert (tmp_path / "timeseries.csv").is_file()
    assert (tmp_path / "trajectories.npz").is_file()


@pytest.mark.parametrize("mode", ["dbact", "static", "random"])
def test_guided_modes_run_from_cli(mode, tmp_path):
    repo = Path(__file__).resolve().parents[1]
    output = tmp_path / mode
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo / "src")
    result = subprocess.run(
        [
            sys.executable,
            str(repo / "scripts" / "run_guided.py"),
            "--config",
            str(repo / "configs" / "simple_room.yaml"),
            "--output",
            str(output),
            "--steps",
            "4",
            "--mode",
            mode,
        ],
        cwd=repo,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert (output / "metrics.json").is_file()
    assert (output / "final_snapshot.png").is_file()
    assert (output / "trajectories.npz").is_file()


def test_multi_run_comparison_outputs(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    cfg = _config()
    run_specs = {
        "baseline": {"guided": False, "guidance_mode": "dbact"},
        "static": {"guided": True, "guidance_mode": "static"},
        "random": {"guided": True, "guidance_mode": "random"},
        "dbact": {"guided": True, "guidance_mode": "dbact"},
    }
    run_dirs = []
    labels = []
    for label, kwargs in run_specs.items():
        out = tmp_path / label
        history = run_simulation(cfg, steps=4, **kwargs)
        save_metrics(history, cfg.metrics, out)
        run_dirs.append(str(out))
        labels.append(label)

    output = tmp_path / "comparison"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo / "src")
    result = subprocess.run(
        [
            sys.executable,
            str(repo / "scripts" / "compare_results.py"),
            "--runs",
            *run_dirs,
            "--labels",
            *labels,
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
    assert (output / "summary.json").is_file()
    assert (output / "metrics_comparison.csv").is_file()
    assert (output / "evacuation_rate_comparison.png").is_file()
    assert (output / "final_metrics_comparison.png").is_file()


def test_two_exits_config_loads_as_prepared_scenario():
    cfg = SimulationConfig.from_yaml(Path(__file__).resolve().parents[1] / "configs" / "two_exits.yaml")
    assert cfg.pedestrians.count == 220
    assert cfg.guiders.count == 6
    assert cfg.room.exit_center_y == 9.0
