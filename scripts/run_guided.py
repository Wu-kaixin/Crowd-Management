#!/usr/bin/env python
"""Run guided scenarios with selectable guider-control baselines."""
from __future__ import annotations

import argparse
from pathlib import Path

from crowd_management.crowd_model import run_simulation
from crowd_management.metrics import save_metrics
from crowd_management.types import SimulationConfig
from crowd_management.visualization import save_animation, save_density_heatmap, save_snapshot, save_timeseries_plot

GUIDANCE_MODE_TITLES = {
    "dbact": "Guided: transferred DBACT-style control",
    "static": "Guided baseline: static guiders",
    "random": "Guided baseline: random moving guiders",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run crowd evacuation with selectable guider mode.")
    parser.add_argument("--config", default="configs/simple_room.yaml")
    parser.add_argument("--output", default="outputs/guided")
    parser.add_argument("--steps", type=int, default=None)
    parser.add_argument("--mode", choices=("dbact", "static", "random"), default="dbact")
    parser.add_argument("--animation", action="store_true", help="Also save an animated GIF.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = SimulationConfig.from_yaml(args.config)
    history = run_simulation(cfg, guided=True, steps=args.steps, guidance_mode=args.mode)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    title = GUIDANCE_MODE_TITLES[args.mode]
    summary = save_metrics(history, cfg.metrics, output)
    save_snapshot(history, cfg.room, output / "final_snapshot.png", title=title)
    save_density_heatmap(history, cfg.room, output / "density_heatmap.png")
    save_timeseries_plot(output / "timeseries.csv", output / "timeseries.png", title=f"{args.mode} time series")
    if args.animation:
        save_animation(history, cfg.room, output / "animation.gif", title=title)
    print(f"Saved {args.mode} guided outputs to {output}")
    print(summary)


if __name__ == "__main__":
    main()
