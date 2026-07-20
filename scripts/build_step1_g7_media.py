"""Build README media only from frozen Step 1 G7 holdout evidence.

The evaluator owns episode filtering and exemplar selection.  This script is a
strict renderer: it rejects pilot/non-holdout data, never ranks cases, and
records hashes for both compact inputs and every generated media artifact.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import shutil
import sys
import tempfile
from typing import Any, Iterable, Mapping, Sequence
import uuid

os.environ.setdefault(
    "MPLCONFIGDIR",
    str(Path(tempfile.gettempdir()) / "crowd-management-matplotlib-cache"),
)

import matplotlib

matplotlib.use("Agg", force=True)

import matplotlib.pyplot as plt
import numpy as np
import PIL
from matplotlib.animation import PillowWriter
from matplotlib.axes import Axes


FREEZE_SCHEMA = "abcg-v2.1-g7-freeze-manifest-v1"
RECORDS_SCHEMA = "abcg-v2.1-g7-records-compact-v1"
SUMMARY_SCHEMA = "abcg-v2.1-g7-readme-summary-v1"
MEDIA_EVIDENCE_SCHEMA = "abcg-v2.1-g7-media-evidence-v1"
MANIFEST_SCHEMA = "abcg-v2.1-g7-media-manifest-v1"

FREEZE_FILE = "freeze_manifest.json"
RECORDS_FILE = "records_compact.json"
SUMMARY_FILE = "readme_summary.json"
EVIDENCE_FILE = "media_evidence.json"
MANIFEST_FILE = "media_manifest.json"
MEDIA_FILES = (
    "blocked_route_timeout.png",
    "same_resource_coverage_gap.png",
    "resource_pareto.png",
    "failure_composition.png",
    "u_c_route_comparison.png",
    "success_case.gif",
    "failure_case.png",
)

SUMMARY_FIELDS = (
    "schema",
    "split",
    "pilot_data_used",
    "frozen_sha",
    "config_hash",
    "records_sha256",
    "record_count",
    "experiment_scale",
    "scenario_summary",
    "same_resource",
    "adaptive_pareto",
    "failure_composition",
    "g6_tracking_comparator",
    "blocked_timeout_paired",
)
EVIDENCE_FIELDS = (
    "schema",
    "split",
    "pilot_data_used",
    "frozen_sha",
    "config_hash",
    "records_sha256",
    "record_count",
    "success_case",
    "failure_case",
    "u_shape_comparison",
    "c_shape_comparison",
)
CASE_FIELDS = (
    "source_record_id",
    "source_record_sha256",
    "scenario",
    "seed",
    "pair_id",
    "method",
    "route_variant",
    "resource_regime",
    "selection_rule",
    "terminal_status",
    "controller_terminal_state",
    "plan_optimal",
    "route_feasible",
    "track_converged",
    "sampled_safe",
    "estimated_deployment_success",
    "truth_validated_success",
    "truth_boundary",
    "source_polygon",
    "targets",
    "initial_positions",
    "paths",
    "trajectories",
)
SCENARIO_METRICS = (
    "estimated_deployment_success_rate",
    "truth_validated_success_rate",
    "blocked_route_timeout_rate",
    "truth_coverage",
    "maximum_consecutive_arc_gap",
    "active_guide_count",
    "method",
    "resource_regime",
    "denominator",
)
SAME_RESOURCE_FIELDS = (
    "scenario",
    "method",
    "truth_coverage",
    "maximum_consecutive_arc_gap",
    "active_guide_count",
)
PARETO_FIELDS = (
    "scenario",
    "method",
    "resource_regime",
    "aggregation",
    "denominator",
    "active_guide_count",
    "truth_coverage",
    "maximum_consecutive_arc_gap",
    "path_length",
    "runtime_ms",
)

COMMON_EVIDENCE_FIELDS = (
    "schema",
    "split",
    "pilot_data_used",
    "frozen_sha",
    "config_hash",
    "record_count",
)
RECORD_FIELDS = (
    "record_id",
    "split",
    "pilot_data_used",
    "frozen_sha",
    "config_hash",
    "scenario",
    "seed",
    "pair_id",
    "method",
    "route_variant",
    "resource_regime",
    "blocked_route_episode",
    "v2_1_routing_pipeline",
    "terminal_status",
    "controller_terminal_state",
    "plan_optimal",
    "route_feasible",
    "track_converged",
    "sampled_safe",
    "estimated_deployment_success",
    "truth_validated_success",
    "metrics",
    "media_payload_sha256",
)
LAYER_FIELDS = (
    "plan_optimal",
    "route_feasible",
    "track_converged",
    "sampled_safe",
    "estimated_deployment_success",
    "truth_validated_success",
)
METRIC_FIELDS = (
    "truth_coverage",
    "maximum_consecutive_arc_gap",
    "active_guide_count",
    "path_length",
    "runtime_ms",
    "tracking_rmse",
)
MEDIA_PAYLOAD_FIELDS = (
    "truth_boundary",
    "source_polygon",
    "targets",
    "initial_positions",
    "paths",
    "trajectories",
)
PRIMARY_METHODS = ("straight_hungarian", "visibility_hungarian")
ROUTE_VARIANTS = ("g6_fixed_resource_straight", "visibility_graph")
RECORD_ROUTE_VARIANTS = {
    "g6_fixed_resource_straight",
    "legacy_unchecked_straight",
    "straight",
    "boundary_corridor",
    "visibility_graph",
}
RESOURCE_REGIMES = ("same_resource", "adaptive_resource")
TERMINAL_STATUSES = {
    "TRUTH_VALIDATED_SUCCESS",
    "ESTIMATED_DEPLOYMENT_SUCCESS_ONLY",
    "TRUTH_VALIDATION_FAILED",
    "TIMEOUT",
    "NO_PROGRESS",
    "ROUTE_INFEASIBLE",
    "INITIAL_UNSAFE",
    "CONSTRAINT_INFEASIBLE",
    "NUMERICAL_FAILURE",
    "SAMPLED_UNSAFE",
    "CAPACITY_SHORTFALL",
    "RESOURCE_UNCERTAIN",
    "HYSTERESIS_GAP_DEGRADED",
    "ROOM_INFEASIBLE",
    "PLAN_INFEASIBLE",
    "TRACKING_TIMEOUT",
    "BOUNDARY_INVALID",
    "BOOTSTRAP_INSUFFICIENT",
    "GEOMETRY_INVALID",
    "FREE_SPACE_INVALID",
    "MULTIPOLYGON",
    "HOLES",
    "OFFSET_TOPOLOGY_CHANGED",
    "PLAN_NOT_OPTIMAL",
    "PLAN_ANALYTIC_VERIFICATION_FAILED",
    "SAFETY_INFEASIBLE",
    "INITIAL_STATE_UNSAFE",
    "PROJECTION_INFEASIBLE",
    "NUMERICAL_RESIDUAL_FAILURE",
    "ZOH_DENSE_CHECK_FAILED",
    "INVALID_SAFETY_RESPONSE",
    "UNSPECIFIED_FAILURE",
    "EVALUATION_ERROR",
    "BOUNDARY_DEGENERATE",
    "INVALID",
    "EMPTY",
    "INFEASIBLE",
    "DEGRADED",
    "OFFSET_INVALID",
    "ASSIGNMENT_INFEASIBLE",
    "G6_TRACK_CONVERGED_ONLY",
}
SELECTION_RULES = {
    "success_case": "first_v2_1_truth_success_by_frozen_record_id",
    "failure_case": "first_v2_1_truth_failure_by_frozen_record_id",
    "comparison": "first_complete_blocked_pair_by_frozen_pair_id",
}
SHA256_LENGTH = 64
GIT_SHA_LENGTH = 40
TRAJECTORY_ENDPOINT_TOLERANCE = 0.061

COLORS = ("#3568a8", "#e07b39", "#4b9654", "#b84b4b", "#7a5aa6", "#4b9199")
SCENARIO_ORDER = {"circle": 0, "ellipse": 1, "u_shape": 2, "c_shape": 3}


class EvidenceValidationError(ValueError):
    """Raised before rendering when compact evidence violates its contract."""


def _reject_json_constant(value: str) -> None:
    raise EvidenceValidationError(f"JSON contains non-finite constant {value!r}.")


def _object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceValidationError(f"JSON contains duplicate key {key!r}.")
        result[key] = value
    return result


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _read_json(path: Path) -> tuple[dict[str, Any], str]:
    if not path.is_file():
        raise EvidenceValidationError(f"Required compact evidence is missing: {path}")
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
        value = json.loads(
            text,
            parse_constant=_reject_json_constant,
            object_pairs_hook=_object_without_duplicates,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EvidenceValidationError(f"Invalid JSON in {path}: {error}") from error
    if not isinstance(value, dict):
        raise EvidenceValidationError(f"{path} must contain one JSON object.")
    _reject_nonfinite(value, str(path))
    return value, _sha256_bytes(raw)


def _reject_nonfinite(value: Any, context: str) -> None:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return
    if isinstance(value, (int, np.integer)):
        return
    if isinstance(value, (float, np.floating)):
        if not math.isfinite(float(value)):
            raise EvidenceValidationError(f"{context} contains a non-finite number.")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            _reject_nonfinite(item, f"{context}.{key}")
        return
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        for index, item in enumerate(value):
            _reject_nonfinite(item, f"{context}[{index}]")
        return
    raise EvidenceValidationError(f"{context} contains unsupported value type {type(value).__name__}.")


def _require_fields(value: Mapping[str, Any], fields: Iterable[str], context: str) -> None:
    missing = [field for field in fields if field not in value]
    if missing:
        raise EvidenceValidationError(f"{context} is missing required fields: {', '.join(missing)}")


def _text(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvidenceValidationError(f"{context} must be a non-empty string.")
    return value.strip()


def _number(
    value: Any,
    context: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, np.integer, np.floating)):
        raise EvidenceValidationError(f"{context} must be a finite number.")
    result = float(value)
    if not math.isfinite(result):
        raise EvidenceValidationError(f"{context} must be finite.")
    if minimum is not None and result < minimum:
        raise EvidenceValidationError(f"{context} must be at least {minimum}.")
    if maximum is not None and result > maximum:
        raise EvidenceValidationError(f"{context} must be at most {maximum}.")
    return result


def _optional_number(
    value: Any,
    context: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float | None:
    """Validate a metric that is genuinely undefined for some cohorts."""
    if value is None:
        return None
    return _number(value, context, minimum=minimum, maximum=maximum)


def _nonnegative_integer(value: Any, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or value < 0:
        raise EvidenceValidationError(f"{context} must be a non-negative integer.")
    return int(value)


def _positive_integer(value: Any, context: str) -> int:
    result = _nonnegative_integer(value, context)
    if result <= 0:
        raise EvidenceValidationError(f"{context} must be a positive integer.")
    return result


def _boolean(value: Any, context: str) -> bool:
    if not isinstance(value, bool):
        raise EvidenceValidationError(f"{context} must be a JSON boolean.")
    return value


def _hex_digest(value: Any, context: str, *, length: int = SHA256_LENGTH) -> str:
    result = _text(value, context).lower()
    if len(result) != length or any(character not in "0123456789abcdef" for character in result):
        raise EvidenceValidationError(f"{context} must be a {length}-character lowercase hex digest.")
    return result


def _canonical_json_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return _sha256_bytes(payload)


def _validate_metrics(value: Any, context: str) -> dict[str, float | int | None]:
    if not isinstance(value, Mapping):
        raise EvidenceValidationError(f"{context} must be an object.")
    _require_fields(value, METRIC_FIELDS, context)
    return {
        "truth_coverage": _optional_number(
            value["truth_coverage"], f"{context}.truth_coverage", minimum=0.0, maximum=1.0
        ),
        "maximum_consecutive_arc_gap": _optional_number(
            value["maximum_consecutive_arc_gap"],
            f"{context}.maximum_consecutive_arc_gap",
            minimum=0.0,
        ),
        "active_guide_count": _nonnegative_integer(
            value["active_guide_count"], f"{context}.active_guide_count"
        ),
        "path_length": _optional_number(
            value["path_length"], f"{context}.path_length", minimum=0.0
        ),
        "runtime_ms": _optional_number(
            value["runtime_ms"], f"{context}.runtime_ms", minimum=0.0
        ),
        "tracking_rmse": _optional_number(
            value["tracking_rmse"], f"{context}.tracking_rmse", minimum=0.0
        ),
    }


def _observed_median(records: Sequence[Mapping[str, Any]], field: str) -> float | None:
    values = [
        float(record["metrics"][field])
        for record in records
        if record["metrics"][field] is not None
    ]
    return float(np.median(values)) if values else None


def _same_number(left: float | int | None, right: float | int | None) -> bool:
    if left is None or right is None:
        return left is None and right is None
    return math.isclose(float(left), float(right), rel_tol=1e-12, abs_tol=1e-12)


def _require_same_number(
    supplied: float | int | None,
    expected: float | int | None,
    context: str,
) -> None:
    if not _same_number(supplied, expected):
        raise EvidenceValidationError(
            f"{context} disagrees with metrics recomputed from records_compact.json."
        )


def _validate_layers(value: Mapping[str, Any], context: str) -> dict[str, bool]:
    _require_fields(value, LAYER_FIELDS, context)
    layers = {field: _boolean(value[field], f"{context}.{field}") for field in LAYER_FIELDS}
    derived_estimated = bool(
        layers["plan_optimal"]
        and layers["route_feasible"]
        and layers["track_converged"]
        and layers["sampled_safe"]
    )
    if layers["estimated_deployment_success"] != derived_estimated:
        raise EvidenceValidationError(
            f"{context}.estimated_deployment_success disagrees with its four prerequisite layers."
        )
    if layers["truth_validated_success"] and not layers["estimated_deployment_success"]:
        raise EvidenceValidationError(
            f"{context}.truth_validated_success requires estimated_deployment_success."
        )
    return layers


def _terminal_status(
    value: Any,
    context: str,
    *,
    estimated_success: bool,
    truth_success: bool,
) -> str:
    result = _text(value, context).upper()
    if result == "CONVERGED":
        raise EvidenceValidationError(
            f"{context} may not use controller CONVERGED as a deployment terminal status."
        )
    if result not in TERMINAL_STATUSES:
        raise EvidenceValidationError(f"{context} contains unsupported terminal status {result!r}.")
    expected_layer_status = (
        "TRUTH_VALIDATED_SUCCESS"
        if truth_success
        else "ESTIMATED_DEPLOYMENT_SUCCESS_ONLY"
        if estimated_success
        else None
    )
    if expected_layer_status is not None and result != expected_layer_status:
        raise EvidenceValidationError(
            f"{context} must equal {expected_layer_status!r} for its layered result."
        )
    if expected_layer_status is None and result in {
        "TRUTH_VALIDATED_SUCCESS",
        "ESTIMATED_DEPLOYMENT_SUCCESS_ONLY",
    }:
        raise EvidenceValidationError(
            f"{context} reports deployment success without the required layers."
        )
    return result


def _canonical_scenario(value: Any) -> str:
    raw = _text(value, "scenario").lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "circle": "circle",
        "ellipse": "ellipse",
        "u": "u_shape",
        "u_shape": "u_shape",
        "ushape": "u_shape",
        "c": "c_shape",
        "c_shape": "c_shape",
        "cshape": "c_shape",
    }
    return aliases.get(raw, raw)


def _records(value: Any, context: str) -> list[dict[str, Any]]:
    if isinstance(value, Mapping) and "records" in value:
        value = value["records"]
    if not isinstance(value, list) or not value:
        raise EvidenceValidationError(f"{context} must be a non-empty list of records.")
    records: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise EvidenceValidationError(f"{context}[{index}] must be an object.")
        records.append(dict(item))
    return records


def _validate_freeze(document: Mapping[str, Any]) -> dict[str, Any]:
    context = "freeze_manifest"
    _require_fields(
        document,
        (
            "schema",
            "frozen_head",
            "resolved_config_sha256",
            "expected_holdout_record_count",
            "expected_holdout_method_count",
            "expected_holdout_v2_1_method_count",
            "expected_holdout_v2_1_record_count",
            "expected_g6_tracking_comparator_method_count",
            "expected_g6_tracking_comparator_record_count",
            "clean_at_freeze",
            "pilot_data_permitted_in_holdout",
        ),
        context,
    )
    if document["schema"] != FREEZE_SCHEMA:
        raise EvidenceValidationError(f"{context}.schema must equal {FREEZE_SCHEMA!r}.")
    if document["clean_at_freeze"] is not True:
        raise EvidenceValidationError("freeze_manifest.clean_at_freeze must be JSON true.")
    if document["pilot_data_permitted_in_holdout"] is not False:
        raise EvidenceValidationError(
            "freeze_manifest.pilot_data_permitted_in_holdout must be JSON false."
        )
    expected_record_count = _positive_integer(
        document["expected_holdout_record_count"],
        f"{context}.expected_holdout_record_count",
    )
    expected_method_count = _positive_integer(
        document["expected_holdout_method_count"],
        f"{context}.expected_holdout_method_count",
    )
    expected_v2_method_count = _positive_integer(
        document["expected_holdout_v2_1_method_count"],
        f"{context}.expected_holdout_v2_1_method_count",
    )
    expected_v2_record_count = _positive_integer(
        document["expected_holdout_v2_1_record_count"],
        f"{context}.expected_holdout_v2_1_record_count",
    )
    expected_g6_method_count = _positive_integer(
        document["expected_g6_tracking_comparator_method_count"],
        f"{context}.expected_g6_tracking_comparator_method_count",
    )
    expected_g6_record_count = _positive_integer(
        document["expected_g6_tracking_comparator_record_count"],
        f"{context}.expected_g6_tracking_comparator_record_count",
    )
    if expected_v2_record_count + expected_g6_record_count != expected_record_count:
        raise EvidenceValidationError(
            "freeze_manifest v2.1 and G6 comparator record counts must partition the holdout."
        )
    if expected_v2_method_count + expected_g6_method_count != expected_method_count:
        raise EvidenceValidationError(
            "freeze_manifest v2.1 and G6 comparator method counts must partition the holdout."
        )
    return {
        "frozen_sha": _hex_digest(document["frozen_head"], f"{context}.frozen_head", length=GIT_SHA_LENGTH),
        "config_hash": _hex_digest(
            document["resolved_config_sha256"], f"{context}.resolved_config_sha256"
        ),
        "expected_record_count": expected_record_count,
        "expected_method_count": expected_method_count,
        "expected_v2_1_method_count": expected_v2_method_count,
        "expected_v2_1_record_count": expected_v2_record_count,
        "expected_g6_tracking_comparator_method_count": expected_g6_method_count,
        "expected_g6_tracking_comparator_record_count": expected_g6_record_count,
    }


def _validate_holdout_identity(
    document: Mapping[str, Any],
    *,
    schema: str,
    fields: Iterable[str],
    context: str,
    identity: Mapping[str, Any],
    records_hash: str | None = None,
    record_count: int | None = None,
) -> None:
    _require_fields(document, fields, context)
    if document["schema"] != schema:
        raise EvidenceValidationError(f"{context}.schema must equal {schema!r}.")
    if document["split"] != "holdout":
        raise EvidenceValidationError(f"{context}.split must equal 'holdout'.")
    if document["pilot_data_used"] is not False:
        raise EvidenceValidationError(f"{context}.pilot_data_used must be JSON false.")
    frozen_sha = _hex_digest(document["frozen_sha"], f"{context}.frozen_sha", length=GIT_SHA_LENGTH)
    config_hash = _hex_digest(document["config_hash"], f"{context}.config_hash")
    if frozen_sha != identity["frozen_sha"] or config_hash != identity["config_hash"]:
        raise EvidenceValidationError(f"{context} does not match the frozen SHA/config hash.")
    declared_count = _positive_integer(document["record_count"], f"{context}.record_count")
    if declared_count != identity["expected_record_count"]:
        raise EvidenceValidationError(
            f"{context}.record_count differs from the preregistered holdout denominator."
        )
    if record_count is not None and declared_count != record_count:
        raise EvidenceValidationError(f"{context}.record_count does not match records_compact.json.")
    if records_hash is not None:
        declared_hash = _hex_digest(document["records_sha256"], f"{context}.records_sha256")
        if declared_hash != records_hash:
            raise EvidenceValidationError(f"{context}.records_sha256 does not match records_compact.json.")


def _validate_records(
    document: Mapping[str, Any], identity: Mapping[str, str]
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    _validate_holdout_identity(
        document,
        schema=RECORDS_SCHEMA,
        fields=(*COMMON_EVIDENCE_FIELDS, "records"),
        context="records_compact",
        identity=identity,
    )
    raw_records = _records(document["records"], "records_compact.records")
    if document["record_count"] != len(raw_records):
        raise EvidenceValidationError("records_compact.record_count must equal len(records).")
    records: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(raw_records):
        context = f"records_compact.records[{index}]"
        _require_fields(raw, RECORD_FIELDS, context)
        if raw["split"] != "holdout" or raw["pilot_data_used"] is not False:
            raise EvidenceValidationError(f"{context} must be non-pilot holdout evidence.")
        if _hex_digest(raw["frozen_sha"], f"{context}.frozen_sha", length=GIT_SHA_LENGTH) != identity["frozen_sha"]:
            raise EvidenceValidationError(f"{context}.frozen_sha differs from freeze_manifest.")
        if _hex_digest(raw["config_hash"], f"{context}.config_hash") != identity["config_hash"]:
            raise EvidenceValidationError(f"{context}.config_hash differs from freeze_manifest.")
        record_id = _text(raw["record_id"], f"{context}.record_id")
        if record_id in by_id:
            raise EvidenceValidationError(f"records_compact contains duplicate record_id {record_id!r}.")
        scenario = _canonical_scenario(raw["scenario"])
        if scenario not in SCENARIO_ORDER:
            raise EvidenceValidationError(f"{context}.scenario is not a formal G7 scenario.")
        seed = _nonnegative_integer(raw["seed"], f"{context}.seed")
        resource_regime = _text(raw["resource_regime"], f"{context}.resource_regime")
        if resource_regime not in RESOURCE_REGIMES:
            raise EvidenceValidationError(f"{context}.resource_regime is unsupported.")
        layers = _validate_layers(raw, context)
        terminal_status = _terminal_status(
            raw["terminal_status"],
            f"{context}.terminal_status",
            estimated_success=layers["estimated_deployment_success"],
            truth_success=layers["truth_validated_success"],
        )
        controller_terminal_state = _text(
            raw["controller_terminal_state"], f"{context}.controller_terminal_state"
        ).upper()
        if controller_terminal_state != "CONVERGED" and controller_terminal_state not in TERMINAL_STATUSES:
            raise EvidenceValidationError(f"{context}.controller_terminal_state is unsupported.")
        route_variant = _text(raw["route_variant"], f"{context}.route_variant")
        if route_variant not in RECORD_ROUTE_VARIANTS:
            raise EvidenceValidationError(f"{context}.route_variant is unsupported.")
        metrics = _validate_metrics(raw["metrics"], f"{context}.metrics")
        media_payload_sha256 = _hex_digest(
            raw["media_payload_sha256"], f"{context}.media_payload_sha256"
        )
        v2_1_routing_pipeline = _boolean(
            raw["v2_1_routing_pipeline"], f"{context}.v2_1_routing_pipeline"
        )
        expected_v2_1 = _text(raw["method"], f"{context}.method") != "g6_fixed_resource_rerun"
        if v2_1_routing_pipeline != expected_v2_1:
            raise EvidenceValidationError(
                f"{context}.v2_1_routing_pipeline must be false only for the frozen G6 comparator."
            )
        record = {
            "record_id": record_id,
            "source_record_sha256": _canonical_json_sha256(raw),
            "scenario": scenario,
            "seed": seed,
            "pair_id": _text(raw["pair_id"], f"{context}.pair_id"),
            "method": _text(raw["method"], f"{context}.method"),
            "route_variant": route_variant,
            "resource_regime": resource_regime,
            "blocked_route_episode": _boolean(
                raw["blocked_route_episode"], f"{context}.blocked_route_episode"
            ),
            "v2_1_routing_pipeline": v2_1_routing_pipeline,
            "terminal_status": terminal_status,
            "controller_terminal_state": controller_terminal_state,
            "metrics": metrics,
            "media_payload_sha256": media_payload_sha256,
            **layers,
        }
        records.append(record)
        by_id[record_id] = record
    v2_records = [record for record in records if record["v2_1_routing_pipeline"]]
    g6_records = [record for record in records if not record["v2_1_routing_pipeline"]]
    observed_methods = {record["method"] for record in records}
    v2_methods = {record["method"] for record in v2_records}
    g6_methods = {record["method"] for record in g6_records}
    expected_counts = {
        "record_count": (len(records), identity["expected_record_count"]),
        "method_count": (len(observed_methods), identity["expected_method_count"]),
        "v2_1_record_count": (len(v2_records), identity["expected_v2_1_record_count"]),
        "v2_1_method_count": (len(v2_methods), identity["expected_v2_1_method_count"]),
        "g6_tracking_comparator_record_count": (
            len(g6_records),
            identity["expected_g6_tracking_comparator_record_count"],
        ),
        "g6_tracking_comparator_method_count": (
            len(g6_methods),
            identity["expected_g6_tracking_comparator_method_count"],
        ),
    }
    mismatches = [
        name for name, (observed, expected) in expected_counts.items() if observed != expected
    ]
    if mismatches:
        raise EvidenceValidationError(
            "records_compact disagrees with frozen method/record partitions: "
            + ", ".join(mismatches)
        )
    return records, by_id


def _validate_blocked_pairs(
    value: Any, records: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    context = "blocked_timeout_paired"
    if not isinstance(value, Mapping):
        raise EvidenceValidationError(f"{context} must be an object.")
    _require_fields(value, ("baseline_label", "candidate_label", "scenarios"), context)
    baseline_label = _text(value["baseline_label"], f"{context}.baseline_label")
    required_baseline = (
        "Frozen G6 fixed-resource straight-feedback adapter rerun on matched G7 holdout"
    )
    if baseline_label != required_baseline:
        raise EvidenceValidationError(
            f"{context}.baseline_label must state that the G6 algorithm was rerun on the G7 holdout."
        )
    candidate_label = _text(value["candidate_label"], f"{context}.candidate_label")
    scenario_value = value["scenarios"]
    if not isinstance(scenario_value, Mapping):
        raise EvidenceValidationError(f"{context}.scenarios must be an object.")
    normalized: dict[str, dict[str, Any]] = {}
    for scenario in ("u_shape", "c_shape"):
        raw = scenario_value.get(scenario)
        item_context = f"{context}.scenarios.{scenario}"
        if not isinstance(raw, Mapping):
            raise EvidenceValidationError(f"{item_context} must be an object.")
        _require_fields(
            raw,
            (
                "pair_ids",
                "resource_regime",
                "denominator",
                "baseline_timeout_rate",
                "candidate_timeout_rate",
                "paired_difference",
                "paired_bootstrap_ci95",
            ),
            item_context,
        )
        if not isinstance(raw["pair_ids"], list) or not raw["pair_ids"]:
            raise EvidenceValidationError(f"{item_context}.pair_ids must be a non-empty list.")
        pair_ids = [_text(item, f"{item_context}.pair_ids") for item in raw["pair_ids"]]
        if pair_ids != sorted(set(pair_ids)):
            raise EvidenceValidationError(f"{item_context}.pair_ids must be unique and frozen-sorted.")
        regime = _text(raw["resource_regime"], f"{item_context}.resource_regime")
        if regime not in RESOURCE_REGIMES:
            raise EvidenceValidationError(f"{item_context}.resource_regime is unsupported.")
        all_blocked_pair_ids = sorted(
            {
                str(record["pair_id"])
                for record in records
                if record["scenario"] == scenario
                and record["resource_regime"] == regime
                and record["blocked_route_episode"]
            }
        )
        if pair_ids != all_blocked_pair_ids:
            raise EvidenceValidationError(
                f"{item_context}.pair_ids must include every blocked-route pair in compact records."
            )
        denominator = _positive_integer(raw["denominator"], f"{item_context}.denominator")
        if denominator != len(pair_ids):
            raise EvidenceValidationError(f"{item_context}.denominator must equal len(pair_ids).")
        baseline_records: list[Mapping[str, Any]] = []
        candidate_records: list[Mapping[str, Any]] = []
        for pair_id in pair_ids:
            candidates = [
                record
                for record in records
                if record["scenario"] == scenario
                and record["pair_id"] == pair_id
                and record["resource_regime"] == regime
                and record["blocked_route_episode"]
            ]
            before = [
                record
                for record in candidates
                if record["method"] == "g6_fixed_resource_rerun"
                and record["route_variant"] == ROUTE_VARIANTS[0]
            ]
            after = [
                record
                for record in candidates
                if record["method"] == "visibility_hungarian"
                and record["route_variant"] == ROUTE_VARIANTS[1]
            ]
            if len(before) != 1 or len(after) != 1 or before[0]["seed"] != after[0]["seed"]:
                raise EvidenceValidationError(
                    f"{item_context} pair {pair_id!r} lacks one seed-matched G6-adapter/visibility record."
                )
            baseline_records.append(before[0])
            candidate_records.append(after[0])
        baseline_rate = sum(
            record["controller_terminal_state"] == "TIMEOUT" for record in baseline_records
        ) / denominator
        candidate_rate = sum(
            record["controller_terminal_state"] == "TIMEOUT" for record in candidate_records
        ) / denominator
        supplied_baseline = _number(
            raw["baseline_timeout_rate"], f"{item_context}.baseline_timeout_rate", minimum=0.0, maximum=1.0
        )
        supplied_candidate = _number(
            raw["candidate_timeout_rate"], f"{item_context}.candidate_timeout_rate", minimum=0.0, maximum=1.0
        )
        supplied_difference = _number(
            raw["paired_difference"], f"{item_context}.paired_difference", minimum=-1.0, maximum=1.0
        )
        if not math.isclose(supplied_baseline, baseline_rate, abs_tol=1e-12):
            raise EvidenceValidationError(f"{item_context}.baseline_timeout_rate disagrees with paired records.")
        if not math.isclose(supplied_candidate, candidate_rate, abs_tol=1e-12):
            raise EvidenceValidationError(f"{item_context}.candidate_timeout_rate disagrees with paired records.")
        if not math.isclose(supplied_difference, candidate_rate - baseline_rate, abs_tol=1e-12):
            raise EvidenceValidationError(f"{item_context}.paired_difference disagrees with paired records.")
        ci = raw["paired_bootstrap_ci95"]
        if not isinstance(ci, list) or len(ci) != 2:
            raise EvidenceValidationError(f"{item_context}.paired_bootstrap_ci95 must contain two bounds.")
        ci_low = _number(ci[0], f"{item_context}.paired_bootstrap_ci95[0]", minimum=-1.0, maximum=1.0)
        ci_high = _number(ci[1], f"{item_context}.paired_bootstrap_ci95[1]", minimum=-1.0, maximum=1.0)
        if ci_low > ci_high:
            raise EvidenceValidationError(f"{item_context}.paired_bootstrap_ci95 bounds are reversed.")
        normalized[scenario] = {
            "pair_ids": pair_ids,
            "resource_regime": regime,
            "denominator": denominator,
            "baseline_timeout_rate": supplied_baseline,
            "candidate_timeout_rate": supplied_candidate,
            "paired_difference": supplied_difference,
            "paired_bootstrap_ci95": [ci_low, ci_high],
        }
    return {
        "baseline_label": baseline_label,
        "candidate_label": candidate_label,
        "scenarios": normalized,
    }


def _validate_summary(
    document: Mapping[str, Any],
    *,
    identity: Mapping[str, Any],
    records_hash: str,
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    record_count = len(records)
    _validate_holdout_identity(
        document,
        schema=SUMMARY_SCHEMA,
        fields=SUMMARY_FIELDS,
        context="readme_summary",
        identity=identity,
        records_hash=records_hash,
        record_count=record_count,
    )
    v2_records = [record for record in records if record["v2_1_routing_pipeline"]]
    g6_records = [record for record in records if not record["v2_1_routing_pipeline"]]
    experiment_scale = document["experiment_scale"]
    if not isinstance(experiment_scale, Mapping):
        raise EvidenceValidationError("experiment_scale must be an object.")
    scale_fields = (
        "total_records",
        "v2_1_deployment_records",
        "g6_tracking_comparator_records",
        "v2_1_method_count",
        "g6_tracking_comparator_method_count",
    )
    _require_fields(experiment_scale, scale_fields, "experiment_scale")
    expected_scale = {
        "total_records": len(records),
        "v2_1_deployment_records": len(v2_records),
        "g6_tracking_comparator_records": len(g6_records),
        "v2_1_method_count": len({record["method"] for record in v2_records}),
        "g6_tracking_comparator_method_count": len(
            {record["method"] for record in g6_records}
        ),
    }
    frozen_scale = {
        "total_records": identity["expected_record_count"],
        "v2_1_deployment_records": identity["expected_v2_1_record_count"],
        "g6_tracking_comparator_records": identity[
            "expected_g6_tracking_comparator_record_count"
        ],
        "v2_1_method_count": identity["expected_v2_1_method_count"],
        "g6_tracking_comparator_method_count": identity[
            "expected_g6_tracking_comparator_method_count"
        ],
    }
    for field, expected in expected_scale.items():
        supplied = _positive_integer(experiment_scale[field], f"experiment_scale.{field}")
        if supplied != expected or supplied != frozen_scale[field]:
            raise EvidenceValidationError(
                f"experiment_scale.{field} disagrees with freeze_manifest/compact records."
            )
    scenario_value = document["scenario_summary"]
    if not isinstance(scenario_value, Mapping):
        raise EvidenceValidationError("scenario_summary must be a scenario mapping.")
    scenario_summary: dict[str, dict[str, Any]] = {}
    for raw_scenario, raw_metrics in scenario_value.items():
        scenario = _canonical_scenario(raw_scenario)
        if scenario in scenario_summary or scenario not in SCENARIO_ORDER:
            raise EvidenceValidationError(f"scenario_summary contains invalid/duplicate scenario {scenario!r}.")
        if not isinstance(raw_metrics, Mapping):
            raise EvidenceValidationError(f"scenario_summary.{raw_scenario} must be an object.")
        context = f"scenario_summary.{raw_scenario}"
        _require_fields(raw_metrics, SCENARIO_METRICS, context)
        regime = _text(raw_metrics["resource_regime"], f"{context}.resource_regime")
        if regime not in RESOURCE_REGIMES:
            raise EvidenceValidationError(f"{context}.resource_regime is unsupported.")
        scenario_summary[scenario] = {
            "estimated_deployment_success_rate": _number(raw_metrics["estimated_deployment_success_rate"], f"{context}.estimated_deployment_success_rate", minimum=0.0, maximum=1.0),
            "truth_validated_success_rate": _number(raw_metrics["truth_validated_success_rate"], f"{context}.truth_validated_success_rate", minimum=0.0, maximum=1.0),
            "blocked_route_timeout_rate": _optional_number(raw_metrics["blocked_route_timeout_rate"], f"{context}.blocked_route_timeout_rate", minimum=0.0, maximum=1.0),
            "truth_coverage": _number(raw_metrics["truth_coverage"], f"{context}.truth_coverage", minimum=0.0, maximum=1.0),
            "maximum_consecutive_arc_gap": _number(raw_metrics["maximum_consecutive_arc_gap"], f"{context}.maximum_consecutive_arc_gap", minimum=0.0),
            "active_guide_count": _nonnegative_integer(raw_metrics["active_guide_count"], f"{context}.active_guide_count"),
            "method": _text(raw_metrics["method"], f"{context}.method"),
            "resource_regime": regime,
            "denominator": _positive_integer(raw_metrics["denominator"], f"{context}.denominator"),
        }
    required_scenarios = set(SCENARIO_ORDER)
    if set(scenario_summary) != required_scenarios:
        raise EvidenceValidationError("scenario_summary must contain exactly circle, ellipse, u_shape, and c_shape.")
    for scenario, supplied in scenario_summary.items():
        selected = [
            record
            for record in records
            if record["scenario"] == scenario
            and record["method"] == "visibility_hungarian"
            and record["resource_regime"] == "same_resource"
        ]
        if not selected:
            raise EvidenceValidationError(
                f"scenario_summary.{scenario} lacks compact visibility_hungarian records."
            )
        blocked = [record for record in selected if record["blocked_route_episode"]]
        expected = {
            "estimated_deployment_success_rate": sum(
                record["estimated_deployment_success"] for record in selected
            ) / len(selected),
            "truth_validated_success_rate": sum(
                record["truth_validated_success"] for record in selected
            ) / len(selected),
            "blocked_route_timeout_rate": (
                sum(record["controller_terminal_state"] == "TIMEOUT" for record in blocked)
                / len(blocked)
                if blocked
                else None
            ),
            "truth_coverage": _observed_median(selected, "truth_coverage"),
            "maximum_consecutive_arc_gap": _observed_median(
                selected, "maximum_consecutive_arc_gap"
            ),
            "active_guide_count": int(
                round(_observed_median(selected, "active_guide_count") or 0.0)
            ),
        }
        if supplied["method"] != "visibility_hungarian":
            raise EvidenceValidationError(
                f"scenario_summary.{scenario}.method must equal 'visibility_hungarian'."
            )
        if supplied["resource_regime"] != "same_resource":
            raise EvidenceValidationError(
                f"scenario_summary.{scenario}.resource_regime must equal 'same_resource'."
            )
        if supplied["denominator"] != len(selected):
            raise EvidenceValidationError(
                f"scenario_summary.{scenario}.denominator disagrees with compact records."
            )
        for field, expected_value in expected.items():
            _require_same_number(
                supplied[field], expected_value, f"scenario_summary.{scenario}.{field}"
            )

    same_resource: list[dict[str, Any]] = []
    same_keys: set[tuple[str, str]] = set()
    for index, raw in enumerate(_records(document["same_resource"], "same_resource")):
        context = f"same_resource[{index}]"
        _require_fields(raw, SAME_RESOURCE_FIELDS, context)
        scenario = _canonical_scenario(raw["scenario"])
        method = _text(raw["method"], f"{context}.method")
        key = (scenario, method)
        if scenario not in SCENARIO_ORDER or key in same_keys:
            raise EvidenceValidationError(f"same_resource contains invalid/duplicate record {key!r}.")
        same_keys.add(key)
        same_resource.append({
            "scenario": scenario,
            "method": method,
            "truth_coverage": _number(raw["truth_coverage"], f"{context}.truth_coverage", minimum=0.0, maximum=1.0),
            "maximum_consecutive_arc_gap": _number(raw["maximum_consecutive_arc_gap"], f"{context}.maximum_consecutive_arc_gap", minimum=0.0),
            "active_guide_count": _nonnegative_integer(raw["active_guide_count"], f"{context}.active_guide_count"),
        })
    methods = sorted({record["method"] for record in same_resource})
    if set(methods) != set(PRIMARY_METHODS):
        raise EvidenceValidationError(
            "same_resource must contain exactly the two preregistered primary methods."
        )
    for scenario in SCENARIO_ORDER:
        selected = [record for record in same_resource if record["scenario"] == scenario]
        if {record["method"] for record in selected} != set(methods):
            raise EvidenceValidationError(f"same_resource scenario {scenario!r} lacks the complete method set.")
        if len({record["active_guide_count"] for record in selected}) != 1:
            raise EvidenceValidationError(f"same_resource scenario {scenario!r} has unequal guide counts.")
    supplied_same = {
        (record["scenario"], record["method"]): record for record in same_resource
    }
    expected_same_keys = set(SCENARIO_ORDER).copy()
    if set(supplied_same) != {
        (scenario, method) for scenario in expected_same_keys for method in PRIMARY_METHODS
    }:
        raise EvidenceValidationError(
            "same_resource must contain one row per scenario and primary method."
        )
    for key, supplied in supplied_same.items():
        scenario, method = key
        selected = [
            record
            for record in records
            if record["scenario"] == scenario
            and record["method"] == method
            and record["resource_regime"] == "same_resource"
        ]
        if not selected:
            raise EvidenceValidationError(f"same_resource row {key!r} lacks compact records.")
        expected_values = {
            "truth_coverage": _observed_median(selected, "truth_coverage"),
            "maximum_consecutive_arc_gap": _observed_median(
                selected, "maximum_consecutive_arc_gap"
            ),
            "active_guide_count": int(
                round(_observed_median(selected, "active_guide_count") or 0.0)
            ),
        }
        for field, expected_value in expected_values.items():
            _require_same_number(
                supplied[field], expected_value, f"same_resource.{scenario}.{method}.{field}"
            )

    adaptive_pareto: list[dict[str, Any]] = []
    pareto_keys: set[tuple[str, str, int]] = set()
    for index, raw in enumerate(_records(document["adaptive_pareto"], "adaptive_pareto")):
        context = f"adaptive_pareto[{index}]"
        _require_fields(raw, PARETO_FIELDS, context)
        scenario = _canonical_scenario(raw["scenario"])
        if scenario not in SCENARIO_ORDER:
            raise EvidenceValidationError(f"{context}.scenario is unsupported.")
        regime = _text(raw["resource_regime"], f"{context}.resource_regime")
        if regime != "adaptive_resource":
            raise EvidenceValidationError(f"{context}.resource_regime must equal 'adaptive_resource'.")
        method = _text(raw["method"], f"{context}.method")
        count = _nonnegative_integer(raw["active_guide_count"], f"{context}.active_guide_count")
        key = (scenario, method, count)
        if key in pareto_keys:
            raise EvidenceValidationError(f"adaptive_pareto contains duplicate point {key!r}.")
        pareto_keys.add(key)
        adaptive_pareto.append({
            "scenario": scenario,
            "method": method,
            "resource_regime": regime,
            "aggregation": _text(raw["aggregation"], f"{context}.aggregation"),
            "denominator": _positive_integer(raw["denominator"], f"{context}.denominator"),
            "active_guide_count": count,
            "truth_coverage": _optional_number(raw["truth_coverage"], f"{context}.truth_coverage", minimum=0.0, maximum=1.0),
            "maximum_consecutive_arc_gap": _optional_number(raw["maximum_consecutive_arc_gap"], f"{context}.maximum_consecutive_arc_gap", minimum=0.0),
            "path_length": _optional_number(raw["path_length"], f"{context}.path_length", minimum=0.0),
            "runtime_ms": _optional_number(raw["runtime_ms"], f"{context}.runtime_ms", minimum=0.0),
        })
    supplied_pareto = {
        (record["scenario"], record["method"], record["active_guide_count"]): record
        for record in adaptive_pareto
    }
    compact_pareto_keys = {
        (
            str(record["scenario"]),
            str(record["method"]),
            int(record["metrics"]["active_guide_count"]),
        )
        for record in records
        if record["resource_regime"] == "adaptive_resource"
    }
    if set(supplied_pareto) != compact_pareto_keys:
        raise EvidenceValidationError(
            "adaptive_pareto rows do not exactly match compact scenario/method/active-count groups."
        )
    for key, supplied in supplied_pareto.items():
        scenario, method, active_count = key
        selected = [
            record
            for record in records
            if record["scenario"] == scenario
            and record["method"] == method
            and record["resource_regime"] == "adaptive_resource"
            and record["metrics"]["active_guide_count"] == active_count
        ]
        if supplied["aggregation"] != "median_by_scenario_method_active_count":
            raise EvidenceValidationError(
                f"adaptive_pareto {key!r} uses an unsupported aggregation."
            )
        if supplied["denominator"] != len(selected):
            raise EvidenceValidationError(
                f"adaptive_pareto {key!r} denominator disagrees with compact records."
            )
        for field in (
            "truth_coverage",
            "maximum_consecutive_arc_gap",
            "path_length",
            "runtime_ms",
        ):
            _require_same_number(
                supplied[field],
                _observed_median(selected, field),
                f"adaptive_pareto.{scenario}.{method}.{active_count}.{field}",
            )

    failure_value = document["failure_composition"]
    if not isinstance(failure_value, Mapping):
        raise EvidenceValidationError("failure_composition must be an object.")
    _require_fields(failure_value, ("counts", "total", "all_records_accounted_for"), "failure_composition")
    counts_value = failure_value["counts"]
    if not isinstance(counts_value, Mapping) or not counts_value:
        raise EvidenceValidationError("failure_composition.counts must be a non-empty object.")
    failure_counts: dict[str, int] = {}
    for key, count in counts_value.items():
        status = _text(key, "failure_composition status").upper()
        if status == "CONVERGED" or status not in TERMINAL_STATUSES:
            raise EvidenceValidationError(f"failure_composition contains unsupported status {status!r}.")
        failure_counts[status] = _nonnegative_integer(count, f"failure_composition.counts.{key}")
    expected_counts: dict[str, int] = {}
    for record in v2_records:
        status = str(record["terminal_status"])
        expected_counts[status] = expected_counts.get(status, 0) + 1
    if failure_counts != expected_counts:
        raise EvidenceValidationError(
            "failure_composition.counts must exactly reproduce all v2.1 deployment records."
        )
    declared_total = _positive_integer(failure_value["total"], "failure_composition.total")
    if declared_total != len(v2_records) or sum(failure_counts.values()) != len(v2_records):
        raise EvidenceValidationError(
            "failure_composition denominator must equal the v2.1 deployment record count."
        )
    if failure_value["all_records_accounted_for"] is not True:
        raise EvidenceValidationError("failure_composition.all_records_accounted_for must be JSON true.")

    g6_value = document["g6_tracking_comparator"]
    if not isinstance(g6_value, Mapping):
        raise EvidenceValidationError("g6_tracking_comparator must be an object.")
    g6_fields = (
        "record_count",
        "blocked_record_count",
        "controller_terminal_counts",
        "controller_terminal_rates",
        "blocked_timeout_count",
        "blocked_timeout_rate",
        "semantics",
    )
    _require_fields(g6_value, g6_fields, "g6_tracking_comparator")
    g6_record_count = _positive_integer(
        g6_value["record_count"], "g6_tracking_comparator.record_count"
    )
    if g6_record_count != len(g6_records):
        raise EvidenceValidationError(
            "g6_tracking_comparator.record_count disagrees with compact records."
        )
    blocked_g6 = [record for record in g6_records if record["blocked_route_episode"]]
    blocked_count = _nonnegative_integer(
        g6_value["blocked_record_count"], "g6_tracking_comparator.blocked_record_count"
    )
    if blocked_count != len(blocked_g6):
        raise EvidenceValidationError(
            "g6_tracking_comparator.blocked_record_count disagrees with compact records."
        )
    raw_controller_counts = g6_value["controller_terminal_counts"]
    raw_controller_rates = g6_value["controller_terminal_rates"]
    if not isinstance(raw_controller_counts, Mapping) or not raw_controller_counts:
        raise EvidenceValidationError(
            "g6_tracking_comparator.controller_terminal_counts must be a non-empty object."
        )
    if not isinstance(raw_controller_rates, Mapping):
        raise EvidenceValidationError(
            "g6_tracking_comparator.controller_terminal_rates must be an object."
        )
    controller_counts: dict[str, int] = {}
    for raw_status, raw_count in raw_controller_counts.items():
        status = _text(raw_status, "g6_tracking_comparator controller status").upper()
        if status != "CONVERGED" and status not in TERMINAL_STATUSES:
            raise EvidenceValidationError(
                f"g6_tracking_comparator contains unsupported controller status {status!r}."
            )
        controller_counts[status] = _nonnegative_integer(
            raw_count, f"g6_tracking_comparator.controller_terminal_counts.{raw_status}"
        )
    expected_controller_counts: dict[str, int] = {}
    for record in g6_records:
        status = str(record["controller_terminal_state"])
        expected_controller_counts[status] = expected_controller_counts.get(status, 0) + 1
    if controller_counts != expected_controller_counts:
        raise EvidenceValidationError(
            "g6_tracking_comparator.controller_terminal_counts disagrees with compact records."
        )
    controller_rates: dict[str, float] = {}
    for raw_status, raw_rate in raw_controller_rates.items():
        status = _text(raw_status, "g6_tracking_comparator controller rate status").upper()
        if status in controller_rates:
            raise EvidenceValidationError(
                "g6_tracking_comparator.controller_terminal_rates contains duplicate normalized statuses."
            )
        controller_rates[status] = _number(
            raw_rate,
            f"g6_tracking_comparator.controller_terminal_rates.{raw_status}",
            minimum=0.0,
            maximum=1.0,
        )
    if set(controller_rates) != set(controller_counts):
        raise EvidenceValidationError(
            "g6_tracking_comparator.controller_terminal_rates must cover exactly the counted statuses."
        )
    for status, count in controller_counts.items():
        rate = controller_rates[status]
        if not math.isclose(rate, count / g6_record_count, abs_tol=1e-12):
            raise EvidenceValidationError(
                f"g6_tracking_comparator.controller_terminal_rates.{status} is inconsistent."
            )
    blocked_timeout_count = _nonnegative_integer(
        g6_value["blocked_timeout_count"], "g6_tracking_comparator.blocked_timeout_count"
    )
    expected_blocked_timeout_count = sum(
        record["controller_terminal_state"] == "TIMEOUT" for record in blocked_g6
    )
    if blocked_timeout_count != expected_blocked_timeout_count:
        raise EvidenceValidationError(
            "g6_tracking_comparator.blocked_timeout_count disagrees with compact records."
        )
    expected_blocked_timeout_rate = (
        expected_blocked_timeout_count / blocked_count if blocked_count else None
    )
    supplied_blocked_timeout_rate = _optional_number(
        g6_value["blocked_timeout_rate"],
        "g6_tracking_comparator.blocked_timeout_rate",
        minimum=0.0,
        maximum=1.0,
    )
    _require_same_number(
        supplied_blocked_timeout_rate,
        expected_blocked_timeout_rate,
        "g6_tracking_comparator.blocked_timeout_rate",
    )
    semantics = _text(g6_value["semantics"], "g6_tracking_comparator.semantics")
    if len(v2_records) + len(g6_records) != record_count:
        raise EvidenceValidationError("v2.1 and G6 comparator partitions do not close.")

    blocked_timeout_paired = _validate_blocked_pairs(document["blocked_timeout_paired"], records)
    return {
        "scenario_summary": scenario_summary,
        "same_resource": same_resource,
        "adaptive_pareto": adaptive_pareto,
        "failure_counts": failure_counts,
        "failure_denominator": len(v2_records),
        "g6_tracking_comparator": {
            "record_count": g6_record_count,
            "blocked_record_count": blocked_count,
            "controller_terminal_counts": controller_counts,
            "blocked_timeout_count": blocked_timeout_count,
            "blocked_timeout_rate": supplied_blocked_timeout_rate,
            "semantics": semantics,
        },
        "blocked_timeout_paired": blocked_timeout_paired,
    }


def _points(value: Any, context: str, *, minimum_count: int = 0) -> np.ndarray:
    try:
        points = np.asarray(value, dtype=float)
    except (TypeError, ValueError) as error:
        raise EvidenceValidationError(f"{context} must be a finite (N, 2) array.") from error
    if points.size == 0 and minimum_count == 0:
        return np.empty((0, 2), dtype=float)
    if points.ndim != 2 or points.shape[1:] != (2,) or not np.all(np.isfinite(points)):
        raise EvidenceValidationError(f"{context} must be a finite (N, 2) array.")
    if len(points) < minimum_count:
        raise EvidenceValidationError(f"{context} requires at least {minimum_count} points.")
    return points.copy()


def _polyline_list(
    value: Any,
    context: str,
    *,
    minimum_count: int = 2,
    allow_empty: bool = False,
) -> list[np.ndarray]:
    if not isinstance(value, list) or (not value and not allow_empty):
        qualifier = "a list" if allow_empty else "a non-empty list"
        raise EvidenceValidationError(f"{context} must be {qualifier} of polylines.")
    return [
        _points(item, f"{context}[{index}]", minimum_count=minimum_count)
        for index, item in enumerate(value)
    ]


def _is_concave(points: np.ndarray) -> bool:
    polygon = points[:-1] if np.array_equal(points[0], points[-1]) else points
    if len(polygon) < 4:
        return False
    signs: set[int] = set()
    for index in range(len(polygon)):
        first = polygon[(index + 1) % len(polygon)] - polygon[index]
        second = polygon[(index + 2) % len(polygon)] - polygon[(index + 1) % len(polygon)]
        cross = float(first[0] * second[1] - first[1] * second[0])
        if abs(cross) > 1e-10:
            signs.add(1 if cross > 0.0 else -1)
    return len(signs) > 1


def _validate_case(
    value: Any,
    context: str,
    *,
    records_by_id: Mapping[str, Mapping[str, Any]],
    expected_selection_rule: str,
    allow_partial_failure_geometry: bool = False,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise EvidenceValidationError(f"{context} must be an object.")
    _require_fields(value, CASE_FIELDS, context)
    source_record_id = _text(value["source_record_id"], f"{context}.source_record_id")
    if source_record_id not in records_by_id:
        raise EvidenceValidationError(f"{context}.source_record_id is absent from records_compact.json.")
    source = records_by_id[source_record_id]
    source_hash = _hex_digest(value["source_record_sha256"], f"{context}.source_record_sha256")
    if source_hash != source["source_record_sha256"]:
        raise EvidenceValidationError(f"{context}.source_record_sha256 is not the canonical source-record hash.")
    scenario = _canonical_scenario(value["scenario"])
    seed = _nonnegative_integer(value["seed"], f"{context}.seed")
    regime = _text(value["resource_regime"], f"{context}.resource_regime")
    selection_rule = _text(value["selection_rule"], f"{context}.selection_rule")
    if selection_rule != expected_selection_rule:
        raise EvidenceValidationError(f"{context}.selection_rule is not the frozen deterministic rule.")
    layers = _validate_layers(value, context)
    terminal_status = _terminal_status(
        value["terminal_status"],
        f"{context}.terminal_status",
        estimated_success=layers["estimated_deployment_success"],
        truth_success=layers["truth_validated_success"],
    )
    controller_terminal_state = _text(
        value["controller_terminal_state"], f"{context}.controller_terminal_state"
    ).upper()
    if controller_terminal_state != "CONVERGED" and controller_terminal_state not in TERMINAL_STATUSES:
        raise EvidenceValidationError(f"{context}.controller_terminal_state is unsupported.")
    metadata = {
        "scenario": scenario,
        "seed": seed,
        "pair_id": _text(value["pair_id"], f"{context}.pair_id"),
        "method": _text(value["method"], f"{context}.method"),
        "route_variant": _text(value["route_variant"], f"{context}.route_variant"),
        "resource_regime": regime,
        "terminal_status": terminal_status,
        "controller_terminal_state": controller_terminal_state,
        **layers,
    }
    for key, expected in metadata.items():
        if source[key] != expected:
            raise EvidenceValidationError(f"{context}.{key} disagrees with source record {source_record_id!r}.")
    minimum_geometry_count = 0 if allow_partial_failure_geometry else 3
    truth = _points(
        value["truth_boundary"],
        f"{context}.truth_boundary",
        minimum_count=minimum_geometry_count,
    )
    polygon = _points(
        value["source_polygon"],
        f"{context}.source_polygon",
        minimum_count=minimum_geometry_count,
    )
    targets = _points(value["targets"], f"{context}.targets", minimum_count=0)
    initial = _points(value["initial_positions"], f"{context}.initial_positions", minimum_count=1)
    paths = _polyline_list(value["paths"], f"{context}.paths", allow_empty=True)
    trajectories = _polyline_list(
        value["trajectories"], f"{context}.trajectories", minimum_count=1
    )
    media_payload_sha256 = _canonical_json_sha256(
        {field: value[field] for field in MEDIA_PAYLOAD_FIELDS}
    )
    if media_payload_sha256 != source["media_payload_sha256"]:
        raise EvidenceValidationError(
            f"{context} geometry payload is not the media payload frozen in its compact record."
        )
    guide_count = len(initial)
    if guide_count != source["metrics"]["active_guide_count"]:
        raise EvidenceValidationError(
            f"{context} guide count disagrees with compact metrics.active_guide_count."
        )
    if len(trajectories) != guide_count:
        raise EvidenceValidationError(f"{context} guide/trajectory counts must match.")
    if bool(targets.size) != bool(paths) or (paths and len(targets) != guide_count) or (
        paths and len(paths) != guide_count
    ):
        raise EvidenceValidationError(
            f"{context} targets and paths must both be absent or cover every guide."
        )
    if layers["estimated_deployment_success"] and not paths:
        raise EvidenceValidationError(f"{context} successful evidence requires targets and paths.")
    if layers["estimated_deployment_success"] and len(polygon) < 3:
        raise EvidenceValidationError(f"{context} successful evidence requires a source polygon.")
    for index, (start, trajectory) in enumerate(zip(initial, trajectories, strict=True)):
        if not np.allclose(trajectory[0], start, atol=1e-9):
            raise EvidenceValidationError(f"{context}.trajectories[{index}] must start at its guide position.")
    if paths:
        for index, (start, target, path, trajectory) in enumerate(
            zip(initial, targets, paths, trajectories, strict=True)
        ):
            if not np.allclose(path[0], start, atol=1e-9) or not np.allclose(path[-1], target, atol=1e-9):
                raise EvidenceValidationError(f"{context}.paths[{index}] must start at its guide and end at its target.")
    if layers["estimated_deployment_success"]:
        final_positions = np.vstack([trajectory[-1] for trajectory in trajectories])
        aggregate_rmse = float(
            np.sqrt(np.mean(np.sum((final_positions - targets) ** 2, axis=1)))
        )
        _require_same_number(
            source["metrics"]["tracking_rmse"],
            aggregate_rmse,
            f"{context}.metrics.tracking_rmse",
        )
        if aggregate_rmse > TRAJECTORY_ENDPOINT_TOLERANCE:
            raise EvidenceValidationError(
                f"{context} aggregate final tracking RMSE exceeds the frozen waypoint tolerance."
            )
    return {
        "source_record_id": source_record_id,
        "source_record_sha256": source_hash,
        "selection_rule": selection_rule,
        **metadata,
        "truth_boundary": truth,
        "source_polygon": polygon,
        "targets": targets,
        "initial_positions": initial,
        "paths": paths,
        "trajectories": trajectories,
    }


def _status_text(case: Mapping[str, Any]) -> str:
    if case["method"] == "g6_fixed_resource_rerun":
        return (
            f"{case['method']} / {case['route_variant']}: "
            f"G6 tracking {case['controller_terminal_state']}; v2.1 deployment layers N/A"
        )
    return f"{case['method']} / {case['route_variant']}: {case['terminal_status']}"


def _validate_comparison(
    value: Any,
    context: str,
    *,
    expected_scenario: str,
    records_by_id: Mapping[str, Mapping[str, Any]],
    blocked_pairs: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    if not isinstance(value, Mapping) or set(value) != {"before", "after"}:
        raise EvidenceValidationError(f"{context} must contain exactly before and after cases.")
    cases = {
        key: _validate_case(
            value[key],
            f"{context}.{key}",
            records_by_id=records_by_id,
            expected_selection_rule=SELECTION_RULES["comparison"],
        )
        for key in ("before", "after")
    }
    before, after = cases["before"], cases["after"]
    if before["route_variant"] != ROUTE_VARIANTS[0] or after["route_variant"] != ROUTE_VARIANTS[1]:
        raise EvidenceValidationError(
            f"{context} must compare the frozen G6 adapter before visibility_graph."
        )
    paired_fields = ("scenario", "seed", "pair_id", "resource_regime")
    if any(before[field] != after[field] for field in paired_fields):
        raise EvidenceValidationError(f"{context} before/after cases are not seed/pair/resource matched.")
    if before["scenario"] != expected_scenario:
        raise EvidenceValidationError(f"{context} scenario does not match its U/C slot.")
    # Boundary and target geometry are method outputs and may differ between
    # the frozen G6 adapter and v2.1.  Pair identity, truth, and starts must
    # match, while each panel retains its actual source, targets, and paths.
    for field in ("truth_boundary", "initial_positions"):
        if not np.array_equal(before[field], after[field]):
            raise EvidenceValidationError(f"{context} before/after {field} differs.")
    if not _is_concave(before["source_polygon"]) or not _is_concave(after["source_polygon"]):
        raise EvidenceValidationError(
            f"{context} must preserve genuinely concave U/C source polygons in both panels."
        )
    frozen_pairs = blocked_pairs["scenarios"][expected_scenario]["pair_ids"]
    if before["pair_id"] != min(frozen_pairs):
        raise EvidenceValidationError(f"{context} is not the first complete pair under the frozen rule.")
    return cases


def _validate_media_evidence(
    document: Mapping[str, Any],
    *,
    identity: Mapping[str, Any],
    records_hash: str,
    records: Sequence[Mapping[str, Any]],
    records_by_id: Mapping[str, Mapping[str, Any]],
    blocked_pairs: Mapping[str, Any],
) -> dict[str, Any]:
    _validate_holdout_identity(
        document,
        schema=MEDIA_EVIDENCE_SCHEMA,
        fields=EVIDENCE_FIELDS,
        context="media_evidence",
        identity=identity,
        records_hash=records_hash,
        record_count=len(records),
    )
    v2_1_records = [
        record
        for record in records
        if record["v2_1_routing_pipeline"]
        and record["method"] != "g6_fixed_resource_rerun"
    ]
    eligible_successes = sorted(
        record["record_id"] for record in v2_1_records if record["truth_validated_success"]
    )
    eligible_failures = sorted(
        record["record_id"] for record in v2_1_records if not record["truth_validated_success"]
    )
    if eligible_successes:
        if document["success_case"] is None:
            raise EvidenceValidationError("success_case is required when v2.1 truth successes exist.")
        success: dict[str, Any] | None = _validate_case(
            document["success_case"],
            "success_case",
            records_by_id=records_by_id,
            expected_selection_rule=SELECTION_RULES["success_case"],
        )
        if not success["truth_validated_success"]:
            raise EvidenceValidationError("success_case is not truth-validated success evidence.")
        if success["source_record_id"] != eligible_successes[0]:
            raise EvidenceValidationError(
                "success_case is not the first v2.1 truth success by frozen record_id."
            )
    else:
        if document["success_case"] is not None:
            raise EvidenceValidationError(
                "success_case must be null when the frozen v2.1 method family has no truth success."
            )
        success = None
    if eligible_failures:
        if document["failure_case"] is None:
            raise EvidenceValidationError("failure_case is required when failed v2.1 records exist.")
        failure: dict[str, Any] | None = _validate_case(
            document["failure_case"],
            "failure_case",
            records_by_id=records_by_id,
            expected_selection_rule=SELECTION_RULES["failure_case"],
            allow_partial_failure_geometry=True,
        )
        if failure["truth_validated_success"]:
            raise EvidenceValidationError("failure_case may not claim truth-validated success.")
        if failure["source_record_id"] != eligible_failures[0]:
            raise EvidenceValidationError(
                "failure_case is not the first v2.1 truth failure by frozen record_id."
            )
    else:
        if document["failure_case"] is not None:
            raise EvidenceValidationError(
                "failure_case must be null when every frozen v2.1 record is truth success."
            )
        failure = None
    return {
        "success_case": success,
        "failure_case": failure,
        "u_shape_comparison": _validate_comparison(
            document["u_shape_comparison"],
            "u_shape_comparison",
            expected_scenario="u_shape",
            records_by_id=records_by_id,
            blocked_pairs=blocked_pairs,
        ),
        "c_shape_comparison": _validate_comparison(
            document["c_shape_comparison"],
            "c_shape_comparison",
            expected_scenario="c_shape",
            records_by_id=records_by_id,
            blocked_pairs=blocked_pairs,
        ),
    }


def _closed(points: np.ndarray) -> np.ndarray:
    if len(points) == 0:
        return points
    if np.array_equal(points[0], points[-1]):
        return points
    return np.vstack((points, points[0]))


def _scenario_sort_key(value: str) -> tuple[int, str]:
    return SCENARIO_ORDER.get(value, len(SCENARIO_ORDER)), value


def _pretty(value: str) -> str:
    return value.replace("_", " ").title()


def _save_png(fig: plt.Figure, path: Path) -> None:
    fig.tight_layout()
    fig.savefig(
        path,
        dpi=160,
        bbox_inches="tight",
        metadata={"Software": "Crowd-Management ABCG-v2.1"},
    )
    plt.close(fig)


def _label_bars(ax: Axes, bars: Any, *, percentage: bool = False) -> None:
    for bar in bars:
        height = float(bar.get_height())
        label = f"{height:.0%}" if percentage else f"{height:.2f}"
        ax.annotate(
            label,
            (bar.get_x() + bar.get_width() / 2.0, height),
            xytext=(0, 3),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=8,
        )


def _plot_blocked_timeout(summary: Mapping[str, Any], path: Path) -> None:
    scenarios = ("u_shape", "c_shape")
    x = np.arange(len(scenarios), dtype=float)
    width = 0.34
    paired = summary["blocked_timeout_paired"]
    g6 = [paired["scenarios"][scenario]["baseline_timeout_rate"] for scenario in scenarios]
    g7 = [paired["scenarios"][scenario]["candidate_timeout_rate"] for scenario in scenarios]
    fig, ax = plt.subplots(figsize=(7.2, 4.4))
    first = ax.bar(x - width / 2.0, g6, width, label=paired["baseline_label"], color=COLORS[3])
    second = ax.bar(x + width / 2.0, g7, width, label=paired["candidate_label"], color=COLORS[0])
    _label_bars(ax, first, percentage=True)
    _label_bars(ax, second, percentage=True)
    ax.set_xticks(x, [_pretty(item) for item in scenarios])
    ax.set_ylabel("One-sided blocked-route TIMEOUT rate")
    ax.set_ylim(0.0, 1.12)
    ax.set_title("Paired U/C holdout: frozen G6 fixed-resource adapter rerun")
    ax.grid(axis="y", alpha=0.22)
    ax.legend(loc="upper right", fontsize=8)
    _save_png(fig, path)


def _plot_same_resource(summary: Mapping[str, Any], path: Path) -> None:
    records = summary["same_resource"]
    scenarios = sorted({record["scenario"] for record in records}, key=_scenario_sort_key)
    methods = sorted({record["method"] for record in records})
    lookup = {(record["scenario"], record["method"]): record for record in records}
    x = np.arange(len(scenarios), dtype=float)
    width = 0.78 / len(methods)
    fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.5))
    for method_index, method in enumerate(methods):
        offset = (method_index - (len(methods) - 1) / 2.0) * width
        coverage = [lookup[(scenario, method)]["truth_coverage"] for scenario in scenarios]
        gap = [lookup[(scenario, method)]["maximum_consecutive_arc_gap"] for scenario in scenarios]
        axes[0].bar(x + offset, coverage, width, color=COLORS[method_index % len(COLORS)], label=method)
        axes[1].bar(x + offset, gap, width, color=COLORS[method_index % len(COLORS)], label=method)
    counts = [int(lookup[(scenario, methods[0])]["active_guide_count"]) for scenario in scenarios]
    labels = [f"{_pretty(scenario)}\nm={count}" for scenario, count in zip(scenarios, counts, strict=True)]
    axes[0].set_ylabel("Truth coverage")
    axes[0].set_ylim(0.0, 1.05)
    axes[0].set_title("Coverage at matched active-guide count")
    axes[1].set_ylabel("Maximum consecutive arc gap")
    axes[1].set_title("Arc gap at matched active-guide count")
    for ax in axes:
        ax.set_xticks(x, labels)
        ax.grid(axis="y", alpha=0.22)
    axes[0].legend(loc="lower right", fontsize=8)
    _save_png(fig, path)


def _plot_resource_pareto(summary: Mapping[str, Any], path: Path) -> None:
    records = summary["adaptive_pareto"]
    metrics = (
        ("truth_coverage", "Truth coverage", "higher is better"),
        ("maximum_consecutive_arc_gap", "Maximum arc gap", "lower is better"),
        ("path_length", "Total path length", "lower is better"),
        ("runtime_ms", "Runtime (ms)", "lower is better"),
    )
    series = sorted({(record["scenario"], record["method"]) for record in records})
    fig, axes = plt.subplots(2, 2, figsize=(10.5, 8.0))
    for ax, (field, label, direction) in zip(axes.ravel(), metrics, strict=True):
        for series_index, (scenario, method) in enumerate(series):
            selected = [
                record
                for record in records
                if record["scenario"] == scenario and record["method"] == method
            ]
            selected.sort(key=lambda record: (record["active_guide_count"], record[field]))
            x = [record["active_guide_count"] for record in selected]
            y = [record[field] for record in selected]
            ax.plot(
                x,
                y,
                marker="o",
                linewidth=1.4,
                color=COLORS[series_index % len(COLORS)],
                label=f"{_pretty(scenario)} / {method}",
            )
        ax.set_xlabel("Active guide count")
        ax.set_ylabel(label)
        ax.set_title(f"{label} ({direction})")
        ax.grid(alpha=0.22)
    axes[0, 0].legend(loc="best", fontsize=8)
    aggregations = sorted({record["aggregation"] for record in records})
    fig.suptitle(f"Adaptive-resource deployment Pareto views ({', '.join(aggregations)})")
    _save_png(fig, path)


def _plot_failure_composition(summary: Mapping[str, Any], path: Path) -> None:
    counts = summary["failure_counts"]
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    labels = [item[0].replace("_", " ") for item in ordered]
    values = [item[1] for item in ordered]
    total = sum(values)
    y = np.arange(len(labels))
    colors = [
        COLORS[2]
        if status == "TRUTH_VALIDATED_SUCCESS"
        else COLORS[1]
        if status == "ESTIMATED_DEPLOYMENT_SUCCESS_ONLY"
        else COLORS[3]
        for status, _ in ordered
    ]
    fig, ax = plt.subplots(figsize=(9.0, max(3.8, 0.48 * len(labels) + 1.7)))
    bars = ax.barh(y, values, color=colors)
    for bar, value in zip(bars, values, strict=True):
        ax.annotate(
            f"{value} ({value / total:.1%})",
            (float(bar.get_width()), bar.get_y() + bar.get_height() / 2.0),
            xytext=(5, 0),
            textcoords="offset points",
            va="center",
            fontsize=8,
        )
    ax.set_yticks(y, labels)
    ax.invert_yaxis()
    ax.set_xlabel("Holdout episode count")
    ax.set_title(f"G7 terminal and failure composition (n={total})")
    ax.grid(axis="x", alpha=0.22)
    _save_png(fig, path)


def _all_case_points(case: Mapping[str, Any]) -> list[np.ndarray]:
    values = [case["truth_boundary"], case["source_polygon"], case["targets"], case["initial_positions"]]
    for groups_name in ("paths", "trajectories"):
        values.extend(case[groups_name])
    return [value for value in values if len(value)]


def _limits(case: Mapping[str, Any]) -> tuple[tuple[float, float], tuple[float, float]]:
    available = _all_case_points(case)
    combined = np.vstack(available) if available else np.array([[0.0, 0.0]])
    low = np.min(combined, axis=0)
    high = np.max(combined, axis=0)
    span = np.maximum(high - low, 1.0)
    pad = 0.08 * span
    return (float(low[0] - pad[0]), float(high[0] + pad[0])), (
        float(low[1] - pad[1]),
        float(high[1] + pad[1]),
    )


def _plot_case_base(ax: Axes, case: Mapping[str, Any], *, show_legend: bool) -> None:
    truth = _closed(case["truth_boundary"])
    if len(case["source_polygon"]):
        source = _closed(case["source_polygon"])
        ax.fill(source[:, 0], source[:, 1], color="#a8adb4", alpha=0.28, label="source polygon")
    ax.plot(truth[:, 0], truth[:, 1], color="#252a31", linewidth=1.5, label="truth boundary")
    targets = case["targets"]
    initial = case["initial_positions"]
    ax.scatter(targets[:, 0], targets[:, 1], marker="*", s=58, color="#d18420", label="targets", zorder=5)
    ax.scatter(initial[:, 0], initial[:, 1], marker="x", s=38, color="#7a5aa6", label="initial", zorder=5)
    ax.set_aspect("equal", adjustable="box")
    xlim, ylim = _limits(case)
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    ax.grid(alpha=0.18)
    if show_legend:
        ax.legend(loc="best", fontsize=7)


def _plot_variant(ax: Axes, case: Mapping[str, Any], *, show_legend: bool) -> None:
    _plot_case_base(ax, case, show_legend=False)
    for index, line in enumerate(case["paths"]):
        ax.plot(
            line[:, 0],
            line[:, 1],
            linestyle="--",
            linewidth=1.2,
            color=COLORS[index % len(COLORS)],
            alpha=0.8,
            label="planned path" if index == 0 else None,
        )
    for index, line in enumerate(case["trajectories"]):
        ax.plot(
            line[:, 0],
            line[:, 1],
            linewidth=1.5,
            color=COLORS[index % len(COLORS)],
            label="trajectory" if index == 0 else None,
        )
    ax.set_title(_status_text(case), fontsize=8.5, wrap=True)
    if show_legend:
        ax.legend(loc="best", fontsize=7)


def _plot_route_comparison(cases: Mapping[str, Mapping[str, Any]], path: Path) -> None:
    u_case = cases["u_shape_comparison"]
    c_case = cases["c_shape_comparison"]
    fig, axes = plt.subplots(2, 2, figsize=(10.5, 8.8))
    for row, (shape_name, comparison) in enumerate((("U-shape", u_case), ("C-shape", c_case))):
        for column, key in enumerate(("before", "after")):
            _plot_variant(
                axes[row, column], comparison[key], show_legend=(row == 0 and column == 0)
            )
            axes[row, column].set_ylabel(shape_name if column == 0 else "")
    fig.suptitle("Frozen holdout exemplars: route and trajectory comparison")
    _save_png(fig, path)


def _plot_single_case(case: Mapping[str, Any], path: Path, title: str) -> None:
    fig, ax = plt.subplots(figsize=(7.2, 6.0))
    _plot_case_base(ax, case, show_legend=False)
    for index, line in enumerate(case["paths"]):
        ax.plot(
            line[:, 0],
            line[:, 1],
            linestyle="--",
            linewidth=1.2,
            color=COLORS[index % len(COLORS)],
            alpha=0.8,
            label="planned path" if index == 0 else None,
        )
    for index, line in enumerate(case["trajectories"]):
        ax.plot(
            line[:, 0],
            line[:, 1],
            linewidth=1.6,
            color=COLORS[index % len(COLORS)],
            label="trajectory" if index == 0 else None,
        )
    ax.set_title(f"{title}\n{_status_text(case)}")
    ax.legend(loc="best", fontsize=7)
    _save_png(fig, path)


def _plot_placeholder(path: Path, title: str, detail: str) -> None:
    fig, ax = plt.subplots(figsize=(7.2, 5.4))
    ax.axis("off")
    ax.text(
        0.5,
        0.58,
        title,
        transform=ax.transAxes,
        ha="center",
        va="center",
        fontsize=17,
        weight="bold",
        color=COLORS[3],
    )
    ax.text(
        0.5,
        0.40,
        detail,
        transform=ax.transAxes,
        ha="center",
        va="center",
        fontsize=10,
        color="#454b52",
    )
    _save_png(fig, path)


def _build_placeholder_gif(path: Path, title: str, detail: str) -> dict[str, Any]:
    fig, ax = plt.subplots(figsize=(6.8, 5.8))
    ax.axis("off")
    ax.text(
        0.5,
        0.58,
        title,
        transform=ax.transAxes,
        ha="center",
        va="center",
        fontsize=17,
        weight="bold",
        color=COLORS[3],
    )
    ax.text(
        0.5,
        0.40,
        detail,
        transform=ax.transAxes,
        ha="center",
        va="center",
        fontsize=10,
        color="#454b52",
    )
    writer = PillowWriter(fps=1)
    with writer.saving(fig, str(path), dpi=110):
        writer.grab_frame()
    plt.close(fig)
    return {
        "source_frame_count": 0,
        "rendered_frame_count": 1,
        "success_media_is_placeholder": True,
    }


def _build_success_gif(case: Mapping[str, Any], path: Path) -> dict[str, int]:
    trajectories = case["trajectories"]
    paths = case["paths"]
    max_points = max(len(line) for line in trajectories)
    rendered_count = min(max_points, 60)
    frame_indices = np.unique(np.linspace(0, max_points - 1, rendered_count, dtype=int))
    fig, ax = plt.subplots(figsize=(6.8, 5.8))
    writer = PillowWriter(fps=4)
    with writer.saving(fig, str(path), dpi=110):
        for frame_index in frame_indices:
            ax.clear()
            _plot_case_base(ax, case, show_legend=False)
            for path_index, line in enumerate(paths):
                ax.plot(
                    line[:, 0],
                    line[:, 1],
                    linestyle="--",
                    linewidth=1.0,
                    color=COLORS[path_index % len(COLORS)],
                    alpha=0.45,
                )
            for trajectory_index, line in enumerate(trajectories):
                endpoint = min(int(frame_index), len(line) - 1)
                trace = line[: endpoint + 1]
                color = COLORS[trajectory_index % len(COLORS)]
                ax.plot(trace[:, 0], trace[:, 1], linewidth=1.7, color=color)
                ax.scatter(trace[-1, 0], trace[-1, 1], s=35, color=color, zorder=6)
            ax.set_title(f"Frozen holdout success exemplar\n{_status_text(case)}")
            writer.grab_frame()
    plt.close(fig)
    return {"source_frame_count": int(max_points), "rendered_frame_count": int(len(frame_indices))}


def _publish_staged_directory(staging_root: Path, output_root: Path) -> None:
    """Publish one complete directory while preserving the prior output on failure."""

    if output_root.exists() and not output_root.is_dir():
        raise EvidenceValidationError(f"Media output exists but is not a directory: {output_root}")
    backup_root: Path | None = None
    if output_root.exists():
        backup_root = output_root.parent / f".{output_root.name}.backup-{uuid.uuid4().hex}"
        output_root.rename(backup_root)
    try:
        staging_root.rename(output_root)
    except BaseException:
        if backup_root is not None and backup_root.exists() and not output_root.exists():
            backup_root.rename(output_root)
        raise
    if backup_root is not None:
        shutil.rmtree(backup_root)


def _render_media(
    summary: Mapping[str, Any],
    cases: Mapping[str, Any],
    output_root: Path,
) -> dict[str, Any]:
    plt.rcParams.update(
        {
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "axes.edgecolor": "#454b52",
            "axes.labelcolor": "#252a31",
            "text.color": "#252a31",
            "font.size": 9.5,
            "savefig.facecolor": "white",
        }
    )
    _plot_blocked_timeout(summary, output_root / "blocked_route_timeout.png")
    _plot_same_resource(summary, output_root / "same_resource_coverage_gap.png")
    _plot_resource_pareto(summary, output_root / "resource_pareto.png")
    _plot_failure_composition(summary, output_root / "failure_composition.png")
    _plot_route_comparison(cases, output_root / "u_c_route_comparison.png")
    if cases["success_case"] is None:
        animation = _build_placeholder_gif(
            output_root / "success_case.gif",
            "No truth-validated success",
            "No frozen ABCG-v2.1 method-family record is truth-validated success.",
        )
        animation["success_exemplar_status"] = "UNAVAILABLE_NO_V2_1_TRUTH_VALIDATED_SUCCESS"
    else:
        animation = _build_success_gif(
            cases["success_case"], output_root / "success_case.gif"
        )
        animation["success_media_is_placeholder"] = False
        animation["success_exemplar_status"] = "AVAILABLE"
    if cases["failure_case"] is None:
        _plot_placeholder(
            output_root / "failure_case.png",
            "No failed holdout record",
            "No frozen ABCG-v2.1 method-family record is a truth-validated failure.",
        )
        animation["failure_media_is_placeholder"] = True
        animation["failure_exemplar_status"] = "UNAVAILABLE_NO_V2_1_TRUTH_FAILURE"
    else:
        _plot_single_case(
            cases["failure_case"],
            output_root / "failure_case.png",
            "Frozen holdout failure exemplar",
        )
        animation["failure_media_is_placeholder"] = False
        animation["failure_exemplar_status"] = "AVAILABLE"
    return animation


def build_media(input_dir: str | Path, output_dir: str | Path) -> dict[str, Any]:
    """Validate four linked evidence files and atomically publish seven assets."""

    input_root = Path(input_dir).resolve()
    output_root = Path(output_dir).resolve()
    if input_root == output_root or input_root.is_relative_to(output_root) or output_root.is_relative_to(input_root):
        raise EvidenceValidationError("Input and output directories must not overlap.")
    freeze_document, freeze_hash = _read_json(input_root / FREEZE_FILE)
    records_document, records_hash = _read_json(input_root / RECORDS_FILE)
    summary_document, summary_hash = _read_json(input_root / SUMMARY_FILE)
    media_document, media_hash = _read_json(input_root / EVIDENCE_FILE)
    identity = _validate_freeze(freeze_document)
    records, records_by_id = _validate_records(records_document, identity)
    summary = _validate_summary(
        summary_document,
        identity=identity,
        records_hash=records_hash,
        records=records,
    )
    cases = _validate_media_evidence(
        media_document,
        identity=identity,
        records_hash=records_hash,
        records=records,
        records_by_id=records_by_id,
        blocked_pairs=summary["blocked_timeout_paired"],
    )

    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging_root = Path(
        tempfile.mkdtemp(prefix=f".{output_root.name}.staging-", dir=output_root.parent)
    )
    try:
        animation = _render_media(summary, cases, staging_root)

        outputs = {
            name: {
                "sha256": _sha256_file(staging_root / name),
                "bytes": int((staging_root / name).stat().st_size),
            }
            for name in MEDIA_FILES
        }
        manifest: dict[str, Any] = {
            "schema": MANIFEST_SCHEMA,
            "split": "holdout",
            "pilot_data_used": False,
            "frozen_sha": identity["frozen_sha"],
            "config_hash": identity["config_hash"],
            "records_sha256": records_hash,
            "record_count": len(records),
            "inputs": {
                FREEZE_FILE: {"schema": FREEZE_SCHEMA, "sha256": freeze_hash},
                RECORDS_FILE: {"schema": RECORDS_SCHEMA, "sha256": records_hash},
                SUMMARY_FILE: {"schema": SUMMARY_SCHEMA, "sha256": summary_hash},
                EVIDENCE_FILE: {"schema": MEDIA_EVIDENCE_SCHEMA, "sha256": media_hash},
            },
            "filter": {
                "split": "holdout",
                "pilot_data_used": False,
                "failed_episodes_retained": True,
                "compact_record_count": len(records),
                "v2_1_failure_denominator": summary["failure_denominator"],
                "g6_tracking_comparator_denominator": summary[
                    "g6_tracking_comparator"
                ]["record_count"],
                "exemplar_selection": {
                    "success_case": SELECTION_RULES["success_case"],
                    "failure_case": SELECTION_RULES["failure_case"],
                    "route_comparisons": SELECTION_RULES["comparison"],
                },
                "best_case_selection_performed": False,
                "selected_source_record_ids": {
                    "success_case": (
                        None
                        if cases["success_case"] is None
                        else cases["success_case"]["source_record_id"]
                    ),
                    "failure_case": (
                        None
                        if cases["failure_case"] is None
                        else cases["failure_case"]["source_record_id"]
                    ),
                    "u_shape_before": cases["u_shape_comparison"]["before"]["source_record_id"],
                    "u_shape_after": cases["u_shape_comparison"]["after"]["source_record_id"],
                    "c_shape_before": cases["c_shape_comparison"]["before"]["source_record_id"],
                    "c_shape_after": cases["c_shape_comparison"]["after"]["source_record_id"],
                },
                "trajectory_frame_cap": 60,
                **animation,
            },
            "environment": {
                "python": platform.python_version(),
                "platform": platform.platform(),
                "numpy": np.__version__,
                "matplotlib": matplotlib.__version__,
                "pillow": PIL.__version__,
                "byteorder": sys.byteorder,
            },
            "outputs": outputs,
        }
        (staging_root / MANIFEST_FILE).write_text(
            json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        _publish_staged_directory(staging_root, output_root)
    finally:
        if staging_root.exists():
            shutil.rmtree(staging_root)
    return manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("reports/step1_g7"),
        help="Directory containing freeze, compact records, summary, and media evidence JSON.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/media/step1_g7"),
        help="Directory for seven README media assets and media_manifest.json.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    manifest = build_media(args.input, args.output)
    print(json.dumps({"manifest": str(args.output / MANIFEST_FILE), "outputs": len(manifest["outputs"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
