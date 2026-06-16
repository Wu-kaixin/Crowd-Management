#!/usr/bin/env python
"""Render synchronized two-run or four-run crowd-management comparisons."""
from __future__ import annotations

import argparse

from crowd_management.advanced_visualization import render_side_by_side_animation


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render synchronized replay comparison.")
    parser.add_argument("--runs", nargs="+", required=True, help="Two or four run directories containing replay.npz.")
    parser.add_argument("--labels", nargs="+", default=None, help="Labels matching --runs.")
    parser.add_argument("--output", required=True, help="Output .mp4 or .gif path.")
    parser.add_argument("--fps", type=int, default=15)
    parser.add_argument("--trail-length", type=int, default=8)
    parser.add_argument("--no-heatmap", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if len(args.runs) not in {2, 4}:
        raise SystemExit("--runs must contain exactly 2 or 4 run directories")
    if args.labels is not None and len(args.labels) != len(args.runs):
        raise SystemExit("--labels must have the same length as --runs")
    output = render_side_by_side_animation(
        args.runs,
        args.labels,
        args.output,
        fps=args.fps,
        trail_length=args.trail_length,
        heatmap=not args.no_heatmap,
    )
    print(f"Saved comparison animation to {output}")


if __name__ == "__main__":
    main()
