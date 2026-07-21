#!/usr/bin/env python3
"""Deterministic CI smoke runner for static containment.

Fixed config + method. Verifies completion, required artifacts, and schema.
Does not assert wall-clock performance (shared CI runners are noisy).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from crowd_management.evaluation.schema_validation import (
    SchemaValidationError,
    validate_evaluation_directory,
)
from crowd_management.experiments.static_containment import run_static_containment

STABLE_FIELDS = (
    "coverage_ratio",
    "max_euclidean_boundary_distance",
    "evaluation_status",
    "boundary_v2_status",
    "periodic_plan_status",
    "resource_status",
    "assignment_status",
    "episode_status",
    "safety_filter_status",
    "safety_projected_steps",
    "method_status",
    "active_guide_count",
    "reserve_guide_count",
    "truth_component_count",
)


def _stable_view(summary: dict) -> dict:
    method = next(iter(summary))
    record = summary[method]
    return {key: record[key] for key in STABLE_FIELDS if key in record}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic CI smoke containment.")
    parser.add_argument("--config", default="configs/ci_smoke.yaml")
    parser.add_argument("--output", default="artifacts/ci_smoke")
    parser.add_argument("--expected", default="tests/golden/ci_smoke_expected.json")
    parser.add_argument("--skip-plots", action="store_true", default=True)
    args = parser.parse_args()

    output = Path(args.output)
    if output.exists():
        for path in sorted(output.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
    output.mkdir(parents=True, exist_ok=True)

    results = run_static_containment(
        args.config,
        output,
        methods=["abcg"],
        save_plots=not args.skip_plots,
    )
    if not results:
        print("smoke failed: empty results", file=sys.stderr)
        return 1

    try:
        checked = validate_evaluation_directory(output, kind="static")
    except SchemaValidationError as error:
        print(f"schema validation failed: {error}", file=sys.stderr)
        return 1

    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    stable = _stable_view(summary)
    expected_path = Path(args.expected)
    if expected_path.is_file():
        expected = json.loads(expected_path.read_text(encoding="utf-8"))
        if stable != expected.get("stable_fields", expected):
            print("stable scientific fields differ from golden expectation", file=sys.stderr)
            print("actual:", json.dumps(stable, indent=2, sort_keys=True), file=sys.stderr)
            print(
                "expected:",
                json.dumps(expected.get("stable_fields", expected), indent=2, sort_keys=True),
                file=sys.stderr,
            )
            return 1

    print(json.dumps({"status": "ok", "checked": checked, "stable_fields": stable}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
