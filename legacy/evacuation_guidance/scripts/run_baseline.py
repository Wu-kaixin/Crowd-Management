#!/usr/bin/env python
"""Run the no-guidance baseline scenario."""
from __future__ import annotations

import argparse
from pathlib import Path

from crowd_management.crowd_model import run_simulation
from crowd_management.metrics import save_metrics
from crowd_management.replay import save_replay
from crowd_management.types import SimulationConfig
from crowd_management.visualization import save_animation, save_density_heatmap, save_snapshot, save_timeseries_plot


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run baseline crowd evacuation without guiders.")
    parser.add_argument("--config", default="legacy/evacuation_guidance/configs/simple_room.yaml")
    parser.add_argument("--output", default="outputs/baseline")
    parser.add_argument("--steps", type=int, default=None)
    parser.add_argument("--animation", action="store_true", help="Also save an animated GIF.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = SimulationConfig.from_yaml(args.config)
    history = run_simulation(cfg, guided=False, steps=args.steps)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    summary = save_metrics(history, cfg.metrics, output)
    save_replay(history, cfg, output, mode="baseline", scenario=Path(args.config).stem)
    save_snapshot(history, cfg.room, output / "final_snapshot.png", title="Baseline: no guidance")
    save_density_heatmap(history, cfg.room, output / "density_heatmap.png")
    save_timeseries_plot(output / "timeseries.csv", output / "timeseries.png", title="Baseline time series")
    if args.animation:
        save_animation(history, cfg.room, output / "animation.gif", title="Baseline: no guidance")
    print(f"Saved baseline outputs to {output}")
    print(summary)


if __name__ == "__main__":
    main()
