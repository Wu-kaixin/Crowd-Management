from __future__ import annotations

import argparse
import json
from pathlib import Path

from crowd_management.evaluation import G6EvaluationConfig, run_g6_evaluation, run_g6_preflight
from crowd_management.evaluation.step1_g6 import PRIMARY_SCENARIOS
from crowd_management.runtime import (
    PERFORMANCE_MODES,
    detect_hardware,
    format_parallel_report,
    hardware_metadata,
    limit_blas_threads,
    select_parallel_plan,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run formal ABCG-v2 Step 1 G6 compliance evaluation.")
    parser.add_argument("--output", default="reports/step1_g6_compliance")
    parser.add_argument("--run-root", default="runs/step1_g6_compliance")
    parser.add_argument("--seed-count", type=int, default=30)
    parser.add_argument("--bootstrap-samples", type=int, default=30)
    parser.add_argument("--observation-count", type=int, default=120)
    parser.add_argument("--ci-resamples", type=int, default=2000)
    parser.add_argument("--max-steps", type=int, default=160)
    parser.add_argument(
        "--workers",
        default="auto",
        help="Case-level worker processes: 'auto' (hardware-aware) or a positive integer.",
    )
    parser.add_argument(
        "--performance-mode",
        choices=[mode for mode in PERFORMANCE_MODES if mode != "manual"],
        default="balanced",
        help="Worker-selection policy used when --workers is 'auto'.",
    )
    args = parser.parse_args()
    if args.seed_count < 1:
        parser.error("--seed-count must be positive")
    requested_workers: int | None = None
    if args.workers != "auto":
        try:
            requested_workers = int(args.workers)
        except ValueError:
            parser.error("--workers must be 'auto' or a positive integer")
        if requested_workers < 1:
            parser.error("--workers must be 'auto' or a positive integer")

    hardware = detect_hardware()
    case_count = args.seed_count * len(PRIMARY_SCENARIOS)
    plan = select_parallel_plan(
        case_count=case_count,
        mode=args.performance_mode,
        requested_workers=requested_workers,
        hardware=hardware,
    )
    print(format_parallel_report(plan, hardware), flush=True)

    preflight = run_g6_preflight()
    with limit_blas_threads(plan.blas_threads_per_worker):
        gate = run_g6_evaluation(
            args.output,
            G6EvaluationConfig(
                seeds=tuple(range(args.seed_count)),
                bootstrap_samples=args.bootstrap_samples,
                observation_count=args.observation_count,
                confidence_interval_resamples=args.ci_resamples,
                max_steps=args.max_steps,
                workers=plan.workers,
            ),
            run_root=args.run_root,
            preflight_evidence=preflight,
        )
    runtime_metadata = {
        "schema": "abcg-runtime-metadata-v1",
        "hardware": hardware_metadata(hardware),
        "parallel_plan": plan.as_metadata(),
    }
    (Path(args.output) / "runtime_metadata.json").write_text(
        json.dumps(runtime_metadata, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"records={gate['primary_record_count']}/{gate['expected_primary_record_count']}, "
        f"failures={gate['failure_count']}, overall_status={gate['overall_status']}, "
        f"g6_status={gate['g6_status']}, evaluated_commit={gate['evaluated_commit']}"
    )


if __name__ == "__main__":
    main()
