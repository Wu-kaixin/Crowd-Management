from __future__ import annotations

import argparse

from crowd_management.experiments.static_containment import run_static_containment


def main() -> None:
    parser = argparse.ArgumentParser(description="Run static unknown-crowd containment baselines.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--methods",
        nargs="+",
        default=["random", "static_circle", "legacy_center_radius", "abcg"],
        choices=["random", "static_circle", "legacy_center_radius", "abcg"],
    )
    parser.add_argument("--skip-plots", action="store_true")
    args = parser.parse_args()
    results = run_static_containment(args.config, args.output, methods=args.methods, save_plots=not args.skip_plots)
    for method, summary in results.items():
        print(f"{method}: coverage={summary['coverage_ratio']:.3f}, gap={summary['max_boundary_gap']:.3f}")


if __name__ == "__main__":
    main()
