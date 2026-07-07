"""Metrics for baseline-vs-guided crowd-management experiments."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

from ...types import MetricsConfig, SimulationHistory


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
    series = {
        "time": data["times"],
        "evacuation_rate": evacuation_rate(history),
        "mean_active_speed": mean_active_speed(history),
        "congestion_index": congestion,
        "near_collision_count": near,
    }
    if "evacuation_exit_ids" in data:
        exit_ids = data["evacuation_exit_ids"]
        known = exit_ids[exit_ids >= 0]
        exit_count = int(known.max()) + 1 if known.size else int(max(1, exit_ids.max(initial=-1) + 1))
        usage = np.zeros((len(exit_ids), exit_count), dtype=float)
        for k in range(len(exit_ids)):
            for exit_idx in range(exit_count):
                usage[k, exit_idx] = float(np.sum(exit_ids[k] == exit_idx))
        for exit_idx in range(exit_count):
            series[f"exit_{exit_idx}_usage_count"] = usage[:, exit_idx]
        total = np.maximum(usage.sum(axis=1), 1.0)
        if exit_count > 1:
            ratios = usage / total[:, None]
            series["exit_imbalance"] = ratios.max(axis=1) - ratios.min(axis=1)
    return series


def path_length_metrics(history: SimulationHistory) -> tuple[float, float]:
    data = history.as_arrays()
    positions = data["positions"]
    if len(positions) <= 1:
        return 0.0, 0.0
    step_lengths = np.linalg.norm(np.diff(positions, axis=0), axis=2)
    per_pedestrian = step_lengths.sum(axis=0)
    total_path_length = float(per_pedestrian.sum())
    mean_path_length = float(per_pedestrian.mean()) if len(per_pedestrian) else 0.0
    return mean_path_length, total_path_length


def summary_metrics(history: SimulationHistory, config: MetricsConfig) -> dict[str, float | int | None]:
    series = time_series_metrics(history, config)
    evac_rate = series["evacuation_rate"]
    times = series["time"]
    evacuated = history.as_arrays()["evacuated"]
    final_mask = evacuated[-1]
    full_evac_time = None
    if len(evac_rate) and evac_rate[-1] >= 1.0:
        full_evac_time = float(times[np.argmax(evac_rate >= 1.0)])
    mean_path_length, total_path_length = path_length_metrics(history)
    final_rate = float(evac_rate[-1]) if len(evac_rate) else 0.0
    mean_speed = float(np.mean(series["mean_active_speed"])) if len(times) else 0.0
    mean_congestion = float(np.mean(series["congestion_index"])) if len(times) else 0.0
    peak_near = int(np.max(series["near_collision_count"])) if len(times) else 0
    summary = {
        "final_time": float(times[-1]) if len(times) else 0.0,
        "final_evacuated": int(final_mask.sum()) if len(final_mask) else 0,
        "total_pedestrians": int(len(final_mask)) if len(final_mask) else 0,
        "evacuation_rate": final_rate,
        "final_evacuation_rate": final_rate,
        "full_evacuation_time": full_evac_time,
        "mean_speed": mean_speed,
        "mean_active_speed_over_time": mean_speed,
        "congestion_index": mean_congestion,
        "peak_congestion_index": float(np.max(series["congestion_index"])) if len(times) else 0.0,
        "mean_congestion_index": mean_congestion,
        "near_collision_count": peak_near,
        "peak_near_collision_count": peak_near,
        "mean_path_length": mean_path_length,
        "total_path_length": total_path_length,
    }
    if "evacuation_exit_ids" in history.as_arrays():
        exit_ids = history.as_arrays()["evacuation_exit_ids"][-1]
        known = exit_ids[exit_ids >= 0]
        exit_count = int(max(2, known.max() + 1 if known.size else 0))
        usage_counts = {f"exit_{idx}": int(np.sum(exit_ids == idx)) for idx in range(exit_count)}
        total_evacuated = max(1, int(np.sum(exit_ids >= 0)))
        usage_ratios = {key: value / total_evacuated for key, value in usage_counts.items()}
        summary["exit_usage_count"] = usage_counts
        summary["exit_usage_ratio"] = usage_ratios
        if usage_ratios:
            summary["exit_imbalance"] = float(max(usage_ratios.values()) - min(usage_ratios.values()))
    if len(times) and len(series["congestion_index"]):
        dt = float(np.median(np.diff(times))) if len(times) > 1 else 0.0
        summary["cumulative_congestion"] = float(np.sum(series["congestion_index"]) * dt)
    return summary


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

    arrays = history.as_arrays()
    np.savez_compressed(output / "trajectories.npz", **arrays)
    return summary


def load_timeseries(path: str | Path) -> dict[str, np.ndarray]:
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    if not rows:
        return {}
    keys = rows[0].keys()
    return {key: np.asarray([float(row[key]) for row in rows], dtype=float) for key in keys}
