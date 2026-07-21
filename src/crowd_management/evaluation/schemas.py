"""Schema names and required-key contracts for formal evaluation outputs."""

from __future__ import annotations

from typing import Final

G6_GATE_SCHEMA: Final = "abcg-v2-step1-gates-v2"
RUNTIME_METADATA_SCHEMA: Final = "abcg-runtime-metadata-v1"
STATIC_MANIFEST_SCHEMA: Final = "step1-pr6-v1"

G6_GATE_REQUIRED_KEYS: Final = (
    "schema",
    "overall_status",
    "g6_status",
    "evaluated_commit",
    "frozen_commit",
    "gates",
    "checks",
    "primary_record_count",
    "expected_primary_record_count",
    "success_count",
    "failure_count",
    "status_counts",
)

PR6_GATE_REQUIRED_KEYS: Final = (
    "record_count",
    "paired_seed_count",
    "heldout_shape_count",
    "variant_count",
    "all_records_accounted_for",
    "g6_status",
)

AGGREGATE_CELL_REQUIRED_KEYS: Final = (
    "run_count",
    "success_count",
    "failure_count",
    "failure_rate",
    "status_counts",
    "metrics",
)

RUNTIME_METADATA_REQUIRED_KEYS: Final = (
    "schema",
    "hardware",
    "parallel_plan",
)

STATIC_SUMMARY_REQUIRED_KEYS: Final = (
    "coverage_ratio",
    "max_euclidean_boundary_distance",
    "evaluation_status",
    "boundary_v2_status",
    "periodic_plan_status",
    "resource_status",
    "assignment_status",
    "episode_status",
    "safety_filter_status",
    "method_status",
)

PRIVACY_FORBIDDEN_RUNTIME_KEYS: Final = (
    "username",
    "user",
    "home",
    "hostname",
    "host_name",
    "ip",
    "ip_address",
    "mac",
    "mac_address",
    "token",
    "password",
    "secret",
)
