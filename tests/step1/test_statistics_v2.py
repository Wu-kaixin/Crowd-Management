from __future__ import annotations

from dataclasses import FrozenInstanceError
import json

import numpy as np
import pytest

from crowd_management.evaluation.statistics_v2 import (
    NoninferioritySpec,
    evaluate_noninferiority,
    failure_composition,
    holm_adjustment,
    mark_pareto_nondominated,
    paired_binary_summary,
    paired_continuous_summary,
    paired_percentile_bootstrap,
    runtime_percentiles,
)


def test_paired_binary_summary_matches_hand_calculation() -> None:
    summary = paired_binary_summary(
        ["a", "b", "c", "d"],
        [False, False, True, True],
        [False, True, False, True],
        direction="higher_is_better",
        event_name="success",
        seed=17,
        resamples=200,
    )

    assert summary["n_total"] == 4
    assert summary["n_complete_pairs"] == 4
    assert summary["all_pairs_accounted_for"] is True
    assert len(summary["pair_key_sha256"]) == 64
    assert summary["baseline_event_rate"] == pytest.approx(0.5)
    assert summary["candidate_event_rate"] == pytest.approx(0.5)
    assert summary["paired_table"] == {
        "both_false": 1,
        "candidate_only_true": 1,
        "baseline_only_true": 1,
        "both_true": 1,
    }
    assert summary["paired_difference"]["mean"] == pytest.approx(0.0)
    assert summary["paired_difference"]["median"] == pytest.approx(0.0)
    assert summary["paired_difference"]["worst_5_percent_mean"] == pytest.approx(-1.0)
    assert summary["one_sided_test"]["p_value"] == pytest.approx(0.75)


def test_all_failed_binary_pairs_remain_in_denominator() -> None:
    summary = paired_binary_summary(
        list(range(5)),
        [False] * 5,
        [False] * 5,
        direction="higher_is_better",
        event_name="success",
        seed=1,
        resamples=40,
    )

    assert summary["n_total"] == 5
    assert summary["baseline_event_count"] == 0
    assert summary["candidate_event_count"] == 0
    assert summary["paired_table"]["both_false"] == 5
    assert summary["bootstrap"]["estimate"] == pytest.approx(0.0)
    assert summary["bootstrap"]["ci_low"] == pytest.approx(0.0)
    assert summary["bootstrap"]["ci_high"] == pytest.approx(0.0)
    assert summary["one_sided_test"]["p_value"] == pytest.approx(1.0)


def test_binary_adverse_event_uses_lower_is_better_direction() -> None:
    summary = paired_binary_summary(
        ["a", "b", "c", "d"],
        [True, True, False, False],
        [False, False, True, False],
        direction="lower_is_better",
        event_name="blocked_route_timeout",
        seed=9,
        resamples=100,
    )

    assert summary["direction"] == "lower_is_better"
    assert summary["event_name"] == "blocked_route_timeout"
    assert summary["baseline_event_rate"] == pytest.approx(0.5)
    assert summary["candidate_event_rate"] == pytest.approx(0.25)
    assert summary["paired_difference"]["worst_tail"] == "upper"
    assert summary["paired_difference"]["worst_5_percent_mean"] == pytest.approx(1.0)
    assert summary["one_sided_test"]["alternative"] == "candidate_less_than_baseline"
    assert summary["one_sided_test"]["favorable_pair_count"] == 2


def test_binary_direction_and_event_name_are_mandatory() -> None:
    with pytest.raises(TypeError):
        paired_binary_summary(["a"], [False], [True], seed=1)
    with pytest.raises(ValueError, match="event_name"):
        paired_binary_summary(
            ["a"],
            [False],
            [True],
            direction="higher_is_better",
            event_name=" ",
            seed=1,
        )


def test_pair_key_digest_is_deterministic_and_order_sensitive() -> None:
    first = paired_binary_summary(
        [("circle", 1), ("u_shape", 2)],
        [False, True],
        [True, False],
        direction="higher_is_better",
        event_name="success",
        seed=4,
        resamples=20,
    )
    repeated = paired_binary_summary(
        [("circle", 1), ("u_shape", 2)],
        [False, True],
        [True, False],
        direction="higher_is_better",
        event_name="success",
        seed=4,
        resamples=20,
    )
    reordered = paired_binary_summary(
        [("u_shape", 2), ("circle", 1)],
        [True, False],
        [False, True],
        direction="higher_is_better",
        event_name="success",
        seed=4,
        resamples=20,
    )

    assert first["pair_key_sha256"] == repeated["pair_key_sha256"]
    assert first["pair_key_sha256"] != reordered["pair_key_sha256"]


def test_paired_continuous_summary_matches_hand_calculation() -> None:
    summary = paired_continuous_summary(
        ["a", "b", "c", "d"],
        [1.0, 2.0, 3.0, 4.0],
        [2.0, 4.0, 2.0, 4.0],
        direction="higher_is_better",
        seed=19,
        resamples=200,
    )

    assert summary["n_total"] == 4
    assert summary["n_complete_pairs"] == 4
    assert summary["n_missing_pairs"] == 0
    assert summary["paired_difference"]["mean"] == pytest.approx(0.5)
    assert summary["paired_difference"]["median"] == pytest.approx(0.5)
    assert summary["paired_difference"]["worst_5_percent_mean"] == pytest.approx(-1.0)
    assert summary["one_sided_test"]["nonzero_pair_count"] == 3
    assert summary["one_sided_test"]["favorable_pair_count"] == 2
    assert summary["one_sided_test"]["p_value"] == pytest.approx(0.5)


def test_continuous_missing_values_are_counted_not_hidden() -> None:
    summary = paired_continuous_summary(
        ["a", "b", "c", "d"],
        [1.0, None, 3.0, None],
        [2.0, 2.0, None, None],
        direction="lower_is_better",
        seed=23,
        resamples=50,
    )

    assert summary["n_total"] == 4
    assert summary["n_complete_pairs"] == 1
    assert summary["n_missing_pairs"] == 3
    assert summary["baseline_missing_count"] == 2
    assert summary["candidate_missing_count"] == 2
    assert summary["both_missing_count"] == 1
    assert summary["all_pairs_accounted_for"] is True
    assert summary["all_pairs_complete"] is False
    assert summary["analysis_population"] == "complete_pairs_only"
    assert summary["inference_status"] == "EXPLORATORY_COMPLETE_CASE_ONLY"
    assert summary["primary_inference_permitted"] is False
    assert summary["baseline_observed"]["n"] == 2
    assert summary["candidate_observed"]["n"] == 2
    assert summary["paired_difference"]["mean"] == pytest.approx(1.0)
    assert summary["one_sided_test"]["p_value"] == pytest.approx(1.0)


def test_all_missing_continuous_pairs_have_explicit_empty_statistics() -> None:
    summary = paired_continuous_summary(
        [1, 2],
        [None, None],
        [None, None],
        direction="higher_is_better",
        seed=2,
        resamples=20,
    )

    assert summary["n_total"] == 2
    assert summary["n_complete_pairs"] == 0
    assert summary["n_missing_pairs"] == 2
    assert summary["primary_inference_permitted"] is False
    assert summary["paired_difference"]["mean"] is None
    assert summary["bootstrap"]["estimate"] is None
    assert summary["bootstrap"]["ci_low"] is None
    assert summary["bootstrap"]["status"] == "INSUFFICIENT_DATA"
    assert summary["inference_status"] == "INSUFFICIENT_DATA"
    assert summary["one_sided_test"]["status"] == "INSUFFICIENT_DATA"
    assert summary["one_sided_test"]["p_value"] is None


def test_pair_validation_rejects_duplicates_nonfinite_and_nonboolean() -> None:
    with pytest.raises(ValueError, match="duplicate pair_id"):
        paired_binary_summary(
            ["same", "same"],
            [False, True],
            [True, True],
            direction="higher_is_better",
            event_name="success",
            seed=1,
        )
    with pytest.raises(ValueError, match="must be finite"):
        paired_continuous_summary(
            ["a"],
            [np.nan],
            [1.0],
            direction="higher_is_better",
            seed=1,
        )
    with pytest.raises(ValueError, match="must be boolean"):
        paired_binary_summary(
            ["a"],
            [0],
            [1],
            direction="higher_is_better",
            event_name="success",
            seed=1,
        )


def test_bootstrap_is_reproducible_and_records_rng_contract() -> None:
    first = paired_percentile_bootstrap(
        [-1.0, 0.0, 2.0, 3.0], seed=101, resamples=300, confidence=0.95
    )
    second = paired_percentile_bootstrap(
        [-1.0, 0.0, 2.0, 3.0], seed=101, resamples=300, confidence=0.95
    )

    assert first == second
    assert first["seed"] == 101
    assert first["resamples"] == 300
    assert first["confidence"] == pytest.approx(0.95)
    assert first["interval_sidedness"] == "two_sided_central"
    assert first["status"] == "OK"
    assert first["lower_quantile"] == pytest.approx(0.025)
    assert first["upper_quantile"] == pytest.approx(0.975)
    assert first["estimate"] == pytest.approx(1.0)


def test_holm_adjustment_matches_hand_calculation_and_rejects_duplicates() -> None:
    adjusted = holm_adjustment(
        [("first", 0.01), ("second", 0.04), ("third", 0.03)], alpha=0.05
    )

    assert adjusted["family_size"] == 3
    assert adjusted["adjusted_p_values"] == pytest.approx(
        {"first": 0.03, "second": 0.06, "third": 0.06}
    )
    assert adjusted["reject"] == {
        "first": True,
        "second": False,
        "third": False,
    }
    with pytest.raises(ValueError, match="duplicate hypothesis"):
        holm_adjustment([("same", 0.01), ("same", 0.02)])
    with pytest.raises(ValueError, match="must not be empty"):
        holm_adjustment([])


def test_holm_ties_are_deterministic_and_input_order_invariant() -> None:
    hypotheses = [("beta", 0.01), ("alpha", 0.01), ("gamma", 0.04)]
    forward = holm_adjustment(hypotheses, alpha=0.05)
    reverse = holm_adjustment(list(reversed(hypotheses)), alpha=0.05)

    assert forward["adjusted_p_values"] == pytest.approx(
        reverse["adjusted_p_values"]
    )
    assert forward["reject"] == reverse["reject"]
    forward_ranks = {
        row["name"]: row["rank"] for row in forward["hypotheses"]
    }
    reverse_ranks = {
        row["name"]: row["rank"] for row in reverse["hypotheses"]
    }
    assert forward_ranks == reverse_ranks == {"alpha": 1, "beta": 2, "gamma": 3}


def test_noninferiority_uses_frozen_lower_or_upper_bound_direction() -> None:
    higher = NoninferioritySpec(
        margin_magnitude=0.05, direction="higher_is_better"
    )
    lower = NoninferioritySpec(
        margin_magnitude=2.0, direction="lower_is_better"
    )
    higher_bootstrap = paired_percentile_bootstrap(
        [0.0, 0.0], seed=31, resamples=50
    )
    lower_bootstrap = paired_percentile_bootstrap(
        [0.5, 0.5], seed=32, resamples=50
    )

    higher_result = evaluate_noninferiority(
        higher_bootstrap, higher, all_pairs_complete=True
    )
    lower_result = evaluate_noninferiority(
        lower_bootstrap, lower, all_pairs_complete=True
    )

    assert higher_result["bound_kind"] == "lower"
    assert higher_result["decision_threshold"] == pytest.approx(-0.05)
    assert higher_result["noninferior"] is True
    assert higher_result["frozen_margin_magnitude"] == pytest.approx(0.05)
    assert higher_result["interval_sidedness"] == "two_sided_central"
    assert higher_result["implied_one_sided_bound_confidence"] == pytest.approx(
        0.975
    )
    assert lower_result["bound_kind"] == "upper"
    assert lower_result["decision_threshold"] == pytest.approx(2.0)
    assert lower_result["noninferior"] is True
    failed = evaluate_noninferiority(
        paired_percentile_bootstrap([-0.06] * 3, seed=33, resamples=50),
        higher,
        all_pairs_complete=True,
    )
    boundary = evaluate_noninferiority(
        paired_percentile_bootstrap([-0.05] * 3, seed=34, resamples=50),
        higher,
        all_pairs_complete=True,
    )
    assert failed["noninferior"] is False
    assert boundary["noninferior"] is False
    assert higher.margin == pytest.approx(0.05)
    with pytest.raises(FrozenInstanceError):
        higher.margin_magnitude = 1.0  # type: ignore[misc]


def test_noninferiority_rejects_unfrozen_or_incomplete_bootstrap_contract() -> None:
    valid = paired_percentile_bootstrap([0.0, 0.1], seed=41, resamples=50)
    spec = NoninferioritySpec(
        margin_magnitude=0.1, direction="higher_is_better", confidence=0.95
    )

    with pytest.raises(ValueError, match="all paired endpoint values"):
        evaluate_noninferiority(valid, spec, all_pairs_complete=False)
    with pytest.raises(ValueError, match="confidence does not match"):
        evaluate_noninferiority(
            valid,
            NoninferioritySpec(
                margin_magnitude=0.1,
                direction="higher_is_better",
                confidence=0.90,
            ),
            all_pairs_complete=True,
        )
    with pytest.raises(ValueError, match="two_sided_central"):
        evaluate_noninferiority(
            {**valid, "interval_sidedness": "one_sided_lower"},
            spec,
            all_pairs_complete=True,
        )
    with pytest.raises(ValueError, match="quantiles"):
        evaluate_noninferiority(
            {**valid, "lower_quantile": 0.05},
            spec,
            all_pairs_complete=True,
        )
    with pytest.raises(ValueError, match="status OK"):
        evaluate_noninferiority(
            paired_percentile_bootstrap([], seed=41, resamples=50),
            spec,
            all_pairs_complete=True,
        )
    with pytest.raises(ValueError, match="margin_magnitude"):
        NoninferioritySpec(
            margin_magnitude=-0.1, direction="higher_is_better"
        )


def test_runtime_percentiles_report_p50_p95_and_missing() -> None:
    summary = runtime_percentiles([1.0, 2.0, None, 4.0, 8.0])

    assert summary["n_total"] == 5
    assert summary["n_observed"] == 4
    assert summary["n_missing"] == 1
    assert summary["p50_ms"] == pytest.approx(3.0)
    assert summary["p95_ms"] == pytest.approx(np.percentile([1.0, 2.0, 4.0, 8.0], 95.0))
    with pytest.raises(ValueError, match="non-negative"):
        runtime_percentiles([1.0, -0.1])


def test_failure_composition_keeps_every_failure() -> None:
    summary = failure_composition(
        ["ROUTE_INFEASIBLE", "TIMEOUT", "TIMEOUT", "SAMPLED_UNSAFE"],
        success_status="TRUTH_VALIDATED_SUCCESS",
        endpoint="truth_validated_success",
    )

    assert summary["endpoint"] == "truth_validated_success"
    assert summary["success_status"] == "TRUTH_VALIDATED_SUCCESS"
    assert summary["n_total"] == 4
    assert summary["success_count"] == 0
    assert summary["failure_count"] == 4
    assert summary["failure_rate"] == pytest.approx(1.0)
    assert summary["failure_counts"] == {
        "ROUTE_INFEASIBLE": 1,
        "SAMPLED_UNSAFE": 1,
        "TIMEOUT": 2,
    }
    assert summary["status_rates"]["TIMEOUT"] == pytest.approx(0.5)
    assert summary["all_records_accounted_for"] is True
    with pytest.raises(TypeError):
        failure_composition(["TRUTH_VALIDATED_SUCCESS"])


def test_failure_composition_does_not_pool_layered_success_statuses() -> None:
    summary = failure_composition(
        [
            "TRUTH_VALIDATED_SUCCESS",
            "ESTIMATED_DEPLOYMENT_SUCCESS",
            "TRUTH_VALIDATION_FAILED",
        ],
        success_status="TRUTH_VALIDATED_SUCCESS",
        endpoint="truth_validated_success",
    )

    assert summary["success_count"] == 1
    assert summary["failure_count"] == 2
    assert summary["failure_counts"]["ESTIMATED_DEPLOYMENT_SUCCESS"] == 1


def test_adaptive_resource_pareto_marks_only_strictly_dominated_points() -> None:
    marked = mark_pareto_nondominated(
        [
            {"case_id": "a", "active_guides": 3, "success_rate": 0.8},
            {"case_id": "b", "active_guides": 4, "success_rate": 0.9},
            {"case_id": "c", "active_guides": 5, "success_rate": 0.7},
            {"case_id": "a-tie", "active_guides": 3, "success_rate": 0.8},
        ],
        {"active_guides": "min", "success_rate": "max"},
    )

    by_id = {row["case_id"]: row for row in marked}
    assert by_id["a"]["pareto_nondominated"] is True
    assert by_id["a-tie"]["pareto_nondominated"] is True
    assert by_id["b"]["pareto_nondominated"] is True
    assert by_id["c"]["pareto_nondominated"] is False
    assert set(by_id["c"]["pareto_dominated_by"]) == {"a", "b", "a-tie"}
    with pytest.raises(ValueError, match="duplicate Pareto"):
        mark_pareto_nondominated(
            [{"case_id": "x", "cost": 1.0}, {"case_id": "x", "cost": 2.0}],
            {"cost": "min"},
        )
    with pytest.raises(ValueError, match="must be finite"):
        mark_pareto_nondominated(
            [{"case_id": "x", "cost": np.inf}], {"cost": "min"}
        )


def test_json_serialization_rejects_stringified_mapping_key_collision() -> None:
    with pytest.raises(ValueError, match="JSON key collision"):
        mark_pareto_nondominated(
            [{"case_id": "x", "cost": 1.0, 1: "integer", "1": "string"}],
            {"cost": "min"},
        )


def test_all_public_results_are_strict_json_safe() -> None:
    ni_bootstrap = paired_percentile_bootstrap([0.0], seed=5, resamples=10)
    payload = {
        "binary": paired_binary_summary(
            [1],
            [False],
            [True],
            direction="higher_is_better",
            event_name="success",
            seed=3,
            resamples=10,
        ),
        "continuous": paired_continuous_summary(
            [1], [None], [None], direction="higher_is_better", seed=3, resamples=10
        ),
        "holm": holm_adjustment({"endpoint": 0.2}),
        "noninferiority": evaluate_noninferiority(
            ni_bootstrap,
            NoninferioritySpec(
                margin_magnitude=0.2, direction="higher_is_better"
            ),
            all_pairs_complete=True,
        ),
        "runtime": runtime_percentiles([None]),
        "failures": failure_composition(
            ["TIMEOUT"],
            success_status="TRUTH_VALIDATED_SUCCESS",
            endpoint="truth_validated_success",
        ),
        "pareto": mark_pareto_nondominated(
            [{"case_id": np.int64(1), "cost": np.float64(2.0)}], {"cost": "min"}
        ),
    }

    encoded = json.dumps(payload, allow_nan=False, sort_keys=True)
    assert json.loads(encoded)["binary"]["n_total"] == 1
