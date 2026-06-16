from pathlib import Path

from crowd_management.crowd_model import CrowdEnvironment, run_simulation
from crowd_management.metrics import summary_metrics, time_series_metrics
from crowd_management.types import SimulationConfig


def _small_config():
    cfg = SimulationConfig.from_yaml(Path(__file__).resolve().parents[1] / "configs" / "simple_room.yaml")
    return cfg


def test_baseline_simulation_runs_short():
    cfg = _small_config()
    history = run_simulation(cfg, guided=False, steps=5)
    data = history.as_arrays()
    assert data["positions"].shape[0] == 6  # includes initial frame
    assert data["positions"].shape[1] == cfg.pedestrians.count
    metrics = summary_metrics(history, cfg.metrics)
    assert metrics["total_pedestrians"] == cfg.pedestrians.count


def test_guided_simulation_records_guiders():
    cfg = _small_config()
    env = CrowdEnvironment(cfg, guided=True)
    history = env.run(steps=5)
    data = history.as_arrays()
    assert "guider_positions" in data
    assert data["guider_positions"].shape[1] == cfg.guiders.count
    series = time_series_metrics(history, cfg.metrics)
    assert "evacuation_rate" in series
