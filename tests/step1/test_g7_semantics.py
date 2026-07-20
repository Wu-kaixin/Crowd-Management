from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from crowd_management.evaluation import (
    DeploymentMetrics,
    G7Record,
    ResourceRegime,
    audit_frozen_g6_evidence,
    compose_layered_outcome,
    failure_rate_composition,
    matched_same_resource_pairs,
    paired_bootstrap_interval,
    resource_normalized_metrics,
    split_resource_regimes,
)


def _metrics(active: int = 4, coverage: float = 0.8) -> DeploymentMetrics:
    return DeploymentMetrics(
        truth_coverage=coverage,
        maximum_consecutive_arc_gap=2.0,
        tracking_rmse=0.05,
        minimum_intersample_clearance=0.9,
        active_guide_count=active,
        path_length=12.0,
        control_energy=6.0,
        runtime_ms=20.0,
        peak_memory_bytes=1000,
    )


def _record(method: str, active: int, regime: ResourceRegime) -> G7Record:
    outcome = compose_layered_outcome(
        plan_optimal=True,
        route_feasible=True,
        controller_terminal_state="CONVERGED",
        sampled_safe=True,
        truth_criteria_met=True,
        terminal_reason="waypoints_complete",
    )
    return G7Record(
        scenario="u_shape",
        method=method,
        seed=3,
        resource_regime=regime,
        outcome=outcome,
        metrics=_metrics(active),
        config_hash="abc",
        base_sha="base",
        branch_sha="branch",
    )


def test_controller_converged_is_tracking_only_not_overall_success() -> None:
    outcome = compose_layered_outcome(
        plan_optimal=True,
        route_feasible=False,
        controller_terminal_state="CONVERGED",
        sampled_safe=True,
        truth_criteria_met=True,
        terminal_reason="legacy_controller_converged",
    )

    assert outcome.track_converged
    assert not outcome.estimated_deployment_success
    assert not outcome.truth_validated_success
    assert outcome.failure_reason == "ROUTE_INFEASIBLE"
    assert outcome.to_dict()["TRACK_CONVERGED"] is True
    assert outcome.to_dict()["ESTIMATED_DEPLOYMENT_SUCCESS"] is False


def test_truth_success_requires_every_estimated_layer_and_truth_gate() -> None:
    outcome = compose_layered_outcome(
        plan_optimal=True,
        route_feasible=True,
        controller_terminal_state="CONVERGED",
        sampled_safe=True,
        truth_criteria_met=True,
        terminal_reason="waypoints_complete",
    )

    assert outcome.estimated_deployment_success
    assert outcome.truth_validated_success
    assert outcome.failure_reason is None
    assert json.loads(json.dumps(outcome.to_dict()))["TRUTH_VALIDATED_SUCCESS"] is True


def test_resource_normalization_keeps_active_count_explicit() -> None:
    normalized = resource_normalized_metrics(_metrics(active=4, coverage=0.8))

    assert normalized == {
        "truth_coverage_per_active_guide": pytest.approx(0.2),
        "arc_gap_times_active_guide_count": pytest.approx(8.0),
        "path_length_per_active_guide": pytest.approx(3.0),
        "control_energy_per_active_guide": pytest.approx(1.5),
        "runtime_ms_per_active_guide": pytest.approx(5.0),
    }


def test_same_resource_pairs_reject_mismatched_active_counts() -> None:
    baseline = _record("straight", 4, ResourceRegime.SAME_RESOURCE)
    candidate = _record("visibility", 5, ResourceRegime.SAME_RESOURCE)

    with pytest.raises(ValueError, match="unequal active guide counts"):
        matched_same_resource_pairs(
            [baseline, candidate], baseline_method="straight", candidate_method="visibility"
        )

    groups = split_resource_regimes(
        [baseline, _record("adaptive", 5, ResourceRegime.ADAPTIVE_RESOURCE)]
    )
    assert len(groups["same_resource"]) == 1
    assert len(groups["adaptive_resource"]) == 1


def test_failure_composition_retains_every_failure_in_denominator() -> None:
    timeout = compose_layered_outcome(
        plan_optimal=True,
        route_feasible=True,
        controller_terminal_state="TIMEOUT",
        sampled_safe=True,
        truth_criteria_met=False,
        terminal_reason="no_progress",
    )
    route_failure = compose_layered_outcome(
        plan_optimal=True,
        route_feasible=False,
        controller_terminal_state="NOT_RUN",
        sampled_safe=False,
        truth_criteria_met=False,
        terminal_reason="disconnected_free_space",
    )
    success = _record("visibility", 4, ResourceRegime.SAME_RESOURCE).outcome

    composition = failure_rate_composition([timeout, route_failure, success])

    assert composition["total"] == 3
    assert composition["counts"]["TIMEOUT"] == 1
    assert composition["counts"]["ROUTE_INFEASIBLE"] == 1
    assert composition["all_records_accounted_for"]


def test_paired_bootstrap_is_reproducible_and_does_not_drop_zeroes() -> None:
    first = paired_bootstrap_interval([0.0, 1.0, -1.0, 0.5], seed=7, resamples=100)
    second = paired_bootstrap_interval([0.0, 1.0, -1.0, 0.5], seed=7, resamples=100)

    assert first == second
    assert first["count"] == 4


def test_frozen_g6_compact_evidence_is_read_only_and_hash_bound() -> None:
    repo = Path(__file__).resolve().parents[2]
    audit = audit_frozen_g6_evidence(repo)

    assert audit["base_sha"] == "1c3642c1adef0f11e0bde7651e2da64afbc45a8b"
    assert audit["file_count"] == 12
    assert audit["all_match"]
    assert all(item["matches"] for item in audit["files"].values())
    assert audit["legacy_visual_overview_file_count"] == 3
    assert audit["legacy_visual_overview_all_match"]


def test_same_resource_pairs_reject_duplicate_and_missing_records() -> None:
    baseline = _record("straight", 4, ResourceRegime.SAME_RESOURCE)
    candidate = _record("visibility", 4, ResourceRegime.SAME_RESOURCE)

    with pytest.raises(ValueError, match="duplicate same_resource"):
        matched_same_resource_pairs(
            [baseline, baseline, candidate],
            baseline_method="straight",
            candidate_method="visibility",
        )
    with pytest.raises(ValueError, match="pairing is incomplete"):
        matched_same_resource_pairs(
            [baseline],
            baseline_method="straight",
            candidate_method="visibility",
        )


def test_metrics_reject_fractional_resource_counts_and_metadata_is_strict_json() -> None:
    with pytest.raises(ValueError, match="active_guide_count"):
        DeploymentMetrics(
            truth_coverage=0.8,
            maximum_consecutive_arc_gap=2.0,
            tracking_rmse=0.1,
            minimum_intersample_clearance=0.8,
            active_guide_count=1.9,  # type: ignore[arg-type]
            path_length=1.0,
            control_energy=1.0,
            runtime_ms=1.0,
        )
    with pytest.raises(ValueError, match="peak_memory_bytes"):
        DeploymentMetrics(
            truth_coverage=0.8,
            maximum_consecutive_arc_gap=2.0,
            tracking_rmse=0.1,
            minimum_intersample_clearance=0.8,
            active_guide_count=2,
            path_length=1.0,
            control_energy=1.0,
            runtime_ms=1.0,
            peak_memory_bytes=2.7,  # type: ignore[arg-type]
        )
    record = _record("visibility", 4, ResourceRegime.SAME_RESOURCE)
    record = G7Record(
        **{**record.__dict__, "metadata": {"route_costs": np.array([1.0, np.inf])}}
    )
    payload = record.to_dict()
    assert payload["metadata"]["route_costs"] == [1.0, None]
    json.dumps(payload, allow_nan=False)
