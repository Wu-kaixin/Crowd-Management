#!/usr/bin/env python
"""Compare baseline and guided experiment outputs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from crowd_management.metrics import load_timeseries
from crowd_management.visualization import save_comparison_plot


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare baseline and guided crowd-management runs.")
    parser.add_argument("--baseline", default="outputs/baseline")
    parser.add_argument("--guided", default="outputs/guided")
    parser.add_argument("--output", default="outputs/comparison")
    return parser.parse_args()


def _load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    args = parse_args()
    baseline_dir = Path(args.baseline)
    guided_dir = Path(args.guided)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

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

    # Time-aligned final comparison is intentionally simple: this is a sprint demo.
    if baseline_series and guided_series:
        comparison["baseline_final_rate_from_timeseries"] = float(baseline_series["evacuation_rate"][-1])
        comparison["guided_final_rate_from_timeseries"] = float(guided_series["evacuation_rate"][-1])

    with open(output / "comparison.json", "w", encoding="utf-8") as f:
        json.dump(comparison, f, indent=2)
    save_comparison_plot(baseline_dir / "timeseries.csv", guided_dir / "timeseries.csv", output / "evacuation_rate_comparison.png")
    print(f"Saved comparison outputs to {output}")
    print(json.dumps(comparison, indent=2))


if __name__ == "__main__":
    main()
