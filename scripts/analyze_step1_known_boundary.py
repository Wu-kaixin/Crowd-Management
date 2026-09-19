"""Aggregate known-boundary Step 1 records without dropping failures."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from shutil import copyfile
from statistics import mean


def _load(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _flag(row: dict[str, str], key: str) -> bool:
    value = str(row.get(key, "")).strip().lower()
    return value in {"true", "1", "yes"}


def _rate(rows: list[dict[str, str]], key: str) -> float:
    if not rows:
        return 0.0
    return sum(_flag(row, key) for row in rows) / len(rows)


def _mean(rows: list[dict[str, str]], key: str) -> float | None:
    values: list[float] = []
    for row in rows:
        raw = row.get(key, "")
        try:
            number = float(raw)
        except (TypeError, ValueError):
            continue
        if number == number:
            values.append(number)
    return mean(values) if values else None


def _group(rows: list[dict[str, str]], key: str) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get(key, "unknown"))].append(row)
    return grouped


def _seed_split(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        try:
            seed = int(row.get("seed", -1))
        except (TypeError, ValueError):
            seed = -1
        if 0 <= seed <= 4:
            grouped["development"].append(row)
        elif 100 <= seed <= 119:
            grouped["holdout"].append(row)
        else:
            grouped["other"].append(row)
    return grouped


def _fmt_block(title: str, block: dict[str, object]) -> list[str]:
    failures = block.get("failures") or {}
    failure_text = ", ".join(f"{key}={value}" for key, value in failures.items()) or "none"
    return [
        f"## {title}",
        "",
        f"- n: {block['n']}",
        f"- execution success: {float(block['execution_success_rate']):.3f}",
        f"- scientific success: {float(block['scientific_success_rate']):.3f}",
        f"- boundary valid: {float(block['boundary_valid_rate']):.3f}",
        f"- deployment valid: {float(block['deployment_valid_rate']):.3f}",
        f"- convergence: {float(block['convergence_rate']):.3f}",
        f"- failures (kept in denominator): {failure_text}",
        "",
    ]


def _block(rows: list[dict[str, str]]) -> dict[str, object]:
    failures: dict[str, int] = defaultdict(int)
    for row in rows:
        if not _flag(row, "scientific_success"):
            failures[str(row.get("failure_reason") or row.get("episode_status") or "unknown")] += 1
    return {
        "n": len(rows),
        "execution_success_rate": _rate(rows, "execution_success"),
        "scientific_success_rate": _rate(rows, "scientific_success"),
        "boundary_valid_rate": _rate(rows, "boundary_valid"),
        "deployment_valid_rate": _rate(rows, "deployment_valid"),
        "convergence_rate": _rate(rows, "episode_converged"),
        "mean_coverage_all": _mean(rows, "coverage_ratio"),
        "mean_tracking_rmse_all": _mean(rows, "episode_final_tracking_rmse"),
        "failures": dict(failures),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--records", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    records_path = Path(args.records)
    rows = _load(records_path)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    copied = output / "records.csv"
    if records_path.resolve() != copied.resolve():
        copyfile(records_path, copied)
    aggregate = {
        "all": _block(rows),
        "by_environment": {key: _block(group) for key, group in _group(rows, "environment").items()},
        "by_shape": {key: _block(group) for key, group in _group(rows, "shape").items()},
        "by_heterogeneity": {key: _block(group) for key, group in _group(rows, "heterogeneity").items()},
        "by_split": {key: _block(group) for key, group in _seed_split(rows).items()},
    }
    (output / "aggregate.json").write_text(json.dumps(aggregate, indent=2), encoding="utf-8")
    with (output / "failure_breakdown.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["failure_reason", "count"])
        writer.writeheader()
        for reason, count in sorted(aggregate["all"]["failures"].items(), key=lambda item: -item[1]):
            writer.writerow({"failure_reason": reason, "count": count})
    def _write_group(name: str, grouped: dict[str, dict[str, object]]) -> None:
        path = output / name
        fieldnames = [
            "group",
            "n",
            "scientific_success_rate",
            "boundary_valid_rate",
            "deployment_valid_rate",
            "convergence_rate",
        ]
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for group, block in grouped.items():
                writer.writerow(
                    {
                        "group": group,
                        "n": block["n"],
                        "scientific_success_rate": block["scientific_success_rate"],
                        "boundary_valid_rate": block["boundary_valid_rate"],
                        "deployment_valid_rate": block["deployment_valid_rate"],
                        "convergence_rate": block["convergence_rate"],
                    }
                )

    _write_group("metrics_by_shape.csv", aggregate["by_shape"])
    _write_group("metrics_by_environment.csv", aggregate["by_environment"])
    readme_lines = [
        "# Step 1 known-boundary results",
        "",
        "The environment boundary is known. The crowd boundary is not known.",
        "JuPedSim spawn geometry is evaluator/simulator-only and is not exposed to ABCG.",
        "",
        "This report distinguishes **execution success** (pipeline completed without crash),",
        "**scientific success** (valid boundary, deployment, resources, plan, assignment,",
        "convergence, and sampled safety), and **failure** (kept in every denominator).",
        "",
    ]
    readme_lines.extend(_fmt_block("All records", aggregate["all"]))
    for env, block in sorted(aggregate["by_environment"].items()):
        readme_lines.extend(_fmt_block(f"Environment: {env}", block))
    for shape, block in sorted(aggregate["by_shape"].items()):
        readme_lines.extend(_fmt_block(f"Crowd shape: {shape}", block))
    for label, block in sorted(aggregate["by_heterogeneity"].items()):
        title = "Homogeneous" if label.lower() in {"false", "0", "no"} else "Heterogeneous"
        if label.lower() in {"true", "1", "yes"}:
            title = "Heterogeneous"
        readme_lines.extend(_fmt_block(title, block))
    for split, block in aggregate["by_split"].items():
        readme_lines.extend(_fmt_block(f"Split: {split}", block))
    (output / "README.md").write_text("\n".join(readme_lines), encoding="utf-8")
    print(f"wrote analysis under {output}")


if __name__ == "__main__":
    main()
