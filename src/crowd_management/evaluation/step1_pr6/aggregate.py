"""PR6 aggregate summaries and paired comparisons."""
from __future__ import annotations

from typing import Any

import numpy as np

from ..shared import percentile_interval as _percentile_interval
from .config import PR6EvaluationConfig


def _aggregate_records(records: list[dict[str, Any]], config: PR6EvaluationConfig) -> dict[str, Any]:
    rng = np.random.default_rng(731_991)
    aggregate: dict[str, Any] = {}
    variants = sorted({str(record["variant"]) for record in records})
    for shape in config.shapes:
        aggregate[shape] = {}
        for variant in variants:
            subset = [record for record in records if record["shape"] == shape and record["variant"] == variant]
            valid = [record for record in subset if record["valid"]]
            aggregate[shape][variant] = {
                "run_count": len(subset),
                "valid_count": len(valid),
                "failure_count": len(subset) - len(valid),
                "failure_rate": float((len(subset) - len(valid)) / len(subset)),
                "curve_chamfer": _percentile_interval(
                    np.asarray([record["curve_chamfer"] for record in valid]),
                    rng,
                    config.confidence_interval_resamples,
                ),
                "curve_hausdorff": _percentile_interval(
                    np.asarray([record["curve_hausdorff"] for record in valid]),
                    rng,
                    config.confidence_interval_resamples,
                ),
                "length_relative_error": _percentile_interval(
                    np.asarray([record["length_relative_error"] for record in valid]),
                    rng,
                    config.confidence_interval_resamples,
                ),
                "plan_iterations": _percentile_interval(
                    np.asarray([record["plan_iterations"] for record in valid]),
                    rng,
                    config.confidence_interval_resamples,
                ),
            }
    return aggregate


def _paired_comparisons(records: list[dict[str, Any]], config: PR6EvaluationConfig) -> dict[str, Any]:
    rng = np.random.default_rng(812_377)
    by_key = {(record["shape"], record["seed"], record["variant"]): record for record in records}
    comparisons: dict[str, Any] = {}
    for shape in config.shapes:
        comparisons[shape] = {}
        for candidate, baseline in (
            ("alpha_neutral", "radial_neutral"),
            ("alpha_bootstrap_gain", "radial_neutral"),
            ("alpha_bootstrap_gain", "alpha_bootstrap_no_gain"),
        ):
            name = f"{candidate}_minus_{baseline}"
            comparisons[shape][name] = {}
            for metric in ("curve_chamfer", "curve_hausdorff", "plan_iterations"):
                differences: list[float] = []
                for seed in config.seeds:
                    candidate_record = by_key[(shape, seed, candidate)]
                    baseline_record = by_key[(shape, seed, baseline)]
                    if candidate_record[metric] is None or baseline_record[metric] is None:
                        continue
                    differences.append(float(candidate_record[metric]) - float(baseline_record[metric]))
                interval = _percentile_interval(np.asarray(differences), rng, config.confidence_interval_resamples)
                interval["win_rate_lower_is_better"] = (
                    float(np.mean(np.asarray(differences) < 0.0)) if differences else None
                )
                comparisons[shape][name][metric] = interval
    return comparisons
