"""Auditable paired statistics for the frozen ABCG-v2.1 G7 holdout.

All paired summaries account for the complete requested pair denominator.
Continuous endpoints may be unavailable after failed episodes, but those
records are reported as missing and any complete-case inference is explicitly
barred from primary conclusions.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Hashable, Mapping, Sequence

import numpy as np
from scipy.stats import binomtest


_DIRECTIONS = {"higher_is_better", "lower_is_better"}


@dataclass(frozen=True)
class NoninferioritySpec:
    """A pre-holdout noninferiority decision rule.

    ``margin_magnitude`` is a non-negative tolerance, not a signed effect.  On
    the candidate-minus-baseline scale, the decision threshold is
    ``-margin_magnitude`` for a higher-is-better endpoint and
    ``+margin_magnitude`` for a lower-is-better endpoint.
    """

    margin_magnitude: float
    direction: str
    confidence: float = 0.95

    def __post_init__(self) -> None:
        margin = _finite_scalar(self.margin_magnitude, "margin_magnitude")
        if margin < 0.0:
            raise ValueError("margin_magnitude must be non-negative.")
        direction = _validate_direction(self.direction)
        confidence = _finite_scalar(self.confidence, "confidence")
        if not 0.0 < confidence < 1.0:
            raise ValueError("confidence must lie strictly between zero and one.")
        object.__setattr__(self, "margin_magnitude", margin)
        object.__setattr__(self, "direction", direction)
        object.__setattr__(self, "confidence", confidence)

    @property
    def margin(self) -> float:
        """Read-only compatibility alias for the non-negative magnitude."""

        return self.margin_magnitude


def _finite_scalar(value: object, name: str) -> float:
    if isinstance(value, (bool, np.bool_)):
        raise ValueError(f"{name} must be a finite real number, not boolean.")
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a finite real number.") from error
    if not np.isfinite(result):
        raise ValueError(f"{name} must be finite.")
    return result


def _positive_integer(value: object, name: str) -> int:
    if (
        isinstance(value, (bool, np.bool_))
        or not isinstance(value, (int, np.integer))
        or int(value) < 1
    ):
        raise ValueError(f"{name} must be a positive integer.")
    return int(value)


def _seed(value: object) -> int:
    if (
        isinstance(value, (bool, np.bool_))
        or not isinstance(value, (int, np.integer))
        or int(value) < 0
    ):
        raise ValueError("seed must be a non-negative integer.")
    return int(value)


def _validate_direction(direction: str) -> str:
    value = str(direction)
    if value not in _DIRECTIONS:
        raise ValueError(
            "direction must be 'higher_is_better' or 'lower_is_better'."
        )
    return value


def _validate_pairs(
    pair_ids: Sequence[Hashable],
    baseline: Sequence[object],
    candidate: Sequence[object],
) -> tuple[list[Hashable], list[object], list[object]]:
    ids = list(pair_ids)
    left = list(baseline)
    right = list(candidate)
    if not (len(ids) == len(left) == len(right)):
        raise ValueError("pair_ids, baseline, and candidate must have equal lengths.")
    seen: set[Hashable] = set()
    for pair_id in ids:
        try:
            duplicate = pair_id in seen
        except TypeError as error:
            raise ValueError("every pair_id must be hashable.") from error
        if duplicate:
            raise ValueError(f"duplicate pair_id: {pair_id!r}")
        seen.add(pair_id)
    return ids, left, right


def _pair_key_sha256(pair_ids: Sequence[Hashable]) -> str:
    """Hash the ordered, canonical JSON representation of the pairing keys."""

    canonical = json.dumps(
        _jsonable(list(pair_ids)),
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _binary(values: Sequence[object], name: str) -> np.ndarray:
    result: list[bool] = []
    for index, value in enumerate(values):
        if not isinstance(value, (bool, np.bool_)):
            raise ValueError(f"{name}[{index}] must be boolean; missing is not allowed.")
        result.append(bool(value))
    return np.asarray(result, dtype=bool)


def _continuous(values: Sequence[object], name: str) -> tuple[np.ndarray, np.ndarray]:
    observed = np.zeros(len(values), dtype=float)
    missing = np.zeros(len(values), dtype=bool)
    for index, value in enumerate(values):
        if value is None:
            missing[index] = True
        else:
            observed[index] = _finite_scalar(value, f"{name}[{index}]")
    return observed, missing


def paired_percentile_bootstrap(
    differences: Sequence[float],
    *,
    seed: int,
    resamples: int = 2000,
    confidence: float = 0.95,
) -> dict[str, object]:
    """Percentile CI for the paired mean difference, with frozen RNG metadata."""

    random_seed = _seed(seed)
    count = _positive_integer(resamples, "resamples")
    level = _finite_scalar(confidence, "confidence")
    if not 0.0 < level < 1.0:
        raise ValueError("confidence must lie strictly between zero and one.")
    values = np.asarray(differences, dtype=float)
    if values.ndim != 1 or not np.all(np.isfinite(values)):
        raise ValueError("differences must be a finite one-dimensional sequence.")
    tail = (1.0 - level) / 2.0
    result: dict[str, object] = {
        "method": "paired_percentile_bootstrap_mean",
        "interval_sidedness": "two_sided_central",
        "status": "OK" if len(values) else "INSUFFICIENT_DATA",
        "n": int(len(values)),
        "seed": random_seed,
        "resamples": count,
        "confidence": level,
        "lower_quantile": tail,
        "upper_quantile": 1.0 - tail,
        "estimate": None,
        "ci_low": None,
        "ci_high": None,
    }
    if len(values) == 0:
        return result
    generator = np.random.default_rng(random_seed)
    indices = generator.integers(0, len(values), size=(count, len(values)))
    bootstrap_means = np.mean(values[indices], axis=1)
    result.update(
        {
            "estimate": float(np.mean(values)),
            "ci_low": float(np.quantile(bootstrap_means, tail)),
            "ci_high": float(np.quantile(bootstrap_means, 1.0 - tail)),
        }
    )
    return result


def _distribution(values: np.ndarray, direction: str) -> dict[str, object]:
    if len(values) == 0:
        return {
            "n": 0,
            "mean": None,
            "median": None,
            "worst_5_percent_mean": None,
            "worst_tail": "lower" if direction == "higher_is_better" else "upper",
        }
    tail_count = max(1, int(np.ceil(0.05 * len(values))))
    ordered = np.sort(values)
    tail = ordered[:tail_count] if direction == "higher_is_better" else ordered[-tail_count:]
    return {
        "n": int(len(values)),
        "mean": float(np.mean(values)),
        "median": float(np.median(values)),
        "worst_5_percent_mean": float(np.mean(tail)),
        "worst_tail": "lower" if direction == "higher_is_better" else "upper",
    }


def _one_sided_sign_test(differences: np.ndarray, direction: str) -> dict[str, object]:
    improvement = differences if direction == "higher_is_better" else -differences
    nonzero = improvement[improvement != 0.0]
    favorable = int(np.count_nonzero(nonzero > 0.0))
    if len(differences) == 0:
        status = "INSUFFICIENT_DATA"
        p_value = None
    else:
        status = "OK"
        p_value = (
            1.0
            if len(nonzero) == 0
            else float(
                binomtest(
                    favorable, len(nonzero), 0.5, alternative="greater"
                ).pvalue
            )
        )
    return {
        "method": "exact_paired_sign_test",
        "test_estimand": "probability_of_favorable_nonzero_pair",
        "status": status,
        "alternative": (
            "candidate_greater_than_baseline"
            if direction == "higher_is_better"
            else "candidate_less_than_baseline"
        ),
        "n_total": int(len(differences)),
        "nonzero_pair_count": int(len(nonzero)),
        "favorable_pair_count": favorable,
        "p_value": p_value,
    }


def paired_binary_summary(
    pair_ids: Sequence[Hashable],
    baseline: Sequence[bool],
    candidate: Sequence[bool],
    *,
    direction: str,
    event_name: str,
    seed: int,
    resamples: int = 2000,
    confidence: float = 0.95,
) -> dict[str, object]:
    """Summarize a complete paired binary endpoint without event filtering.

    ``True`` denotes the named event.  The explicit direction is essential for
    adverse events such as ``TIMEOUT`` where a smaller event rate is better.
    """

    ids, left_raw, right_raw = _validate_pairs(pair_ids, baseline, candidate)
    endpoint_direction = _validate_direction(direction)
    label = str(event_name).strip()
    if not label:
        raise ValueError("event_name must be non-empty.")
    left = _binary(left_raw, "baseline")
    right = _binary(right_raw, "candidate")
    differences = right.astype(float) - left.astype(float)
    bootstrap = paired_percentile_bootstrap(
        differences,
        seed=seed,
        resamples=resamples,
        confidence=confidence,
    )
    both_false = int(np.count_nonzero(~left & ~right))
    candidate_only = int(np.count_nonzero(~left & right))
    baseline_only = int(np.count_nonzero(left & ~right))
    both_true = int(np.count_nonzero(left & right))
    return {
        "schema": "abcg-v2.1-paired-binary-summary-v1",
        "difference_definition": "candidate_minus_baseline",
        "direction": endpoint_direction,
        "event_name": label,
        "pair_key_sha256": _pair_key_sha256(ids),
        "n_total": len(ids),
        "n_complete_pairs": len(ids),
        "all_pairs_accounted_for": True,
        "all_pairs_complete": True,
        "inference_status": bootstrap["status"],
        "primary_inference_permitted": len(ids) > 0,
        "baseline_event_count": int(np.count_nonzero(left)),
        "candidate_event_count": int(np.count_nonzero(right)),
        "baseline_event_rate": float(np.mean(left)) if len(left) else None,
        "candidate_event_rate": float(np.mean(right)) if len(right) else None,
        "paired_table": {
            "both_false": both_false,
            "candidate_only_true": candidate_only,
            "baseline_only_true": baseline_only,
            "both_true": both_true,
        },
        "paired_difference": {
            **_distribution(differences, endpoint_direction),
            "ci_low": bootstrap["ci_low"],
            "ci_high": bootstrap["ci_high"],
        },
        "bootstrap": bootstrap,
        "one_sided_test": _one_sided_sign_test(
            differences, endpoint_direction
        ),
    }


def paired_continuous_summary(
    pair_ids: Sequence[Hashable],
    baseline: Sequence[float | None],
    candidate: Sequence[float | None],
    *,
    direction: str,
    seed: int,
    resamples: int = 2000,
    confidence: float = 0.95,
) -> dict[str, object]:
    """Summarize paired continuous data while retaining failed/missing pairs."""

    ids, left_raw, right_raw = _validate_pairs(pair_ids, baseline, candidate)
    endpoint_direction = _validate_direction(direction)
    left, left_missing = _continuous(left_raw, "baseline")
    right, right_missing = _continuous(right_raw, "candidate")
    complete = ~(left_missing | right_missing)
    differences = right[complete] - left[complete]
    bootstrap = paired_percentile_bootstrap(
        differences,
        seed=seed,
        resamples=resamples,
        confidence=confidence,
    )
    missing_count = int(np.count_nonzero(~complete))
    complete_count = int(np.count_nonzero(complete))
    if complete_count == 0:
        inference_status = "INSUFFICIENT_DATA"
    elif missing_count == 0:
        inference_status = "VALID_ALL_PAIRS"
    else:
        inference_status = "EXPLORATORY_COMPLETE_CASE_ONLY"
    return {
        "schema": "abcg-v2.1-paired-continuous-summary-v1",
        "difference_definition": "candidate_minus_baseline",
        "direction": endpoint_direction,
        "pair_key_sha256": _pair_key_sha256(ids),
        "n_total": len(ids),
        "n_complete_pairs": complete_count,
        "n_missing_pairs": missing_count,
        "baseline_missing_count": int(np.count_nonzero(left_missing)),
        "candidate_missing_count": int(np.count_nonzero(right_missing)),
        "both_missing_count": int(np.count_nonzero(left_missing & right_missing)),
        "all_pairs_accounted_for": True,
        "all_pairs_complete": missing_count == 0,
        "analysis_population": "complete_pairs_only",
        "missing_data_policy": "no_imputation",
        "inference_status": inference_status,
        "primary_inference_permitted": complete_count > 0 and missing_count == 0,
        "baseline_observed": _distribution(left[~left_missing], endpoint_direction),
        "candidate_observed": _distribution(right[~right_missing], endpoint_direction),
        "complete_pair_baseline": _distribution(left[complete], endpoint_direction),
        "complete_pair_candidate": _distribution(right[complete], endpoint_direction),
        "paired_difference": {
            **_distribution(differences, endpoint_direction),
            "ci_low": bootstrap["ci_low"],
            "ci_high": bootstrap["ci_high"],
            "inference_status": inference_status,
        },
        "bootstrap": bootstrap,
        "one_sided_test": _one_sided_sign_test(differences, endpoint_direction),
    }


def holm_adjustment(
    hypotheses: Mapping[str, float] | Sequence[tuple[str, float]],
    *,
    alpha: float = 0.05,
) -> dict[str, object]:
    """Apply Holm family-wise adjustment with deterministic tie ordering."""

    threshold = _finite_scalar(alpha, "alpha")
    if not 0.0 < threshold < 1.0:
        raise ValueError("alpha must lie strictly between zero and one.")
    entries = list(hypotheses.items()) if isinstance(hypotheses, Mapping) else list(hypotheses)
    if not entries:
        raise ValueError("Holm hypothesis family must not be empty.")
    names: set[str] = set()
    validated: list[tuple[str, float]] = []
    for entry in entries:
        if not isinstance(entry, (tuple, list)) or len(entry) != 2:
            raise ValueError("hypotheses must contain (name, p_value) pairs.")
        name = str(entry[0])
        if not name:
            raise ValueError("hypothesis names must be non-empty.")
        if name in names:
            raise ValueError(f"duplicate hypothesis name: {name!r}")
        names.add(name)
        p_value = _finite_scalar(entry[1], f"p_value[{name!r}]")
        if not 0.0 <= p_value <= 1.0:
            raise ValueError("p-values must lie in [0, 1].")
        validated.append((name, p_value))
    ordered = sorted(validated, key=lambda item: (item[1], item[0]))
    family_size = len(ordered)
    adjusted: dict[str, float] = {}
    rejected: dict[str, bool] = {}
    running_adjusted = 0.0
    still_rejecting = True
    ranks: dict[str, int] = {}
    for index, (name, p_value) in enumerate(ordered):
        remaining = family_size - index
        running_adjusted = max(running_adjusted, min(1.0, remaining * p_value))
        adjusted[name] = running_adjusted
        local_reject = p_value <= threshold / remaining
        still_rejecting = still_rejecting and local_reject
        rejected[name] = still_rejecting
        ranks[name] = index + 1
    return {
        "method": "Holm",
        "alpha": threshold,
        "family_size": family_size,
        "hypotheses": [
            {
                "name": name,
                "raw_p_value": p_value,
                "adjusted_p_value": adjusted[name],
                "rank": ranks[name],
                "reject": rejected[name],
            }
            for name, p_value in validated
        ],
        "adjusted_p_values": {name: adjusted[name] for name, _ in validated},
        "reject": {name: rejected[name] for name, _ in validated},
    }


def evaluate_noninferiority(
    bootstrap_summary: Mapping[str, object],
    spec: NoninferioritySpec,
    *,
    all_pairs_complete: bool,
) -> dict[str, object]:
    """Evaluate NI only from a valid, complete-pair frozen bootstrap summary."""

    if not isinstance(spec, NoninferioritySpec):
        raise TypeError("spec must be NoninferioritySpec.")
    if not isinstance(all_pairs_complete, (bool, np.bool_)):
        raise ValueError("all_pairs_complete must be boolean.")
    if not bool(all_pairs_complete):
        raise ValueError("noninferiority requires all paired endpoint values.")
    if not isinstance(bootstrap_summary, Mapping):
        raise TypeError("bootstrap_summary must be a mapping.")

    required = {
        "method",
        "interval_sidedness",
        "status",
        "n",
        "seed",
        "resamples",
        "confidence",
        "lower_quantile",
        "upper_quantile",
        "estimate",
        "ci_low",
        "ci_high",
    }
    missing = sorted(required - set(bootstrap_summary))
    if missing:
        raise ValueError(f"bootstrap_summary is missing required fields: {missing!r}")
    if bootstrap_summary["method"] != "paired_percentile_bootstrap_mean":
        raise ValueError("unsupported bootstrap method for noninferiority.")
    if bootstrap_summary["interval_sidedness"] != "two_sided_central":
        raise ValueError("noninferiority requires a two_sided_central interval.")
    if bootstrap_summary["status"] != "OK":
        raise ValueError("noninferiority requires bootstrap status OK.")

    sample_count = _positive_integer(bootstrap_summary["n"], "bootstrap_summary['n']")
    random_seed = _seed(bootstrap_summary["seed"])
    resamples = _positive_integer(
        bootstrap_summary["resamples"], "bootstrap_summary['resamples']"
    )
    interval_confidence = _finite_scalar(
        bootstrap_summary["confidence"], "bootstrap_summary['confidence']"
    )
    if not np.isclose(interval_confidence, spec.confidence, rtol=0.0, atol=1.0e-12):
        raise ValueError("bootstrap confidence does not match the frozen NI spec.")
    lower_quantile = _finite_scalar(
        bootstrap_summary["lower_quantile"], "bootstrap_summary['lower_quantile']"
    )
    upper_quantile = _finite_scalar(
        bootstrap_summary["upper_quantile"], "bootstrap_summary['upper_quantile']"
    )
    expected_tail = (1.0 - interval_confidence) / 2.0
    if not (
        np.isclose(lower_quantile, expected_tail, rtol=0.0, atol=1.0e-12)
        and np.isclose(
            upper_quantile, 1.0 - expected_tail, rtol=0.0, atol=1.0e-12
        )
    ):
        raise ValueError("bootstrap quantiles do not match a central interval.")

    effect = _finite_scalar(bootstrap_summary["estimate"], "estimate")
    lower = _finite_scalar(bootstrap_summary["ci_low"], "ci_low")
    upper = _finite_scalar(bootstrap_summary["ci_high"], "ci_high")
    if lower > upper or not lower <= effect <= upper:
        raise ValueError("ci_low <= estimate <= ci_high is required.")
    if spec.direction == "higher_is_better":
        bound_kind = "lower"
        bound = lower
        decision_threshold = -spec.margin_magnitude
        passed = bound > decision_threshold
        rule = "ci_low > -margin_magnitude"
    else:
        bound_kind = "upper"
        bound = upper
        decision_threshold = spec.margin_magnitude
        passed = bound < decision_threshold
        rule = "ci_high < margin_magnitude"
    return {
        "method": "two_sided_confidence_bound_noninferiority",
        "difference_definition": "candidate_minus_baseline",
        "estimate": effect,
        "ci_low": lower,
        "ci_high": upper,
        "confidence": interval_confidence,
        "interval_sidedness": "two_sided_central",
        "lower_quantile": lower_quantile,
        "upper_quantile": upper_quantile,
        "implied_one_sided_bound_confidence": (1.0 + interval_confidence) / 2.0,
        "bootstrap_method": bootstrap_summary["method"],
        "bootstrap_status": bootstrap_summary["status"],
        "bootstrap_n": sample_count,
        "bootstrap_seed": random_seed,
        "bootstrap_resamples": resamples,
        "all_pairs_complete": True,
        "frozen_margin_magnitude": spec.margin_magnitude,
        "frozen_direction": spec.direction,
        "bound_kind": bound_kind,
        "bound_value": bound,
        "decision_threshold": decision_threshold,
        "decision_rule": rule,
        "noninferior": bool(passed),
    }


def runtime_percentiles(values: Sequence[float | None]) -> dict[str, object]:
    """Return runtime P50/P95 while exposing any unavailable measurements."""

    observed, missing = _continuous(list(values), "runtime_ms")
    valid = observed[~missing]
    if np.any(valid < 0.0):
        raise ValueError("runtime values must be non-negative.")
    return {
        "n_total": len(observed),
        "n_observed": int(len(valid)),
        "n_missing": int(np.count_nonzero(missing)),
        "p50_ms": float(np.percentile(valid, 50.0)) if len(valid) else None,
        "p95_ms": float(np.percentile(valid, 95.0)) if len(valid) else None,
    }


def failure_composition(
    terminal_statuses: Sequence[str],
    *,
    success_status: str,
    endpoint: str,
) -> dict[str, object]:
    """Count every record against one explicit, unpooled success endpoint."""

    if not isinstance(success_status, str) or not success_status.strip():
        raise ValueError("success_status must be one non-empty string.")
    if not isinstance(endpoint, str) or not endpoint.strip():
        raise ValueError("endpoint must be one non-empty string.")
    success = success_status.strip()
    endpoint_label = endpoint.strip()
    counts: dict[str, int] = {}
    for index, raw_status in enumerate(terminal_statuses):
        if not isinstance(raw_status, str) or not raw_status:
            raise ValueError(f"terminal_statuses[{index}] must be a non-empty string.")
        counts[raw_status] = counts.get(raw_status, 0) + 1
    total = len(terminal_statuses)
    success_count = counts.get(success, 0)
    failure_counts = {
        status: count for status, count in sorted(counts.items()) if status != success
    }
    failure_count = total - success_count
    status_rates = {
        status: float(count / total) if total else None
        for status, count in sorted(counts.items())
    }
    return {
        "endpoint": endpoint_label,
        "success_status": success,
        "n_total": total,
        "success_count": success_count,
        "failure_count": failure_count,
        "success_rate": float(success_count / total) if total else None,
        "failure_rate": float(failure_count / total) if total else None,
        "counts": dict(sorted(counts.items())),
        "status_rates": status_rates,
        "failure_counts": failure_counts,
        "all_records_accounted_for": sum(counts.values()) == total,
    }


def mark_pareto_nondominated(
    points: Sequence[Mapping[str, Any]],
    objectives: Mapping[str, str],
    *,
    id_key: str = "case_id",
) -> list[dict[str, object]]:
    """Mark adaptive-resource points under strict Pareto dominance."""

    if not objectives:
        raise ValueError("objectives must not be empty.")
    directions = {str(name): str(direction) for name, direction in objectives.items()}
    if any(direction not in {"min", "max"} for direction in directions.values()):
        raise ValueError("objective directions must be 'min' or 'max'.")
    rows: list[dict[str, object]] = []
    identifiers: list[Hashable] = []
    seen: set[Hashable] = set()
    objective_values: list[np.ndarray] = []
    signs = np.asarray(
        [1.0 if direction == "min" else -1.0 for direction in directions.values()]
    )
    for index, point in enumerate(points):
        if id_key not in point:
            raise ValueError(f"point {index} is missing unique id_key {id_key!r}.")
        identifier = point[id_key]
        try:
            duplicate = identifier in seen
        except TypeError as error:
            raise ValueError(f"point {index} identifier must be hashable.") from error
        if duplicate:
            raise ValueError(f"duplicate Pareto point identifier: {identifier!r}")
        seen.add(identifier)
        identifiers.append(identifier)
        values = []
        for name in directions:
            if name not in point:
                raise ValueError(f"point {identifier!r} is missing objective {name!r}.")
            values.append(_finite_scalar(point[name], f"point[{identifier!r}][{name!r}]") )
        objective_values.append(np.asarray(values) * signs)
        rows.append(_jsonable(dict(point)))
    result: list[dict[str, object]] = []
    for index, (row, value) in enumerate(zip(rows, objective_values, strict=True)):
        dominators: list[object] = []
        for other_index, other in enumerate(objective_values):
            if index == other_index:
                continue
            if np.all(other <= value) and np.any(other < value):
                dominators.append(_jsonable(identifiers[other_index]))
        result.append(
            {
                **row,
                "pareto_nondominated": len(dominators) == 0,
                "pareto_dominated_by": dominators,
                "pareto_objectives": dict(directions),
            }
        )
    return result


def _jsonable(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return [_jsonable(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return _jsonable(value.item())
    if isinstance(value, float):
        if not np.isfinite(value):
            raise ValueError("output data must not contain non-finite values.")
        return value
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            json_key = str(key)
            if json_key in result:
                raise ValueError(
                    f"JSON key collision after string conversion: {json_key!r}."
                )
            result[json_key] = _jsonable(item)
        return result
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise ValueError(f"value of type {type(value).__name__!r} is not JSON-safe.")


__all__ = [
    "NoninferioritySpec",
    "evaluate_noninferiority",
    "failure_composition",
    "holm_adjustment",
    "mark_pareto_nondominated",
    "paired_binary_summary",
    "paired_continuous_summary",
    "paired_percentile_bootstrap",
    "runtime_percentiles",
]
