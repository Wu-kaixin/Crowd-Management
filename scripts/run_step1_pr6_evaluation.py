from __future__ import annotations

import argparse

from crowd_management.evaluation import PR6EvaluationConfig, run_pr6_evaluation


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the paired ABCG-v2 Step 1 PR6 evaluation.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--seed-count", type=int, default=30)
    parser.add_argument("--bootstrap-samples", type=int, default=12)
    parser.add_argument("--observation-count", type=int, default=280)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.seed_count < 1:
        parser.error("--seed-count must be positive")
    evidence = run_pr6_evaluation(
        args.output,
        PR6EvaluationConfig(
            seeds=tuple(range(args.seed_count)),
            bootstrap_samples=args.bootstrap_samples,
            observation_count=args.observation_count,
            workers=args.workers,
        ),
    )
    print(
        f"records={evidence['record_count']}, paired_seeds={evidence['paired_seed_count']}, "
        f"shapes={evidence['heldout_shape_count']}, g6_status={evidence['g6_status']}"
    )


if __name__ == "__main__":
    main()
