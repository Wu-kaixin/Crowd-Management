#!/usr/bin/env python
"""Render a static crowd-management dashboard figure."""
from __future__ import annotations

import argparse

from crowd_management.advanced_visualization import render_dashboard


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render visualization dashboard.")
    parser.add_argument("--runs", nargs="+", required=True, help="Run directories containing replay.npz and metrics.")
    parser.add_argument("--labels", nargs="+", required=True, help="Labels matching --runs.")
    parser.add_argument("--output", required=True, help="Output PNG path.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if len(args.labels) != len(args.runs):
        raise SystemExit("--labels must have the same length as --runs")
    output = render_dashboard(args.runs, args.labels, args.output)
    print(f"Saved dashboard to {output}")


if __name__ == "__main__":
    main()
