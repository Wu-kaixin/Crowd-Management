"""G6 aggregate summaries and paired comparisons."""
from __future__ import annotations

from typing import Any

import numpy as np

from ..shared import bootstrap_metric_summary as _summary
from .config import G6EvaluationConfig, METRIC_DIRECTIONS


def _aggregate(records: list[dict[str, Any]], config: G6EvaluationConfig) -> dict[str, Any]:
    rng = np.random.default_rng(700_001)
    aggregate: dict[str, Any] = {}
    for scenario in config.scenarios:
        aggregate[scenario] = {}
        for method in config.methods:
            subset = [record for record in records if record["scenario"] == scenario and record["method"] == method]
            aggregate[scenario][method] = {
                "run_count": len(subset),
                "success_count": int(sum(bool(record["success"]) for record in subset)),
                "failure_count": int(sum(not bool(record["success"]) for record in subset)),
                "failure_rate": float(np.mean([not bool(record["success"]) for record in subset])) if subset else None,
                "status_counts": {
                    status: sum(record["status"] == status for record in subset)
                    for status in sorted({str(record["status"]) for record in subset})
                },
                "metrics": {
                    metric: _summary(
                        [float(record[metric]) for record in subset if record.get(metric) is not None],
                        rng,
                        config.confidence_interval_resamples,
                        direction,
                    )
                    for metric, direction in METRIC_DIRECTIONS.items()
                },
            }
    return aggregate


def _paired_comparisons(records: list[dict[str, Any]], config: G6EvaluationConfig) -> dict[str, Any]:
    rng = np.random.default_rng(700_003)
    by_key = {(record["scenario"], record["seed"], record["method"]): record for record in records}
    comparisons: dict[str, Any] = {}
    for scenario in config.scenarios:
        comparisons[scenario] = {}
        for baseline in config.methods:
            if baseline == "abcg_v2" or "abcg_v2" not in config.methods:
                continue
            comparison: dict[str, Any] = {}
            for metric in ("plan_max_arc_gap_m", "tracking_rmse_final", "path_length_m", "coverage_ratio", "total_runtime_ms"):
                differences = []
                paired_count = 0
                for seed in config.seeds:
                    full = by_key[(scenario, seed, "abcg_v2")]
                    other = by_key[(scenario, seed, baseline)]
                    if full.get(metric) is None or other.get(metric) is None:
                        continue
                    paired_count += 1
                    differences.append(float(full[metric]) - float(other[metric]))
                if differences:
                    array = np.asarray(differences)
                    indices = rng.integers(0, len(array), size=(config.confidence_interval_resamples, len(array)))
                    bootstrap = np.mean(array[indices], axis=1)
                    std = float(np.std(array, ddof=1)) if len(array) > 1 else 0.0
                    direction = METRIC_DIRECTIONS[metric]
                    wins = array < 0.0 if direction == "lower" else array > 0.0
                    comparison[metric] = {
                        "paired_count": paired_count,
                        "missing_pair_count": len(config.seeds) - paired_count,
                        "mean_difference_abcg_v2_minus_baseline": float(np.mean(array)),
                        "median_difference": float(np.median(array)),
                        "ci95_low": float(np.percentile(bootstrap, 2.5)),
                        "ci95_high": float(np.percentile(bootstrap, 97.5)),
                        "cohen_dz": float(np.mean(array) / std) if std > 0.0 else None,
                        "win_rate": float(np.mean(wins)),
                        "direction": direction,
                    }
                else:
                    comparison[metric] = {"paired_count": 0, "missing_pair_count": len(config.seeds)}
            comparisons[scenario][f"abcg_v2_minus_{baseline}"] = comparison
    return comparisons
