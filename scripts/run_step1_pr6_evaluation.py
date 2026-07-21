from __future__ import annotations

import argparse
import json
from pathlib import Path

from crowd_management.evaluation import PR6EvaluationConfig, run_pr6_evaluation
from crowd_management.runtime import (
    PERFORMANCE_MODES,
    detect_hardware,
    format_parallel_report,
    hardware_metadata,
    limit_blas_threads,
    select_parallel_plan,
)

HELDOUT_SHAPES = ("u_shape", "c_shape")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the paired ABCG-v2 Step 1 PR6 evaluation.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--seed-count", type=int, default=30)
    parser.add_argument("--bootstrap-samples", type=int, default=12)
    parser.add_argument("--observation-count", type=int, default=280)
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
    case_count = args.seed_count * len(HELDOUT_SHAPES)
    plan = select_parallel_plan(
        case_count=case_count,
        mode=args.performance_mode,
        requested_workers=requested_workers,
        hardware=hardware,
    )
    print(format_parallel_report(plan, hardware), flush=True)

    with limit_blas_threads(plan.blas_threads_per_worker):
        evidence = run_pr6_evaluation(
            args.output,
            PR6EvaluationConfig(
                seeds=tuple(range(args.seed_count)),
                bootstrap_samples=args.bootstrap_samples,
                observation_count=args.observation_count,
                workers=plan.workers,
            ),
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
        f"records={evidence['record_count']}, paired_seeds={evidence['paired_seed_count']}, "
        f"shapes={evidence['heldout_shape_count']}, g6_status={evidence['g6_status']}"
    )


if __name__ == "__main__":
    main()
