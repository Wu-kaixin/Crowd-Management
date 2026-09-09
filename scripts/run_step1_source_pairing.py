"""Paired Step-1 source robustness evaluation.

Compare ABCG under nominally matched:

    synthetic crowd observations
        vs
    JuPedSim crowd observations

Failures remain in the denominator.

This evaluation tests source robustness only.
It does not test dynamic pedestrian behaviour.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from crowd_management.experiments.static_containment import (
    run_static_containment,
)


NUMERIC_METRICS = (
    "coverage_ratio",
    "max_euclidean_boundary_distance",
    "radial_deployment_error",
    "angular_uniformity_error",
    "minimum_inter_guider_distance",
    "guide_crowd_safety_violation_count",
    "active_guide_count",
    "periodic_max_arc_gap",
    "episode_final_tracking_rmse",
    "safety_projected_steps",
    "safety_infeasible_steps",
)


def load_yaml(
    path: Path,
) -> dict[str, Any]:
    with open(
        path,
        encoding="utf-8",
    ) as file:
        return yaml.safe_load(file)


def write_seeded_config(
    source_path: Path,
    destination: Path,
    seed: int,
) -> None:
    data = load_yaml(source_path)

    data["seed"] = int(seed)

    crowd = data.setdefault(
        "crowd",
        {},
    )

    crowd["seed"] = int(seed)

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with open(
        destination,
        "w",
        encoding="utf-8",
    ) as file:
        yaml.safe_dump(
            data,
            file,
            sort_keys=False,
            allow_unicode=True,
        )


def as_number(
    value: Any,
) -> float | None:
    if isinstance(
        value,
        (int, float, np.integer, np.floating),
    ):
        return float(value)

    return None


def run_one(
    *,
    pair_name: str,
    source_name: str,
    config_path: Path,
    seed: int,
    output_root: Path,
    save_plots: bool,
) -> dict[str, Any]:
    run_dir = (
        output_root
        / "runs"
        / pair_name
        / source_name
        / f"seed_{seed:03d}"
    )

    seeded_config = (
        output_root
        / "resolved_configs"
        / pair_name
        / source_name
        / f"seed_{seed:03d}.yaml"
    )

    write_seeded_config(
        config_path,
        seeded_config,
        seed,
    )

    record: dict[str, Any] = {
        "pair": pair_name,
        "source": source_name,
        "seed": seed,
        "run_success": False,
        "run_error": "",
    }

    try:
        result = run_static_containment(
            seeded_config,
            run_dir,
            methods=["abcg"],
            save_plots=save_plots,
        )

        summary = result["abcg"]

        record["execution_success"] = True
        record["boundary_valid"] = summary.get("boundary_v2_status") == "VALID"
        record["pipeline_valid"] = summary.get("boundary_v2_status") == "VALID" and summary.get("resource_status") == "VALID" and summary.get("periodic_plan_status") == "VALID" and summary.get("assignment_status") == "VALID"
        record["episode_converged"] = summary.get("episode_status") == "CONVERGED"
        record["scientific_success"] = summary.get("method_status") == "converged_pr5_safety_filtered_episode"
        record["episode_status"] = summary.get(
            "episode_status",
            "",
        )
        record["method_status"] = summary.get(
            "method_status",
            "",
        )
        record["boundary_v2_status"] = summary.get(
            "boundary_v2_status",
            "",
        )
        record["resource_status"] = summary.get(
            "resource_status",
            "",
        )

        for metric in NUMERIC_METRICS:
            value = as_number(
                summary.get(metric)
            )

            record[metric] = (
                value
                if value is not None
                else ""
            )

    except Exception as exc:
        record["run_error"] = (
            f"{type(exc).__name__}: {exc}"
        )

    return record


def paired_deltas(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    index: dict[
        tuple[str, int, str],
        dict[str, Any],
    ] = {
        (
            str(row["pair"]),
            int(row["seed"]),
            str(row["source"]),
        ): row
        for row in records
    }

    pairs = sorted(
        {
            (
                str(row["pair"]),
                int(row["seed"]),
            )
            for row in records
        }
    )

    result: list[dict[str, Any]] = []

    for pair_name, seed in pairs:
        synthetic = index.get(
            (
                pair_name,
                seed,
                "synthetic",
            )
        )

        jupedsim = index.get(
            (
                pair_name,
                seed,
                "jupedsim",
            )
        )

        row: dict[str, Any] = {
            "pair": pair_name,
            "seed": seed,
            "paired_available": False,
        }

        if (
            synthetic is None
            or jupedsim is None
            or not synthetic["run_success"]
            or not jupedsim["run_success"]
        ):
            result.append(row)
            continue

        row["paired_available"] = True

        for metric in NUMERIC_METRICS:
            a = as_number(
                synthetic.get(metric)
            )
            b = as_number(
                jupedsim.get(metric)
            )

            if a is not None and b is not None:
                row[
                    f"delta_jupedsim_minus_synthetic__{metric}"
                ] = b - a

        result.append(row)

    return result


def aggregate(
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    output: dict[str, Any] = {}

    groups = sorted(
        {
            (
                str(row["pair"]),
                str(row["source"]),
            )
            for row in records
        }
    )

    for pair_name, source_name in groups:
        subset = [
            row
            for row in records
            if row["pair"] == pair_name
            and row["source"] == source_name
        ]

        successful = [
            row
            for row in subset
            if row["run_success"]
        ]

        group_key = (
            f"{pair_name}/{source_name}"
        )

        group: dict[str, Any] = {
            "n_total": len(subset),
            "n_successful": len(successful),
            "success_rate": (
                len(successful) / len(subset)
                if subset
                else 0.0
            ),
            "metrics": {},
        }

        for metric in NUMERIC_METRICS:
            values = [
                as_number(row.get(metric))
                for row in successful
            ]

            values = [
                value
                for value in values
                if value is not None
            ]

            if values:
                arr = np.asarray(
                    values,
                    dtype=float,
                )

                group["metrics"][metric] = {
                    "n": int(len(arr)),
                    "mean": float(
                        np.mean(arr)
                    ),
                    "std": float(
                        np.std(
                            arr,
                            ddof=1,
                        )
                    )
                    if len(arr) > 1
                    else 0.0,
                    "min": float(
                        np.min(arr)
                    ),
                    "max": float(
                        np.max(arr)
                    ),
                }

        output[group_key] = group

    return output


def write_csv(
    path: Path,
    rows: list[dict[str, Any]],
) -> None:
    if not rows:
        return

    fieldnames: list[str] = []

    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with open(
        path,
        "w",
        encoding="utf-8",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
        )

        writer.writeheader()

        for row in rows:
            writer.writerow(row)


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--manifest",
        default=(
            "configs/step1_benchmark/"
            "benchmark_manifest.yaml"
        ),
    )

    parser.add_argument(
        "--output",
        default=(
            "reports/step1_source_pairing"
        ),
    )

    parser.add_argument(
        "--seeds",
        nargs="+",
        type=int,
        default=[0, 1, 2],
    )

    parser.add_argument(
        "--save-plots",
        action="store_true",
    )

    args = parser.parse_args()

    manifest_path = Path(
        args.manifest
    ).resolve()

    output_root = Path(
        args.output
    ).resolve()

    manifest = load_yaml(
        manifest_path
    )

    config_root = (
        manifest_path.parent
    )

    records: list[
        dict[str, Any]
    ] = []

    for pair_name, pair in (
        manifest["paired_cases"].items()
    ):
        for seed in args.seeds:
            for source_name in (
                "synthetic",
                "jupedsim",
            ):
                config_path = (
                    config_root
                    / pair[source_name]
                )

                record = run_one(
                    pair_name=pair_name,
                    source_name=source_name,
                    config_path=config_path,
                    seed=seed,
                    output_root=output_root,
                    save_plots=args.save_plots,
                )

                records.append(
                    record
                )

                print(
                    pair_name,
                    source_name,
                    seed,
                    record["run_success"],
                )

    deltas = paired_deltas(
        records
    )

    summary = aggregate(
        records
    )

    write_csv(
        output_root
        / "records.csv",
        records,
    )

    write_csv(
        output_root
        / "paired_deltas.csv",
        deltas,
    )

    with open(
        output_root
        / "aggregate.json",
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            {
                "scope": (
                    "Step-1 source robustness: "
                    "synthetic vs JuPedSim"
                ),
                "seeds": args.seeds,
                "failure_policy": (
                    "Failures remain in denominator."
                ),
                "pairing_note": manifest.get(
                    "pairing_note",
                    "",
                ),
                "groups": summary,
            },
            file,
            indent=2,
        )

    print(
        f"Results written to: "
        f"{output_root}"
    )


if __name__ == "__main__":
    main()