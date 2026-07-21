"""Structural validation for formal evaluation and experiment outputs."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from .schemas import (
    AGGREGATE_CELL_REQUIRED_KEYS,
    G6_GATE_REQUIRED_KEYS,
    G6_GATE_SCHEMA,
    PR6_GATE_REQUIRED_KEYS,
    PRIVACY_FORBIDDEN_RUNTIME_KEYS,
    RUNTIME_METADATA_REQUIRED_KEYS,
    RUNTIME_METADATA_SCHEMA,
    STATIC_MANIFEST_SCHEMA,
    STATIC_SUMMARY_REQUIRED_KEYS,
)


class SchemaValidationError(ValueError):
    """Raised when a result artifact violates the expected schema contract."""


def _require_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SchemaValidationError(f"{name} must be a JSON object")
    return value


def _require_keys(payload: dict[str, Any], keys: tuple[str, ...], name: str) -> None:
    missing = [key for key in keys if key not in payload]
    if missing:
        raise SchemaValidationError(f"{name} missing required keys: {missing}")


def _assert_no_nonfinite_leaves(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            _assert_no_nonfinite_leaves(item, f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _assert_no_nonfinite_leaves(item, f"{path}[{index}]")
        return
    if isinstance(value, float) and not math.isfinite(value):
        raise SchemaValidationError(f"{path} contains non-finite float {value!r}")


def _assert_no_privacy_keys(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            lowered = str(key).lower()
            if any(token in lowered for token in PRIVACY_FORBIDDEN_RUNTIME_KEYS):
                raise SchemaValidationError(f"{path}.{key} looks like a privacy-sensitive field")
            _assert_no_privacy_keys(item, f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _assert_no_privacy_keys(item, f"{path}[{index}]")


def validate_g6_gate_evidence(payload: dict[str, Any]) -> None:
    """Validate formal G6 gate_evidence.json structure."""
    data = _require_mapping(payload, "gate_evidence")
    _require_keys(data, G6_GATE_REQUIRED_KEYS, "gate_evidence")
    if data.get("schema") != G6_GATE_SCHEMA:
        raise SchemaValidationError(f"unexpected gate schema: {data.get('schema')!r}")
    if not isinstance(data["gates"], dict) or not isinstance(data["checks"], dict):
        raise SchemaValidationError("gates and checks must be objects")
    primary = int(data["primary_record_count"])
    expected = int(data["expected_primary_record_count"])
    success = int(data["success_count"])
    failure = int(data["failure_count"])
    if primary != expected:
        raise SchemaValidationError("primary_record_count must equal expected_primary_record_count")
    if success + failure != primary:
        raise SchemaValidationError("success_count + failure_count must equal primary_record_count")
    _assert_no_nonfinite_leaves(data)


def validate_pr6_gate_evidence(payload: dict[str, Any]) -> None:
    """Validate PR6 gate_evidence.json structure."""
    data = _require_mapping(payload, "pr6_gate_evidence")
    _require_keys(data, PR6_GATE_REQUIRED_KEYS, "pr6_gate_evidence")
    if int(data["record_count"]) < 1:
        raise SchemaValidationError("record_count must be positive")
    if not bool(data["all_records_accounted_for"]):
        raise SchemaValidationError("all_records_accounted_for must be true")
    _assert_no_nonfinite_leaves(data)


def validate_records(records: list[Any], *, unique_keys: tuple[str, ...]) -> None:
    """Validate a records.json array and uniqueness of composite keys."""
    if not isinstance(records, list):
        raise SchemaValidationError("records must be a JSON array")
    seen: set[tuple[Any, ...]] = set()
    for index, record in enumerate(records):
        mapping = _require_mapping(record, f"records[{index}]")
        key = tuple(mapping.get(field) for field in unique_keys)
        if key in seen:
            raise SchemaValidationError(f"duplicate record key {dict(zip(unique_keys, key, strict=True))}")
        seen.add(key)
        success = mapping.get("success")
        status = mapping.get("status")
        if success is True and isinstance(status, str) and status not in {"CONVERGED", "VALID", "PASS"}:
            # Soft consistency: success True should not be an explicit failure token.
            if status.upper().endswith("FAIL") or "INFEASIBLE" in status.upper() or status == "TIMEOUT":
                raise SchemaValidationError(f"records[{index}] success=True contradicts status={status!r}")
    _assert_no_nonfinite_leaves(records)


def validate_aggregate(payload: dict[str, Any]) -> None:
    """Validate nested scenario/method aggregate cells."""
    data = _require_mapping(payload, "aggregate")
    for scenario, methods in data.items():
        method_map = _require_mapping(methods, f"aggregate.{scenario}")
        for method, cell in method_map.items():
            cell_map = _require_mapping(cell, f"aggregate.{scenario}.{method}")
            _require_keys(cell_map, AGGREGATE_CELL_REQUIRED_KEYS, f"aggregate.{scenario}.{method}")
            run_count = int(cell_map["run_count"])
            if int(cell_map["success_count"]) + int(cell_map["failure_count"]) != run_count:
                raise SchemaValidationError(f"aggregate.{scenario}.{method} success+failure must equal run_count")
    _assert_no_nonfinite_leaves(data)


def validate_paired_comparisons(payload: dict[str, Any]) -> None:
    """Validate paired comparison tree is a nested object without non-finite leaves."""
    data = _require_mapping(payload, "paired_comparisons")
    if not data:
        raise SchemaValidationError("paired_comparisons must not be empty")
    _assert_no_nonfinite_leaves(data)


def validate_runtime_metadata(payload: dict[str, Any]) -> None:
    """Validate runtime_metadata.json and reject privacy-looking keys."""
    data = _require_mapping(payload, "runtime_metadata")
    _require_keys(data, RUNTIME_METADATA_REQUIRED_KEYS, "runtime_metadata")
    if data.get("schema") != RUNTIME_METADATA_SCHEMA:
        raise SchemaValidationError(f"unexpected runtime metadata schema: {data.get('schema')!r}")
    _assert_no_privacy_keys(data)
    _assert_no_nonfinite_leaves(data)


def validate_static_summary(payload: dict[str, Any]) -> None:
    """Validate static containment summary.json method entries."""
    data = _require_mapping(payload, "summary")
    if not data:
        raise SchemaValidationError("summary must contain at least one method")
    for method, record in data.items():
        mapping = _require_mapping(record, f"summary.{method}")
        _require_keys(mapping, STATIC_SUMMARY_REQUIRED_KEYS, f"summary.{method}")
    _assert_no_nonfinite_leaves(data)


def validate_static_manifest(payload: dict[str, Any]) -> None:
    """Validate static containment manifest.json top-level contract."""
    data = _require_mapping(payload, "manifest")
    for key in ("schema_version", "repository", "config", "methods", "run_status"):
        if key not in data:
            raise SchemaValidationError(f"manifest missing {key}")
    if data.get("schema_version") != STATIC_MANIFEST_SCHEMA:
        raise SchemaValidationError(f"unexpected manifest schema_version: {data.get('schema_version')!r}")
    _assert_no_nonfinite_leaves(data)


def validate_evaluation_directory(path: Path | str, *, kind: str) -> list[str]:
    """Validate a directory of evaluation artifacts. Returns list of checked files."""
    import json

    root = Path(path)
    checked: list[str] = []
    if kind == "g6":
        gate = json.loads((root / "gate_evidence.json").read_text(encoding="utf-8"))
        validate_g6_gate_evidence(gate)
        checked.append("gate_evidence.json")
        records = json.loads((root / "records.json").read_text(encoding="utf-8"))
        validate_records(records, unique_keys=("scenario", "seed", "method"))
        if len(records) != int(gate["primary_record_count"]):
            raise SchemaValidationError("records length must match primary_record_count")
        checked.append("records.json")
        aggregate = json.loads((root / "aggregate.json").read_text(encoding="utf-8"))
        validate_aggregate(aggregate)
        checked.append("aggregate.json")
        paired = json.loads((root / "paired_comparisons.json").read_text(encoding="utf-8"))
        validate_paired_comparisons(paired)
        checked.append("paired_comparisons.json")
    elif kind == "pr6":
        gate = json.loads((root / "gate_evidence.json").read_text(encoding="utf-8"))
        validate_pr6_gate_evidence(gate)
        checked.append("gate_evidence.json")
        records = json.loads((root / "records.json").read_text(encoding="utf-8"))
        validate_records(records, unique_keys=("shape", "seed", "variant"))
        if len(records) != int(gate["record_count"]):
            raise SchemaValidationError("records length must match record_count")
        checked.append("records.json")
        paired = json.loads((root / "paired_comparisons.json").read_text(encoding="utf-8"))
        validate_paired_comparisons(paired)
        checked.append("paired_comparisons.json")
    elif kind == "static":
        summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
        validate_static_summary(summary)
        checked.append("summary.json")
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        validate_static_manifest(manifest)
        checked.append("manifest.json")
    else:
        raise SchemaValidationError(f"unknown validation kind: {kind}")
    runtime_path = root / "runtime_metadata.json"
    if runtime_path.is_file():
        runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
        validate_runtime_metadata(runtime)
        checked.append("runtime_metadata.json")
    return checked
