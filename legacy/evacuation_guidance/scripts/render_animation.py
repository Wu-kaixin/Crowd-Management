#!/usr/bin/env python
"""Render a single crowd-management run as MP4 or GIF."""
from __future__ import annotations

import argparse

from crowd_management.advanced_visualization import render_run_animation


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a single replay animation.")
    parser.add_argument("--run", required=True, help="Run directory containing replay.npz.")
    parser.add_argument("--output", required=True, help="Output .mp4 or .gif path.")
    parser.add_argument("--fps", type=int, default=15)
    parser.add_argument("--trail-length", type=int, default=10)
    parser.add_argument("--heatmap", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output = render_run_animation(args.run, args.output, fps=args.fps, trail_length=args.trail_length, heatmap=args.heatmap)
    print(f"Saved animation to {output}")


if __name__ == "__main__":
    main()
