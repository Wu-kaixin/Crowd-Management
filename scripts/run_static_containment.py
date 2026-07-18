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
        print(
            f"{method}: coverage={summary['coverage_ratio']:.3f}, "
            f"max_euclidean_distance={summary['max_euclidean_boundary_distance']:.3f}, "
            f"evaluation_status={summary['evaluation_status']}, "
            f"boundary_v2_status={summary['boundary_v2_status']}, "
            f"periodic_plan_status={summary['periodic_plan_status']}, "
            f"resource_status={summary['resource_status']}, "
            f"assignment_status={summary['assignment_status']}, "
            f"episode_status={summary['episode_status']}, "
            f"safety_filter_status={summary['safety_filter_status']}, "
            f"safety_projected_steps={summary['safety_projected_steps']}"
        )


if __name__ == "__main__":
    main()
