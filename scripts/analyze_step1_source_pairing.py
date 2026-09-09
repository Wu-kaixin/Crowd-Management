"""Analyze Step-1 synthetic vs JuPedSim paired evaluation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats


METRICS = {
    "coverage_ratio": "higher",
    "max_euclidean_boundary_distance": "lower",
    "radial_deployment_error": "lower",
    "angular_uniformity_error": "lower",
    "minimum_inter_guider_distance": "higher",
    "guide_crowd_safety_violation_count": "lower",
    "active_guide_count": "descriptive",
    "periodic_max_arc_gap": "lower",
    "episode_final_tracking_rmse": "lower",
    "safety_projected_steps": "descriptive",
    "safety_infeasible_steps": "lower",
}


def bootstrap_ci(
    values: np.ndarray,
    *,
    seed: int = 12345,
    samples: int = 10000,
) -> tuple[float, float]:
    values = np.asarray(values, dtype=float)

    if len(values) == 0:
        return float("nan"), float("nan")

    rng = np.random.default_rng(seed)

    means = np.empty(samples, dtype=float)

    for i in range(samples):
        sample = rng.choice(
            values,
            size=len(values),
            replace=True,
        )
        means[i] = np.mean(sample)

    return (
        float(np.percentile(means, 2.5)),
        float(np.percentile(means, 97.5)),
    )


def paired_effect(
    synthetic: np.ndarray,
    jupedsim: np.ndarray,
) -> dict:
    synthetic = np.asarray(synthetic, dtype=float)
    jupedsim = np.asarray(jupedsim, dtype=float)

    mask = (
        np.isfinite(synthetic)
        & np.isfinite(jupedsim)
    )

    synthetic = synthetic[mask]
    jupedsim = jupedsim[mask]

    delta = jupedsim - synthetic

    if len(delta) == 0:
        return {
            "n": 0,
        }

    ci_low, ci_high = bootstrap_ci(delta)

    if len(delta) >= 2 and np.std(delta, ddof=1) > 0:
        t_stat, t_p = stats.ttest_rel(
            jupedsim,
            synthetic,
        )

        try:
            w_stat, w_p = stats.wilcoxon(delta)
        except ValueError:
            w_stat = float("nan")
            w_p = float("nan")

        standardized_effect = (
            float(
                np.mean(delta)
                / np.std(delta, ddof=1)
            )
        )
    else:
        t_stat = float("nan")
        t_p = float("nan")
        w_stat = float("nan")
        w_p = float("nan")
        standardized_effect = float("nan")

    return {
        "n": int(len(delta)),
        "synthetic_mean": float(
            np.mean(synthetic)
        ),
        "jupedsim_mean": float(
            np.mean(jupedsim)
        ),
        "mean_delta_jps_minus_synthetic": float(
            np.mean(delta)
        ),
        "median_delta": float(
            np.median(delta)
        ),
        "delta_std": float(
            np.std(delta, ddof=1)
        )
        if len(delta) > 1
        else 0.0,
        "bootstrap_95_ci": [
            ci_low,
            ci_high,
        ],
        "paired_t_p": float(t_p),
        "wilcoxon_p": float(w_p),
        "standardized_paired_effect": (
            standardized_effect
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--input",
        default=(
            "reports/"
            "step1_source_pairing/"
            "records.csv"
        ),
    )

    parser.add_argument(
        "--output",
        default=(
            "reports/"
            "step1_source_pairing/"
            "analysis.json"
        ),
    )

    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    df = pd.read_csv(input_path)

    result = {
        "scope": (
            "Step-1 source robustness "
            "analysis"
        ),
        "interpretation": (
            "Paired comparison of ABCG "
            "under nominally matched "
            "synthetic and JuPedSim "
            "static crowd observations."
        ),
        "overall_run_success": {},
        "pairs": {},
    }

    for source in (
        "synthetic",
        "jupedsim",
    ):
        subset = df[
            df["source"] == source
        ]

        result[
            "overall_run_success"
        ][source] = {
            "n": int(len(subset)),
            "successes": int(
                subset["run_success"].sum()
            ),
            "rate": float(
                subset["run_success"].mean()
            ),
        }

    for pair_name in sorted(
        df["pair"].unique()
    ):
        pair_df = df[
            df["pair"] == pair_name
        ]

        synthetic = (
            pair_df[
                pair_df["source"]
                == "synthetic"
            ]
            .sort_values("seed")
            .set_index("seed")
        )

        jupedsim = (
            pair_df[
                pair_df["source"]
                == "jupedsim"
            ]
            .sort_values("seed")
            .set_index("seed")
        )

        common_seeds = (
            synthetic.index
            .intersection(
                jupedsim.index
            )
        )

        pair_result = {
            "n_paired": int(
                len(common_seeds)
            ),
            "metrics": {},
        }

        for metric, direction in (
            METRICS.items()
        ):
            if (
                metric
                not in synthetic.columns
                or metric
                not in jupedsim.columns
            ):
                continue

            s = (
                pd.to_numeric(
                    synthetic.loc[
                        common_seeds,
                        metric,
                    ],
                    errors="coerce",
                )
                .to_numpy()
            )

            j = (
                pd.to_numeric(
                    jupedsim.loc[
                        common_seeds,
                        metric,
                    ],
                    errors="coerce",
                )
                .to_numpy()
            )

            analysis = paired_effect(
                s,
                j,
            )

            analysis[
                "preferred_direction"
            ] = direction

            pair_result[
                "metrics"
            ][metric] = analysis

        result["pairs"][
            pair_name
        ] = pair_result

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with open(
        output_path,
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            result,
            file,
            indent=2,
        )

    print(
        f"Analysis written to "
        f"{output_path}"
    )


if __name__ == "__main__":
    main()