"""CLI entry for Step 2 gather-then-surround.

PowerShell:

    conda activate abcg
    python scripts/run_gather_then_surround.py --config configs/step2_gather/square_dispersed_gather.yaml --output runs/step2_gather
"""

from __future__ import annotations

import argparse

from crowd_management.experiments.step2_gather import run_gather_then_surround


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Step 2: gather dispersed pedestrians, then surround."
    )
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--skip-plots", action="store_true")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--no-hold-window", action="store_true")
    args = parser.parse_args()
    summary = run_gather_then_surround(
        args.config,
        args.output,
        save_plots=not args.skip_plots,
        live=not args.headless,
        headless=args.headless,
        hold_window=None if args.headless else (not args.no_hold_window),
    )
    print(
        "gather_then_surround: "
        f"status={summary['status']}, "
        f"phase_final={summary['phase_final']}, "
        f"steps={summary['steps']}, "
        f"gather_fraction={summary.get('gather_fraction')}, "
        f"surround_boundary={summary.get('surround_boundary_status')}, "
        f"scientific_success={summary.get('scientific_success')}"
    )


if __name__ == "__main__":
    main()
