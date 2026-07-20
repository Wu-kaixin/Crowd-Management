from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys

import pytest

import scripts.build_step1_g7_media as media_builder
from scripts.build_step1_g7_media import (
    EVIDENCE_FILE,
    FREEZE_FILE,
    FREEZE_SCHEMA,
    MANIFEST_FILE,
    MEDIA_EVIDENCE_SCHEMA,
    MEDIA_FILES,
    RECORDS_FILE,
    RECORDS_SCHEMA,
    SUMMARY_FILE,
    SUMMARY_SCHEMA,
    EvidenceValidationError,
    build_media,
)


FROZEN_SHA = "a" * 40
CONFIG_HASH = "b" * 64


def _layers(*, estimated: bool, truth: bool) -> dict[str, bool]:
    if estimated:
        return {
            "plan_optimal": True,
            "route_feasible": True,
            "track_converged": True,
            "sampled_safe": True,
            "estimated_deployment_success": True,
            "truth_validated_success": truth,
        }
    return {
        "plan_optimal": True,
        "route_feasible": False,
        "track_converged": False,
        "sampled_safe": True,
        "estimated_deployment_success": False,
        "truth_validated_success": False,
    }


def _record(
    record_id: str,
    scenario: str,
    seed: int,
    pair_id: str,
    method: str,
    route_variant: str,
    terminal_status: str,
    *,
    estimated: bool,
    truth: bool,
    blocked: bool = False,
    resource_regime: str = "same_resource",
    controller_terminal_state: str | None = None,
    truth_coverage: float = 0.8,
    maximum_consecutive_arc_gap: float = 2.0,
    active_guide_count: int = 2,
    path_length: float | None = 12.0,
    runtime_ms: float | None = 7.0,
    tracking_rmse: float | None = None,
) -> dict[str, object]:
    record: dict[str, object] = {
        "record_id": record_id,
        "split": "holdout",
        "pilot_data_used": False,
        "frozen_sha": FROZEN_SHA,
        "config_hash": CONFIG_HASH,
        "scenario": scenario,
        "seed": seed,
        "pair_id": pair_id,
        "method": method,
        "route_variant": route_variant,
        "resource_regime": resource_regime,
        "blocked_route_episode": blocked,
        "v2_1_routing_pipeline": method != "g6_fixed_resource_rerun",
        "terminal_status": terminal_status,
        "controller_terminal_state": (
            controller_terminal_state
            if controller_terminal_state is not None
            else ("CONVERGED" if estimated else terminal_status)
        ),
        "metrics": {
            "truth_coverage": truth_coverage,
            "maximum_consecutive_arc_gap": maximum_consecutive_arc_gap,
            "active_guide_count": active_guide_count,
            "path_length": path_length,
            "runtime_ms": runtime_ms,
            "tracking_rmse": 0.0 if estimated and tracking_rmse is None else tracking_rmse,
        },
        **_layers(estimated=estimated, truth=truth),
    }
    record["media_payload_sha256"] = _canonical_record_hash(_media_payload(record))
    return record


def _records() -> list[dict[str, object]]:
    records = [
        _record(
            "000-circle-failure",
            "circle",
            10000,
            "circle-general-000",
            "straight_hungarian",
            "straight",
            "NO_PROGRESS",
            estimated=False,
            truth=False,
            truth_coverage=0.40,
            maximum_consecutive_arc_gap=3.0,
            path_length=10.0,
            runtime_ms=5.0,
        ),
        _record(
            "010-circle-success",
            "circle",
            10001,
            "circle-general-001",
            "visibility_hungarian",
            "visibility_graph",
            "TRUTH_VALIDATED_SUCCESS",
            estimated=True,
            truth=True,
            truth_coverage=0.90,
            maximum_consecutive_arc_gap=1.5,
            path_length=12.0,
            runtime_ms=6.0,
        ),
        _record(
            "020-ellipse-before",
            "ellipse",
            10002,
            "ellipse-general-000",
            "straight_hungarian",
            "straight",
            "ESTIMATED_DEPLOYMENT_SUCCESS_ONLY",
            estimated=True,
            truth=False,
            truth_coverage=0.80,
            maximum_consecutive_arc_gap=2.0,
            path_length=11.0,
            runtime_ms=5.5,
        ),
        _record(
            "021-ellipse-after",
            "ellipse",
            10002,
            "ellipse-general-000",
            "visibility_hungarian",
            "visibility_graph",
            "TRUTH_VALIDATED_SUCCESS",
            estimated=True,
            truth=True,
            truth_coverage=0.92,
            maximum_consecutive_arc_gap=1.4,
            path_length=12.5,
            runtime_ms=6.5,
        ),
        _record(
            "099-u-primary-straight",
            "u_shape",
            11001,
            "u-pair-001",
            "straight_hungarian",
            "straight",
            "ROUTE_INFEASIBLE",
            estimated=False,
            truth=False,
            blocked=True,
            truth_coverage=0.35,
            maximum_consecutive_arc_gap=3.8,
            path_length=10.0,
            runtime_ms=8.3,
        ),
        _record(
            "100-u-before",
            "u_shape",
            11001,
            "u-pair-001",
            "g6_fixed_resource_rerun",
            "g6_fixed_resource_straight",
            "ROUTE_INFEASIBLE",
            estimated=False,
            truth=False,
            blocked=True,
            controller_terminal_state="TIMEOUT",
            truth_coverage=0.30,
            maximum_consecutive_arc_gap=4.0,
            path_length=9.0,
            runtime_ms=8.0,
        ),
        _record(
            "101-u-after",
            "u_shape",
            11001,
            "u-pair-001",
            "visibility_hungarian",
            "visibility_graph",
            "TRUTH_VALIDATED_SUCCESS",
            estimated=True,
            truth=True,
            blocked=True,
            truth_coverage=0.88,
            maximum_consecutive_arc_gap=1.8,
            path_length=15.0,
            runtime_ms=9.0,
        ),
        _record(
            "102-u-visibility-ofat",
            "u_shape",
            11001,
            "u-pair-001",
            "visibility_phase0",
            "visibility_graph",
            "ROUTE_INFEASIBLE",
            estimated=False,
            truth=False,
            blocked=True,
            truth_coverage=0.50,
            maximum_consecutive_arc_gap=3.0,
            path_length=13.0,
            runtime_ms=8.5,
        ),
        _record(
            "199-c-primary-straight",
            "c_shape",
            11002,
            "c-pair-001",
            "straight_hungarian",
            "straight",
            "ROUTE_INFEASIBLE",
            estimated=False,
            truth=False,
            blocked=True,
            truth_coverage=0.32,
            maximum_consecutive_arc_gap=4.0,
            path_length=9.0,
            runtime_ms=8.5,
        ),
        _record(
            "200-c-before",
            "c_shape",
            11002,
            "c-pair-001",
            "g6_fixed_resource_rerun",
            "g6_fixed_resource_straight",
            "ROUTE_INFEASIBLE",
            estimated=False,
            truth=False,
            blocked=True,
            controller_terminal_state="TIMEOUT",
            truth_coverage=0.25,
            maximum_consecutive_arc_gap=4.2,
            path_length=8.0,
            runtime_ms=8.2,
        ),
        _record(
            "201-c-after",
            "c_shape",
            11002,
            "c-pair-001",
            "visibility_hungarian",
            "visibility_graph",
            "TRUTH_VALIDATED_SUCCESS",
            estimated=True,
            truth=True,
            blocked=True,
            truth_coverage=0.86,
            maximum_consecutive_arc_gap=1.9,
            path_length=16.0,
            runtime_ms=9.2,
        ),
    ]
    records.append(
        _record(
            "202-c-visibility-ofat",
            "c_shape",
            11002,
            "c-pair-001",
            "visibility_phase0",
            "visibility_graph",
            "ROUTE_INFEASIBLE",
            estimated=False,
            truth=False,
            blocked=True,
            truth_coverage=0.45,
            maximum_consecutive_arc_gap=3.2,
            path_length=14.0,
            runtime_ms=8.7,
        )
    )
    for scenario_index, scenario in enumerate(("circle", "ellipse", "u_shape", "c_shape")):
        seed = 12000 + scenario_index
        records.extend(
            (
                _record(
                    f"300-{scenario}-adaptive-nominal",
                    scenario,
                    seed,
                    f"{scenario}-adaptive-nominal",
                    "adaptive_nominal_visibility",
                    "visibility_graph",
                    "TRUTH_VALIDATED_SUCCESS",
                    estimated=True,
                    truth=True,
                    resource_regime="adaptive_resource",
                    truth_coverage=0.75 + 0.02 * scenario_index,
                    maximum_consecutive_arc_gap=2.5 - 0.1 * scenario_index,
                    active_guide_count=5,
                    path_length=10.0 + scenario_index,
                    runtime_ms=7.0 + scenario_index,
                ),
                _record(
                    f"310-{scenario}-adaptive-robust",
                    scenario,
                    seed,
                    f"{scenario}-adaptive-robust",
                    "adaptive_robust_visibility",
                    "visibility_graph",
                    "TRUTH_VALIDATED_SUCCESS",
                    estimated=True,
                    truth=True,
                    resource_regime="adaptive_resource",
                    truth_coverage=0.85 + 0.02 * scenario_index,
                    maximum_consecutive_arc_gap=2.0 - 0.1 * scenario_index,
                    active_guide_count=7,
                    path_length=14.0 + scenario_index,
                    runtime_ms=9.0 + scenario_index,
                ),
            )
        )
    return records


def _canonical_record_hash(record: object) -> str:
    payload = json.dumps(
        record,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _geometry(scenario: str) -> tuple[list[list[float]], list[list[float]]]:
    if scenario == "u_shape":
        source = [
            [-3.0, -3.0],
            [3.0, -3.0],
            [3.0, 3.0],
            [1.0, 3.0],
            [1.0, -1.0],
            [-1.0, -1.0],
            [-1.0, 3.0],
            [-3.0, 3.0],
        ]
    elif scenario == "c_shape":
        source = [
            [-3.0, -3.0],
            [3.0, -3.0],
            [3.0, -1.0],
            [-1.0, -1.0],
            [-1.0, 1.0],
            [3.0, 1.0],
            [3.0, 3.0],
            [-3.0, 3.0],
        ]
    else:
        source = [[-2.0, -2.0], [2.0, -2.0], [2.0, 2.0], [-2.0, 2.0]]
    truth = [[1.12 * x, 1.12 * y] for x, y in source]
    return source, truth


def _media_payload(record: dict[str, object]) -> dict[str, object]:
    scenario = str(record["scenario"])
    source, truth = _geometry(scenario)
    initial = [[-4.0, -4.0], [4.0, -4.0]]
    targets = [[-3.0, 0.0], [3.0, 0.0]]
    paths = [
        [initial[0], [-4.0, 0.0], targets[0]],
        [initial[1], [4.0, 0.0], targets[1]],
    ]
    if bool(record["estimated_deployment_success"]):
        trajectories = [
            [initial[0], [-4.0, -2.0], [-4.0, 0.0], targets[0]],
            [initial[1], [4.0, -2.0], [4.0, 0.0], targets[1]],
        ]
    else:
        trajectories = [
            [initial[0], [-3.8, -3.7]],
            [initial[1], [3.8, -3.7]],
        ]
    return {
        "truth_boundary": truth,
        "source_polygon": source,
        "targets": targets,
        "initial_positions": initial,
        "paths": paths,
        "trajectories": trajectories,
    }


def _case(
    record: dict[str, object],
    *,
    selection_rule: str,
) -> dict[str, object]:
    payload = _media_payload(record)
    return {
        "source_record_id": record["record_id"],
        "source_record_sha256": _canonical_record_hash(record),
        "scenario": record["scenario"],
        "seed": record["seed"],
        "pair_id": record["pair_id"],
        "method": record["method"],
        "route_variant": record["route_variant"],
        "resource_regime": record["resource_regime"],
        "selection_rule": selection_rule,
        "terminal_status": record["terminal_status"],
        "controller_terminal_state": record["controller_terminal_state"],
        **{field: record[field] for field in media_builder.LAYER_FIELDS},
        **payload,
    }


def _freeze(records: list[dict[str, object]]) -> dict[str, object]:
    methods = {str(record["method"]) for record in records}
    v2_records = [record for record in records if record["v2_1_routing_pipeline"]]
    g6_records = [record for record in records if not record["v2_1_routing_pipeline"]]
    return {
        "schema": FREEZE_SCHEMA,
        "frozen_head": FROZEN_SHA,
        "resolved_config_sha256": CONFIG_HASH,
        "expected_holdout_method_count": len(methods),
        "expected_holdout_record_count": len(records),
        "expected_holdout_v2_1_method_count": len(
            {str(record["method"]) for record in v2_records}
        ),
        "expected_holdout_v2_1_record_count": len(v2_records),
        "expected_g6_tracking_comparator_method_count": len(
            {str(record["method"]) for record in g6_records}
        ),
        "expected_g6_tracking_comparator_record_count": len(g6_records),
        "clean_at_freeze": True,
        "pilot_data_permitted_in_holdout": False,
    }


def _summary(records: list[dict[str, object]]) -> dict[str, object]:
    def metric(record: dict[str, object], field: str) -> float | int | None:
        metrics = record["metrics"]
        assert isinstance(metrics, dict)
        value = metrics[field]
        return value if value is None else float(value)

    def median(selected: list[dict[str, object]], field: str) -> float | None:
        values = [metric(record, field) for record in selected]
        observed = [float(value) for value in values if value is not None]
        return float(statistics.median(observed)) if observed else None

    scenarios = ("circle", "ellipse", "u_shape", "c_shape")
    scenario_summary: dict[str, dict[str, object]] = {}
    same_resource: list[dict[str, object]] = []
    for scenario in scenarios:
        candidate = [
            record
            for record in records
            if record["scenario"] == scenario
            and record["method"] == "visibility_hungarian"
            and record["resource_regime"] == "same_resource"
        ]
        blocked = [record for record in candidate if record["blocked_route_episode"]]
        scenario_summary[scenario] = {
            "estimated_deployment_success_rate": sum(
                bool(record["estimated_deployment_success"]) for record in candidate
            )
            / len(candidate),
            "truth_validated_success_rate": sum(
                bool(record["truth_validated_success"]) for record in candidate
            )
            / len(candidate),
            "blocked_route_timeout_rate": (
                sum(record["controller_terminal_state"] == "TIMEOUT" for record in blocked)
                / len(blocked)
                if blocked
                else None
            ),
            "truth_coverage": median(candidate, "truth_coverage"),
            "maximum_consecutive_arc_gap": median(
                candidate, "maximum_consecutive_arc_gap"
            ),
            "active_guide_count": int(round(median(candidate, "active_guide_count") or 0.0)),
            "method": "visibility_hungarian",
            "resource_regime": "same_resource",
            "denominator": len(candidate),
        }
        for method in media_builder.PRIMARY_METHODS:
            selected = [
                record
                for record in records
                if record["scenario"] == scenario
                and record["method"] == method
                and record["resource_regime"] == "same_resource"
            ]
            same_resource.append(
                {
                    "scenario": scenario,
                    "method": method,
                    "truth_coverage": median(selected, "truth_coverage"),
                    "maximum_consecutive_arc_gap": median(
                        selected, "maximum_consecutive_arc_gap"
                    ),
                    "active_guide_count": int(
                        round(median(selected, "active_guide_count") or 0.0)
                    ),
                }
            )
    adaptive: list[dict[str, object]] = []
    adaptive_keys = sorted(
        {
            (
                str(record["scenario"]),
                str(record["method"]),
                int(metric(record, "active_guide_count") or 0),
            )
            for record in records
            if record["resource_regime"] == "adaptive_resource"
        }
    )
    for scenario, method_name, count in adaptive_keys:
        selected = [
            record
            for record in records
            if record["scenario"] == scenario
            and record["method"] == method_name
            and record["resource_regime"] == "adaptive_resource"
            and int(metric(record, "active_guide_count") or 0) == count
        ]
        adaptive.append(
            {
                "scenario": scenario,
                "method": method_name,
                "resource_regime": "adaptive_resource",
                "aggregation": "median_by_scenario_method_active_count",
                "denominator": len(selected),
                "active_guide_count": count,
                "truth_coverage": median(selected, "truth_coverage"),
                "maximum_consecutive_arc_gap": median(
                    selected, "maximum_consecutive_arc_gap"
                ),
                "path_length": median(selected, "path_length"),
                "runtime_ms": median(selected, "runtime_ms"),
            }
        )
    v2_records = [record for record in records if record["v2_1_routing_pipeline"]]
    g6_records = [record for record in records if not record["v2_1_routing_pipeline"]]
    failure_counts: dict[str, int] = {}
    for record in v2_records:
        status = str(record["terminal_status"])
        failure_counts[status] = failure_counts.get(status, 0) + 1
    controller_terminal_counts: dict[str, int] = {}
    for record in g6_records:
        status = str(record["controller_terminal_state"])
        controller_terminal_counts[status] = controller_terminal_counts.get(status, 0) + 1
    blocked_g6 = [record for record in g6_records if record["blocked_route_episode"]]
    blocked_timeout_count = sum(
        record["controller_terminal_state"] == "TIMEOUT" for record in blocked_g6
    )

    blocked_scenarios: dict[str, dict[str, object]] = {}
    for scenario in ("u_shape", "c_shape"):
        pair_ids = sorted(
            {
                str(record["pair_id"])
                for record in records
                if record["scenario"] == scenario
                and record["blocked_route_episode"]
                and record["resource_regime"] == "same_resource"
            }
        )
        baseline = [
            record
            for record in records
            if record["scenario"] == scenario
            and record["method"] == "g6_fixed_resource_rerun"
            and record["pair_id"] in pair_ids
        ]
        candidate = [
            record
            for record in records
            if record["scenario"] == scenario
            and record["method"] == "visibility_hungarian"
            and record["pair_id"] in pair_ids
        ]
        baseline_rate = sum(
            record["controller_terminal_state"] == "TIMEOUT" for record in baseline
        ) / len(pair_ids)
        candidate_rate = sum(
            record["controller_terminal_state"] == "TIMEOUT" for record in candidate
        ) / len(pair_ids)
        blocked_scenarios[scenario] = {
            "pair_ids": pair_ids,
            "resource_regime": "same_resource",
            "denominator": len(pair_ids),
            "baseline_timeout_rate": baseline_rate,
            "candidate_timeout_rate": candidate_rate,
            "paired_difference": candidate_rate - baseline_rate,
            "paired_bootstrap_ci95": [
                candidate_rate - baseline_rate,
                candidate_rate - baseline_rate,
            ],
        }
    return {
        "schema": SUMMARY_SCHEMA,
        "split": "holdout",
        "pilot_data_used": False,
        "frozen_sha": FROZEN_SHA,
        "config_hash": CONFIG_HASH,
        "records_sha256": "0" * 64,
        "record_count": len(records),
        "experiment_scale": {
            "total_records": len(records),
            "v2_1_deployment_records": len(v2_records),
            "g6_tracking_comparator_records": len(g6_records),
            "v2_1_method_count": len({str(record["method"]) for record in v2_records}),
            "g6_tracking_comparator_method_count": len(
                {str(record["method"]) for record in g6_records}
            ),
        },
        "scenario_summary": scenario_summary,
        "same_resource": same_resource,
        "adaptive_pareto": adaptive,
        "failure_composition": {
            "total": len(v2_records),
            "all_records_accounted_for": True,
            "counts": dict(sorted(failure_counts.items())),
        },
        "g6_tracking_comparator": {
            "record_count": len(g6_records),
            "blocked_record_count": len(blocked_g6),
            "controller_terminal_counts": dict(sorted(controller_terminal_counts.items())),
            "controller_terminal_rates": {
                status: count / len(g6_records)
                for status, count in sorted(controller_terminal_counts.items())
            },
            "blocked_timeout_count": blocked_timeout_count,
            "blocked_timeout_rate": (
                blocked_timeout_count / len(blocked_g6) if blocked_g6 else None
            ),
            "semantics": "G6 tracking-only comparator; v2.1 deployment layers are not asserted.",
        },
        "blocked_timeout_paired": {
            "baseline_label": (
                "Frozen G6 fixed-resource straight-feedback adapter rerun on matched G7 holdout"
            ),
            "candidate_label": "ABCG-v2.1 visibility-graph routing",
            "scenarios": blocked_scenarios,
        },
    }


def _evidence(records: list[dict[str, object]]) -> dict[str, object]:
    by_id = {str(record["record_id"]): record for record in records}
    v2_records = [
        record
        for record in records
        if record["v2_1_routing_pipeline"]
        and record["method"] != "g6_fixed_resource_rerun"
    ]
    successes = sorted(
        (record for record in v2_records if record["truth_validated_success"]),
        key=lambda record: str(record["record_id"]),
    )
    failures = sorted(
        (record for record in v2_records if not record["truth_validated_success"]),
        key=lambda record: str(record["record_id"]),
    )
    return {
        "schema": MEDIA_EVIDENCE_SCHEMA,
        "split": "holdout",
        "pilot_data_used": False,
        "frozen_sha": FROZEN_SHA,
        "config_hash": CONFIG_HASH,
        "records_sha256": "0" * 64,
        "record_count": len(records),
        "success_case": (
            _case(
                successes[0],
                selection_rule="first_v2_1_truth_success_by_frozen_record_id",
            )
            if successes
            else None
        ),
        "failure_case": (
            _case(
                failures[0],
                selection_rule="first_v2_1_truth_failure_by_frozen_record_id",
            )
            if failures
            else None
        ),
        "u_shape_comparison": {
            "before": _case(
                by_id["100-u-before"],
                selection_rule="first_complete_blocked_pair_by_frozen_pair_id",
            ),
            "after": _case(
                by_id["101-u-after"],
                selection_rule="first_complete_blocked_pair_by_frozen_pair_id",
            ),
        },
        "c_shape_comparison": {
            "before": _case(
                by_id["200-c-before"],
                selection_rule="first_complete_blocked_pair_by_frozen_pair_id",
            ),
            "after": _case(
                by_id["201-c-after"],
                selection_rule="first_complete_blocked_pair_by_frozen_pair_id",
            ),
        },
    }


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, allow_nan=True, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def _write_json(path: Path, value: object) -> None:
    path.write_bytes(_json_bytes(value))


def _write_inputs(
    root: Path, records_override: list[dict[str, object]] | None = None
) -> dict[str, object]:
    root.mkdir(parents=True)
    records = _records() if records_override is None else records_override
    records_document: dict[str, object] = {
        "schema": RECORDS_SCHEMA,
        "split": "holdout",
        "pilot_data_used": False,
        "frozen_sha": FROZEN_SHA,
        "config_hash": CONFIG_HASH,
        "record_count": len(records),
        "records": records,
    }
    records_payload = _json_bytes(records_document)
    records_hash = hashlib.sha256(records_payload).hexdigest()
    summary = _summary(records)
    evidence = _evidence(records)
    summary["records_sha256"] = records_hash
    evidence["records_sha256"] = records_hash
    freeze = _freeze(records)
    _write_json(root / FREEZE_FILE, freeze)
    (root / RECORDS_FILE).write_bytes(records_payload)
    _write_json(root / SUMMARY_FILE, summary)
    _write_json(root / EVIDENCE_FILE, evidence)
    return {
        "freeze": freeze,
        "records": records_document,
        "summary": summary,
        "evidence": evidence,
    }


def _write_linked_documents(
    root: Path,
    records_document: dict[str, object],
    summary: dict[str, object],
    evidence: dict[str, object],
) -> None:
    records = records_document["records"]
    assert isinstance(records, list)
    record_count = len(records)
    records_document["record_count"] = record_count
    records_payload = _json_bytes(records_document)
    records_hash = hashlib.sha256(records_payload).hexdigest()
    (root / RECORDS_FILE).write_bytes(records_payload)
    freeze = _load(root / FREEZE_FILE)
    refreshed_freeze = _freeze(records)
    for field in (
        "expected_holdout_method_count",
        "expected_holdout_record_count",
        "expected_holdout_v2_1_method_count",
        "expected_holdout_v2_1_record_count",
        "expected_g6_tracking_comparator_method_count",
        "expected_g6_tracking_comparator_record_count",
    ):
        freeze[field] = refreshed_freeze[field]
    summary["records_sha256"] = records_hash
    summary["record_count"] = record_count
    evidence["records_sha256"] = records_hash
    evidence["record_count"] = record_count
    _write_json(root / FREEZE_FILE, freeze)
    _write_json(root / SUMMARY_FILE, summary)
    _write_json(root / EVIDENCE_FILE, evidence)


def _rebind_cases(
    root: Path,
    evidence: dict[str, object],
    cases: list[dict[str, object]],
) -> None:
    records_document = _load(root / RECORDS_FILE)
    records = records_document["records"]
    assert isinstance(records, list)
    by_id = {str(record["record_id"]): record for record in records}
    for case in cases:
        record = by_id[str(case["source_record_id"])]
        if case["estimated_deployment_success"]:
            squared_errors = [
                (float(trajectory[-1][0]) - float(target[0])) ** 2
                + (float(trajectory[-1][1]) - float(target[1])) ** 2
                for target, trajectory in zip(
                    case["targets"], case["trajectories"], strict=True
                )
            ]
            record["metrics"]["tracking_rmse"] = (  # type: ignore[index]
                sum(squared_errors) / len(squared_errors)
            ) ** 0.5
        record["media_payload_sha256"] = _canonical_record_hash(
            {field: case[field] for field in media_builder.MEDIA_PAYLOAD_FIELDS}
        )
        case["source_record_sha256"] = _canonical_record_hash(record)
    summary = _load(root / SUMMARY_FILE)
    _write_linked_documents(root, records_document, summary, evidence)


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_builds_seven_media_from_four_linked_holdout_inputs(tmp_path: Path) -> None:
    input_dir = tmp_path / "compact"
    output_dir = tmp_path / "media"
    _write_inputs(input_dir)

    manifest = build_media(input_dir, output_dir)

    assert manifest["split"] == "holdout"
    assert manifest["pilot_data_used"] is False
    assert manifest["record_count"] == len(_records())
    fixture_records = _records()
    assert manifest["filter"]["compact_record_count"] == len(fixture_records)
    assert manifest["filter"]["v2_1_failure_denominator"] == sum(
        bool(record["v2_1_routing_pipeline"]) for record in fixture_records
    )
    assert manifest["filter"]["g6_tracking_comparator_denominator"] == sum(
        not bool(record["v2_1_routing_pipeline"]) for record in fixture_records
    )
    assert manifest["filter"]["best_case_selection_performed"] is False
    assert manifest["filter"]["selected_source_record_ids"]["success_case"] == (
        "010-circle-success"
    )
    assert manifest["filter"]["selected_source_record_ids"]["failure_case"] == (
        "000-circle-failure"
    )
    assert set(manifest["inputs"]) == {FREEZE_FILE, RECORDS_FILE, SUMMARY_FILE, EVIDENCE_FILE}
    assert set(manifest["outputs"]) == set(MEDIA_FILES)
    for name in MEDIA_FILES:
        path = output_dir / name
        assert path.is_file() and path.stat().st_size > 0
        assert manifest["outputs"][name]["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert json.loads((output_dir / MANIFEST_FILE).read_text(encoding="utf-8")) == manifest
    assert (output_dir / "success_case.gif").read_bytes().startswith(b"GIF")


def test_blocked_timeout_validation_retains_candidate_terminal_composition(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "compact"
    written = _write_inputs(input_dir)
    records_document = written["records"]
    records = records_document["records"]
    assert isinstance(records, list)

    validated = media_builder._validate_blocked_pairs(
        written["summary"]["blocked_timeout_paired"], records
    )

    for scenario in ("u_shape", "c_shape"):
        item = validated["scenarios"][scenario]
        assert sum(item["candidate_terminal_counts"].values()) == item["denominator"]


@pytest.mark.parametrize("all_truth_success", [False, True])
def test_missing_success_or_failure_uses_honest_placeholder_media(
    tmp_path: Path, all_truth_success: bool
) -> None:
    records = _records()
    for record in records:
        if all_truth_success:
            record.update(
                terminal_status="TRUTH_VALIDATED_SUCCESS",
                controller_terminal_state="CONVERGED",
                **_layers(estimated=True, truth=True),
            )
        else:
            record.update(
                terminal_status="NO_PROGRESS",
                controller_terminal_state="NO_PROGRESS",
                **_layers(estimated=False, truth=False),
            )
        record["metrics"]["tracking_rmse"] = 0.0 if all_truth_success else None  # type: ignore[index]
        record["media_payload_sha256"] = _canonical_record_hash(_media_payload(record))
    input_dir = tmp_path / "compact"
    output_dir = tmp_path / "media"
    _write_inputs(input_dir, records)

    manifest = build_media(input_dir, output_dir)

    selected = manifest["filter"]["selected_source_record_ids"]
    if all_truth_success:
        assert selected["success_case"] is not None
        assert selected["failure_case"] is None
        assert manifest["filter"]["failure_media_is_placeholder"] is True
        assert manifest["filter"]["failure_exemplar_status"] == (
            "UNAVAILABLE_NO_V2_1_TRUTH_FAILURE"
        )
    else:
        assert selected["success_case"] is None
        assert selected["failure_case"] is not None
        assert manifest["filter"]["success_media_is_placeholder"] is True
        assert manifest["filter"]["success_exemplar_status"] == (
            "UNAVAILABLE_NO_V2_1_TRUTH_VALIDATED_SUCCESS"
        )
    assert (output_dir / "success_case.gif").read_bytes().startswith(b"GIF")
    assert (output_dir / "failure_case.png").is_file()


@pytest.mark.parametrize("all_truth_success", [False, True])
def test_missing_exemplar_may_not_be_spoofed(
    tmp_path: Path, all_truth_success: bool
) -> None:
    records = _records()
    for record in records:
        record.update(
            terminal_status=("TRUTH_VALIDATED_SUCCESS" if all_truth_success else "NO_PROGRESS"),
            controller_terminal_state=("CONVERGED" if all_truth_success else "NO_PROGRESS"),
            **_layers(estimated=all_truth_success, truth=all_truth_success),
        )
        record["metrics"]["tracking_rmse"] = 0.0 if all_truth_success else None  # type: ignore[index]
        record["media_payload_sha256"] = _canonical_record_hash(_media_payload(record))
    input_dir = tmp_path / "compact"
    _write_inputs(input_dir, records)
    evidence = _load(input_dir / EVIDENCE_FILE)
    if all_truth_success:
        evidence["failure_case"] = copy.deepcopy(evidence["success_case"])
    else:
        evidence["success_case"] = copy.deepcopy(evidence["failure_case"])
    _write_json(input_dir / EVIDENCE_FILE, evidence)

    with pytest.raises(EvidenceValidationError, match="must be null"):
        build_media(input_dir, tmp_path / "media")


@pytest.mark.parametrize(
    ("filename", "mutate"),
    [
        (FREEZE_FILE, lambda value: value.update(pilot_data_permitted_in_holdout=True)),
        (RECORDS_FILE, lambda value: value.update(pilot_data_used=True)),
        (SUMMARY_FILE, lambda value: value.update(pilot_data_used=True)),
        (EVIDENCE_FILE, lambda value: value.update(pilot_data_used=True)),
    ],
)
def test_rejects_pilot_spoof_in_every_contract_file(
    tmp_path: Path, filename: str, mutate: object
) -> None:
    input_dir = tmp_path / "compact"
    output_dir = tmp_path / "media"
    _write_inputs(input_dir)
    value = _load(input_dir / filename)
    mutate(value)  # type: ignore[operator]
    _write_json(input_dir / filename, value)

    with pytest.raises(EvidenceValidationError):
        build_media(input_dir, output_dir)
    assert not output_dir.exists()


@pytest.mark.parametrize("mutation", ["frozen_sha", "config_hash", "records_hash", "record_count"])
def test_rejects_broken_freeze_or_records_binding(tmp_path: Path, mutation: str) -> None:
    input_dir = tmp_path / "compact"
    output_dir = tmp_path / "media"
    _write_inputs(input_dir)
    summary = _load(input_dir / SUMMARY_FILE)
    if mutation == "frozen_sha":
        summary["frozen_sha"] = "c" * 40
    elif mutation == "config_hash":
        summary["config_hash"] = "d" * 64
    elif mutation == "records_hash":
        summary["records_sha256"] = "e" * 64
    else:
        summary["record_count"] = 6
    _write_json(input_dir / SUMMARY_FILE, summary)

    with pytest.raises(EvidenceValidationError):
        build_media(input_dir, output_dir)
    assert not output_dir.exists()


@pytest.mark.parametrize("section", ["scenario", "same_resource", "adaptive_pareto"])
def test_rejects_summary_metrics_not_recomputed_from_compact_records(
    tmp_path: Path, section: str
) -> None:
    input_dir = tmp_path / "compact"
    _write_inputs(input_dir)
    summary = _load(input_dir / SUMMARY_FILE)
    if section == "scenario":
        row = summary["scenario_summary"]["circle"]  # type: ignore[index]
        row["truth_coverage"] = float(row["truth_coverage"]) - 0.01
    elif section == "same_resource":
        row = summary["same_resource"][0]  # type: ignore[index]
        row["maximum_consecutive_arc_gap"] = float(
            row["maximum_consecutive_arc_gap"]
        ) + 0.01
    else:
        row = summary["adaptive_pareto"][0]  # type: ignore[index]
        row["path_length"] = float(row["path_length"]) + 0.01
    _write_json(input_dir / SUMMARY_FILE, summary)

    with pytest.raises(EvidenceValidationError, match="recomputed|compact records"):
        build_media(input_dir, tmp_path / "media")


@pytest.mark.parametrize("field", ["metrics", "media_payload_sha256"])
def test_compact_record_requires_recomputable_metrics_and_media_binding(
    tmp_path: Path, field: str
) -> None:
    input_dir = tmp_path / "compact"
    _write_inputs(input_dir)
    records = _load(input_dir / RECORDS_FILE)
    del records["records"][0][field]  # type: ignore[index]
    _write_json(input_dir / RECORDS_FILE, records)

    with pytest.raises(EvidenceValidationError, match=field):
        build_media(input_dir, tmp_path / "media")


def test_g6_tracking_failure_is_never_selected_as_v2_1_failure_exemplar(
    tmp_path: Path,
) -> None:
    records = _records()
    records.append(
        _record(
            "000-a-g6-tracking-failure",
            "circle",
            9999,
            "circle-g6-comparator-extra",
            "g6_fixed_resource_rerun",
            "g6_fixed_resource_straight",
            "PLAN_NOT_OPTIMAL",
            estimated=False,
            truth=False,
            controller_terminal_state="TIMEOUT",
        )
    )
    input_dir = tmp_path / "compact"
    _write_inputs(input_dir, records)

    manifest = build_media(input_dir, tmp_path / "media")

    assert manifest["filter"]["selected_source_record_ids"]["failure_case"] == (
        "000-circle-failure"
    )


@pytest.mark.parametrize(
    ("status", "controller_status"),
    [
        ("DEGRADED", "TIMEOUT"),
        ("OFFSET_INVALID", "TIMEOUT"),
        ("ASSIGNMENT_INFEASIBLE", "TIMEOUT"),
        ("G6_TRACK_CONVERGED_ONLY", "CONVERGED"),
    ],
)
def test_accepts_frozen_g6_adapter_terminal_vocabulary(
    tmp_path: Path, status: str, controller_status: str
) -> None:
    records = _records()
    before = next(record for record in records if record["record_id"] == "100-u-before")
    before["terminal_status"] = status
    before["controller_terminal_state"] = controller_status
    before["media_payload_sha256"] = _canonical_record_hash(_media_payload(before))
    input_dir = tmp_path / "compact"
    _write_inputs(input_dir, records)

    manifest = build_media(input_dir, tmp_path / "media")

    assert manifest["filter"]["g6_tracking_comparator_denominator"] == 2


def test_rejects_mixed_v2_1_and_g6_failure_denominators(tmp_path: Path) -> None:
    input_dir = tmp_path / "compact"
    _write_inputs(input_dir)
    summary = _load(input_dir / SUMMARY_FILE)
    summary["failure_composition"]["total"] += 1  # type: ignore[index,operator]
    _write_json(input_dir / SUMMARY_FILE, summary)

    with pytest.raises(EvidenceValidationError, match="v2.1 deployment record count"):
        build_media(input_dir, tmp_path / "media")


def test_rejects_false_v2_1_pipeline_flag_on_non_g6_method(tmp_path: Path) -> None:
    input_dir = tmp_path / "compact"
    _write_inputs(input_dir)
    records = _load(input_dir / RECORDS_FILE)
    records["records"][0]["v2_1_routing_pipeline"] = False  # type: ignore[index]
    _write_json(input_dir / RECORDS_FILE, records)

    with pytest.raises(EvidenceValidationError, match="false only for the frozen G6"):
        build_media(input_dir, tmp_path / "media")


def test_paired_timeout_denominator_cannot_omit_a_blocked_pair(tmp_path: Path) -> None:
    input_dir = tmp_path / "compact"
    _write_inputs(input_dir)
    records_document = _load(input_dir / RECORDS_FILE)
    records = records_document["records"]
    records.extend(  # type: ignore[union-attr]
        [
            _record(
                "110-u-before",
                "u_shape",
                11003,
                "u-pair-002",
                "g6_fixed_resource_rerun",
                "g6_fixed_resource_straight",
                "ROUTE_INFEASIBLE",
                estimated=False,
                truth=False,
                blocked=True,
                controller_terminal_state="TIMEOUT",
            ),
            _record(
                "111-u-after",
                "u_shape",
                11003,
                "u-pair-002",
                "visibility_hungarian",
                "visibility_graph",
                "TRUTH_VALIDATED_SUCCESS",
                estimated=True,
                truth=True,
                blocked=True,
            ),
        ]
    )
    assert isinstance(records, list)
    summary = _summary(records)
    omitted = summary["blocked_timeout_paired"]["scenarios"]["u_shape"]  # type: ignore[index]
    omitted["pair_ids"] = ["u-pair-001"]
    omitted["denominator"] = 1
    evidence = _load(input_dir / EVIDENCE_FILE)
    _write_linked_documents(input_dir, records_document, summary, evidence)

    with pytest.raises(EvidenceValidationError, match="every blocked-route pair"):
        build_media(input_dir, tmp_path / "media")


def test_accepts_convex_method_estimates_for_concave_truth(tmp_path: Path) -> None:
    input_dir = tmp_path / "compact"
    _write_inputs(input_dir)
    evidence = _load(input_dir / EVIDENCE_FILE)
    rectangle = [[-3.0, -3.0], [3.0, -3.0], [3.0, 3.0], [-3.0, 3.0]]
    before = evidence["u_shape_comparison"]["before"]  # type: ignore[index]
    after = evidence["u_shape_comparison"]["after"]  # type: ignore[index]
    before["source_polygon"] = rectangle
    after["source_polygon"] = rectangle
    _rebind_cases(input_dir, evidence, [before, after])

    manifest = build_media(input_dir, tmp_path / "media")

    assert len(manifest["outputs"]["u_c_route_comparison.png"]["sha256"]) == 64


def test_rejects_rectangle_truth_disguised_as_u_shape(tmp_path: Path) -> None:
    input_dir = tmp_path / "compact"
    _write_inputs(input_dir)
    evidence = _load(input_dir / EVIDENCE_FILE)
    rectangle = [[-3.0, -3.0], [3.0, -3.0], [3.0, 3.0], [-3.0, 3.0]]
    before = evidence["u_shape_comparison"]["before"]  # type: ignore[index]
    after = evidence["u_shape_comparison"]["after"]  # type: ignore[index]
    before["truth_boundary"] = rectangle
    after["truth_boundary"] = rectangle
    _rebind_cases(input_dir, evidence, [before, after])

    with pytest.raises(EvidenceValidationError, match="concave"):
        build_media(input_dir, tmp_path / "media")


@pytest.mark.parametrize("mutation", ["wrong_variant", "wrong_pair", "bad_source_hash", "converged"])
def test_rejects_unpaired_or_semantically_spoofed_cases(tmp_path: Path, mutation: str) -> None:
    input_dir = tmp_path / "compact"
    _write_inputs(input_dir)
    evidence = _load(input_dir / EVIDENCE_FILE)
    after = evidence["u_shape_comparison"]["after"]  # type: ignore[index]
    if mutation == "wrong_variant":
        after["route_variant"] = "boundary_corridor"
    elif mutation == "wrong_pair":
        after["pair_id"] = "different-pair"
    elif mutation == "bad_source_hash":
        after["source_record_sha256"] = "f" * 64
    else:
        failure = evidence["failure_case"]  # type: ignore[index]
        failure["terminal_status"] = "CONVERGED"
    _write_json(input_dir / EVIDENCE_FILE, evidence)

    with pytest.raises(EvidenceValidationError):
        build_media(input_dir, tmp_path / "media")


@pytest.mark.parametrize("mutation", ["count", "path_start", "success_end"])
def test_rejects_guide_path_trajectory_inconsistency(tmp_path: Path, mutation: str) -> None:
    input_dir = tmp_path / "compact"
    _write_inputs(input_dir)
    evidence = _load(input_dir / EVIDENCE_FILE)
    case = evidence["success_case"]  # type: ignore[index]
    if mutation == "count":
        case["paths"].pop()
    elif mutation == "path_start":
        case["paths"][0][0] = [99.0, 99.0]
    else:
        case["trajectories"][0][-1] = [0.0, 0.0]
    _write_json(input_dir / EVIDENCE_FILE, evidence)

    with pytest.raises(EvidenceValidationError):
        build_media(input_dir, tmp_path / "media")


def test_blocked_comparison_preserves_each_method_actual_targets(tmp_path: Path) -> None:
    input_dir = tmp_path / "compact"
    _write_inputs(input_dir)
    evidence = _load(input_dir / EVIDENCE_FILE)
    before = evidence["u_shape_comparison"]["before"]  # type: ignore[index]
    before["targets"][0] = [-2.7, -2.6]
    before["paths"][0][-1] = [-2.7, -2.6]
    _rebind_cases(input_dir, evidence, [before])

    manifest = build_media(input_dir, tmp_path / "media")

    assert set(manifest["outputs"]) == set(MEDIA_FILES)


def test_success_case_targets_are_interpreted_in_assigned_guide_order(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "compact"
    _write_inputs(input_dir)
    evidence = _load(input_dir / EVIDENCE_FILE)
    case = evidence["success_case"]  # type: ignore[index]
    case["targets"] = list(reversed(case["targets"]))
    for index in range(len(case["paths"])):
        case["paths"][index][-1] = case["targets"][index]
        case["trajectories"][index][-1] = case["targets"][index]
    _rebind_cases(input_dir, evidence, [case])

    manifest = build_media(input_dir, tmp_path / "media")

    assert manifest["filter"]["selected_source_record_ids"]["success_case"] == (
        "010-circle-success"
    )


def test_aggregate_tracking_rmse_allows_one_guide_outside_pointwise_tolerance(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "compact"
    _write_inputs(input_dir)
    evidence = _load(input_dir / EVIDENCE_FILE)
    case = evidence["success_case"]  # type: ignore[index]
    first_target = case["targets"][0]
    case["trajectories"][0][-1] = [first_target[0] + 0.08, first_target[1]]
    _rebind_cases(input_dir, evidence, [case])

    manifest = build_media(input_dir, tmp_path / "media")

    assert 0.08 > media_builder.TRAJECTORY_ENDPOINT_TOLERANCE
    assert manifest["filter"]["success_media_is_placeholder"] is False


def test_prepare_failure_case_may_have_only_initial_state_trajectory(tmp_path: Path) -> None:
    input_dir = tmp_path / "compact"
    _write_inputs(input_dir)
    evidence = _load(input_dir / EVIDENCE_FILE)
    failure = evidence["failure_case"]  # type: ignore[index]
    failure["truth_boundary"] = []
    failure["source_polygon"] = []
    failure["targets"] = []
    failure["paths"] = []
    failure["trajectories"] = [[point] for point in failure["initial_positions"]]
    _rebind_cases(input_dir, evidence, [failure])

    manifest = build_media(input_dir, tmp_path / "media")

    assert set(manifest["outputs"]) == set(MEDIA_FILES)


@pytest.mark.parametrize("failure_point", ["second_plot", "gif"])
def test_render_failure_keeps_existing_output_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure_point: str
) -> None:
    input_dir = tmp_path / "compact"
    output_dir = tmp_path / "media"
    _write_inputs(input_dir)
    output_dir.mkdir()
    (output_dir / "sentinel.txt").write_text("old-output", encoding="utf-8")
    before = {path.name: path.read_bytes() for path in output_dir.iterdir()}

    def fail(*args: object, **kwargs: object) -> None:
        raise RuntimeError("injected renderer failure")

    monkeypatch.setattr(
        media_builder,
        "_plot_same_resource" if failure_point == "second_plot" else "_build_success_gif",
        fail,
    )
    with pytest.raises(RuntimeError, match="injected"):
        build_media(input_dir, output_dir)

    assert {path.name: path.read_bytes() for path in output_dir.iterdir()} == before
    assert not list(tmp_path.glob(".media.staging-*"))


def test_repeated_render_has_identical_asset_and_manifest_hashes(tmp_path: Path) -> None:
    input_dir = tmp_path / "compact"
    _write_inputs(input_dir)
    first = build_media(input_dir, tmp_path / "media-a")
    second = build_media(input_dir, tmp_path / "media-b")

    assert first == second
    for name in (*MEDIA_FILES, MANIFEST_FILE):
        first_hash = hashlib.sha256((tmp_path / "media-a" / name).read_bytes()).hexdigest()
        second_hash = hashlib.sha256((tmp_path / "media-b" / name).read_bytes()).hexdigest()
        assert first_hash == second_hash


def test_nonblocked_scenarios_may_report_blocked_timeout_as_not_applicable(tmp_path: Path) -> None:
    input_dir = tmp_path / "compact"
    _write_inputs(input_dir)
    summary = _load(input_dir / SUMMARY_FILE)
    summary["scenario_summary"]["circle"]["blocked_route_timeout_rate"] = None  # type: ignore[index]
    summary["scenario_summary"]["ellipse"]["blocked_route_timeout_rate"] = None  # type: ignore[index]
    _write_json(input_dir / SUMMARY_FILE, summary)

    result = build_media(input_dir, tmp_path / "media")

    assert set(result["outputs"]) == set(MEDIA_FILES)


def test_clean_checkout_cli_runs_from_detached_local_clone(tmp_path: Path) -> None:
    source_root = Path(__file__).resolve().parents[2]
    source_head = subprocess.run(
        ["git", "-C", str(source_root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout.strip()
    clone_root = tmp_path / "clean-checkout"
    clone_result = subprocess.run(
        [
            "git",
            "-c",
            f"safe.directory={source_root / '.git'}",
            "clone",
            "--no-hardlinks",
            "--no-checkout",
            str(source_root),
            str(clone_root),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert clone_result.returncode == 0, clone_result.stderr
    detach_result = subprocess.run(
        ["git", "-C", str(clone_root), "checkout", "--detach", source_head],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert detach_result.returncode == 0, detach_result.stderr
    cloned_head = subprocess.run(
        ["git", "-C", str(clone_root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout.strip()
    assert cloned_head == source_head
    assert (
        subprocess.run(
            ["git", "-C", str(clone_root), "status", "--porcelain"],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout
        == ""
    )

    input_dir = tmp_path / "compact"
    output_dir = tmp_path / "media"
    _write_inputs(input_dir)
    script = (clone_root / "scripts" / "build_step1_g7_media.py").resolve()
    assert script.is_file()
    assert script.is_relative_to(clone_root.resolve())

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--input",
            str(input_dir),
            "--output",
            str(output_dir),
        ],
        cwd=clone_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    manifest = _load(output_dir / MANIFEST_FILE)
    assert set(manifest["outputs"]) == set(MEDIA_FILES)
    for name in MEDIA_FILES:
        path = output_dir / name
        assert path.is_file() and path.stat().st_size > 0
        assert manifest["outputs"][name]["sha256"] == hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
    assert (
        subprocess.run(
            ["git", "-C", str(clone_root), "status", "--porcelain"],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout
        == ""
    )
