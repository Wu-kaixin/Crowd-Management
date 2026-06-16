"""Replay serialization for offline crowd visualization."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .types import MetricsConfig, RoomConfig, SimulationConfig, SimulationHistory


@dataclass(frozen=True)
class ReplayData:
    times: np.ndarray
    pedestrian_positions: np.ndarray
    pedestrian_velocities: np.ndarray
    pedestrian_evacuated: np.ndarray
    guider_positions: np.ndarray
    guider_targets: np.ndarray
    room: RoomConfig
    metrics: MetricsConfig
    mode: str
    scenario: str


def _room_to_array(room: RoomConfig) -> np.ndarray:
    return np.asarray([room.width, room.height, room.exit_center_y, room.exit_width, room.exit_depth], dtype=float)


def _room_from_array(values: np.ndarray) -> RoomConfig:
    return RoomConfig(
        width=float(values[0]),
        height=float(values[1]),
        exit_center_y=float(values[2]),
        exit_width=float(values[3]),
        exit_depth=float(values[4]),
    )


def _metrics_to_array(metrics: MetricsConfig) -> np.ndarray:
    return np.asarray([metrics.congestion_radius, metrics.near_collision_distance], dtype=float)


def _metrics_from_array(values: np.ndarray) -> MetricsConfig:
    return MetricsConfig(congestion_radius=float(values[0]), near_collision_distance=float(values[1]))


def save_replay(
    history: SimulationHistory,
    config: SimulationConfig,
    output_dir: str | Path,
    mode: str,
    scenario: str = "simple_room",
) -> Path:
    """Save a compact replay.npz that can be rendered without re-running simulation."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    arrays = history.as_arrays()
    times = arrays["times"]
    ped_positions = arrays["positions"]
    ped_velocities = arrays["velocities"]
    ped_evacuated = arrays["evacuated"]
    if "guider_positions" in arrays:
        guider_positions = arrays["guider_positions"]
    else:
        guider_positions = np.zeros((len(times), 0, 2), dtype=float)
    if "guider_targets" in arrays:
        guider_targets = arrays["guider_targets"]
    else:
        guider_targets = np.zeros((len(times), 0, 2), dtype=float)

    path = output / "replay.npz"
    np.savez_compressed(
        path,
        times=times,
        pedestrian_positions=ped_positions,
        pedestrian_velocities=ped_velocities,
        pedestrian_evacuated=ped_evacuated,
        guider_positions=guider_positions,
        guider_targets=guider_targets,
        room=_room_to_array(config.room),
        metrics=_metrics_to_array(config.metrics),
        mode=np.asarray(mode),
        scenario=np.asarray(scenario),
    )
    return path


def load_replay(path_or_run_dir: str | Path) -> ReplayData:
    path = Path(path_or_run_dir)
    if path.is_dir():
        path = path / "replay.npz"
    with np.load(path, allow_pickle=False) as raw:
        room = _room_from_array(raw["room"])
        metrics = _metrics_from_array(raw["metrics"])
        mode = str(raw["mode"].item()) if raw["mode"].shape == () else str(raw["mode"])
        scenario = str(raw["scenario"].item()) if raw["scenario"].shape == () else str(raw["scenario"])
        return ReplayData(
            times=np.asarray(raw["times"], dtype=float),
            pedestrian_positions=np.asarray(raw["pedestrian_positions"], dtype=float),
            pedestrian_velocities=np.asarray(raw["pedestrian_velocities"], dtype=float),
            pedestrian_evacuated=np.asarray(raw["pedestrian_evacuated"], dtype=bool),
            guider_positions=np.asarray(raw["guider_positions"], dtype=float),
            guider_targets=np.asarray(raw["guider_targets"], dtype=float),
            room=room,
            metrics=metrics,
            mode=mode,
            scenario=scenario,
        )
