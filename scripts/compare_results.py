#!/usr/bin/env python
"""Compare two or more crowd-management experiment outputs."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from crowd_management.metrics import load_timeseries
from crowd_management.visualization import save_comparison_plot

FINAL_METRICS = [
    "final_evacuation_rate",
    "mean_speed",
    "congestion_index",
    "near_collision_count",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare crowd-management experiment runs.")
    parser.add_argument("--baseline", default="outputs/baseline", help="Baseline directory for legacy two-run comparison.")
    parser.add_argument("--guided", default="outputs/guided", help="Guided directory for legacy two-run comparison.")
    parser.add_argument("--runs", nargs="+", default=None, help="Run directories for multi-run comparison.")
    parser.add_argument("--labels", nargs="+", default=None, help="Labels matching --runs.")
    parser.add_argument("--output", default="outputs/comparison")
    return parser.parse_args()


def _load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _save_multi_evacuation_plot(run_dirs: list[Path], labels: list[str], output_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for run_dir, label in zip(run_dirs, labels):
        series = load_timeseries(run_dir / "timeseries.csv")
        if series:
            ax.plot(series["time"], series["evacuation_rate"], label=label)
    ax.set_xlabel("time [s]")
    ax.set_ylabel("evacuation rate")
    ax.set_ylim(0.0, 1.02)
    ax.set_title("Evacuation rate comparison")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=160)
    plt.close(fig)


def _save_final_metrics_plot(summaries: dict[str, dict], output_path: Path) -> None:
    labels = list(summaries.keys())
    fig, axes = plt.subplots(2, 2, figsize=(10, 7))
    axes = axes.ravel()
    for ax, metric in zip(axes, FINAL_METRICS):
        values = [float(summaries[label].get(metric, 0.0) or 0.0) for label in labels]
        ax.bar(labels, values)
        ax.set_title(metric)
        ax.tick_params(axis="x", rotation=20)
        ax.grid(True, axis="y", alpha=0.25)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=160)
    plt.close(fig)


def _write_metrics_csv(summaries: dict[str, dict], output_path: Path) -> None:
    keys = [
        "label",
        "final_evacuated",
        "total_pedestrians",
        "final_evacuation_rate",
        "full_evacuation_time",
        "mean_speed",
        "congestion_index",
        "near_collision_count",
        "mean_path_length",
        "total_path_length",
    ]
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        for label, summary in summaries.items():
            row = {key: summary.get(key) for key in keys if key != "label"}
            row["label"] = label
            writer.writerow(row)


def _legacy_comparison(baseline_dir: Path, guided_dir: Path, output: Path) -> dict:
    baseline_summary = _load_json(baseline_dir / "metrics.json")
    guided_summary = _load_json(guided_dir / "metrics.json")
    baseline_series = load_timeseries(baseline_dir / "timeseries.csv")
    guided_series = load_timeseries(guided_dir / "timeseries.csv")

    comparison = {
        "baseline": baseline_summary,
        "guided": guided_summary,
        "delta_final_evacuation_rate": guided_summary["final_evacuation_rate"] - baseline_summary["final_evacuation_rate"],
        "delta_peak_congestion_index": guided_summary["peak_congestion_index"] - baseline_summary["peak_congestion_index"],
        "delta_mean_active_speed_over_time": guided_summary["mean_active_speed_over_time"] - baseline_summary["mean_active_speed_over_time"],
    }
    if baseline_series and guided_series:
        comparison["baseline_final_rate_from_timeseries"] = float(baseline_series["evacuation_rate"][-1])
        comparison["guided_final_rate_from_timeseries"] = float(guided_series["evacuation_rate"][-1])

    _write_json(output / "summary.json", comparison)
    _write_json(output / "comparison.json", comparison)
    save_comparison_plot(baseline_dir / "timeseries.csv", guided_dir / "timeseries.csv", output / "evacuation_rate_comparison.png")
    return comparison


def _multi_run_comparison(run_dirs: list[Path], labels: list[str], output: Path) -> dict:
    summaries = {label: _load_json(run_dir / "metrics.json") for label, run_dir in zip(labels, run_dirs)}
    baseline_label = labels[0]
    baseline = summaries[baseline_label]
    deltas = {}
    for label, summary in summaries.items():
        deltas[label] = {
            "delta_final_evacuation_rate_vs_baseline": summary["final_evacuation_rate"] - baseline["final_evacuation_rate"],
            "delta_mean_speed_vs_baseline": summary.get("mean_speed", 0.0) - baseline.get("mean_speed", 0.0),
            "delta_congestion_index_vs_baseline": summary.get("congestion_index", 0.0) - baseline.get("congestion_index", 0.0),
            "delta_near_collision_count_vs_baseline": summary.get("near_collision_count", 0) - baseline.get("near_collision_count", 0),
        }
    comparison = {
        "labels": labels,
        "runs": summaries,
        "baseline_label": baseline_label,
        "deltas_vs_baseline": deltas,
    }
    _write_json(output / "summary.json", comparison)
    _write_json(output / "comparison.json", comparison)
    _write_metrics_csv(summaries, output / "metrics_comparison.csv")
    _save_multi_evacuation_plot(run_dirs, labels, output / "evacuation_rate_comparison.png")
    _save_final_metrics_plot(summaries, output / "final_metrics_comparison.png")
    return comparison


def main() -> None:
    args = parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    if args.runs is not None:
        if args.labels is None:
            labels = [Path(run).name for run in args.runs]
        else:
            labels = args.labels
        if len(labels) != len(args.runs):
            raise SystemExit("--labels must have the same length as --runs")
        comparison = _multi_run_comparison([Path(run) for run in args.runs], labels, output)
    else:
        comparison = _legacy_comparison(Path(args.baseline), Path(args.guided), output)

    print(f"Saved comparison outputs to {output}")
    print(json.dumps(comparison, indent=2))


if __name__ == "__main__":
    main()
