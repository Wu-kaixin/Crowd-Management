"""Check that the committed Wolfram math-verification results are fresh.

Designed for CI runners without a Wolfram license: this script never executes
Mathematica. It only verifies that the committed evidence is internally
consistent and still corresponds to the expected base ``main`` SHA, so stale
or hand-edited results are flagged instead of silently presented as current.

Checks performed:

1. All required Wolfram scripts, artifacts, figures, and reports exist.
2. ``provenance.json`` SHA-256 hashes match the actual Wolfram source files,
   input case files, and result files on disk.
3. ``summary.json`` totals equal the per-claim tallies recomputed from
   ``MATHEMATICAL_CLAIM_MATRIX.csv`` and the test counts in
   ``test_report.json``.
4. Every figure has PNG + PDF + data file in the media directory.
5. The audited ``main`` SHA is consistent across summary, provenance, and the
   verification report, and (optionally) matches ``--expected-base-sha`` or
   the current ``git merge-base HEAD origin/main``.
6. No Wolfram test recorded a failure.

Exit code 0 = fresh; 1 = stale or inconsistent (details on stdout).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ART_DIR = REPO_ROOT / "artifacts" / "math_verification"
MEDIA_DIR = REPO_ROOT / "reports" / "media" / "math_verification"
MATRIX_CSV = REPO_ROOT / "docs" / "math" / "MATHEMATICAL_CLAIM_MATRIX.csv"
REPORT_MD = REPO_ROOT / "docs" / "math" / "MATHEMATICAL_VERIFICATION_REPORT.md"

REQUIRED_ARTIFACTS = [
    "test_report.json",
    "test_results.csv",
    "symbolic_results.json",
    "numerical_results.json",
    "counterexamples.json",
    "implementation_comparison.json",
    "summary.json",
    "provenance.json",
]

REQUIRED_FIGURES = [
    "mathematical_verification_summary",
    "symbolic_identity_residuals",
    "python_wolfram_crosscheck",
    "periodic_coverage_formula",
    "guide_resource_bound",
    "controller_stability_region",
    "controller_lyapunov_validation",
    "safety_projection_geometry",
    "safety_kkt_residuals",
    "assignment_optimality_crosscheck",
    "metric_invariance_tests",
    "assumption_and_limitation_matrix",
]

# Status keys of summary.json mapped to claim-matrix status values.
STATUS_FIELDS = {
    "symbolically_proved": "SYMBOLICALLY_PROVED",
    "exactly_verified": "EXACTLY_VERIFIED",
    "numerically_verified": "NUMERICALLY_VERIFIED_WITHIN_DOMAIN",
    "property_tested": "PROPERTY_TESTED",
    "counterexamples_found": "COUNTEREXAMPLE_FOUND",
    "implementation_mismatches": "IMPLEMENTATION_MISMATCH",
    "assumption_gaps": "ASSUMPTION_GAP",
    "not_verifiable": "NOT_VERIFIABLE_BY_CAS",
    "not_applicable": "NOT_APPLICABLE",
    "not_run": "NOT_RUN",
}


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


class Checker:
    def __init__(self) -> None:
        self.errors: list[str] = []

    def fail(self, message: str) -> None:
        self.errors.append(message)
        print(f"FAIL  {message}")

    def ok(self, message: str) -> None:
        print(f"ok    {message}")


def resolve_expected_base_sha(explicit: str | None) -> str | None:
    if explicit:
        return explicit
    try:
        result = subprocess.run(
            ["git", "merge-base", "HEAD", "origin/main"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--expected-base-sha",
        default=None,
        help=(
            "Base main SHA the verification must correspond to. Defaults to "
            "'git merge-base HEAD origin/main' when available."
        ),
    )
    parser.add_argument(
        "--skip-base-sha-check",
        action="store_true",
        help="Only check internal consistency, not alignment with the current base SHA.",
    )
    args = parser.parse_args()

    checker = Checker()

    # 1. Required files exist. ------------------------------------------------
    missing = [name for name in REQUIRED_ARTIFACTS if not (ART_DIR / name).is_file()]
    if missing:
        checker.fail(f"missing artifacts: {missing}")
        print("\nSTALE: required artifacts are absent; run the Wolfram suite locally.")
        return 1
    checker.ok(f"all {len(REQUIRED_ARTIFACTS)} required artifacts present")

    for doc in (MATRIX_CSV, REPORT_MD):
        if not doc.is_file():
            checker.fail(f"missing document: {doc.relative_to(REPO_ROOT)}")

    figure_missing = [
        f"{stem}.{ext}"
        for stem in REQUIRED_FIGURES
        for ext in ("png", "pdf")
        if not (MEDIA_DIR / f"{stem}.{ext}").is_file()
    ]
    data_missing = [
        stem
        for stem in REQUIRED_FIGURES
        if not any((MEDIA_DIR / f"{stem}.{ext}").is_file() for ext in ("json", "csv"))
    ]
    if figure_missing:
        checker.fail(f"missing figure files: {figure_missing}")
    if data_missing:
        checker.fail(f"figures without data file: {data_missing}")
    if not figure_missing and not data_missing:
        checker.ok(f"all {len(REQUIRED_FIGURES)} figures have PNG + PDF + data")

    provenance = json.loads((ART_DIR / "provenance.json").read_text(encoding="utf-8"))
    summary = json.loads((ART_DIR / "summary.json").read_text(encoding="utf-8"))
    test_report = json.loads((ART_DIR / "test_report.json").read_text(encoding="utf-8"))

    # 2. Hash integrity. -------------------------------------------------------
    hash_groups = {
        "wolfram_script_sha256": "Wolfram source",
        "input_case_sha256": "input case",
        "result_sha256": "result file",
    }
    for key, label in hash_groups.items():
        recorded: dict[str, str] = provenance.get(key, {})
        if not recorded:
            checker.fail(f"provenance.json has no {key} section")
            continue
        bad = []
        for rel_path, expected in recorded.items():
            path = REPO_ROOT / rel_path.replace("\\", "/")
            if not path.is_file():
                bad.append(f"{rel_path} (missing)")
            elif sha256_of(path) != expected:
                bad.append(rel_path)
        if bad:
            checker.fail(f"{label} hashes stale or modified: {bad}")
        else:
            checker.ok(f"{len(recorded)} {label} hashes match provenance")

    # 3. Summary totals vs claim matrix and test report. -----------------------
    with MATRIX_CSV.open(encoding="utf-8", newline="") as fh:
        claims = list(csv.DictReader(fh))
    if summary.get("total_claims") != len(claims):
        checker.fail(
            f"summary.total_claims={summary.get('total_claims')} but matrix has {len(claims)} rows"
        )
    else:
        checker.ok(f"total_claims matches matrix ({len(claims)})")

    for field, status in STATUS_FIELDS.items():
        actual = sum(1 for row in claims if row["status"] == status)
        recorded_count = summary.get(field)
        if recorded_count != actual:
            checker.fail(f"summary.{field}={recorded_count} but matrix tally is {actual}")
    checker.ok("per-status tallies checked against claim matrix")

    results = test_report.get("results", [])
    reported_total = len(results)
    reported_failed = sum(1 for r in results if r.get("outcome") != "Success")
    suite_failed = sum(s.get("tests_failed", 0) for s in test_report.get("suites", []))
    if suite_failed != reported_failed:
        checker.fail(
            f"test_report suites report {suite_failed} failures but per-test "
            f"results contain {reported_failed}"
        )
    if summary.get("total_wolfram_tests") != reported_total:
        checker.fail(
            f"summary.total_wolfram_tests={summary.get('total_wolfram_tests')} "
            f"but test_report says {reported_total}"
        )
    if summary.get("failed") != reported_failed:
        checker.fail(
            f"summary.failed={summary.get('failed')} but test_report says {reported_failed}"
        )
    if reported_failed:
        checker.fail(f"test_report records {reported_failed} failed Wolfram tests")
    else:
        checker.ok(f"test report: {reported_total} tests, 0 failed")

    # 4. SHA alignment. ---------------------------------------------------------
    shas = {
        "summary.main_sha": summary.get("main_sha"),
        "provenance.main_sha": provenance.get("main_sha"),
    }
    if len(set(shas.values())) != 1:
        checker.fail(f"main SHA disagreement: {shas}")
    else:
        checker.ok(f"artifacts agree on audited main SHA {summary['main_sha'][:12]}")

    report_text = REPORT_MD.read_text(encoding="utf-8") if REPORT_MD.is_file() else ""
    if summary.get("main_sha") and summary["main_sha"] not in report_text:
        checker.fail("verification report does not cite the audited main SHA")
    else:
        checker.ok("verification report cites the audited main SHA")

    if not args.skip_base_sha_check:
        expected = resolve_expected_base_sha(args.expected_base_sha)
        if expected is None:
            print("warn  could not determine expected base SHA (no origin/main?); skipping")
        elif expected != summary.get("main_sha"):
            checker.fail(
                "verification is STALE: audited main SHA "
                f"{summary.get('main_sha', '?')[:12]} != expected base {expected[:12]}. "
                "Re-run the local Wolfram verification against the new base."
            )
        else:
            checker.ok("audited main SHA matches the current expected base")

    print()
    if checker.errors:
        print(f"RESULT: STALE/INCONSISTENT ({len(checker.errors)} problem(s))")
        return 1
    print("RESULT: FRESH (all consistency checks passed; Mathematica itself was NOT re-executed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
