#!/usr/bin/env python
"""Render density heatmap snapshots from a replay."""
from __future__ import annotations

import argparse

from crowd_management.advanced_visualization import render_heatmap_snapshots


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render selected density heatmap snapshots.")
    parser.add_argument("--run", required=True, help="Run directory containing replay.npz.")
    parser.add_argument("--times", nargs="*", type=float, default=[], help="Snapshot times in seconds.")
    parser.add_argument("--output", required=True, help="Output PNG path.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output = render_heatmap_snapshots(args.run, args.times, args.output)
    print(f"Saved heatmap snapshots to {output}")


if __name__ == "__main__":
    main()
