"""Typed record shapes for static containment summaries and manifests.

ROLE: ORCHESTRATION TYPES — TypedDict contracts aligned with evaluation.schemas.
"""

from __future__ import annotations

from typing import Any, NotRequired, TypedDict

from ...evaluation.schemas import STATIC_MANIFEST_SCHEMA, STATIC_SUMMARY_REQUIRED_KEYS

# Re-export schema constants used by writers/validators.
STATIC_CONTAINMENT_MANIFEST_SCHEMA = STATIC_MANIFEST_SCHEMA
STATIC_CONTAINMENT_SUMMARY_KEYS = STATIC_SUMMARY_REQUIRED_KEYS


class MethodSummary(TypedDict, total=False):
    """Per-method metrics.json / summary.json row (required keys enforced at validate)."""

    coverage_ratio: float
    max_euclidean_boundary_distance: float
    evaluation_status: str
    boundary_v2_status: str
    periodic_plan_status: str
    resource_status: str
    assignment_status: str
    episode_status: str
    safety_filter_status: str
    method_status: str
    # Extended diagnostic fields commonly present:
    metrics_position_source: str
    initial_endpoint_coverage_ratio: float
    initial_endpoint_max_euclidean_boundary_distance: float
    boundary_v2_method: str
    boundary_confidence_status: str
    periodic_max_arc_gap: float | str
    active_guide_count: int
    reserve_guide_count: int
    resource_unmet_target_count: int
    assignment_switch_count: int
    episode_control_steps: int
    episode_final_tracking_rmse: float | str
    safety_projected_steps: int
    safety_infeasible_steps: int
    safety_max_residual_after: float | str


class ManifestConfigBlock(TypedDict):
    source: str
    sha256: str
    seed: int


class StaticManifest(TypedDict):
    """Top-level manifest.json contract (schema_version == STATIC_MANIFEST_SCHEMA)."""

    schema_version: str
    created_at_utc: str
    run_scope: str
    closed_loop: bool
    converged: bool
    run_status: str
    stop_reason: str
    repository: dict[str, Any]
    config: ManifestConfigBlock
    environment: dict[str, Any]
    methods: list[str]
    truth_boundary: dict[str, Any]
    boundary_v2: dict[str, Any]
    resource_decision: dict[str, Any]
    periodic_plan: dict[str, Any]
    assignments: dict[str, dict[str, Any]]
    episodes: dict[str, dict[str, Any]]
    velocity_safety: dict[str, Any]
    limitations: list[str]


class RunStatusDecision(TypedDict):
    run_status: str
    stop_reason: str
    closed_loop: bool
    converged: bool
    geometry_valid: bool
    geometry_status: str
    plan_valid: bool
    plan_status: str
    resource_status: str
    boundary_length: NotRequired[float | None]
