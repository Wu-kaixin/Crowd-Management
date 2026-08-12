"""Summarize the Wolfram verification artifacts and check frozen tolerances.

Reads ``artifacts/math_verification/`` and prints a compact comparison table:
suite outcomes, cross-language residuals against the frozen tolerances, and
safety-projection measures.  Exits non-zero if any Wolfram test failed or any
frozen tolerance was exceeded.

This script does not rerun Mathematica; it only audits the exported evidence.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = REPO_ROOT / "artifacts" / "math_verification"

FROZEN_TOLERANCES = {
    "cross_language": 1.0e-9,
    "projection_distance": 1.0e-6,
    "kkt_stationarity": 1.0e-8,
}


def _load(name: str) -> dict:
    with open(ARTIFACTS / name, encoding="utf-8") as handle:
        return json.load(handle)


def main() -> int:
    failures: list[str] = []

    report = _load("test_report.json")
    print("== Wolfram test suites ==")
    for suite in report["suites"]:
        print(
            f"  {suite['suite']:<20} succeeded={suite['tests_succeeded']:<3} "
            f"failed={suite['tests_failed']:<3} time={suite['time_elapsed_milliseconds']}ms"
        )
        if suite["tests_failed"]:
            failures.append(f"suite {suite['suite']} has {suite['tests_failed']} failed tests")
    failed_rows = [row for row in report["results"] if row["outcome"] != "Success"]
    for row in failed_rows:
        print(f"  FAILED: {row['suite']}::{row['test_id']} -> {row['outcome']}")

    numerical = _load("numerical_results.json")
    print("== Cross-language residuals (relative, frozen tolerance 1e-9) ==")
    for key in (
        "geometry_length_residual_max",
        "coverage_H_residual_max",
        "controller_trace_residual_max",
        "statistics_residual_max",
        "metrics_residual_max",
    ):
        value = float(numerical[key])
        status = "OK" if value <= FROZEN_TOLERANCES["cross_language"] else "EXCEEDED"
        print(f"  {key:<36} {value:.3e}  {status}")
        if status == "EXCEEDED":
            failures.append(f"{key} = {value} exceeds frozen tolerance")

    print("== Safety projection measures ==")
    for measure in numerical["safety_projection_measures"]:
        if "dykstra_vs_reference_distance" not in measure:
            failures.append(f"safety instance {measure.get('name')}: {measure.get('status')}")
            continue
        dist = float(measure["dykstra_vs_reference_distance"])
        stat = float(measure["kkt_stationarity"])
        ok_dist = dist <= FROZEN_TOLERANCES["projection_distance"]
        ok_kkt = stat <= FROZEN_TOLERANCES["kkt_stationarity"]
        print(
            f"  {measure['name']:<36} |u_dykstra - u_ref|={dist:.3e} "
            f"({'OK' if ok_dist else 'EXCEEDED'})  kkt_stationarity={stat:.3e} "
            f"({'OK' if ok_kkt else 'EXCEEDED'})"
        )
        if not ok_dist:
            failures.append(f"{measure['name']}: projection distance {dist} exceeds tolerance")
        if not ok_kkt:
            failures.append(f"{measure['name']}: KKT stationarity {stat} exceeds tolerance")

    summary = _load("summary.json")
    print("== Summary ==")
    for key in (
        "total_claims",
        "symbolically_proved",
        "exactly_verified",
        "numerically_verified",
        "property_tested",
        "counterexamples_found",
        "implementation_mismatches",
        "assumption_gaps",
        "not_verifiable",
        "total_wolfram_tests",
        "succeeded",
        "failed",
        "main_sha",
        "mathematica_version",
    ):
        print(f"  {key}: {summary[key]}")

    if failures:
        print("== FAILURES ==")
        for failure in failures:
            print(f"  {failure}")
        return 1
    print("All Wolfram evidence within frozen tolerances.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
