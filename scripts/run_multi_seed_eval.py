#!/usr/bin/env python
"""Run multi-seed guidance evaluation for baseline/static/random/dbact modes."""
from __future__ import annotations

import argparse
import csv
import json
from dataclasses import replace
from pathlib import Path
from statistics import mean, stdev
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from crowd_management.crowd_model import run_simulation
from crowd_management.metrics import save_metrics
from crowd_management.replay import save_replay
from crowd_management.types import SimulationConfig
from crowd_management.visualization import save_density_heatmap, save_snapshot, save_timeseries_plot

MODES = ("baseline", "static", "random", "dbact")
SUMMARY_METRICS = [
    "final_evacuation_rate",
    "final_evacuated_count",
    "mean_speed",
    "congestion_index",
    "peak_near_collision_count",
    "final_time",
    "full_evacuation_time",
]
PLOT_SPECS = [
    ("final_evacuation_rate", "Evacuation rate", "evacuation_rate_mean_std.png"),
    ("congestion_index", "Congestion index", "congestion_index_mean_std.png"),
    ("mean_speed", "Mean speed", "mean_speed_mean_std.png"),
    ("peak_near_collision_count", "Peak near-collision count", "near_collision_mean_std.png"),
]
MODE_TITLES = {
    "baseline": "Baseline: no guidance",
    "static": "Guided baseline: static guiders",
    "random": "Guided baseline: random moving guiders",
    "dbact": "Guided: transferred DBACT-style control",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run multi-seed guidance evaluation.")
    parser.add_argument("--config", default="configs/simple_room.yaml")
    parser.add_argument("--modes", nargs="+", choices=MODES, default=list(MODES))
    parser.add_argument("--seeds", nargs="+", type=int, default=list(range(10)))
    parser.add_argument("--steps", type=int, default=400)
    parser.add_argument("--output", default="runs/multi_seed_eval_v1")
    return parser.parse_args()


def _json_default(value: Any) -> Any:
    if hasattr(value, "item"):
        return value.item()
    return value


def _write_json(path: Path, data: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=_json_default)


def _metric_value(metrics: dict[str, Any], key: str) -> float | int | None:
    if key == "final_evacuated_count":
        return metrics.get("final_evacuated")
    return metrics.get(key)


def _run_one(
    config_path: Path,
    base_config: SimulationConfig,
    mode: str,
    seed: int,
    steps: int,
    output: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    run_dir = output / f"{mode}_seed_{seed}"
    run_dir.mkdir(parents=True, exist_ok=True)

    cfg = replace(base_config, seed=seed)
    guided = mode != "baseline"
    guidance_mode = "dbact" if mode == "baseline" else mode
    history = run_simulation(cfg, guided=guided, steps=steps, guidance_mode=guidance_mode)
    metrics = save_metrics(history, cfg.metrics, run_dir)
    save_replay(history, cfg, run_dir, mode=mode, scenario=config_path.stem)
    save_snapshot(history, cfg.room, run_dir / "final_snapshot.png", title=MODE_TITLES[mode])
    save_density_heatmap(history, cfg.room, run_dir / "density_heatmap.png")
    save_timeseries_plot(run_dir / "timeseries.csv", run_dir / "timeseries.png", title=f"{mode} seed {seed} time series")

    row = {
        "mode": mode,
        "seed": seed,
        "run_dir": str(run_dir),
    }
    for metric in SUMMARY_METRICS:
        row[metric] = _metric_value(metrics, metric)
    record = {
        "mode": mode,
        "seed": seed,
        "run_dir": str(run_dir),
        "metrics": metrics,
    }
    return row, record


def _write_summary_csv(rows: list[dict[str, Any]], output_path: Path) -> None:
    fieldnames = ["mode", "seed", "run_dir", *SUMMARY_METRICS]
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _aggregate(rows: list[dict[str, Any]], modes: list[str]) -> dict[str, dict[str, dict[str, float | int | None]]]:
    aggregate: dict[str, dict[str, dict[str, float | int | None]]] = {}
    for mode in modes:
        mode_rows = [row for row in rows if row["mode"] == mode]
        aggregate[mode] = {}
        for metric in SUMMARY_METRICS:
            values = [float(row[metric]) for row in mode_rows if row.get(metric) is not None]
            if not values:
                aggregate[mode][metric] = {"mean": None, "std": None, "min": None, "max": None, "count": 0}
                continue
            aggregate[mode][metric] = {
                "mean": mean(values),
                "std": stdev(values) if len(values) > 1 else 0.0,
                "min": min(values),
                "max": max(values),
                "count": len(values),
            }
    return aggregate


def _write_aggregate_csv(aggregate: dict[str, dict[str, dict[str, float | int | None]]], output_path: Path) -> None:
    fieldnames = ["mode"]
    for metric in SUMMARY_METRICS:
        fieldnames.extend([f"{metric}_mean", f"{metric}_std", f"{metric}_min", f"{metric}_max", f"{metric}_count"])
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for mode, metrics in aggregate.items():
            row: dict[str, Any] = {"mode": mode}
            for metric, stats in metrics.items():
                for stat_name, value in stats.items():
                    row[f"{metric}_{stat_name}"] = value
            writer.writerow(row)


def _save_mean_std_plot(
    aggregate: dict[str, dict[str, dict[str, float | int | None]]],
    modes: list[str],
    metric: str,
    ylabel: str,
    output_path: Path,
) -> None:
    means = [aggregate[mode][metric]["mean"] for mode in modes]
    stds = [aggregate[mode][metric]["std"] for mode in modes]
    numeric_means = [float(value) if value is not None else 0.0 for value in means]
    numeric_stds = [float(value) if value is not None else 0.0 for value in stds]

    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.bar(modes, numeric_means, yerr=numeric_stds, capsize=5, color=["#6f7f95", "#4f9d69", "#d08c36", "#4c78a8"])
    ax.set_xlabel("guidance mode")
    ax.set_ylabel(ylabel)
    ax.set_title(f"{ylabel}: mean +/- std across seeds")
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=160)
    plt.close(fig)


def run_multi_seed_eval(config: str | Path, modes: list[str], seeds: list[int], steps: int, output: str | Path) -> dict[str, Any]:
    config_path = Path(config)
    output_path = Path(output)
    output_path.mkdir(parents=True, exist_ok=True)
    base_config = SimulationConfig.from_yaml(config_path)

    rows: list[dict[str, Any]] = []
    run_records: list[dict[str, Any]] = []
    for mode in modes:
        for seed in seeds:
            row, record = _run_one(config_path, base_config, mode, seed, steps, output_path)
            rows.append(row)
            run_records.append(record)

    aggregate = _aggregate(rows, modes)
    summary = {
        "config": str(config_path),
        "modes": modes,
        "seeds": seeds,
        "steps": steps,
        "runs": run_records,
    }
    _write_summary_csv(rows, output_path / "summary.csv")
    _write_aggregate_csv(aggregate, output_path / "aggregate_metrics.csv")
    _write_json(output_path / "summary.json", summary)
    _write_json(output_path / "aggregate_metrics.json", aggregate)

    for metric, ylabel, filename in PLOT_SPECS:
        _save_mean_std_plot(aggregate, modes, metric, ylabel, output_path / filename)

    return {"summary": summary, "aggregate": aggregate}


def main() -> None:
    args = parse_args()
    result = run_multi_seed_eval(args.config, args.modes, args.seeds, args.steps, args.output)
    print(f"Saved multi-seed evaluation outputs to {args.output}")
    print(json.dumps(result["aggregate"], indent=2, default=_json_default))


if __name__ == "__main__":
    main()
