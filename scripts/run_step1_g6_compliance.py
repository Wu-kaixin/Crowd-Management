from __future__ import annotations

import argparse

from crowd_management.evaluation import G6EvaluationConfig, run_g6_evaluation, run_g6_preflight


def main() -> None:
    parser = argparse.ArgumentParser(description="Run formal ABCG-v2 Step 1 G6 compliance evaluation.")
    parser.add_argument("--output", default="reports/step1_g6_compliance")
    parser.add_argument("--run-root", default="runs/step1_g6_compliance")
    parser.add_argument("--seed-count", type=int, default=30)
    parser.add_argument("--bootstrap-samples", type=int, default=30)
    parser.add_argument("--observation-count", type=int, default=120)
    parser.add_argument("--ci-resamples", type=int, default=2000)
    parser.add_argument("--max-steps", type=int, default=160)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.seed_count < 1:
        parser.error("--seed-count must be positive")
    preflight = run_g6_preflight()
    gate = run_g6_evaluation(
        args.output,
        G6EvaluationConfig(
            seeds=tuple(range(args.seed_count)),
            bootstrap_samples=args.bootstrap_samples,
            observation_count=args.observation_count,
            confidence_interval_resamples=args.ci_resamples,
            max_steps=args.max_steps,
            workers=args.workers,
        ),
        run_root=args.run_root,
        preflight_evidence=preflight,
    )
    print(
        f"records={gate['primary_record_count']}/{gate['expected_primary_record_count']}, "
        f"failures={gate['failure_count']}, overall_status={gate['overall_status']}, "
        f"g6_status={gate['g6_status']}, evaluated_commit={gate['evaluated_commit']}"
    )


if __name__ == "__main__":
    main()
