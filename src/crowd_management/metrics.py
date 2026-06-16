"""Metrics for baseline-vs-guided crowd-management experiments."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

from .types import MetricsConfig, SimulationHistory


def evacuation_rate(history: SimulationHistory) -> np.ndarray:
    data = history.as_arrays()
    evacuated = data["evacuated"]
    if evacuated.size == 0:
        return np.zeros(0, dtype=float)
    return evacuated.mean(axis=1)


def mean_active_speed(history: SimulationHistory) -> np.ndarray:
    data = history.as_arrays()
    speeds = np.linalg.norm(data["velocities"], axis=2)
    active = ~data["evacuated"]
    out = np.zeros(len(speeds), dtype=float)
    for k in range(len(speeds)):
        if np.any(active[k]):
            out[k] = float(speeds[k][active[k]].mean())
    return out


def near_collision_count(positions: np.ndarray, evacuated: np.ndarray, threshold: float) -> int:
    active_positions = positions[~evacuated]
    count = 0
    for i in range(len(active_positions)):
        delta = active_positions[i + 1 :] - active_positions[i]
        if len(delta) == 0:
            continue
        dist = np.linalg.norm(delta, axis=1)
        count += int(np.sum(dist < threshold))
    return count


def congestion_index(positions: np.ndarray, evacuated: np.ndarray, radius: float) -> float:
    """Average local neighbor count within a given radius for active pedestrians."""
    active_positions = positions[~evacuated]
    n = len(active_positions)
    if n <= 1:
        return 0.0
    counts = []
    for i in range(n):
        dist = np.linalg.norm(active_positions - active_positions[i], axis=1)
        counts.append(int(np.sum((dist < radius) & (dist > 1e-9))))
    return float(np.mean(counts))


def time_series_metrics(history: SimulationHistory, config: MetricsConfig) -> dict[str, np.ndarray]:
    data = history.as_arrays()
    positions = data["positions"]
    evacuated = data["evacuated"]
    congestion = np.asarray(
        [congestion_index(positions[k], evacuated[k], config.congestion_radius) for k in range(len(positions))],
        dtype=float,
    )
    near = np.asarray(
        [near_collision_count(positions[k], evacuated[k], config.near_collision_distance) for k in range(len(positions))],
        dtype=float,
    )
    return {
        "time": data["times"],
        "evacuation_rate": evacuation_rate(history),
        "mean_active_speed": mean_active_speed(history),
        "congestion_index": congestion,
        "near_collision_count": near,
    }


def summary_metrics(history: SimulationHistory, config: MetricsConfig) -> dict[str, float | int | None]:
    series = time_series_metrics(history, config)
    evac_rate = series["evacuation_rate"]
    times = series["time"]
    evacuated = history.as_arrays()["evacuated"]
    final_mask = evacuated[-1]
    full_evac_time = None
    if len(evac_rate) and evac_rate[-1] >= 1.0:
        full_evac_time = float(times[np.argmax(evac_rate >= 1.0)])
    return {
        "final_time": float(times[-1]) if len(times) else 0.0,
        "final_evacuated": int(final_mask.sum()) if len(final_mask) else 0,
        "total_pedestrians": int(len(final_mask)) if len(final_mask) else 0,
        "final_evacuation_rate": float(evac_rate[-1]) if len(evac_rate) else 0.0,
        "full_evacuation_time": full_evac_time,
        "mean_active_speed_over_time": float(np.mean(series["mean_active_speed"])) if len(times) else 0.0,
        "peak_congestion_index": float(np.max(series["congestion_index"])) if len(times) else 0.0,
        "mean_congestion_index": float(np.mean(series["congestion_index"])) if len(times) else 0.0,
        "peak_near_collision_count": int(np.max(series["near_collision_count"])) if len(times) else 0,
    }


def save_metrics(history: SimulationHistory, config: MetricsConfig, output_dir: str | Path) -> dict[str, float | int | None]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    series = time_series_metrics(history, config)
    summary = summary_metrics(history, config)

    with open(output / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    with open(output / "timeseries.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        keys = list(series.keys())
        writer.writerow(keys)
        for row in zip(*(series[k] for k in keys)):
            writer.writerow([float(v) for v in row])
    return summary


def load_timeseries(path: str | Path) -> dict[str, np.ndarray]:
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    if not rows:
        return {}
    keys = rows[0].keys()
    return {key: np.asarray([float(row[key]) for row in rows], dtype=float) for key in keys}
