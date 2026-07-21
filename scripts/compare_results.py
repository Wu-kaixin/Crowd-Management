"""Compare two evaluation output directories on scientific fields only.

Machine- and run-dependent fields (runtimes, memory, commits, hashes,
timestamps) are pruned before comparison; every remaining field must match
exactly. Exit code 0 means scientifically identical.

Usage:
    python scripts/compare_results.py --reference DIR_A --candidate DIR_B \
        [--files records.json aggregate.json ...]
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

# Keys whose values legitimately differ between runs/machines/commits.
_PRUNE_KEY_PATTERN = re.compile(
    r"(runtime|_ms$|^wall_time|commit|memory_bytes|timestamp|source_sha256"
    r"|^packages$|^python$|^platform$|^os$|^hardware$|^parallel_plan$|^workers$)",
    re.IGNORECASE,
)

DEFAULT_FILES = (
    "records.json",
    "aggregate.json",
    "paired_comparisons.json",
    "ablation_records.json",
    "ablation_aggregate.json",
    "robustness_records.json",
    "robustness_aggregate.json",
    "gate_evidence.json",
    "summary.json",
)


def _prune(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _prune(item) for key, item in value.items() if not _PRUNE_KEY_PATTERN.search(str(key))}
    if isinstance(value, list):
        return [_prune(item) for item in value]
    return value


def _diff(reference: Any, candidate: Any, path: str, out: list[str]) -> None:
    if type(reference) is not type(candidate) and not (
        isinstance(reference, (int, float)) and isinstance(candidate, (int, float))
    ):
        out.append(f"{path}: type {type(reference).__name__} != {type(candidate).__name__}")
        return
    if isinstance(reference, dict):
        for key in sorted(set(reference) | set(candidate)):
            if key not in reference:
                out.append(f"{path}.{key}: missing in reference")
            elif key not in candidate:
                out.append(f"{path}.{key}: missing in candidate")
            else:
                _diff(reference[key], candidate[key], f"{path}.{key}", out)
        return
    if isinstance(reference, list):
        if len(reference) != len(candidate):
            out.append(f"{path}: length {len(reference)} != {len(candidate)}")
            return
        for index, (ref_item, cand_item) in enumerate(zip(reference, candidate, strict=True)):
            _diff(ref_item, cand_item, f"{path}[{index}]", out)
        return
    if isinstance(reference, float) and isinstance(candidate, float):
        if math.isnan(reference) and math.isnan(candidate):
            return
        if reference != candidate:
            out.append(f"{path}: {reference!r} != {candidate!r}")
        return
    if reference != candidate:
        out.append(f"{path}: {reference!r} != {candidate!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare evaluation outputs on scientific fields.")
    parser.add_argument("--reference", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--files", nargs="+", default=None)
    parser.add_argument("--max-report", type=int, default=25)
    args = parser.parse_args()

    reference_dir = Path(args.reference)
    candidate_dir = Path(args.candidate)
    names = args.files if args.files else [name for name in DEFAULT_FILES if (reference_dir / name).is_file()]
    if not names:
        print(f"no comparable files found in {reference_dir}")
        return 2

    failures = 0
    for name in names:
        ref_path = reference_dir / name
        cand_path = candidate_dir / name
        if not ref_path.is_file() or not cand_path.is_file():
            print(f"[MISSING] {name}: reference={ref_path.is_file()} candidate={cand_path.is_file()}")
            failures += 1
            continue
        reference = _prune(json.loads(ref_path.read_text(encoding="utf-8")))
        candidate = _prune(json.loads(cand_path.read_text(encoding="utf-8")))
        differences: list[str] = []
        _diff(reference, candidate, name, differences)
        if differences:
            failures += 1
            print(f"[DIFF] {name}: {len(differences)} differing fields")
            for line in differences[: args.max_report]:
                print(f"    {line}")
            if len(differences) > args.max_report:
                print(f"    ... {len(differences) - args.max_report} more")
        else:
            print(f"[OK] {name}")
    print("RESULT:", "IDENTICAL" if failures == 0 else f"{failures} file(s) differ")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
