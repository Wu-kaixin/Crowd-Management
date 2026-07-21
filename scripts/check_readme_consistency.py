#!/usr/bin/env python3
"""Check README / docs consistency against the live repository.

Fails when README still hard-codes obsolete test counts, points at missing
files, or disagrees with the authoritative pytest collection count.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

OBSOLETE_TEST_COUNT_PATTERNS = (
    re.compile(r"Tests-77%20passed"),
    re.compile(r"Tests-95%20passed"),
    re.compile(r"`95 passed`"),
    re.compile(r"\b77 passed\b"),
)

REQUIRED_SCRIPTS = (
    "scripts/run_static_containment.py",
    "scripts/run_step1_pr6_evaluation.py",
    "scripts/run_step1_g6_compliance.py",
    "scripts/build_readme_media.py",
    "scripts/compare_results.py",
    "scripts/run_ci_smoke.py",
    "scripts/check_readme_consistency.py",
)

REQUIRED_REPORT_LINKS = (
    "reports/step1_g6_compliance/G6_COMPLIANCE_REPORT.md",
    "docs/performance/final_report.md",
    "docs/RESEARCH_SPEC.md",
)

CI_BADGE_PATTERN = re.compile(
    r"https://github\.com/Wu-kaixin/Crowd-Management/actions/workflows/ci\.yml/badge\.svg",
    re.IGNORECASE,
)


def _collect_test_count(repo: Path) -> int:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"pytest --collect-only failed:\n{result.stdout}\n{result.stderr}")
    match = re.search(r"(\d+)\s+tests?\s+collected", result.stdout)
    if not match:
        # pytest -q collect-only may end with "N tests collected in ..."
        match = re.search(r"^(\d+)\s+tests?\s+collected", result.stdout, re.MULTILINE)
    if not match:
        # fallback: last non-empty line like "168 tests collected in 0.74s"
        for line in reversed(result.stdout.splitlines()):
            match = re.search(r"(\d+)\s+tests?\s+collected", line)
            if match:
                break
    if not match:
        raise RuntimeError(f"could not parse collected test count from:\n{result.stdout}")
    return int(match.group(1))


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def check(repo: Path) -> list[str]:
    errors: list[str] = []
    readme = repo / "README.md"
    text = _read(readme)

    for pattern in OBSOLETE_TEST_COUNT_PATTERNS:
        if pattern.search(text):
            errors.append(f"README.md still contains obsolete test-count pattern: {pattern.pattern}")

    if "Development Status" in text and text.count("## Development Status") != 1:
        errors.append("README.md must contain exactly one Development Status section")

    if not CI_BADGE_PATTERN.search(text):
        errors.append("README.md must include a GitHub Actions CI badge pointing at ci.yml")

    marker_match = re.search(
        r"<!-- TEST_COUNT_START -->\s*(\d+)\s*<!-- TEST_COUNT_END -->",
        text,
    )
    collected = _collect_test_count(repo)
    if marker_match:
        marked = int(marker_match.group(1))
        if marked != collected:
            errors.append(f"README TEST_COUNT marker={marked} disagrees with pytest collect-only={collected}")
    elif re.search(r"\b\d+\s+passed\b", text):
        errors.append(
            "README.md hard-codes a passed-count without TEST_COUNT markers; "
            "use CI badge + a single marked count or remove hard-coded counts"
        )

    for relative in REQUIRED_SCRIPTS:
        if not (repo / relative).is_file():
            errors.append(f"required script missing: {relative}")
        elif relative not in text and relative != "scripts/check_readme_consistency.py":
            # check script itself need not be advertised in README
            if relative in {
                "scripts/run_static_containment.py",
                "scripts/run_step1_pr6_evaluation.py",
                "scripts/run_step1_g6_compliance.py",
                "scripts/build_readme_media.py",
            }:
                if Path(relative).name not in text and relative not in text:
                    errors.append(f"README.md does not mention required command: {relative}")

    for relative in REQUIRED_REPORT_LINKS:
        if relative in text and not (repo / relative).is_file():
            errors.append(f"README links to missing report: {relative}")
        if relative in REQUIRED_REPORT_LINKS and relative not in text and relative.endswith("final_report.md"):
            # performance report should be linked once README mentions performance
            if "performance" in text.lower() and relative not in text:
                errors.append(f"README mentions performance but lacks link to {relative}")

    if "local-main-backup" in text:
        # Ensure we don't claim legacy paths exist on main.
        for forbidden in ("legacy/evacuation_guidance/", "src/crowd_management/legacy/"):
            if forbidden in text and (repo / forbidden).exists():
                errors.append(f"legacy path unexpectedly present on current branch: {forbidden}")

    agents = repo / "AGENTS.md"
    if agents.is_file():
        agents_text = _read(agents)
        match = re.search(r"(\d+)\s+tests", agents_text)
        if match and int(match.group(1)) != collected:
            errors.append(f"AGENTS.md test count {match.group(1)} disagrees with collect-only {collected}")

    workflow = repo / ".github/workflows/ci.yml"
    if not workflow.is_file():
        errors.append("missing .github/workflows/ci.yml")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate README consistency.")
    parser.add_argument("--repo", default=".")
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    errors = check(repo)
    if errors:
        print("README consistency check FAILED:")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("README consistency check OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
