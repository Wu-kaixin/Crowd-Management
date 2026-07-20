"""ABCG-v2.1 G7 proof-strengthened evaluation and freeze protocol.

The formal runner deliberately separates pilot, independent uncertainty
calibration, freeze, and holdout.  Analytic truth is created alongside each
synthetic observation but is never passed to boundary estimation, planning,
routing, assignment, waypoint control, or the sampled-data safety callback.
It is used only after the episode has terminated.
"""
from __future__ import annotations

import argparse
from concurrent.futures import Future, ProcessPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
import hashlib
import importlib.metadata
import json
import multiprocessing
import os
import platform
from pathlib import Path
import subprocess
import sys
from time import perf_counter
import tracemalloc
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
from shapely.geometry import LineString, MultiPoint, Point, Polygon
import yaml

from ..containment_metrics import coverage_ratio_to_points
from ..controllers.analytic_arc import optimize_equal_arc_phase, plan_analytic_equal_arc
from ..controllers.assignment import (
    AssignmentConfig,
    assign_cyclic_order_preserving,
    assign_guides_to_targets,
)
from ..controllers.resources_v2 import RobustResourceConfig, allocate_robust_resources
from ..controllers.routing import PairwiseRouteMatrix, build_pairwise_route_matrix
from ..controllers.periodic_arc_cvt import PeriodicArcCVTConfig, plan_periodic_arc_coverage
from ..controllers.safety import VelocitySafetyConfig
from ..controllers.safety_v2 import VelocityProjectionConfig, project_velocity_safety_v2
from ..controllers.waypoint import FixedWaypointPaths, WaypointEpisodeRunner, WaypointRunnerConfig
from ..estimation.boundary_v2 import BoundaryEstimateFailure, BoundaryEstimateV2, estimate_boundary_v2
from ..estimation.boundary_v3 import (
    BoundaryStabilityConfig,
    BoundaryStabilityFailure,
    align_boundary_replica,
    estimate_boundary_stability,
)
from ..geometry.arclength import max_consecutive_arc_gap, resample_closed_curve_by_arclength
from ..geometry.buffer import BufferedPolygonGeometry, PolygonBufferConfig, build_polygon_buffer
from ..geometry.free_space import FreeSpaceConfig, GuideFreeSpace, build_guide_free_space

from .schemas import (
    DeploymentMetrics,
    G7Record,
    LayeredOutcome,
    ResourceRegime,
    compose_layered_outcome,
)
from .statistics_v2 import (
    NoninferioritySpec,
    evaluate_noninferiority,
    holm_adjustment,
    paired_binary_summary,
    paired_continuous_summary,
    runtime_percentiles,
)
from .step1_g6 import (
    PRIMARY_SCENARIOS as G6_PRIMARY_SCENARIOS,
    G6EvaluationConfig,
    _boundary_config,
    _initial_guides,
    _observed_case,
    _run_feedback_episode as _run_g6_feedback_episode,
)

G6_BASE_SHA = "1c3642c1adef0f11e0bde7651e2da64afbc45a8b"
IMPLEMENTATION_FREEZE_SHA = "f2494922b2431bfd9a37a247add8a79acfdc18ed"

G7_SCHEMA = "abcg-v2.1-g7-evaluation-v1"
FREEZE_SCHEMA = "abcg-v2.1-g7-freeze-manifest-v1"
SUCCESS_DEFINITION: dict[str, object] = {
    "PLAN_OPTIMAL": "analytic phi=1 equal-arc plan verified against H*=L^3/(12m^2) and G=L/m",
    "ROUTE_FEASIBLE": "complete assigned routes exist and every checked route carries a valid canonical-clearance certificate",
    "TRACK_CONVERGED": "fixed-waypoint controller terminal state is CONVERGED",
    "SAMPLED_SAFE": "every safety projection is feasible, within residual tolerances, and passes its ZOH dense check",
    "ESTIMATED_DEPLOYMENT_SUCCESS": "PLAN_OPTIMAL and ROUTE_FEASIBLE and TRACK_CONVERGED and SAMPLED_SAFE",
    "TRUTH_VALIDATED_SUCCESS": "estimated success plus evaluator-only truth coverage and truth arc-gap criteria",
    "controller_converged_scope": "tracking_only",
}
G6_ADAPTER_ACTIVE_COUNT = 8
G6_ADAPTER_BOOTSTRAP_SAMPLES = 30
G6_ADAPTER_MAX_STEPS = 160
G6_ADAPTER_ASSIGNMENT_SWITCH_PENALTY = 0.25
G6_ADAPTER_PERIODIC_MAX_ITERATIONS = 200
STATISTICS_PLAN: dict[str, object] = {
    "paired_unit": ["scenario", "seed", "case_cohort", "resource_regime"],
    "binary_denominator": "all paired holdout episodes including every failure",
    "continuous_missingness": "retain record and report missing count and reason; never impute",
    "paired_bootstrap_resamples": 2000,
    "confidence": 0.95,
    "primary_superiority": [
        "ESTIMATED_DEPLOYMENT_SUCCESS",
        "TRUTH_VALIDATED_SUCCESS",
        "one_sided_u_c_blocked_route_timeout_reduction",
    ],
    "multiplicity": "Holm step-down over primary superiority p-values",
    "primary_candidate_geometry": (
        "visibility_hungarian with raw signed-normal bootstrap tube expansion; "
        "explicit UNCALIBRATED_STABILITY_HEURISTIC, not a calibrated confidence tube"
    ),
    "uncertainty_ablation": [
        "none",
        "uncalibrated_stability_heuristic_primary",
        "independently_calibrated_tube_or_RESOURCE_UNCERTAIN_when_calibration_fails",
    ],
    "blocked_timeout_comparator": {
        "method": "g6_fixed_resource_rerun",
        "label": "Frozen G6 fixed-resource straight-feedback adapter rerun on matched G7 holdout",
        "bootstrap_samples": G6_ADAPTER_BOOTSTRAP_SAMPLES,
        "fixed_active_guides": G6_ADAPTER_ACTIVE_COUNT,
        "max_steps": G6_ADAPTER_MAX_STEPS,
        "assignment_switch_penalty": G6_ADAPTER_ASSIGNMENT_SWITCH_PENALTY,
        "periodic_max_iterations": G6_ADAPTER_PERIODIC_MAX_ITERATIONS,
        "scope": "blocked_route_controller_TIMEOUT_only_not_v2_1_deployment_success",
    },
    "noninferiority_margin_magnitude": 0.10,
    "candidate_minus_baseline_decision_threshold": -0.10,
    "noninferiority": [
        "circle_ellipse_estimated_success_candidate_minus_baseline",
        "qp_minus_dykstra_case_level_all_captured_snapshots_sampled_safe",
    ],
    "backend_replay_pairing_unit": "episode_case_all_captured_snapshots_must_pass",
    "backend_replay_minimum_complete_cases": 2,
}

PRIMARY_METHODS = ("straight_hungarian", "visibility_hungarian")
BLOCKED_COMPARATOR_METHODS = ("g6_fixed_resource_rerun",)
OFAT_METHODS = (
    "boundary_corridor_hungarian",
    "visibility_cyclic",
    "visibility_phase0",
    "visibility_uncertainty_none",
    "visibility_uncertainty_calibrated",
    "visibility_qp",
)
ADAPTIVE_METHODS = ("adaptive_nominal_visibility", "adaptive_robust_visibility")
MIN_BACKEND_REPLAY_CASES = 2


@dataclass(frozen=True)
class G7EvaluationConfig:
    """Resolved G7 protocol and simulator values.

    Historical G6 seeds ``0..29`` are reference-only and are intentionally not
    accepted as any G7 execution split.
    """

    pilot_seeds: tuple[int, ...] = (1000, 1001)
    calibration_fit_seeds: tuple[int, ...] = (2000, 2001)
    calibration_validation_seeds: tuple[int, ...] = (2002, 2003)
    holdout_general_seeds: tuple[int, ...] = (10000, 10001, 10002, 10003, 10004, 10005)
    holdout_blocked_seeds: tuple[int, ...] = (11000, 11001, 11002)
    scenarios: tuple[str, ...] = ("circle", "ellipse", "u_shape", "c_shape")
    blocked_scenarios: tuple[str, ...] = ("u_shape", "c_shape")
    observation_count: int = 120
    boundary_bootstrap_samples: int = 12
    calibration_bootstrap_replicas: int = 4
    phase_grid_size: int = 12
    bootstrap_resamples: int = 2000
    parallel_workers: int = 24
    available_guides: int = 16
    fixed_active_guides: int = 8
    required_arc_gap: float = 2.2
    safety_distance: float = 0.8
    coverage_radius: float = 1.25
    truth_coverage_minimum: float = 0.95
    room_size: tuple[float, float] = (10.0, 10.0)
    room_margin: float = 0.2
    sample_spacing: float = 0.08
    alpha_scale: float = 2.5
    dt: float = 0.1
    k_p: float = 1.2
    v_max: float = 0.8
    waypoint_tolerance: float = 0.06
    tracking_rmse_tolerance: float = 0.06
    speed_tolerance: float = 0.05
    hold_steps: int = 4
    max_steps: int = 240
    no_progress_window: int = 40
    min_progress: float = 1.0e-3
    min_guide_distance: float = 0.45
    zoh_samples: int = 21
    safety_primal_tolerance: float = 1.0e-8
    safety_kkt_tolerance: float = 2.0e-5
    safety_active_tolerance: float = 2.0e-4
    safety_iterate_tolerance: float = 1.0e-5
    safety_max_iterations: int = 1500
    safety_replay_stride: int = 20
    geometry_clearance_tolerance: float = 1.0e-7
    noninferiority_margin_magnitude: float = 0.10

    @property
    def calibration_seeds(self) -> tuple[int, ...]:
        """Ordered independent calibration seeds (fit first, validation second)."""

        return self.calibration_fit_seeds + self.calibration_validation_seeds

    def __post_init__(self) -> None:
        split_sets = (
            set(self.pilot_seeds),
            set(self.calibration_fit_seeds),
            set(self.calibration_validation_seeds),
            set(self.holdout_general_seeds),
            set(self.holdout_blocked_seeds),
        )
        if any(not values for values in split_sets):
            raise ValueError("every G7 split must contain at least one seed")
        if any(left & right for index, left in enumerate(split_sets) for right in split_sets[index + 1 :]):
            raise ValueError("pilot, calibration-fit, calibration-validation, and holdout seeds must be disjoint")
        historical = set(range(30))
        if any(values & historical for values in split_sets):
            raise ValueError("historical G6 seeds 0..29 are reference-only")
        valid_scenarios = {"circle", "ellipse", "u_shape", "c_shape"}
        if not set(self.scenarios).issubset(valid_scenarios):
            raise ValueError("unsupported scenario")
        if not set(self.blocked_scenarios).issubset({"u_shape", "c_shape"}):
            raise ValueError("blocked_scenarios must contain only U/C shapes")
        for name in (
            "observation_count",
            "boundary_bootstrap_samples",
            "calibration_bootstrap_replicas",
            "phase_grid_size",
            "bootstrap_resamples",
            "parallel_workers",
            "available_guides",
            "fixed_active_guides",
            "hold_steps",
            "max_steps",
            "no_progress_window",
            "zoh_samples",
            "safety_max_iterations",
            "safety_replay_stride",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or int(value) != value or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.fixed_active_guides > self.available_guides:
            raise ValueError("fixed_active_guides cannot exceed available_guides")
        for name in (
            "required_arc_gap",
            "safety_distance",
            "coverage_radius",
            "sample_spacing",
            "alpha_scale",
            "dt",
            "k_p",
            "v_max",
            "waypoint_tolerance",
            "tracking_rmse_tolerance",
            "speed_tolerance",
            "min_progress",
            "min_guide_distance",
            "safety_primal_tolerance",
            "safety_kkt_tolerance",
            "safety_active_tolerance",
            "safety_iterate_tolerance",
            "geometry_clearance_tolerance",
        ):
            if not np.isfinite(float(getattr(self, name))) or float(getattr(self, name)) <= 0.0:
                raise ValueError(f"{name} must be finite and positive")
        if not 0.0 <= self.truth_coverage_minimum <= 1.0:
            raise ValueError("truth_coverage_minimum must lie in [0,1]")
        if self.noninferiority_margin_magnitude != 0.10:
            raise ValueError("G7 noninferiority margin magnitude is preregistered at 0.10")
        if self.dt * self.k_p > 1.0:
            raise ValueError("dt*k_p must not exceed one")

    def quickened(self) -> "G7EvaluationConfig":
        """Return the deterministic smoke configuration used by ``--quick``."""
        return replace(
            self,
            pilot_seeds=self.pilot_seeds[:1],
            calibration_fit_seeds=self.calibration_fit_seeds[:1],
            calibration_validation_seeds=self.calibration_validation_seeds[:1],
            holdout_general_seeds=self.holdout_general_seeds[:1],
            holdout_blocked_seeds=self.holdout_blocked_seeds[:1],
            scenarios=("u_shape",),
            blocked_scenarios=("u_shape",),
            observation_count=min(self.observation_count, 96),
            boundary_bootstrap_samples=min(self.boundary_bootstrap_samples, 2),
            calibration_bootstrap_replicas=min(self.calibration_bootstrap_replicas, 2),
            phase_grid_size=min(self.phase_grid_size, 3),
            bootstrap_resamples=min(self.bootstrap_resamples, 100),
            fixed_active_guides=min(self.fixed_active_guides, 4),
            max_steps=min(self.max_steps, 45),
            no_progress_window=min(self.no_progress_window, 12),
            zoh_samples=min(self.zoh_samples, 7),
        )

# SHA-256 values captured from the clean, pulled main baseline before the G7
# branch was created.  Only tracked compact evidence is protected here; large
# ignored records and trajectories remain external artifacts by design.
G6_COMPACT_EVIDENCE_SHA256: dict[str, str] = {
    "G6_COMPLIANCE_REPORT.md": "7ddfb981dff8db72b3c8aa73b68525927f34d73e7d2c58320f55f95f725b1a33",
    "ablation_aggregate.json": "5d7231d1f7d827a5619f21b409c6927b5e2cad1608379d8b814be44f8c14ec48",
    "aggregate.json": "9274797e27ee3aac7314b50196c502946bdba683678f9066b53d9929d5bbe446",
    "evaluation_config.json": "7434c75c2cce10bfccb1e54fd8e135733a397ad4b3620d5668f026e05833c908",
    "evaluation_snapshot.json": "e0856a8fb02c96dcc9f855b081f727f48b84c3a54b8a965554c92dc31dc2fa10",
    "failure_gallery.json": "bff99be12a6d410ef95ddaa7a51775c02e8f84b35431bb95f98b32879e5be18e",
    "gate_evidence.json": "9e17c474834c056260503db079a7f297ed0153947c8d1d7fbfa56fce79bd9740",
    "paired_comparisons.json": "19d6a4dfb3ae8f59abe885ae6c554c6ab238b475623abbb51ab45aff1c54fbf2",
    "performance.json": "7f8af84a05a86b98d8357a7666b9fc809fa6006aed03579619d181f171057a22",
    "preflight_evidence.json": "f874d688dcdebe3c5e60e6f4c2f7909b82527a9755614a77f50001fc99394ed5",
    "robustness_aggregate.json": "74bc7c219bac5c9dc0d41cb7aeb65542735491f655bcff5d676dab89861b51d4",
    "stress_cases.json": "b76c4b5922b43a8ed533f4cd7d02a0a940b5a2fa7f62cf8f9a549a396eeb4585",
}

G6_VISUAL_OVERVIEW_SHA256: dict[str, str] = {
    "abcg_metrics_summary.png": "50c0df80dcdcc3e0d075ede71a35bcc035b20123d1721bb3b4713babf304e364",
    "abcg_static_containment.gif": "6f467eecd73c9e78fe1ac4f8fca37c3e2651e4cbde1f3a4811a50cec820f3274",
    "abcg_static_containment_grid.png": "c24a5b6f29b7bb0b8beb8c7d1a107772ad1dad838d14bde25f376ba0e6b145ff",
}


def audit_frozen_g6_evidence(repo: str | Path) -> dict[str, Any]:
    """Verify that every tracked compact G6 artifact still matches main."""
    root = Path(repo).resolve()
    evidence_root = root / "reports" / "step1_g6_compliance"
    files: dict[str, dict[str, Any]] = {}
    for name, expected in G6_COMPACT_EVIDENCE_SHA256.items():
        path = evidence_root / name
        actual = _sha256(path) if path.is_file() else None
        files[name] = {
            "exists": path.is_file(),
            "expected_sha256": expected,
            "actual_sha256": actual,
            "matches": actual == expected,
        }
    media: dict[str, dict[str, Any]] = {}
    for name, expected in G6_VISUAL_OVERVIEW_SHA256.items():
        path = root / "reports" / "media" / name
        actual = _sha256(path) if path.is_file() else None
        media[name] = {
            "exists": path.is_file(),
            "expected_sha256": expected,
            "actual_sha256": actual,
            "matches": actual == expected,
        }
    return {
        "schema": "abcg-v2.1-g6-readonly-audit-v1",
        "base_sha": G6_BASE_SHA,
        "implementation_freeze_sha": IMPLEMENTATION_FREEZE_SHA,
        "evidence_directory": "reports/step1_g6_compliance",
        "file_count": len(files),
        "all_match": all(item["matches"] for item in files.values()),
        "files": files,
        "legacy_visual_overview_file_count": len(media),
        "legacy_visual_overview_all_match": all(item["matches"] for item in media.values()),
        "legacy_visual_overview": media,
    }


def split_resource_regimes(records: Iterable[G7Record]) -> dict[str, list[G7Record]]:
    """Partition records before aggregation so regimes cannot be pooled."""
    result = {str(regime): [] for regime in ResourceRegime}
    for record in records:
        result[str(record.resource_regime)].append(record)
    return result


def matched_same_resource_pairs(
    records: Sequence[G7Record],
    *,
    baseline_method: str,
    candidate_method: str,
) -> list[tuple[G7Record, G7Record]]:
    """Pair only scenario/seed records with exactly equal active guide counts."""
    eligible = [record for record in records if record.resource_regime == ResourceRegime.SAME_RESOURCE]
    def pair_key(record: G7Record) -> tuple[object, ...]:
        return (
            record.scenario,
            record.seed,
            record.config_hash,
            record.metadata.get("case_id"),
            record.metadata.get("resource_cohort"),
        )

    def unique(method: str) -> dict[tuple[object, ...], G7Record]:
        result: dict[tuple[object, ...], G7Record] = {}
        for record in eligible:
            if record.method != method:
                continue
            key = pair_key(record)
            if key in result:
                raise ValueError(f"duplicate same_resource record for {method!r}: {key!r}")
            result[key] = record
        return result

    baseline = unique(baseline_method)
    candidate = unique(candidate_method)
    if baseline.keys() != candidate.keys():
        missing_baseline = sorted(candidate.keys() - baseline.keys(), key=repr)
        missing_candidate = sorted(baseline.keys() - candidate.keys(), key=repr)
        raise ValueError(
            "same_resource pairing is incomplete: "
            f"missing_baseline={missing_baseline!r}, missing_candidate={missing_candidate!r}"
        )
    pairs: list[tuple[G7Record, G7Record]] = []
    for key in sorted(baseline, key=repr):
        left = baseline[key]
        right = candidate[key]
        if left.metrics.active_guide_count != right.metrics.active_guide_count:
            raise ValueError(f"same_resource pair {key!r} has unequal active guide counts.")
        pairs.append((left, right))
    return pairs


def paired_bootstrap_interval(
    differences: Sequence[float],
    *,
    seed: int,
    resamples: int = 2000,
    confidence: float = 0.95,
) -> dict[str, float | int | None]:
    """Paired percentile bootstrap CI; no failed record is filtered upstream."""
    values = np.asarray(differences, dtype=float)
    if values.ndim != 1 or not np.all(np.isfinite(values)):
        raise ValueError("differences must be a finite one-dimensional sequence.")
    if isinstance(resamples, bool) or resamples < 1:
        raise ValueError("resamples must be positive.")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must lie strictly between zero and one.")
    if len(values) == 0:
        return {"count": 0, "mean": None, "median": None, "ci95_low": None, "ci95_high": None}
    rng = np.random.default_rng(int(seed))
    sample_ids = rng.integers(0, len(values), size=(int(resamples), len(values)))
    boot = np.mean(values[sample_ids], axis=1)
    tail = (1.0 - confidence) / 2.0
    return {
        "count": int(len(values)),
        "mean": float(np.mean(values)),
        "median": float(np.median(values)),
        "ci95_low": float(np.quantile(boot, tail)),
        "ci95_high": float(np.quantile(boot, 1.0 - tail)),
    }


def failure_rate_composition(outcomes: Iterable[LayeredOutcome]) -> dict[str, Any]:
    """Count every episode exactly once, including all successful outcomes."""
    counts: dict[str, int] = {}
    total = 0
    successes = 0
    for outcome in outcomes:
        total += 1
        if outcome.estimated_deployment_success:
            successes += 1
            key = str(  # keep successes visible in the denominator accounting
                "TRUTH_VALIDATED_SUCCESS"
                if outcome.truth_validated_success
                else "ESTIMATED_DEPLOYMENT_SUCCESS_ONLY"
            )
        else:
            key = outcome.failure_reason or outcome.controller_terminal_state or "UNSPECIFIED_FAILURE"
        counts[key] = counts.get(key, 0) + 1
    return {
        "total": total,
        "estimated_successes": successes,
        "estimated_success_rate": (successes / total) if total else None,
        "counts": dict(sorted(counts.items())),
        "all_records_accounted_for": sum(counts.values()) == total,
    }


def load_g7_config(path: str | Path, *, quick: bool = False) -> G7EvaluationConfig:
    """Load the checked-in protocol YAML and resolve an optional smoke subset."""
    source = Path(path)
    raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError("G7 config must contain a YAML mapping")
    splits = raw.get("splits", {})
    evaluation = raw.get("evaluation", {})
    motion = raw.get("motion", {})
    safety = raw.get("safety", {})
    execution = raw.get("execution", {})
    if not all(
        isinstance(item, Mapping)
        for item in (splits, evaluation, motion, safety, execution)
    ):
        raise ValueError("splits/evaluation/motion/safety/execution must be mappings")
    allowed_split_keys = {
        "pilot_seeds",
        "calibration_fit_seeds",
        "calibration_validation_seeds",
        "holdout_general_seeds",
        "holdout_blocked_seeds",
        "scenarios",
        "blocked_scenarios",
    }
    unknown_split_keys = sorted(set(splits) - allowed_split_keys)
    if unknown_split_keys:
        raise ValueError(f"unknown G7 split keys: {unknown_split_keys!r}")
    values: dict[str, object] = {
        "pilot_seeds": tuple(int(value) for value in splits.get("pilot_seeds", (1000, 1001))),
        "calibration_fit_seeds": tuple(
            int(value) for value in splits.get("calibration_fit_seeds", (2000, 2001))
        ),
        "calibration_validation_seeds": tuple(
            int(value) for value in splits.get("calibration_validation_seeds", (2002, 2003))
        ),
        "holdout_general_seeds": tuple(int(value) for value in splits.get("holdout_general_seeds", range(10000, 10006))),
        "holdout_blocked_seeds": tuple(int(value) for value in splits.get("holdout_blocked_seeds", range(11000, 11003))),
        "scenarios": tuple(str(value) for value in splits.get("scenarios", ("circle", "ellipse", "u_shape", "c_shape"))),
        "blocked_scenarios": tuple(str(value) for value in splits.get("blocked_scenarios", ("u_shape", "c_shape"))),
    }
    field_groups = {
        "evaluation": evaluation,
        "motion": motion,
        "safety": safety,
        "execution": execution,
    }
    known = set(G7EvaluationConfig.__dataclass_fields__)
    for group in field_groups.values():
        for key, value in group.items():
            if key not in known:
                raise ValueError(f"unknown G7 config key: {key}")
            if key == "room_size":
                value = tuple(float(item) for item in value)
            values[key] = value
    config = G7EvaluationConfig(**values)
    return config.quickened() if quick else config


def resolved_config_hash(config: G7EvaluationConfig) -> str:
    return _canonical_hash({"schema": G7_SCHEMA, "config": asdict(config)})


def _canonical_hash(value: object) -> str:
    payload = json.dumps(
        _strict_jsonable(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _strict_jsonable(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return _strict_jsonable(value.tolist())
    if isinstance(value, np.generic):
        return _strict_jsonable(value.item())
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _strict_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_strict_jsonable(item) for item in value]
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def write_strict_json(path: str | Path, value: object) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            _strict_jsonable(value),
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout.strip()


def _git_bytes(repo: Path, *args: str) -> bytes:
    """Return exact Git object bytes without platform text conversion."""
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    return completed.stdout


def _git_snapshot(repo: Path) -> dict[str, object]:
    head = _git(repo, "rev-parse", "HEAD")
    branch = _git(repo, "branch", "--show-current")
    dirty_entries = tuple(
        line for line in _git(repo, "status", "--porcelain", "--untracked-files=all").splitlines() if line
    )
    return {
        "head": head,
        "branch": branch,
        "clean": not dirty_entries,
        "dirty_entry_count": len(dirty_entries),
        "dirty_entries": list(dirty_entries),
    }


def _source_hash(repo: Path) -> tuple[str, list[str]]:
    tracked = _git(repo, "ls-files").splitlines()
    selected = sorted(
        value.replace("\\", "/")
        for value in tracked
        if (value.replace("\\", "/").startswith("src/crowd_management/") and value.endswith(".py"))
        or value.replace("\\", "/") in {
            "scripts/run_step1_g7.py",
            "scripts/build_step1_g7_media.py",
        }
    )
    if not selected:
        raise RuntimeError("no tracked G7 source files found")
    digest = hashlib.sha256()
    for relative in selected:
        # Freeze the bytes addressed by HEAD, not checkout-filtered worktree
        # bytes.  The latter vary with core.autocrlf and would make the same
        # commit hash differently across clean Windows/Linux checkouts.
        data = _git_bytes(repo, "cat-file", "blob", f"HEAD:{relative}")
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(data).digest())
    return digest.hexdigest(), selected


def _read_protocol_evidence(path: str | Path, split: str) -> dict[str, object]:
    source = Path(path)
    value = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("split") != split:
        raise ValueError(f"{source} is not {split} evidence")
    if value.get("formal") is not False:
        raise ValueError(f"{split} evidence must be explicitly non-formal")
    return value


def _equal_optional_number(left: object, right: object) -> bool:
    if left is None or right is None:
        return left is None and right is None
    try:
        return bool(np.isclose(float(left), float(right), rtol=0.0, atol=1.0e-12))
    except (TypeError, ValueError):
        return False


def _validate_pilot_evidence_contract(
    evidence: Mapping[str, object],
    config: G7EvaluationConfig,
    *,
    quick: bool,
) -> dict[str, object]:
    expected_hash = resolved_config_hash(config)
    expected_cases = evaluation_cases(config, "pilot")
    expected_methods = evaluation_methods("pilot", quick=quick)
    expected_keys = sorted(
        (str(case["scenario"]), int(case["seed"]), method)
        for case in expected_cases
        for method in expected_methods
    )
    required_exact = {
        "schema": "abcg-v2.1-g7-pilot-evidence-v1",
        "split": "pilot",
        "formal": False,
        "quick": bool(quick),
        "diagnostic_only": True,
        "pilot_data_used": False,
        "pilot_data_used_for_formal_conclusion": False,
        "historical_g6_seeds_used": False,
        "config_hash": expected_hash,
        "seeds": list(config.pilot_seeds),
        "scenarios": list(config.blocked_scenarios),
        "methods": list(expected_methods),
        "record_count": len(expected_keys),
        "expected_record_count": len(expected_keys),
    }
    mismatches = [key for key, value in required_exact.items() if evidence.get(key) != value]
    if mismatches:
        raise ValueError(f"pilot evidence contract mismatch: {mismatches!r}")
    records = evidence.get("records")
    if not isinstance(records, list) or len(records) != len(expected_keys):
        raise ValueError("pilot evidence records are missing or incomplete")
    observed_keys: list[tuple[str, int, str]] = []
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            raise ValueError(f"pilot record {index} must be an object")
        try:
            key = (str(record["scenario"]), int(record["seed"]), str(record["method"]))
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"pilot record {index} has an invalid identity") from error
        if record.get("config_hash") != expected_hash:
            raise ValueError(f"pilot record {index} config hash mismatch")
        if record.get("split") != "pilot" or record.get("pilot_data_used") is not False:
            raise ValueError(f"pilot record {index} lacks explicit non-formal split flags")
        observed_keys.append(key)
    if sorted(observed_keys) != expected_keys or len(set(observed_keys)) != len(observed_keys):
        raise ValueError("pilot case/method matrix is not unique and complete")
    records_sha = _canonical_hash(records)
    deterministic_sha = _canonical_hash(
        [_deterministic_record_projection(record) for record in records]
    )
    if evidence.get("records_sha256") != records_sha:
        raise ValueError("pilot records_sha256 is not reproducible")
    if evidence.get("deterministic_records_sha256") != deterministic_sha:
        raise ValueError("pilot deterministic_records_sha256 is not reproducible")
    return {
        **required_exact,
        "record_identity_sha256": _canonical_hash(expected_keys),
        "records_sha256": records_sha,
        "deterministic_records_sha256": deterministic_sha,
    }


def _validate_calibration_evidence_contract(
    evidence: Mapping[str, object],
    config: G7EvaluationConfig,
    *,
    quick: bool,
) -> dict[str, object]:
    expected_hash = resolved_config_hash(config)
    required_exact = {
        "schema": "abcg-v2.1-g7-independent-calibration-v1",
        "split": "calibration",
        "formal": False,
        "quick": bool(quick),
        "pilot_data_used": False,
        "historical_g6_seeds_used": False,
        "factor_fit_uses_validation_data": False,
        "seed_splits_disjoint": True,
        "config_hash": expected_hash,
        "seeds": list(config.calibration_seeds),
        "factor_fit_seeds": list(config.calibration_fit_seeds),
        "independent_validation_seeds": list(config.calibration_validation_seeds),
        "scenarios": list(config.scenarios),
        "target_coverage": 0.95,
    }
    mismatches = [key for key, value in required_exact.items() if evidence.get(key) != value]
    if mismatches:
        raise ValueError(f"calibration evidence contract mismatch: {mismatches!r}")
    cases = evidence.get("cases")
    if not isinstance(cases, list):
        raise ValueError("calibration evidence cases must be a list")
    for index, case in enumerate(cases):
        if not isinstance(case, Mapping) or case.get("truth_access") != "calibration_scoring_only":
            raise ValueError(f"calibration case {index} violates the truth firewall")
    recalculated = _recalculate_calibration_contract(cases, config)
    exact_fields = (
        "status",
        "calibration_factor",
        "fitted_calibration_factor",
        "coverage_gate_passed",
        "case_count",
        "fit_valid_case_count",
        "validation_valid_case_count",
        "validation_point_count",
        "validation_covered_count",
    )
    reported = {
        "status": evidence.get("status"),
        "calibration_factor": evidence.get("calibration_factor"),
        "fitted_calibration_factor": evidence.get("fitted_calibration_factor"),
        "coverage_gate_passed": evidence.get("coverage_gate_passed"),
        "case_count": evidence.get("case_count"),
        "fit_valid_case_count": evidence.get("fit_valid_case_count"),
        "validation_valid_case_count": evidence.get("validation_valid_case_count"),
        "validation_point_count": evidence.get("validation_point_count"),
        "validation_covered_count": evidence.get("validation_covered_count"),
    }
    disagreements = [key for key in exact_fields if reported[key] != recalculated[key]]
    for key, evidence_key in (
        ("validation_pointwise_coverage", "validation_pointwise_coverage"),
        ("validation_simultaneous_coverage", "validation_simultaneous_coverage"),
        ("validation_pointwise_coverage", "pointwise_coverage"),
        ("validation_simultaneous_coverage", "simultaneous_coverage"),
    ):
        if not _equal_optional_number(recalculated[key], evidence.get(evidence_key)):
            disagreements.append(evidence_key)
    embedded_recalculation = evidence.get("recalculated_contract")
    if _canonical_hash(embedded_recalculation) != _canonical_hash(recalculated):
        disagreements.append("recalculated_contract")
    fitted_factor = recalculated["fitted_calibration_factor"]
    if fitted_factor is not None:
        for index, case in enumerate(cases):
            if not isinstance(case, Mapping) or case.get("status") != "VALID_CALIBRATION_CASE":
                continue
            values = np.asarray(case["point_ratio_values"], dtype=float)
            expected_count = int(np.count_nonzero(values <= float(fitted_factor) + 1.0e-15))
            expected_simultaneous = bool(np.all(values <= float(fitted_factor) + 1.0e-15))
            if not _equal_optional_number(case.get("coverage_factor"), fitted_factor):
                disagreements.append(f"cases[{index}].coverage_factor")
            if case.get("pointwise_covered_count") != expected_count:
                disagreements.append(f"cases[{index}].pointwise_covered_count")
            if case.get("simultaneous_covered") is not expected_simultaneous:
                disagreements.append(f"cases[{index}].simultaneous_covered")
    if disagreements:
        raise ValueError(f"calibration evidence is not independently reproducible: {sorted(set(disagreements))!r}")
    return {
        **required_exact,
        **recalculated,
        "cases_sha256": _canonical_hash(cases),
    }


def _validate_embedded_protocol_summaries(
    manifest: Mapping[str, object],
    config: G7EvaluationConfig,
    *,
    quick: bool,
) -> None:
    pilot = manifest.get("pilot_evidence_summary")
    calibration = manifest.get("calibration_evidence_summary")
    if not isinstance(pilot, Mapping) or not isinstance(calibration, Mapping):
        raise RuntimeError("freeze manifest lacks normalized protocol evidence summaries")
    expected_pilot_count = len(evaluation_cases(config, "pilot")) * len(
        evaluation_methods("pilot", quick=quick)
    )
    pilot_checks = {
        "schema": "abcg-v2.1-g7-pilot-evidence-v1",
        "split": "pilot",
        "formal": False,
        "quick": bool(quick),
        "pilot_data_used": False,
        "config_hash": resolved_config_hash(config),
        "seeds": list(config.pilot_seeds),
        "scenarios": list(config.blocked_scenarios),
        "methods": list(evaluation_methods("pilot", quick=quick)),
        "record_count": expected_pilot_count,
        "expected_record_count": expected_pilot_count,
    }
    calibration_checks = {
        "schema": "abcg-v2.1-g7-independent-calibration-v1",
        "split": "calibration",
        "formal": False,
        "quick": bool(quick),
        "pilot_data_used": False,
        "factor_fit_uses_validation_data": False,
        "config_hash": resolved_config_hash(config),
        "seeds": list(config.calibration_seeds),
        "factor_fit_seeds": list(config.calibration_fit_seeds),
        "independent_validation_seeds": list(config.calibration_validation_seeds),
        "scenarios": list(config.scenarios),
        "expected_case_count": len(config.scenarios) * len(config.calibration_seeds),
    }
    pilot_mismatch = [key for key, value in pilot_checks.items() if pilot.get(key) != value]
    calibration_mismatch = [key for key, value in calibration_checks.items() if calibration.get(key) != value]
    digest_fields = (
        (pilot, "records_sha256"),
        (pilot, "deterministic_records_sha256"),
        (pilot, "record_identity_sha256"),
        (calibration, "cases_sha256"),
        (calibration, "case_keys_sha256"),
    )
    invalid_digests = [
        key for summary, key in digest_fields
        if not isinstance(summary.get(key), str) or len(str(summary.get(key))) != 64
    ]
    if pilot_mismatch or calibration_mismatch or invalid_digests:
        raise RuntimeError(
            "embedded protocol evidence summary verification failed: "
            f"pilot={pilot_mismatch!r}, calibration={calibration_mismatch!r}, digests={invalid_digests!r}"
        )
    status = calibration.get("status")
    factor = calibration.get("calibration_factor")
    if status != manifest.get("calibration_status") or factor != manifest.get("calibration_factor"):
        raise RuntimeError("embedded calibration summary disagrees with manifest status/factor")
    if status == "CALIBRATED_TUBE":
        if calibration.get("coverage_gate_passed") is not True or factor is None:
            raise RuntimeError("embedded CALIBRATED_TUBE summary lacks independent validation PASS")
    elif factor is not None:
        raise RuntimeError("embedded uncalibrated summary carries a deployment factor")


def create_freeze_manifest(
    repo: str | Path,
    config_path: str | Path,
    output_path: str | Path,
    *,
    pilot_evidence_path: str | Path,
    calibration_evidence_path: str | Path,
    quick: bool = False,
) -> dict[str, object]:
    """Freeze a clean committed source/config/statistics/success snapshot."""
    root = Path(repo).resolve()
    config_file = Path(config_path).resolve()
    pilot_file = Path(pilot_evidence_path).resolve()
    calibration_file = Path(calibration_evidence_path).resolve()
    snapshot = _git_snapshot(root)
    if not snapshot["clean"]:
        raise RuntimeError(f"freeze requires a clean worktree: {snapshot['dirty_entries']!r}")
    config = load_g7_config(config_file, quick=quick)
    pilot = _read_protocol_evidence(pilot_file, "pilot")
    calibration = _read_protocol_evidence(calibration_file, "calibration")
    pilot_summary = _validate_pilot_evidence_contract(pilot, config, quick=quick)
    calibration_summary = _validate_calibration_evidence_contract(
        calibration, config, quick=quick
    )
    source_sha, source_files = _source_hash(root)
    calibration_status = str(calibration_summary["status"])
    calibration_factor = calibration_summary["calibration_factor"]
    if calibration_status == "CALIBRATED_TUBE":
        if calibration_factor is None or not np.isfinite(float(calibration_factor)) or float(calibration_factor) <= 0.0:
            raise ValueError("CALIBRATED_TUBE evidence requires a positive finite factor")
    elif calibration_factor is not None:
        raise ValueError("uncalibrated evidence must not carry a calibration factor")
    pilot_sha = _sha256(pilot_file)
    calibration_sha = _sha256(calibration_file)
    pilot_summary = {**pilot_summary, "evidence_sha256": pilot_sha}
    calibration_summary = {**calibration_summary, "evidence_sha256": calibration_sha}
    manifest: dict[str, object] = {
        "schema": FREEZE_SCHEMA,
        "protocol": "Pilot -> independent Calibration -> Freeze -> Holdout",
        "frozen_head": snapshot["head"],
        "frozen_branch": snapshot["branch"],
        "clean_at_freeze": True,
        "quick": bool(quick),
        "base_sha": G6_BASE_SHA,
        "implementation_freeze_sha": IMPLEMENTATION_FREEZE_SHA,
        "source_sha256": source_sha,
        "source_files": source_files,
        "config_file_sha256": _sha256(config_file),
        "resolved_config_sha256": resolved_config_hash(config),
        "success_definition_sha256": _canonical_hash(SUCCESS_DEFINITION),
        "statistics_plan_sha256": _canonical_hash(STATISTICS_PLAN),
        "pilot_evidence_sha256": pilot_sha,
        "calibration_evidence_sha256": calibration_sha,
        "pilot_evidence_summary_sha256": _canonical_hash(pilot_summary),
        "calibration_evidence_summary_sha256": _canonical_hash(calibration_summary),
        "pilot_evidence_summary": pilot_summary,
        "calibration_evidence_summary": calibration_summary,
        # Compatibility aliases are complete normalized summaries, not a
        # permissive subset of user-supplied evidence.
        "pilot_contract": pilot_summary,
        "calibration_contract": calibration_summary,
        "calibration_status": calibration_status,
        "calibration_factor": calibration_factor,
        "pilot_data_permitted_in_holdout": False,
        "expected_holdout_case_count": len(evaluation_cases(config, "holdout")),
        "expected_holdout_method_count": len(evaluation_methods("holdout", quick=quick)),
        "expected_holdout_record_count": (
            len(evaluation_cases(config, "holdout"))
            * len(evaluation_methods("holdout", quick=quick))
        ),
        "expected_holdout_v2_1_method_count": len(
            [method for method in evaluation_methods("holdout", quick=quick)
             if method != "g6_fixed_resource_rerun"]
        ),
        "expected_holdout_v2_1_record_count": (
            len(evaluation_cases(config, "holdout"))
            * len([method for method in evaluation_methods("holdout", quick=quick)
                   if method != "g6_fixed_resource_rerun"])
        ),
        "expected_g6_tracking_comparator_method_count": int(
            "g6_fixed_resource_rerun" in evaluation_methods("holdout", quick=quick)
        ),
        "expected_g6_tracking_comparator_record_count": (
            len(evaluation_cases(config, "holdout"))
            if "g6_fixed_resource_rerun" in evaluation_methods("holdout", quick=quick)
            else 0
        ),
        "protocol_pre_freeze_matrix_note": (
            "330 total formal records = 300 ABCG-v2.1 deployment records plus 30 tracking-only "
            "G6 fixed-resource adapter records; checked straight was promoted to the v2.1 primary baseline"
        ),
        "noninferiority_margin_magnitude": 0.10,
        "candidate_minus_baseline_decision_threshold": -0.10,
        "execution": {
            "configured_parallel_workers": config.parallel_workers,
            "expected_actual_case_workers": min(
                config.parallel_workers,
                len(evaluation_cases(config, "holdout")),
            ),
            "execution_mode": (
                "case_process_pool_spawn"
                if min(config.parallel_workers, len(evaluation_cases(config, "holdout"))) > 1
                else "serial_case_loop"
            ),
            "worker_start_method": "spawn",
            "worker_numeric_thread_limit": 1,
            "case_parallelism_unit": "independent_scenario_seed_cohort_case",
            "record_order": "case_index_then_frozen_method_order",
            "runtime_measurement_semantics": (
                "per_episode_wall_latency_inside_case_process_under_frozen_case_concurrency"
            ),
            "gpu_used": False,
            "gpu_policy": "CPU-only NumPy/SciPy/Shapely geometry and solver pipeline",
        },
        "environment": environment_snapshot(),
    }
    write_strict_json(output_path, manifest)
    return manifest


def verify_freeze_manifest(
    repo: str | Path,
    config_path: str | Path,
    manifest_path: str | Path,
    *,
    quick: bool = False,
) -> dict[str, object]:
    """Refuse holdout unless every preregistered frozen input still matches."""
    root = Path(repo).resolve()
    config_file = Path(config_path).resolve()
    manifest_file = Path(manifest_path).resolve()
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    if manifest.get("schema") != FREEZE_SCHEMA:
        raise ValueError("invalid G7 freeze manifest schema")
    snapshot = _git_snapshot(root)
    if not snapshot["clean"]:
        raise RuntimeError(f"holdout requires a clean worktree: {snapshot['dirty_entries']!r}")
    if snapshot["head"] != manifest.get("frozen_head"):
        raise RuntimeError("holdout HEAD differs from frozen HEAD")
    if snapshot["branch"] != manifest.get("frozen_branch"):
        raise RuntimeError("holdout branch differs from frozen branch")
    if bool(manifest.get("quick")) != bool(quick):
        raise RuntimeError("holdout quick mode differs from frozen mode")
    config = load_g7_config(config_file, quick=quick)
    source_sha, source_files = _source_hash(root)
    checks = {
        "source_sha256": source_sha,
        "source_files": source_files,
        "config_file_sha256": _sha256(config_file),
        "resolved_config_sha256": resolved_config_hash(config),
        "success_definition_sha256": _canonical_hash(SUCCESS_DEFINITION),
        "statistics_plan_sha256": _canonical_hash(STATISTICS_PLAN),
        "expected_holdout_case_count": len(evaluation_cases(config, "holdout")),
        "expected_holdout_method_count": len(evaluation_methods("holdout", quick=quick)),
        "expected_holdout_record_count": (
            len(evaluation_cases(config, "holdout"))
            * len(evaluation_methods("holdout", quick=quick))
        ),
        "expected_holdout_v2_1_method_count": len(
            [method for method in evaluation_methods("holdout", quick=quick)
             if method != "g6_fixed_resource_rerun"]
        ),
        "expected_holdout_v2_1_record_count": (
            len(evaluation_cases(config, "holdout"))
            * len([method for method in evaluation_methods("holdout", quick=quick)
                   if method != "g6_fixed_resource_rerun"])
        ),
        "expected_g6_tracking_comparator_method_count": int(
            "g6_fixed_resource_rerun" in evaluation_methods("holdout", quick=quick)
        ),
        "expected_g6_tracking_comparator_record_count": (
            len(evaluation_cases(config, "holdout"))
            if "g6_fixed_resource_rerun" in evaluation_methods("holdout", quick=quick)
            else 0
        ),
        "execution": {
            "configured_parallel_workers": config.parallel_workers,
            "expected_actual_case_workers": min(
                config.parallel_workers,
                len(evaluation_cases(config, "holdout")),
            ),
            "execution_mode": (
                "case_process_pool_spawn"
                if min(config.parallel_workers, len(evaluation_cases(config, "holdout"))) > 1
                else "serial_case_loop"
            ),
            "worker_start_method": "spawn",
            "worker_numeric_thread_limit": 1,
            "case_parallelism_unit": "independent_scenario_seed_cohort_case",
            "record_order": "case_index_then_frozen_method_order",
            "runtime_measurement_semantics": (
                "per_episode_wall_latency_inside_case_process_under_frozen_case_concurrency"
            ),
            "gpu_used": False,
            "gpu_policy": "CPU-only NumPy/SciPy/Shapely geometry and solver pipeline",
        },
    }
    mismatches = [key for key, value in checks.items() if manifest.get(key) != value]
    if mismatches:
        raise RuntimeError(f"frozen input verification failed: {mismatches!r}")
    if manifest.get("pilot_data_permitted_in_holdout") is not False:
        raise RuntimeError("freeze manifest does not prohibit pilot data in holdout")
    _validate_embedded_protocol_summaries(manifest, config, quick=quick)
    pilot_summary = manifest["pilot_evidence_summary"]
    calibration_summary = manifest["calibration_evidence_summary"]
    if (
        not isinstance(pilot_summary, Mapping)
        or pilot_summary.get("evidence_sha256") != manifest.get("pilot_evidence_sha256")
        or not isinstance(calibration_summary, Mapping)
        or calibration_summary.get("evidence_sha256") != manifest.get("calibration_evidence_sha256")
    ):
        raise RuntimeError("embedded protocol summaries disagree with frozen evidence file hashes")
    if (
        _canonical_hash(pilot_summary) != manifest.get("pilot_evidence_summary_sha256")
        or _canonical_hash(calibration_summary) != manifest.get("calibration_evidence_summary_sha256")
        or manifest.get("pilot_contract") != pilot_summary
        or manifest.get("calibration_contract") != calibration_summary
    ):
        raise RuntimeError("embedded protocol summary digest or compatibility alias mismatch")
    calibration_status = str(manifest.get("calibration_status"))
    calibration_factor = manifest.get("calibration_factor")
    if calibration_status == "CALIBRATED_TUBE":
        if calibration_factor is None or not np.isfinite(float(calibration_factor)) or float(calibration_factor) <= 0.0:
            raise RuntimeError("frozen calibrated tube factor is invalid")
    elif calibration_factor is not None:
        raise RuntimeError("uncalibrated freeze manifest carries a factor")
    return {**manifest, "holdout_verification": "PASS"}


def reject_g6_output(repo: str | Path, output: str | Path) -> None:
    root = Path(repo).resolve()
    target = Path(output).resolve()
    protected = (root / "reports" / "step1_g6_compliance").resolve()
    if target == protected or protected in target.parents:
        raise ValueError("G7 output may not write inside the frozen G6 evidence directory")


def environment_snapshot() -> dict[str, object]:
    packages: dict[str, str | None] = {}
    for name in ("numpy", "scipy", "shapely", "PyYAML", "matplotlib"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    return {
        "python": sys.version.split()[0],
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "logical_cpu_count": os.cpu_count(),
        "processor_identifier": os.environ.get("PROCESSOR_IDENTIFIER"),
        "packages": packages,
    }


def _g6_config(config: G7EvaluationConfig, scenario: str, seed: int, *, bootstrap: int) -> G6EvaluationConfig:
    return G6EvaluationConfig(
        seeds=(int(seed),),
        scenarios=(str(scenario),),
        observation_count=int(config.observation_count),
        bootstrap_samples=max(1, int(bootstrap)),
        confidence_interval_resamples=max(1, int(config.bootstrap_resamples)),
        available_guides=int(config.available_guides),
        fixed_guide_count=int(config.fixed_active_guides),
        required_arc_gap=float(config.required_arc_gap),
        safety_distance=float(config.safety_distance),
        coverage_radius=float(config.coverage_radius),
        room_size=tuple(config.room_size),
        dt=float(config.dt),
        max_steps=int(config.max_steps),
        workers=1,
        alpha_scale=float(config.alpha_scale),
        sample_spacing=float(config.sample_spacing),
    )


def _estimate_boundary(
    observation: np.ndarray,
    config: G7EvaluationConfig,
    scenario: str,
    seed: int,
    *,
    bootstrap: int | None = None,
) -> BoundaryEstimateV2 | BoundaryEstimateFailure:
    count = 0 if bootstrap is None else int(bootstrap)
    g6 = _g6_config(config, scenario, seed, bootstrap=max(1, int(count)))
    boundary_config = replace(
        _boundary_config(g6, bootstrap_samples=int(count)),
        room_margin=float(config.room_margin),
    )
    rng = np.random.default_rng(31_000_003 + 4099 * int(seed))
    return estimate_boundary_v2(observation, boundary_config, rng)


def _bootstrap_observation(observation: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Geometric bootstrap support with duplicates removed before NN scaling.

    Multiplicity still determines which support points survive the bootstrap;
    removing exact duplicates prevents zero nearest-neighbour distances from
    collapsing the alpha-shape connectivity radius to numerical epsilon.
    """

    sampled = observation[rng.integers(0, len(observation), len(observation))]
    return np.unique(np.asarray(sampled, dtype=float), axis=0)


def _safe_calibration_ratios(
    absolute_error: np.ndarray,
    raw_radius: np.ndarray,
) -> tuple[np.ndarray | None, int]:
    """Return finite ratios, treating 0/0 as zero and positive/0 as invalid."""

    error = np.asarray(absolute_error, dtype=float)
    radius = np.asarray(raw_radius, dtype=float)
    if (
        error.shape != radius.shape
        or error.ndim != 1
        or not np.all(np.isfinite(error))
        or not np.all(np.isfinite(radius))
        or np.any(error < 0.0)
        or np.any(radius < 0.0)
    ):
        raise ValueError("calibration errors/radii must be same-shape finite non-negative vectors")
    epsilon = np.finfo(float).eps
    invalid = (radius <= epsilon) & (error > epsilon)
    invalid_count = int(np.count_nonzero(invalid))
    if invalid_count:
        return None, invalid_count
    ratios = np.zeros_like(error)
    np.divide(error, radius, out=ratios, where=radius > epsilon)
    return ratios, 0


def _recalculate_calibration_contract(
    cases: Sequence[Mapping[str, object]],
    config: G7EvaluationConfig,
) -> dict[str, object]:
    """Recompute fit factor and untouched-validation coverage from case payloads."""

    expected = {
        (subset, scenario, int(seed))
        for subset, seeds in (
            ("factor_fit", config.calibration_fit_seeds),
            ("independent_validation", config.calibration_validation_seeds),
        )
        for scenario in config.scenarios
        for seed in seeds
    }
    observed: dict[tuple[str, str, int], Mapping[str, object]] = {}
    valid_ratios: dict[tuple[str, str, int], np.ndarray] = {}
    for index, case in enumerate(cases):
        if not isinstance(case, Mapping):
            raise ValueError(f"calibration case {index} must be an object")
        try:
            key = (
                str(case["calibration_subset"]),
                str(case["scenario"]),
                int(case["seed"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"calibration case {index} has an invalid identity") from error
        if key not in expected:
            raise ValueError(f"unexpected calibration case identity: {key!r}")
        if key in observed:
            raise ValueError(f"duplicate calibration case identity: {key!r}")
        observed[key] = case
        if case.get("status") != "VALID_CALIBRATION_CASE":
            continue
        raw_ratios = case.get("point_ratio_values")
        if not isinstance(raw_ratios, Sequence) or isinstance(raw_ratios, (str, bytes)):
            raise ValueError(f"valid calibration case {key!r} lacks point_ratio_values")
        ratios = np.asarray(raw_ratios, dtype=float)
        if ratios.ndim != 1 or len(ratios) < 8 or not np.all(np.isfinite(ratios)) or np.any(ratios < 0.0):
            raise ValueError(f"calibration ratios for {key!r} must be finite and non-negative")
        reported_score = float(case.get("simultaneous_score", np.nan))
        if not np.isclose(reported_score, float(np.max(ratios)), rtol=0.0, atol=1.0e-12):
            raise ValueError(f"calibration simultaneous_score mismatch for {key!r}")
        if int(case.get("point_count", -1)) != len(ratios):
            raise ValueError(f"calibration point_count mismatch for {key!r}")
        valid_ratios[key] = ratios

    missing = sorted(expected - set(observed))
    if missing:
        raise ValueError(f"calibration evidence is missing cases: {missing!r}")

    fit_expected = {key for key in expected if key[0] == "factor_fit"}
    validation_expected = {key for key in expected if key[0] == "independent_validation"}
    fit_valid = {key for key in fit_expected if key in valid_ratios}
    validation_valid = {key for key in validation_expected if key in valid_ratios}
    fit_shapes = {key[1] for key in fit_valid}
    validation_shapes = {key[1] for key in validation_valid}
    fit_complete = fit_valid == fit_expected and len(fit_shapes) >= 2
    validation_complete = validation_valid == validation_expected and len(validation_shapes) >= 2
    fitted_factor: float | None = None
    if fit_complete:
        fitted_factor = float(max(np.max(valid_ratios[key]) for key in sorted(fit_valid)))
        if not np.isfinite(fitted_factor) or fitted_factor <= 0.0:
            fitted_factor = None
            fit_complete = False

    pointwise: float | None = None
    simultaneous: float | None = None
    validation_point_count = 0
    validation_covered_count = 0
    if fitted_factor is not None and validation_complete:
        validation_arrays = [valid_ratios[key] for key in sorted(validation_valid)]
        validation_point_count = int(sum(len(values) for values in validation_arrays))
        validation_covered_count = int(
            sum(np.count_nonzero(values <= fitted_factor + 1.0e-15) for values in validation_arrays)
        )
        pointwise = validation_covered_count / validation_point_count
        simultaneous = float(
            np.mean([bool(np.all(values <= fitted_factor + 1.0e-15)) for values in validation_arrays])
        )
    coverage_passed = bool(
        fitted_factor is not None
        and fit_complete
        and validation_complete
        and pointwise is not None
        and simultaneous is not None
        and pointwise >= 0.95
        and simultaneous >= 0.95
    )
    status = "CALIBRATED_TUBE" if coverage_passed else "CALIBRATION_INSUFFICIENT"
    return {
        "expected_case_count": len(expected),
        "case_count": len(observed),
        "case_keys_sha256": _canonical_hash(sorted(expected)),
        "fit_expected_case_count": len(fit_expected),
        "fit_valid_case_count": len(fit_valid),
        "fit_complete": fit_complete,
        "fit_shape_ids": sorted(fit_shapes),
        "validation_expected_case_count": len(validation_expected),
        "validation_valid_case_count": len(validation_valid),
        "validation_complete": validation_complete,
        "validation_shape_ids": sorted(validation_shapes),
        "fitted_calibration_factor": fitted_factor,
        "validation_point_count": validation_point_count,
        "validation_covered_count": validation_covered_count,
        "validation_pointwise_coverage": pointwise,
        "validation_simultaneous_coverage": simultaneous,
        "coverage_gate_passed": coverage_passed,
        "status": status,
        "calibration_factor": fitted_factor if coverage_passed else None,
    }


def run_calibration(
    config: G7EvaluationConfig,
    output: str | Path,
    *,
    config_hash: str,
    quick: bool,
) -> dict[str, object]:
    """Build independent signed-normal calibration evidence.

    Truth is used only here as the calibration reference; no deployment plan
    or controller receives it.  Formal holdout can use the resulting factor
    only after its file hash is captured by the clean freeze manifest.
    """
    output_dir = Path(output)
    output_dir.mkdir(parents=True, exist_ok=True)
    cases: list[dict[str, object]] = []
    for subset, seeds in (
        ("factor_fit", config.calibration_fit_seeds),
        ("independent_validation", config.calibration_validation_seeds),
    ):
        for scenario in config.scenarios:
            for seed in seeds:
                g6 = _g6_config(config, scenario, seed, bootstrap=1)
                observation, truth = _observed_case(scenario, seed, g6)
                base = _estimate_boundary(observation, config, scenario, seed, bootstrap=0)
                record: dict[str, object] = {
                    "calibration_subset": subset,
                    "scenario": scenario,
                    "seed": int(seed),
                    "observation_hash": _canonical_hash(np.round(observation, 12)),
                    "truth_access": "calibration_scoring_only",
                }
                if isinstance(base, BoundaryEstimateFailure):
                    record.update(status=base.status, failure_reason=base.diagnostics.get("reason"))
                    cases.append(record)
                    continue

                replicas: list[np.ndarray] = []
                replica_failures: list[dict[str, object]] = []
                rng = np.random.default_rng(41_000_009 + 8191 * int(seed))
                for replica_id in range(config.calibration_bootstrap_replicas):
                    sampled = _bootstrap_observation(observation, rng)
                    replica = _estimate_boundary(
                        sampled,
                        config,
                        scenario,
                        seed + 100_000 + replica_id,
                        bootstrap=0,
                    )
                    if isinstance(replica, BoundaryEstimateV2):
                        replicas.append(replica.curve_points)
                    else:
                        replica_failures.append(
                            {
                                "replica_id": replica_id,
                                "status": replica.status,
                                "reason": replica.diagnostics.get("reason"),
                            }
                        )
                stability = estimate_boundary_stability(
                    base.curve_points,
                    replicas,
                    config=BoundaryStabilityConfig(
                        sample_count=128,
                        min_bootstrap_success_fraction=0.7,
                        min_calibration_shapes=2,
                        min_calibration_replicas=min(
                            4, config.calibration_bootstrap_replicas
                        ),
                    ),
                )
                if isinstance(stability, BoundaryStabilityFailure):
                    record.update(
                        status=stability.status,
                        failure_reason=stability.diagnostics.get("reason"),
                        requested_bootstrap_replicas=config.calibration_bootstrap_replicas,
                        successful_bootstrap_replicas=len(replicas),
                        replica_failures=replica_failures,
                    )
                    cases.append(record)
                    continue
                try:
                    reference = align_boundary_replica(stability.base_curve, truth)
                except ValueError as error:
                    record.update(
                        status="CALIBRATION_REFERENCE_INVALID", failure_reason=str(error)
                    )
                    cases.append(record)
                    continue

                absolute_error = np.abs(reference.signed_normal_displacement)
                ratios, invalid_ratio_count = _safe_calibration_ratios(
                    absolute_error,
                    stability.raw_tube_radius,
                )
                if ratios is None:
                    record.update(
                        status="CALIBRATION_RATIO_INVALID",
                        failure_reason="positive_reference_error_with_zero_bootstrap_radius",
                        invalid_ratio_point_count=invalid_ratio_count,
                        bootstrap_success_count=stability.bootstrap_success_count,
                        requested_bootstrap_replicas=config.calibration_bootstrap_replicas,
                        replica_failures=replica_failures,
                    )
                    cases.append(record)
                    continue
                record.update(
                    status="VALID_CALIBRATION_CASE",
                    bootstrap_success_count=stability.bootstrap_success_count,
                    requested_bootstrap_replicas=config.calibration_bootstrap_replicas,
                    replica_failures=replica_failures,
                    stability_score=stability.stability_score,
                    simultaneous_score=float(np.max(ratios)),
                    point_count=len(ratios),
                    point_ratio_values=ratios.tolist(),
                    base_curve_sha256=stability.base_curve.sha256,
                )
                cases.append(record)

    recalculated = _recalculate_calibration_contract(cases, config)
    fitted_factor = recalculated["fitted_calibration_factor"]
    if fitted_factor is not None:
        for record in cases:
            ratios = record.get("point_ratio_values")
            if not isinstance(ratios, Sequence):
                continue
            values = np.asarray(ratios, dtype=float)
            record["coverage_factor"] = fitted_factor
            record["pointwise_covered_count"] = int(
                np.count_nonzero(values <= float(fitted_factor) + 1.0e-15)
            )
            record["simultaneous_covered"] = bool(
                np.all(values <= float(fitted_factor) + 1.0e-15)
            )

    evidence: dict[str, object] = {
        "schema": "abcg-v2.1-g7-independent-calibration-v1",
        "split": "calibration",
        "formal": False,
        "quick": bool(quick),
        "pilot_data_used": False,
        "historical_g6_seeds_used": False,
        "factor_fit_uses_validation_data": False,
        "status": recalculated["status"],
        "calibration_factor": recalculated["calibration_factor"],
        "fitted_calibration_factor": fitted_factor,
        "target_coverage": 0.95,
        "pointwise_coverage": recalculated["validation_pointwise_coverage"],
        "simultaneous_coverage": recalculated["validation_simultaneous_coverage"],
        "validation_pointwise_coverage": recalculated["validation_pointwise_coverage"],
        "validation_simultaneous_coverage": recalculated["validation_simultaneous_coverage"],
        "unique_shape_count": len(recalculated["validation_shape_ids"]),
        "valid_shape_ids": recalculated["validation_shape_ids"],
        "case_count": len(cases),
        "valid_case_count": sum(
            case["status"] == "VALID_CALIBRATION_CASE" for case in cases
        ),
        "fit_case_count": recalculated["fit_expected_case_count"],
        "fit_valid_case_count": recalculated["fit_valid_case_count"],
        "validation_case_count": recalculated["validation_expected_case_count"],
        "validation_valid_case_count": recalculated["validation_valid_case_count"],
        "validation_point_count": recalculated["validation_point_count"],
        "validation_covered_count": recalculated["validation_covered_count"],
        "coverage_gate_passed": recalculated["coverage_gate_passed"],
        "seed_splits_disjoint": not bool(
            set(config.calibration_seeds)
            & (
                set(config.pilot_seeds)
                | set(config.holdout_general_seeds)
                | set(config.holdout_blocked_seeds)
            )
        ),
        "seeds": list(config.calibration_seeds),
        "factor_fit_seeds": list(config.calibration_fit_seeds),
        "independent_validation_seeds": list(config.calibration_validation_seeds),
        "scenarios": list(config.scenarios),
        "config_hash": config_hash,
        "recalculated_contract": recalculated,
        "cases": cases,
        "limitations": [
            "calibrated_for_the_frozen_static_synthetic_generator_only",
            "not_human_safety_certification",
            "not_a_bound_on_arbitrary_high_frequency_truth_perimeter",
        ],
    }
    write_strict_json(output_dir / "calibration_evidence.json", evidence)
    return evidence


@dataclass
class _PreparedCase:
    scenario: str
    seed: int
    cohort: str
    initial_layout: str
    observation: np.ndarray
    initial_guides: np.ndarray
    boundary: BoundaryEstimateV2 | BoundaryEstimateFailure
    stability_status: str
    stability_score: float | None
    raw_tube_max: float | None
    calibration_factor: float | None
    calibration_status: str
    route_cache: dict[tuple[object, ...], object]


def _one_sided_guides(count: int) -> np.ndarray:
    y = np.linspace(0.55, 9.45, int(count))
    return np.column_stack((np.full(int(count), 0.55), y))


def _prepare_case(
    config: G7EvaluationConfig,
    scenario: str,
    seed: int,
    cohort: str,
    *,
    forced_layout: str | None,
    calibration_status: str,
    calibration_factor: float | None,
    observation_truth: tuple[np.ndarray, np.ndarray] | None = None,
) -> tuple[_PreparedCase, np.ndarray]:
    if observation_truth is None:
        g6 = _g6_config(config, scenario, seed, bootstrap=config.boundary_bootstrap_samples)
        observation, truth = _observed_case(scenario, seed, g6)
    else:
        observation = np.asarray(observation_truth[0], dtype=float)
        truth = np.asarray(observation_truth[1], dtype=float)
    boundary = _estimate_boundary(observation, config, scenario, seed, bootstrap=0)
    stability_status = "BOUNDARY_INVALID"
    stability_score: float | None = None
    raw_tube_max: float | None = None
    if isinstance(boundary, BoundaryEstimateV2):
        replicas: list[np.ndarray] = []
        rng = np.random.default_rng(51_000_019 + 12289 * int(seed))
        replica_count = int(config.boundary_bootstrap_samples)
        for replica_id in range(replica_count):
            sampled = _bootstrap_observation(observation, rng)
            replica = _estimate_boundary(
                sampled,
                config,
                scenario,
                seed + 200_000 + replica_id,
                bootstrap=0,
            )
            if isinstance(replica, BoundaryEstimateV2):
                replicas.append(replica.curve_points)
        stability = estimate_boundary_stability(
            boundary.curve_points,
            replicas,
            config=BoundaryStabilityConfig(
                sample_count=128,
                min_bootstrap_success_fraction=0.5,
                min_calibration_shapes=2,
                min_calibration_replicas=min(4, replica_count),
            ),
        )
        if isinstance(stability, BoundaryStabilityFailure):
            stability_status = stability.status
        else:
            stability_status = stability.status
            stability_score = float(stability.stability_score)
            raw_tube_max = float(np.max(stability.raw_tube_radius))
    if forced_layout == "one_sided":
        initial_guides = _one_sided_guides(config.available_guides)
        layout = "one_sided"
    else:
        initial_guides, layout = _initial_guides(seed, config.available_guides)
    planning = _PreparedCase(
        scenario=scenario,
        seed=int(seed),
        cohort=cohort,
        initial_layout=layout,
        observation=observation,
        initial_guides=initial_guides,
        boundary=boundary,
        stability_status=stability_status,
        stability_score=stability_score,
        raw_tube_max=raw_tube_max,
        calibration_factor=calibration_factor,
        calibration_status=calibration_status,
        route_cache={},
    )
    # Truth remains a separate return value.  Only _score_truth receives it.
    return planning, truth


def _method_spec(method: str) -> dict[str, object]:
    specs: dict[str, dict[str, object]] = {
        "g6_fixed_resource_rerun": {
            "route": "g6_fixed_resource_straight", "assignment": "g6_lambda_0_25",
            "phase": "g6_periodic_confidence", "uncertainty": "g6_bootstrap_confidence",
            "safety": "g6_dykstra_sampled_only", "resource": "fixed",
            "compatibility_comparator": True, "v2_1_routing_pipeline": False,
        },
        "legacy_unchecked_straight": {
            "route": "unchecked_straight", "assignment": "hungarian", "phase": "zero",
            "uncertainty": "none", "safety": "dykstra", "resource": "fixed",
            "compatibility_comparator": True, "v2_1_routing_pipeline": False,
        },
        "straight_hungarian": {
            "route": "straight", "assignment": "hungarian", "phase": "optimized",
            "uncertainty": "stability", "safety": "dykstra", "resource": "fixed",
            "compatibility_comparator": False, "v2_1_routing_pipeline": True,
        },
        "visibility_hungarian": {
            "route": "visibility_graph", "assignment": "hungarian", "phase": "optimized",
            "uncertainty": "stability", "safety": "dykstra", "resource": "fixed",
        },
        "boundary_corridor_hungarian": {
            "route": "boundary_corridor", "assignment": "hungarian", "phase": "optimized",
            "uncertainty": "stability", "safety": "dykstra", "resource": "fixed",
        },
        "visibility_cyclic": {
            "route": "visibility_graph", "assignment": "cyclic", "phase": "optimized",
            "uncertainty": "stability", "safety": "dykstra", "resource": "fixed",
        },
        "visibility_phase0": {
            "route": "visibility_graph", "assignment": "hungarian", "phase": "zero",
            "uncertainty": "stability", "safety": "dykstra", "resource": "fixed",
        },
        "visibility_uncertainty_none": {
            "route": "visibility_graph", "assignment": "hungarian", "phase": "optimized",
            "uncertainty": "none", "safety": "dykstra", "resource": "fixed",
        },
        "visibility_uncertainty_calibrated": {
            "route": "visibility_graph", "assignment": "hungarian", "phase": "optimized",
            "uncertainty": "calibrated_tube", "safety": "dykstra", "resource": "fixed",
        },
        "visibility_qp": {
            "route": "visibility_graph", "assignment": "hungarian", "phase": "optimized",
            "uncertainty": "stability", "safety": "slsqp_convex_qcqp", "resource": "fixed",
        },
        "adaptive_nominal_visibility": {
            "route": "visibility_graph", "assignment": "hungarian", "phase": "optimized",
            "uncertainty": "none", "safety": "dykstra", "resource": "nominal",
        },
        "adaptive_robust_visibility": {
            "route": "visibility_graph", "assignment": "hungarian", "phase": "optimized",
            "uncertainty": "calibrated_tube", "safety": "dykstra", "resource": "robust",
        },
    }
    if method not in specs:
        raise ValueError(f"unknown G7 method: {method}")
    return specs[method]


def _public_route_variant(method: str) -> str:
    """Stable evidence label; the legacy name must not resemble a checked route."""

    if method == "legacy_unchecked_straight":
        return "legacy_unchecked_straight"
    if method == "g6_fixed_resource_rerun":
        return "g6_fixed_resource_straight"
    return str(_method_spec(method)["route"])


def _curve_targets(curve: np.ndarray, arc_s: np.ndarray, length: float, sites: np.ndarray) -> np.ndarray:
    coordinates = np.mod(np.asarray(sites, dtype=float), float(length))
    step = float(length) / len(curve)
    scaled = coordinates / step
    first = np.floor(scaled).astype(int) % len(curve)
    fraction = scaled - np.floor(scaled)
    second = (first + 1) % len(curve)
    return curve[first] + fraction[:, None] * (curve[second] - curve[first])


def _canonical_geometry(
    planning: _PreparedCase,
    config: G7EvaluationConfig,
    uncertainty_mode: str,
) -> tuple[BufferedPolygonGeometry | None, GuideFreeSpace | None, dict[str, object]]:
    if isinstance(planning.boundary, BoundaryEstimateFailure):
        return None, None, {"status": planning.boundary.status, "reason": planning.boundary.diagnostics.get("reason")}
    extra = 0.0
    uncertainty_status = "NONE"
    if uncertainty_mode == "stability":
        if planning.raw_tube_max is None or not np.isfinite(planning.raw_tube_max):
            return None, None, {
                "status": "RESOURCE_UNCERTAIN",
                "reason": "bootstrap_stability_radius_not_available",
                "stability_status": planning.stability_status,
            }
        extra = float(planning.raw_tube_max)
        uncertainty_status = "UNCALIBRATED_STABILITY_HEURISTIC"
    elif uncertainty_mode == "calibrated_tube":
        if (
            planning.calibration_status != "CALIBRATED_TUBE"
            or planning.calibration_factor is None
            or planning.raw_tube_max is None
        ):
            return None, None, {
                "status": "RESOURCE_UNCERTAIN",
                "reason": "independent_calibrated_tube_not_available",
                "calibration_status": planning.calibration_status,
                "stability_status": planning.stability_status,
            }
        else:
            extra = float(planning.calibration_factor * planning.raw_tube_max)
            uncertainty_status = "CALIBRATED_TUBE"
    simplification_tolerance = float(config.sample_spacing / 2.0)
    source_polygon = Polygon(planning.boundary.curve_points).simplify(
        simplification_tolerance,
        preserve_topology=True,
    )
    buffer_result = build_polygon_buffer(
        source_polygon,
        PolygonBufferConfig(
            # The simplification error budget is included conservatively so
            # the canonical route/safety clearance still covers the original
            # estimated ring to the declared tolerance.
            clearance=float(config.safety_distance + extra + simplification_tolerance),
            quad_segs=4,
            room_size=tuple(config.room_size),
            room_margin=float(config.room_margin),
            allow_holes=False,
            allow_topology_change=False,
        ),
    )
    if not isinstance(buffer_result, BufferedPolygonGeometry):
        return None, None, {
            "status": buffer_result.status,
            "reason": buffer_result.diagnostics.get("reason"),
            "diagnostics": dict(buffer_result.diagnostics),
        }
    free_result = build_guide_free_space(
        buffer_result,
        FreeSpaceConfig(room_size=tuple(config.room_size), room_margin=float(config.room_margin)),
    )
    if not isinstance(free_result, GuideFreeSpace):
        return buffer_result, None, {
            "status": free_result.status,
            "reason": free_result.diagnostics.get("reason"),
            "diagnostics": dict(free_result.diagnostics),
        }
    return buffer_result, free_result, {
        "status": "VALID",
        "uncertainty_status": uncertainty_status,
        "uncertainty_extra_clearance": extra,
        "uncertainty_is_calibrated_confidence": uncertainty_status == "CALIBRATED_TUBE",
        "stability_mode_semantics": (
            "raw_tube_max_heuristic_expansion_not_calibrated_confidence"
            if uncertainty_mode == "stability" else None
        ),
        "source_simplification_tolerance": simplification_tolerance,
        "source_vertex_count_before": len(planning.boundary.curve_points),
        "source_vertex_count_after": len(buffer_result.source_polygon.exterior.coords) - 1,
        "stability_score": planning.stability_score,
        "geometry_sha256": free_result.geometry_sha256,
        "canonical_source_sha256": _canonical_hash(
            np.round(np.asarray(buffer_result.source_polygon.exterior.coords[:-1], dtype=float), 12)
        ),
    }


def _canonical_safety_points(
    buffer_geometry: BufferedPolygonGeometry,
    spacing: float,
) -> np.ndarray:
    """Sample safety constraints from the exact canonical routing source."""
    points, _, _, _, _ = resample_closed_curve_by_arclength(
        np.asarray(buffer_geometry.source_polygon.exterior.coords[:-1], dtype=float),
        spacing=float(spacing),
    )
    return points


def _failure_record(
    planning: _PreparedCase,
    *,
    method: str,
    regime: ResourceRegime,
    active_count: int,
    status: str,
    reason: str,
    config_hash: str,
    branch_sha: str,
    frozen_sha: str,
    plan_optimal: bool = False,
    route_feasible: bool = False,
    runtime_ms: float | None = None,
    peak_memory_bytes: int | None = None,
    diagnostics: Mapping[str, object] | None = None,
    truth: np.ndarray | None = None,
    evaluation_config: G7EvaluationConfig | None = None,
) -> tuple[G7Record, dict[str, object]]:
    failure_diagnostics = dict(diagnostics or {})
    truth_coverage: float = 0.0
    truth_gap: float | None = None
    truth_boundary: list[object] = []
    truth_access = "evaluator_only_not_used_due_to_pretruth_failure"
    if truth is not None and evaluation_config is not None:
        try:
            truth_coverage, truth_gap = _truth_metrics(
                planning.initial_guides[:active_count],
                truth,
                evaluation_config,
            )
            truth_boundary = np.asarray(truth, dtype=float).tolist()
            truth_access = "post_terminal_failure_scoring_only"
        except Exception as error:
            # Failure serialization is the final denominator-preservation
            # boundary.  A secondary evaluator-only truth error must never
            # escape and erase the original episode failure.
            truth_access = "post_terminal_truth_scoring_failed_record_retained"
            failure_diagnostics["truth_scoring_error"] = {
                "exception_type": type(error).__name__,
                "message": str(error),
            }
    outcome = compose_layered_outcome(
        plan_optimal=plan_optimal,
        route_feasible=route_feasible,
        controller_terminal_state=status,
        sampled_safe=False,
        truth_criteria_met=False,
        terminal_reason=reason,
        failure_reason=status,
        diagnostics={"control_called": False, **failure_diagnostics},
    )
    metrics = DeploymentMetrics(
        truth_coverage=truth_coverage,
        maximum_consecutive_arc_gap=truth_gap,
        tracking_rmse=None,
        minimum_intersample_clearance=None,
        active_guide_count=int(active_count),
        path_length=0.0,
        control_energy=0.0,
        runtime_ms=0.0 if runtime_ms is None else runtime_ms,
        peak_memory_bytes=0 if peak_memory_bytes is None else peak_memory_bytes,
    )
    record = G7Record(
        scenario=planning.scenario,
        method=method,
        seed=planning.seed,
        resource_regime=regime,
        outcome=outcome,
        metrics=metrics,
        config_hash=config_hash,
        base_sha=G6_BASE_SHA,
        branch_sha=branch_sha,
        metadata={
            "case_id": f"{planning.cohort}:{planning.scenario}:{planning.seed}",
            "case_cohort": planning.cohort,
            "resource_cohort": f"{planning.cohort}:{active_count}",
            "initial_layout": planning.initial_layout,
            "frozen_sha": frozen_sha,
            "environment": environment_snapshot(),
            "truth_access": truth_access,
            "control_called": False,
            "precontrol_zero_motion_metrics": True,
            **failure_diagnostics,
        },
    )
    media_positions = planning.initial_guides[:active_count]
    if isinstance(planning.boundary, BoundaryEstimateV2):
        source_polygon = Polygon(planning.boundary.curve_points)
        if evaluation_config is not None:
            source_polygon = source_polygon.simplify(
                float(evaluation_config.sample_spacing / 2.0), preserve_topology=True
            )
        source_points = np.asarray(source_polygon.exterior.coords[:-1], dtype=float).tolist()
        source_semantics = "canonical_estimated_source_before_buffer"
    else:
        diagnostic_hull = MultiPoint(np.asarray(planning.observation, dtype=float)).convex_hull
        source_points = (
            np.asarray(diagnostic_hull.exterior.coords[:-1], dtype=float).tolist()
            if isinstance(diagnostic_hull, Polygon)
            else []
        )
        source_semantics = "diagnostic_observation_hull_boundary_estimation_failed"
    media = {
        "scenario": planning.scenario,
        "seed": planning.seed,
        "method": method,
        "truth_boundary": truth_boundary,
        "source_polygon": source_points,
        "source_polygon_semantics": source_semantics,
        "targets": [],
        "initial_positions": media_positions.tolist(),
        "paths": [],
        "trajectories": [[point.tolist()] for point in media_positions],
        "status": status,
        "failure_reason": reason,
    }
    return record, media


def _route_matrix(
    planning: _PreparedCase,
    guides: np.ndarray,
    targets: np.ndarray,
    free_space: GuideFreeSpace,
    route_method: str,
) -> PairwiseRouteMatrix:
    key = (
        route_method,
        free_space.geometry_sha256,
        _canonical_hash(np.round(guides, 10)),
        _canonical_hash(np.round(targets, 10)),
    )
    cached = planning.route_cache.get(key)
    if isinstance(cached, PairwiseRouteMatrix):
        return cached
    matrix = build_pairwise_route_matrix(guides, targets, free_space, route_method)
    planning.route_cache[key] = matrix
    return matrix


def _trajectory_clearance(
    trajectory: np.ndarray,
    source_polygon: object,
    required_clearance: float,
) -> float:
    values: list[float] = []
    for guide_id in range(trajectory.shape[1]):
        track = trajectory[:, guide_id, :]
        for point in track:
            values.append(float(Point(point).distance(source_polygon) - required_clearance))
        for first, second in zip(track[:-1], track[1:], strict=True):
            values.append(float(LineString((first, second)).distance(source_polygon) - required_clearance))
    return min(values) if values else 0.0


def _truth_metrics(
    final_positions: np.ndarray,
    truth: np.ndarray,
    config: G7EvaluationConfig,
) -> tuple[float, float | None]:
    truth_curve, truth_s, truth_length, _, _ = resample_closed_curve_by_arclength(
        truth,
        spacing=config.sample_spacing,
    )
    coverage = coverage_ratio_to_points(final_positions, truth, config.coverage_radius) if len(final_positions) else 0.0
    if not len(final_positions):
        return float(coverage), float(truth_length)
    nearest = np.argmin(
        np.linalg.norm(final_positions[:, None, :] - truth_curve[None, :, :], axis=2),
        axis=1,
    )
    coordinates = np.unique(truth_s[nearest])
    gap = max_consecutive_arc_gap(coordinates, truth_length) if len(coordinates) else None
    return float(coverage), None if gap is None else float(gap)


def _episode_failure_reason(*, route_feasible: bool, replan_reason: str | None) -> str | None:
    """Preserve layer priority even when the legacy ablation still enters control."""

    if not route_feasible:
        return "ROUTE_INFEASIBLE"
    if replan_reason == "NO_PROGRESS_DETECTED":
        return "NO_PROGRESS"
    return None


def _evaluate_g6_fixed_resource_adapter(
    planning: _PreparedCase,
    truth: np.ndarray,
    config: G7EvaluationConfig,
    *,
    config_hash: str,
    branch_sha: str,
    frozen_sha: str,
) -> tuple[G7Record, dict[str, object]]:
    """Run frozen G6 components with only resource count adapted to fixed m=8.

    This comparator is intentionally tracking-only.  It receives neither a
    v2.1 route certificate nor an S5 dense safety certificate, so its old
    controller ``CONVERGED`` state is never promoted to deployment success.
    """

    method = "g6_fixed_resource_rerun"
    active_count = min(
        G6_ADAPTER_ACTIVE_COUNT,
        config.fixed_active_guides,
        config.available_guides,
    )
    initial = planning.initial_guides[:active_count].copy()
    started = perf_counter()
    tracemalloc.start()
    g6_boundary: BoundaryEstimateV2 | BoundaryEstimateFailure | None = None
    targets = np.empty((0, 2), dtype=float)
    try:
        g6_config = replace(
            _g6_config(
                config,
                planning.scenario,
                planning.seed,
                bootstrap=G6_ADAPTER_BOOTSTRAP_SAMPLES,
            ),
            bootstrap_samples=G6_ADAPTER_BOOTSTRAP_SAMPLES,
            fixed_guide_count=active_count,
            max_steps=G6_ADAPTER_MAX_STEPS,
        )
        scenario_index = G6_PRIMARY_SCENARIOS.index(planning.scenario)
        g6_boundary = estimate_boundary_v2(
            planning.observation,
            _boundary_config(g6_config),
            np.random.default_rng(42_000_019 + 4099 * planning.seed + scenario_index),
        )
        if isinstance(g6_boundary, BoundaryEstimateFailure):
            raise RuntimeError(
                f"{g6_boundary.status}: "
                f"{g6_boundary.diagnostics.get('reason', 'g6_boundary_invalid')}"
            )
        plan = plan_periodic_arc_coverage(
            g6_boundary,
            active_count,
            PeriodicArcCVTConfig(max_iterations=G6_ADAPTER_PERIODIC_MAX_ITERATIONS),
        )
        if (
            np.asarray(plan.target_xy).shape != (active_count, 2)
            or not np.all(np.isfinite(plan.target_xy))
            or plan.active_count != active_count
        ):
            raise RuntimeError(f"{plan.status}: g6_periodic_plan_invalid")
        targets = np.asarray(plan.target_xy, dtype=float)
        assignment = assign_guides_to_targets(
            initial,
            targets,
            AssignmentConfig(lambda_switch=G6_ADAPTER_ASSIGNMENT_SWITCH_PENALTY),
        )
        if assignment.status != "VALID" or len(assignment.unmet_target_ids):
            raise RuntimeError(
                f"{assignment.status}: "
                f"{assignment.diagnostics.get('reason', 'g6_assignment_failed')}"
            )
        trace, events, episode = _run_g6_feedback_episode(
            planning.observation,
            initial,
            targets,
            assignment,
            g6_config,
        )
        terminal = str(episode["episode_status"])
        runtime_ms = (perf_counter() - started) * 1000.0
        _, peak = tracemalloc.get_traced_memory()
        final_positions = np.asarray(trace["positions"][-1], dtype=float)
        truth_coverage, truth_gap = _truth_metrics(final_positions, truth, config)
        truth_criteria = bool(
            truth_coverage >= config.truth_coverage_minimum
            and truth_gap is not None
            and truth_gap <= config.required_arc_gap + 1.0e-9
        )
        failure_reason = (
            terminal
            if terminal != "CONVERGED"
            else "G6_TRACK_CONVERGED_ONLY"
        )
        outcome = compose_layered_outcome(
            plan_optimal=False,
            route_feasible=False,
            controller_terminal_state=terminal,
            sampled_safe=False,
            truth_criteria_met=truth_criteria,
            terminal_reason=terminal,
            failure_reason=failure_reason,
            diagnostics={
                "control_called": True,
                "tracking_only_comparator": True,
                "old_safety_not_promoted_to_SAMPLED_SAFE": True,
            },
        )
        metrics = DeploymentMetrics(
            truth_coverage=truth_coverage,
            maximum_consecutive_arc_gap=truth_gap,
            tracking_rmse=(
                None
                if episode.get("tracking_rmse_final") is None
                else float(episode["tracking_rmse_final"])
            ),
            minimum_intersample_clearance=None,
            active_guide_count=active_count,
            path_length=float(episode["path_length_m"]),
            control_energy=float(episode["control_energy_m2_per_s"]),
            runtime_ms=runtime_ms,
            peak_memory_bytes=peak,
        )
        source_semantics = {
            "label": "Frozen G6 fixed-resource straight-feedback adapter rerun on matched G7 holdout",
            "boundary": "G6 alpha bootstrap estimator and frozen G6 RNG",
            "boundary_bootstrap_samples": G6_ADAPTER_BOOTSTRAP_SAMPLES,
            "planner": "G6 confidence-gated periodic Lloyd with fixed m adapter",
            "periodic_max_iterations": G6_ADAPTER_PERIODIC_MAX_ITERATIONS,
            "assignment_lambda_switch": G6_ADAPTER_ASSIGNMENT_SWITCH_PENALTY,
            "controller": "G6 ABCGv2Controller straight fixed-target feedback",
            "controller_max_steps": G6_ADAPTER_MAX_STEPS,
            "fixed_active_guides": active_count,
            "adaptations": [
                "adaptive_G6_resource_policy_replaced_by_fixed_m8_for_same_resource_comparison",
                "matched_G7_holdout_seeds_observations_and_initial_guides",
            ],
            "not_exact_historical_G6_run": True,
            "not_v2_1_deployment_success_comparator": True,
            "runtime_scope": "observation_available_then_g6_boundary_plan_control_excludes_truth_scoring",
            "quick_smoke_active_count_reduced": active_count != G6_ADAPTER_ACTIVE_COUNT,
        }
        record = G7Record(
            scenario=planning.scenario,
            method=method,
            seed=planning.seed,
            resource_regime=ResourceRegime.SAME_RESOURCE,
            outcome=outcome,
            metrics=metrics,
            config_hash=config_hash,
            base_sha=G6_BASE_SHA,
            branch_sha=branch_sha,
            metadata={
                "case_id": f"{planning.cohort}:{planning.scenario}:{planning.seed}",
                "case_cohort": planning.cohort,
                "resource_cohort": f"{planning.cohort}:{active_count}",
                "initial_layout": planning.initial_layout,
                "frozen_sha": frozen_sha,
                "environment": environment_snapshot(),
                "truth_access": "evaluator_only_after_terminal",
                "runtime_scope": "observation_available_then_g6_boundary_plan_control_excludes_truth_scoring",
                "observation_hash": _canonical_hash(np.round(planning.observation, 12)),
                "method_spec": _method_spec(method),
                "comparison_role": "g6_tracking_only_blocked_timeout_comparator",
                "v2_1_routing_pipeline": False,
                "g6_source_semantics": source_semantics,
                "g6_plan": {
                    "status": plan.status,
                    "active_count": plan.active_count,
                    "max_arc_gap": plan.max_arc_gap,
                    "h_final": float(plan.h_history[-1]),
                },
                "assignment": {
                    "status": assignment.status,
                    "total_cost": assignment.total_cost,
                    "guide_to_target": assignment.guide_to_target.tolist(),
                    "lambda_switch": G6_ADAPTER_ASSIGNMENT_SWITCH_PENALTY,
                },
                "g6_episode_events": events,
                "g6_old_safety": {
                    "safety_projection_count": episode["safety_projection_count"],
                    "safety_infeasible_count": episode["safety_infeasible_count"],
                    "not_an_S5_dense_certificate": True,
                },
            },
        )
        guide_to_target = np.asarray(assignment.guide_to_target, dtype=int)
        assigned_targets = targets[guide_to_target]
        media = {
            "scenario": planning.scenario,
            "seed": planning.seed,
            "method": method,
            "truth_boundary": np.asarray(truth, dtype=float).tolist(),
            "source_polygon": np.asarray(g6_boundary.curve_points, dtype=float).tolist(),
            "source_polygon_semantics": "frozen_g6_bootstrap_boundary_curve",
            "targets": assigned_targets.tolist(),
            "initial_positions": initial.tolist(),
            "paths": [np.vstack((initial[index], assigned_targets[index])).tolist() for index in range(active_count)],
            "trajectories": [
                np.asarray(trace["positions"][:, guide_id, :], dtype=float).tolist()
                for guide_id in range(active_count)
            ],
            "status": terminal,
            "failure_reason": failure_reason,
            "estimated_deployment_success": False,
            "truth_validated_success": False,
        }
        return record, media
    except Exception as error:
        _, peak = tracemalloc.get_traced_memory()
        status_prefix = str(error).split(":", 1)[0].strip().upper()
        status = status_prefix if status_prefix in {
            "BOUNDARY_INVALID",
            "OFFSET_INVALID",
            "CAPACITY_SHORTFALL",
            "ASSIGNMENT_INFEASIBLE",
            "SAFETY_INFEASIBLE",
            "TIMEOUT",
        } else "EVALUATION_ERROR"
        record, media = _failure_record(
            planning,
            method=method,
            regime=ResourceRegime.SAME_RESOURCE,
            active_count=active_count,
            status=status,
            reason=f"{type(error).__name__}: {error}",
            config_hash=config_hash,
            branch_sha=branch_sha,
            frozen_sha=frozen_sha,
            runtime_ms=(perf_counter() - started) * 1000.0,
            peak_memory_bytes=peak,
            diagnostics={
                "exception_scope": "g6_fixed_resource_adapter",
                "exception_type": type(error).__name__,
                "comparison_role": "g6_tracking_only_blocked_timeout_comparator",
                "v2_1_routing_pipeline": False,
                "g6_source_semantics": {
                    "label": "Frozen G6 fixed-resource straight-feedback adapter rerun on matched G7 holdout",
                    "boundary_bootstrap_samples": G6_ADAPTER_BOOTSTRAP_SAMPLES,
                    "controller_max_steps": G6_ADAPTER_MAX_STEPS,
                    "fixed_active_guides": active_count,
                    "not_exact_historical_G6_run": True,
                },
            },
            truth=truth,
            evaluation_config=config,
        )
        metadata = dict(record.metadata)
        metadata["v2_1_routing_pipeline"] = False
        record = replace(record, metadata=metadata)
        if isinstance(g6_boundary, BoundaryEstimateV2):
            media["source_polygon"] = np.asarray(g6_boundary.curve_points, dtype=float).tolist()
            media["source_polygon_semantics"] = "frozen_g6_bootstrap_boundary_curve"
        media["initial_positions"] = initial.tolist()
        media["trajectories"] = [[point.tolist()] for point in initial]
        media["targets"] = []
        media["paths"] = []
        return record, media
    finally:
        if tracemalloc.is_tracing():
            tracemalloc.stop()


def evaluate_g7_method(
    planning: _PreparedCase,
    truth: np.ndarray,
    config: G7EvaluationConfig,
    method: str,
    *,
    config_hash: str,
    branch_sha: str,
    frozen_sha: str,
) -> tuple[G7Record, dict[str, object]]:
    """Evaluate one method while keeping truth outside every planning call."""
    if method == "g6_fixed_resource_rerun":
        return _evaluate_g6_fixed_resource_adapter(
            planning,
            truth,
            config,
            config_hash=config_hash,
            branch_sha=branch_sha,
            frozen_sha=frozen_sha,
        )
    spec = _method_spec(method)
    regime = (
        ResourceRegime.SAME_RESOURCE
        if spec["resource"] == "fixed"
        else ResourceRegime.ADAPTIVE_RESOURCE
    )
    # Route matrices are method-local instrumentation.  Reusing a matrix from
    # an earlier method would make runtime and memory comparisons order-dependent.
    planning.route_cache = {}
    failure_active_count = (
        min(config.fixed_active_guides, config.available_guides)
        if regime == ResourceRegime.SAME_RESOURCE
        else 0
    )
    start = perf_counter()
    tracemalloc.start()
    try:
        if isinstance(planning.boundary, BoundaryEstimateFailure):
            _, peak = tracemalloc.get_traced_memory()
            return _failure_record(
                planning,
                method=method,
                regime=regime,
                active_count=failure_active_count,
                status=planning.boundary.status,
                reason=str(planning.boundary.diagnostics.get("reason", planning.boundary.status)),
                config_hash=config_hash,
                branch_sha=branch_sha,
                frozen_sha=frozen_sha,
                runtime_ms=(perf_counter() - start) * 1000.0,
                peak_memory_bytes=peak,
                diagnostics={"boundary_diagnostics": dict(planning.boundary.diagnostics)},
                truth=truth,
                evaluation_config=config,
            )

        buffer_geometry, free_space, geometry_info = _canonical_geometry(
            planning,
            config,
            str(spec["uncertainty"]),
        )
        if buffer_geometry is None or free_space is None:
            _, peak = tracemalloc.get_traced_memory()
            status = str(geometry_info.get("status", "GEOMETRY_INVALID"))
            return _failure_record(
                planning,
                method=method,
                regime=regime,
                active_count=failure_active_count,
                status=status,
                reason=str(geometry_info.get("reason", status)),
                config_hash=config_hash,
                branch_sha=branch_sha,
                frozen_sha=frozen_sha,
                runtime_ms=(perf_counter() - start) * 1000.0,
                peak_memory_bytes=peak,
                diagnostics=geometry_info,
                truth=truth,
                evaluation_config=config,
            )

        curve, curve_s, length, _, _ = resample_closed_curve_by_arclength(
            buffer_geometry.exterior,
            spacing=config.sample_spacing,
        )
        resource_config = RobustResourceConfig(
            required_arc_gap=config.required_arc_gap,
            m_min=4,
        )
        if spec["resource"] == "fixed":
            active_count = min(config.fixed_active_guides, config.available_guides)
            resource_evidence: dict[str, object] = {
                "status": "FIXED_RESOURCE",
                "nominal_count": int(np.ceil(length / config.required_arc_gap)),
                "robust_count": None,
                "active_count": active_count,
            }
        else:
            nominal_length = length
            if spec["resource"] == "robust":
                nominal_buffer, _, nominal_info = _canonical_geometry(planning, config, "none")
                if nominal_buffer is None:
                    _, peak = tracemalloc.get_traced_memory()
                    return _failure_record(
                        planning,
                        method=method,
                        regime=regime,
                        active_count=failure_active_count,
                        status=str(nominal_info.get("status", "GEOMETRY_INVALID")),
                        reason=str(nominal_info.get("reason", "nominal_geometry_invalid")),
                        config_hash=config_hash,
                        branch_sha=branch_sha,
                        frozen_sha=frozen_sha,
                        runtime_ms=(perf_counter() - start) * 1000.0,
                        peak_memory_bytes=peak,
                        diagnostics={"nominal_geometry": nominal_info, "robust_geometry": geometry_info},
                        truth=truth,
                        evaluation_config=config,
                    )
                _, _, nominal_length, _, _ = resample_closed_curve_by_arclength(
                    nominal_buffer.exterior,
                    spacing=config.sample_spacing,
                )
            decision = allocate_robust_resources(
                nominal_length,
                config.available_guides,
                resource_config,
                uncertainty_mode=("calibrated_tube" if spec["resource"] == "robust" else "none"),
                uncertainty_status=(planning.calibration_status if spec["resource"] == "robust" else None),
                robust_envelope_length=(length if spec["resource"] == "robust" else None),
            )
            active_count = decision.active_count
            resource_evidence = decision.to_dict()
            resource_evidence.update(
                {
                    "nominal_geometry_length": float(nominal_length),
                    "robust_geometry_length": float(length) if spec["resource"] == "robust" else None,
                    "nominal_count": decision.nominal_count,
                    "robust_count": decision.robust_count,
                }
            )
            if decision.status in {"CAPACITY_SHORTFALL", "RESOURCE_UNCERTAIN"}:
                _, peak = tracemalloc.get_traced_memory()
                return _failure_record(
                    planning,
                    method=method,
                    regime=regime,
                    active_count=active_count,
                    status=decision.status,
                    reason=str(decision.diagnostics.get("reason", decision.status)),
                    config_hash=config_hash,
                    branch_sha=branch_sha,
                    frozen_sha=frozen_sha,
                    runtime_ms=(perf_counter() - start) * 1000.0,
                    peak_memory_bytes=peak,
                    diagnostics={"resource": resource_evidence, "geometry": geometry_info},
                    truth=truth,
                    evaluation_config=config,
                )
        guides = planning.initial_guides[:active_count].copy()
        failure_active_count = int(active_count)
        assignment_config = AssignmentConfig(lambda_switch=0.0)
        center = np.asarray(config.room_size, dtype=float) / 2.0
        guide_cycle_order = np.argsort(
            np.arctan2(guides[:, 1] - center[1], guides[:, 0] - center[0]),
            kind="stable",
        )

        def targets_for(sites: np.ndarray) -> np.ndarray:
            return _curve_targets(curve, curve_s, length, sites)

        if spec["phase"] == "zero":
            plan = plan_analytic_equal_arc(length, active_count, phase=0.0)
            phase_evidence: dict[str, object] = {
                "status": plan.status,
                "phase": plan.phase,
                "phase_zero_cost": None,
                "optimized_cost": None,
                "grid_size": 0,
            }
        else:
            def deployment_cost(sites: np.ndarray) -> float | np.ndarray:
                targets = targets_for(sites)
                if spec["route"] == "unchecked_straight":
                    matrix = np.linalg.norm(guides[:, None, :] - targets[None, :, :], axis=2)
                else:
                    matrix = _route_matrix(
                        planning,
                        guides,
                        targets,
                        free_space,
                        str(spec["route"]),
                    ).path_cost_matrix
                if spec["assignment"] != "cyclic":
                    return matrix
                cyclic = assign_cyclic_order_preserving(
                    guides,
                    targets,
                    assignment_config,
                    guide_cycle_order=guide_cycle_order,
                    target_cycle_order=np.arange(len(targets)),
                    pairwise_cost_matrix=matrix,
                )
                if cyclic.status != "VALID" or len(cyclic.unmet_target_ids):
                    return float("inf")
                return float(cyclic.total_cost)

            optimized = optimize_equal_arc_phase(
                length,
                active_count,
                deployment_cost,
                grid_size=config.phase_grid_size,
            )
            if optimized.plan is None:
                _, peak = tracemalloc.get_traced_memory()
                return _failure_record(
                    planning,
                    method=method,
                    regime=regime,
                    active_count=active_count,
                    status="ROUTE_INFEASIBLE",
                    reason="no_phase_has_complete_route_assignment",
                    config_hash=config_hash,
                    branch_sha=branch_sha,
                    frozen_sha=frozen_sha,
                    plan_optimal=False,
                    runtime_ms=(perf_counter() - start) * 1000.0,
                    peak_memory_bytes=peak,
                    diagnostics={"phase": optimized.diagnostics, "resource": resource_evidence},
                    truth=truth,
                    evaluation_config=config,
                )
            plan = optimized.plan
            phase_evidence = {
                "status": optimized.status,
                "phase": plan.phase,
                "phase_zero_cost": optimized.phase_zero_cost,
                "optimized_cost": optimized.optimized_cost,
                "grid_size": config.phase_grid_size,
                "objective": (
                    "cyclic_order_preserving_assignment_total_path_cost"
                    if spec["assignment"] == "cyclic"
                    else "hungarian_assignment_total_path_cost"
                ),
                "evaluation_kind": optimized.diagnostics.get("evaluation_kind"),
            }
        if plan.status != "PLAN_OPTIMAL":
            _, peak = tracemalloc.get_traced_memory()
            return _failure_record(
                planning,
                method=method,
                regime=regime,
                active_count=active_count,
                status=plan.status,
                reason=str(plan.diagnostics.get("reason", plan.status)),
                config_hash=config_hash,
                branch_sha=branch_sha,
                frozen_sha=frozen_sha,
                runtime_ms=(perf_counter() - start) * 1000.0,
                peak_memory_bytes=peak,
                diagnostics={"plan": plan.diagnostics},
                truth=truth,
                evaluation_config=config,
            )
        targets = targets_for(plan.target_s)

        route_matrix: PairwiseRouteMatrix | None = None
        if spec["route"] == "unchecked_straight":
            costs = np.linalg.norm(guides[:, None, :] - targets[None, :, :], axis=2)
        else:
            route_matrix = _route_matrix(
                planning,
                guides,
                targets,
                free_space,
                str(spec["route"]),
            )
            costs = route_matrix.path_cost_matrix
        if spec["assignment"] == "cyclic":
            assignment = assign_cyclic_order_preserving(
                guides,
                targets,
                assignment_config,
                guide_cycle_order=guide_cycle_order,
                target_cycle_order=np.arange(len(targets)),
                pairwise_cost_matrix=costs,
            )
        else:
            assignment = assign_guides_to_targets(
                guides,
                targets,
                assignment_config,
                pairwise_cost_matrix=costs,
            )
        if assignment.status not in {"VALID"} or len(assignment.unmet_target_ids):
            _, peak = tracemalloc.get_traced_memory()
            status = "ROUTE_INFEASIBLE" if assignment.status == "ROUTE_INFEASIBLE" else assignment.status
            return _failure_record(
                planning,
                method=method,
                regime=regime,
                active_count=active_count,
                status=status,
                reason=str(assignment.diagnostics.get("reason", status)),
                config_hash=config_hash,
                branch_sha=branch_sha,
                frozen_sha=frozen_sha,
                plan_optimal=True,
                runtime_ms=(perf_counter() - start) * 1000.0,
                peak_memory_bytes=peak,
                diagnostics={
                    "assignment": assignment.diagnostics,
                    "route_matrix": None if route_matrix is None else route_matrix.to_jsonable(),
                },
                truth=truth,
                evaluation_config=config,
            )

        legacy_clearance_matrix: PairwiseRouteMatrix | None = None
        route_feasible_layer = True
        if spec["route"] == "unchecked_straight":
            # The legacy ablation still follows its Euclidean assignment and
            # direct path, but its ROUTE_FEASIBLE layer is scored read-only
            # against the same canonical free space used by visibility.
            legacy_clearance_matrix = _route_matrix(
                planning,
                guides,
                targets,
                free_space,
                "straight",
            )
            route_feasible_layer = all(
                target_id < 0
                or (
                    legacy_clearance_matrix.paths[guide_id][int(target_id)].status == "ROUTE_FEASIBLE"
                    and legacy_clearance_matrix.paths[guide_id][int(target_id)].certificate is not None
                    and legacy_clearance_matrix.paths[guide_id][int(target_id)].certificate.valid
                )
                for guide_id, target_id in enumerate(assignment.guide_to_target)
            )

        guide_paths: list[np.ndarray | None] = []
        route_certificates: list[dict[str, object] | None] = []
        planned_path_length = 0.0
        for guide_id, target_id in enumerate(assignment.guide_to_target):
            if target_id < 0:
                guide_paths.append(None)
                route_certificates.append(None)
                continue
            if route_matrix is None:
                waypoints = np.vstack((guides[guide_id], targets[target_id]))
                guide_paths.append(waypoints)
                checked = legacy_clearance_matrix.paths[guide_id][int(target_id)]
                route_certificates.append(
                    {
                        **checked.to_jsonable(),
                        "unchecked_legacy_baseline": True,
                        "control_path_uses_direct_segment_despite_failed_precheck": checked.status != "ROUTE_FEASIBLE",
                    }
                )
                planned_path_length += float(np.linalg.norm(np.diff(waypoints, axis=0), axis=1).sum())
            else:
                route = route_matrix.paths[guide_id][int(target_id)]
                if route.status != "ROUTE_FEASIBLE" or route.certificate is None or not route.certificate.valid:
                    _, peak = tracemalloc.get_traced_memory()
                    return _failure_record(
                        planning,
                        method=method,
                        regime=regime,
                        active_count=active_count,
                        status="ROUTE_INFEASIBLE",
                        reason=route.terminal_reason,
                        config_hash=config_hash,
                        branch_sha=branch_sha,
                        frozen_sha=frozen_sha,
                        plan_optimal=True,
                        runtime_ms=(perf_counter() - start) * 1000.0,
                        peak_memory_bytes=peak,
                        diagnostics={"control_called": False, "route": route.to_jsonable()},
                        truth=truth,
                        evaluation_config=config,
                    )
                guide_paths.append(route.waypoints)
                route_certificates.append(route.to_jsonable().get("certificate"))
                planned_path_length += float(route.path_length or 0.0)
        fixed_paths = FixedWaypointPaths.from_guide_paths(
            assignment.guide_to_target,
            guide_paths,
            route_status="ROUTE_FEASIBLE",
            route_mode=str(spec["route"]),
            clearance_margin_m=float(config.safety_distance),
            diagnostics={"geometry_sha256": free_space.geometry_sha256},
        )
        runner = WaypointEpisodeRunner(
            WaypointRunnerConfig(
                dt=config.dt,
                k_p=config.k_p,
                v_max=config.v_max,
                waypoint_tolerance_m=config.waypoint_tolerance,
                final_rmse_tolerance_m=config.tracking_rmse_tolerance,
                speed_tolerance_mps=config.speed_tolerance,
                hold_steps=config.hold_steps,
                max_steps=config.max_steps,
                no_progress_window=config.no_progress_window,
                min_progress_m=config.min_progress,
            )
        )
        safety_callback = None
        identical_problem_replay: list[dict[str, object]] = []
        replay_instrumentation_wall_ms = 0.0
        replay_peak_memory_bytes = 0
        replay_instrumentation_error: dict[str, str] | None = None
        replay_probe_matches_primary_trajectory: bool | None = None
        if spec["safety"] != "disabled":
            crowd_curve = _canonical_safety_points(
                buffer_geometry,
                spacing=max(0.04, config.sample_spacing / 2.0),
            )
            safety_config = VelocitySafetyConfig(
                enabled=True,
                min_guide_distance=config.min_guide_distance,
                min_crowd_distance=float(buffer_geometry.clearance),
                room_margin=config.room_margin,
            )
            projection_config = VelocityProjectionConfig(
                backend=str(spec["safety"]),
                primal_tolerance=config.safety_primal_tolerance,
                kkt_tolerance=config.safety_kkt_tolerance,
                active_tolerance=config.safety_active_tolerance,
                iterate_tolerance=config.safety_iterate_tolerance,
                max_iterations=config.safety_max_iterations,
                zoh_samples=config.zoh_samples,
            )

            def safety_callback(request: object) -> object:
                primary_result = project_velocity_safety_v2(
                    request.positions,
                    request.nominal_control,
                    crowd_curve,
                    np.asarray(config.room_size, dtype=float),
                    request.dt,
                    config.v_max,
                    safety_config,
                    projection_config,
                )
                return primary_result

        episode = runner.run(guides, fixed_paths, safety_callback=safety_callback)
        runtime_ms = (perf_counter() - start) * 1000.0
        _, peak = tracemalloc.get_traced_memory()
        # End the primary measurement before QP replay.  The alternative
        # backend is instrumentation on frozen request copies and must not
        # contaminate primary closed-loop runtime or peak-memory endpoints.
        tracemalloc.stop()
        if method == "visibility_hungarian":
            replay_started = perf_counter()
            tracemalloc.start()
            try:
                def replay_safety_callback(request: object) -> object:
                    primary_result = project_velocity_safety_v2(
                        request.positions,
                        request.nominal_control,
                        crowd_curve,
                        np.asarray(config.room_size, dtype=float),
                        request.dt,
                        config.v_max,
                        safety_config,
                        projection_config,
                    )
                    if int(request.step_index) % config.safety_replay_stride == 0:
                        alternate_result = project_velocity_safety_v2(
                            request.positions,
                            request.nominal_control,
                            crowd_curve,
                            np.asarray(config.room_size, dtype=float),
                            request.dt,
                            config.v_max,
                            safety_config,
                            replace(projection_config, backend="slsqp_convex_qcqp"),
                        )
                        left = primary_result.certificate
                        right = alternate_result.certificate
                        identical_problem_replay.append(
                            {
                                "step_index": int(request.step_index),
                                "capture_rule": f"independent_deterministic_visibility_replay_step_mod_{config.safety_replay_stride}_equals_0",
                                "dykstra_problem_sha256": left.problem_sha256,
                                "qp_problem_sha256": right.problem_sha256,
                                "problem_sha256_match": left.problem_sha256 == right.problem_sha256,
                                "dykstra": {
                                    "status": left.status,
                                    "feasible": left.feasible,
                                    "primal_residual": left.residuals.primal_residual,
                                    "kkt_residual": left.residuals.kkt_residual,
                                    "runtime_ms": left.runtime_ms,
                                    "control_adjustment": left.control_adjustment_norm,
                                    "zoh": None if left.zoh is None else left.zoh.to_dict(),
                                },
                                "qp": {
                                    "status": right.status,
                                    "feasible": right.feasible,
                                    "primal_residual": right.residuals.primal_residual,
                                    "kkt_residual": right.residuals.kkt_residual,
                                    "runtime_ms": right.runtime_ms,
                                    "control_adjustment": right.control_adjustment_norm,
                                    "zoh": None if right.zoh is None else right.zoh.to_dict(),
                                },
                                "applied_control_distance": float(
                                    np.linalg.norm(
                                        primary_result.applied_control
                                        - alternate_result.applied_control
                                    )
                                ),
                            }
                        )
                    return primary_result

                replay_episode = runner.run(
                    guides,
                    fixed_paths,
                    safety_callback=replay_safety_callback,
                )
                replay_probe_matches_primary_trajectory = bool(
                    replay_episode.positions.shape == episode.positions.shape
                    and np.allclose(
                        replay_episode.positions,
                        episode.positions,
                        rtol=0.0,
                        atol=1.0e-12,
                    )
                )
                for item in identical_problem_replay:
                    item["closed_loop_probe_matches_primary"] = (
                        replay_probe_matches_primary_trajectory
                    )
            except Exception as replay_error:
                replay_instrumentation_error = {
                    "exception_type": type(replay_error).__name__,
                    "message": str(replay_error),
                }
                identical_problem_replay = []
            finally:
                replay_instrumentation_wall_ms = (perf_counter() - replay_started) * 1000.0
                _, replay_peak_memory_bytes = tracemalloc.get_traced_memory()
                tracemalloc.stop()
        final_positions = episode.positions[-1]
        truth_coverage, truth_gap = _truth_metrics(final_positions, truth, config)
        truth_criteria = bool(
            truth_coverage >= config.truth_coverage_minimum
            and truth_gap is not None
            and truth_gap <= config.required_arc_gap + 1.0e-9
        )
        clearance = _trajectory_clearance(
            episode.positions,
            buffer_geometry.source_polygon,
            float(buffer_geometry.clearance),
        )
        zoh_certificates: list[Mapping[str, object]] = []
        problem_hashes: list[str] = []
        for item in episode.safety_diagnostics:
            outer = item.get("diagnostics", {})
            certificate = outer.get("certificate", {}) if isinstance(outer, Mapping) else {}
            if isinstance(certificate, Mapping):
                if isinstance(certificate.get("problem_sha256"), str):
                    problem_hashes.append(str(certificate["problem_sha256"]))
                zoh = certificate.get("zoh")
                if isinstance(zoh, Mapping):
                    zoh_certificates.append(zoh)
        all_zoh_safe = bool(zoh_certificates) and all(bool(item.get("safe")) for item in zoh_certificates)
        zoh_all_min = min(
            (float(item["minimum_clearance"]) for item in zoh_certificates),
            default=None,
        )
        zoh_guide_min = min(
            (float(item["minimum_guide_clearance"]) for item in zoh_certificates if item.get("minimum_guide_clearance") is not None),
            default=None,
        )
        zoh_crowd_min = min(
            (float(item["minimum_crowd_clearance"]) for item in zoh_certificates if item.get("minimum_crowd_clearance") is not None),
            default=None,
        )
        zoh_room_min = min(
            (float(item["minimum_room_clearance"]) for item in zoh_certificates),
            default=None,
        )
        minimum_intersample_clearance = (
            clearance if zoh_all_min is None else min(clearance, zoh_all_min)
        )
        sampled_safe = clearance >= -config.geometry_clearance_tolerance
        if spec["safety"] != "disabled":
            sampled_safe = bool(
                sampled_safe
                and all_zoh_safe
                and episode.terminal_status != "SAFETY_INFEASIBLE"
                and all(
                    item.get("feasible", False)
                    and float(item.get("primal_residual", np.inf)) <= config.safety_primal_tolerance
                    and float(item.get("kkt_residual", np.inf)) <= config.safety_kkt_tolerance
                    for item in episode.safety_diagnostics
                )
            )
        outcome = compose_layered_outcome(
            plan_optimal=True,
            route_feasible=route_feasible_layer,
            controller_terminal_state=episode.terminal_status,
            sampled_safe=sampled_safe,
            truth_criteria_met=truth_criteria,
            terminal_reason=episode.terminal_reason,
            failure_reason=_episode_failure_reason(
                route_feasible=route_feasible_layer,
                replan_reason=episode.replan_reason,
            ),
            diagnostics={
                "estimated_criteria": {
                    "analytic_gap": plan.max_arc_gap,
                    "required_gap": config.required_arc_gap,
                },
                "control_called": True,
                "legacy_route_clearance_checked_before_control": route_matrix is not None,
                "control_despite_route_infeasible_for_legacy_ablation": bool(
                    spec["route"] == "unchecked_straight" and not route_feasible_layer
                ),
            },
        )
        actual_path_length = float(
            np.linalg.norm(np.diff(episode.positions, axis=0), axis=2).sum()
        )
        control_energy = float(np.sum(episode.applied_controls**2) * config.dt)
        metrics = DeploymentMetrics(
            truth_coverage=truth_coverage,
            maximum_consecutive_arc_gap=truth_gap,
            tracking_rmse=float(episode.tracking_rmse_history[-1]),
            minimum_intersample_clearance=float(minimum_intersample_clearance),
            active_guide_count=active_count,
            path_length=actual_path_length,
            control_energy=control_energy,
            runtime_ms=runtime_ms,
            peak_memory_bytes=peak,
        )
        safety_summary = {
            "backend": str(spec["safety"]),
            "step_count": len(episode.safety_diagnostics),
            "feasible": sampled_safe,
            "max_primal_residual": max(
                (float(item.get("primal_residual", 0.0)) for item in episode.safety_diagnostics),
                default=0.0,
            ),
            "max_kkt_residual": max(
                (float(item.get("kkt_residual", 0.0)) for item in episode.safety_diagnostics),
                default=0.0,
            ),
            "minimum_clearance": minimum_intersample_clearance,
            "minimum_polygon_segment_margin": clearance,
            "minimum_zoh_all_constraint_margin": zoh_all_min,
            "minimum_zoh_guide_clearance": zoh_guide_min,
            "minimum_zoh_crowd_clearance": zoh_crowd_min,
            "minimum_zoh_room_clearance": zoh_room_min,
            "all_zoh_safe": all_zoh_safe,
            "zoh_certificate_count": len(zoh_certificates),
            "projection_problem_sha256": problem_hashes,
            "geometry_clearance_tolerance": config.geometry_clearance_tolerance,
            "runtime_ms_excluding_replay_instrumentation": runtime_ms,
            "total_instrumented_runtime_ms": runtime_ms + replay_instrumentation_wall_ms,
            "replay_instrumentation_wall_ms": replay_instrumentation_wall_ms,
            "replay_instrumentation_peak_memory_bytes": replay_peak_memory_bytes,
            "peak_memory_includes_replay_instrumentation": False,
            "record_peak_memory_scope": "unmodified_primary_closed_loop_before_independent_full_episode_qp_replay",
            "replay_probe_matches_primary_trajectory": replay_probe_matches_primary_trajectory,
            "replay_instrumentation_error": replay_instrumentation_error,
            "control_adjustment": float(np.linalg.norm(episode.applied_controls - episode.nominal_controls)),
            "limitations": [
                "not_human_safety_certification",
                "not_unconditional_continuous_time_safety_proof",
                "zoh_checks_static_point_constraints; polygon_LineString_clearance_is_posthoc",
            ],
        }
        record = G7Record(
            scenario=planning.scenario,
            method=method,
            seed=planning.seed,
            resource_regime=regime,
            outcome=outcome,
            metrics=metrics,
            config_hash=config_hash,
            base_sha=G6_BASE_SHA,
            branch_sha=branch_sha,
            metadata={
                "case_id": f"{planning.cohort}:{planning.scenario}:{planning.seed}",
                "case_cohort": planning.cohort,
                "resource_cohort": f"{planning.cohort}:{active_count}",
                "initial_layout": planning.initial_layout,
                "frozen_sha": frozen_sha,
                "environment": environment_snapshot(),
                "truth_access": "evaluator_only_after_terminal",
                "observation_hash": _canonical_hash(np.round(planning.observation, 12)),
                "method_spec": spec,
                "comparison_role": (
                    "deprecated_unchecked_straight_hybrid_not_in_formal_matrix"
                    if method == "legacy_unchecked_straight"
                    else "ABCG_v2_1_evaluation_method"
                ),
                "v2_1_routing_pipeline": method != "legacy_unchecked_straight",
                "route_precheck_bypassed_for_legacy_ablation": spec["route"] == "unchecked_straight",
                "control_despite_route_infeasible_for_legacy_ablation": bool(
                    spec["route"] == "unchecked_straight" and not route_feasible_layer
                ),
                "resource": resource_evidence,
                "geometry": geometry_info,
                "plan": {
                    "status": plan.status,
                    "h_star": plan.h_star,
                    "gap": plan.max_arc_gap,
                    "phase": plan.phase,
                    "phase_evidence": phase_evidence,
                },
                "assignment": {
                    "status": assignment.status,
                    "total_cost": assignment.total_cost,
                    "guide_to_target": assignment.guide_to_target.tolist(),
                    "solver": assignment.diagnostics.get("solver"),
                },
                "route": {
                    "method": spec["route"],
                    "planned_path_length": planned_path_length,
                    "clearance_certificates": route_certificates,
                },
                "waypoint": {
                    "path_version": fixed_paths.path_version,
                    "waypoint_index": episode.waypoint_index_history[-1].tolist(),
                    "progress": float(episode.progress_fraction[-1]),
                    "replan_reason": episode.replan_reason,
                    "terminal_reason": episode.terminal_reason,
                },
                "safety_certificate_summary": safety_summary,
                "identical_problem_replay": identical_problem_replay,
                "identical_problem_replay_error": replay_instrumentation_error,
            },
        )
        assigned_targets = targets[np.asarray(assignment.guide_to_target, dtype=int)]
        media = {
            "scenario": planning.scenario,
            "seed": planning.seed,
            "method": method,
            "truth_boundary": truth.tolist(),
            "source_polygon": np.asarray(buffer_geometry.source_polygon.exterior.coords[:-1]).tolist(),
            "targets": assigned_targets.tolist(),
            "initial_positions": guides.tolist(),
            "paths": [None if path is None else path.tolist() for path in guide_paths],
            "trajectories": [episode.positions[:, guide_id, :].tolist() for guide_id in range(active_count)],
            "status": episode.terminal_status,
            "failure_reason": outcome.failure_reason,
            "estimated_deployment_success": outcome.estimated_deployment_success,
            "truth_validated_success": outcome.truth_validated_success,
        }
        return record, media
    except Exception as error:  # keep every unexpected episode in the formal denominator
        _, peak = tracemalloc.get_traced_memory()
        return _failure_record(
            planning,
            method=method,
            regime=regime,
            active_count=failure_active_count,
            status="EVALUATION_ERROR",
            reason=f"{type(error).__name__}: {error}",
            config_hash=config_hash,
            branch_sha=branch_sha,
            frozen_sha=frozen_sha,
            runtime_ms=(perf_counter() - start) * 1000.0,
            peak_memory_bytes=peak,
            diagnostics={"exception_type": type(error).__name__},
            truth=truth,
            evaluation_config=config,
        )
    finally:
        if tracemalloc.is_tracing():
            tracemalloc.stop()


def evaluation_cases(
    config: G7EvaluationConfig,
    phase: str,
) -> list[dict[str, object]]:
    if phase == "pilot":
        return [
            {
                "scenario": scenario,
                "seed": seed,
                "cohort": "pilot",
                "forced_layout": None,
            }
            for scenario in config.blocked_scenarios
            for seed in config.pilot_seeds
        ]
    if phase != "holdout":
        raise ValueError("deployment cases exist only for pilot or holdout")
    general = [
        {
            "scenario": scenario,
            "seed": seed,
            "cohort": "general",
            "forced_layout": None,
        }
        for scenario in config.scenarios
        for seed in config.holdout_general_seeds
    ]
    blocked = [
        {
            "scenario": scenario,
            "seed": seed,
            "cohort": "blocked_supplement",
            "forced_layout": "one_sided",
        }
        for scenario in config.blocked_scenarios
        for seed in config.holdout_blocked_seeds
    ]
    return general + blocked


def evaluation_methods(phase: str, *, quick: bool) -> tuple[str, ...]:
    if phase == "pilot":
        return BLOCKED_COMPARATOR_METHODS + ("visibility_hungarian",)
    if phase != "holdout":
        raise ValueError("deployment methods exist only for pilot or holdout")
    if quick:
        return PRIMARY_METHODS + BLOCKED_COMPARATOR_METHODS + ADAPTIVE_METHODS
    return PRIMARY_METHODS + BLOCKED_COMPARATOR_METHODS + OFAT_METHODS + ADAPTIVE_METHODS


def _record_dict(record: G7Record) -> dict[str, object]:
    value = record.to_dict()
    value.update(
        {
            "terminal_status": _failure_status(record),
            "controller_terminal_state": record.outcome.controller_terminal_state,
            "terminal_reason": record.outcome.terminal_reason,
            "failure_reason": record.outcome.failure_reason,
            "PLAN_OPTIMAL": record.outcome.plan_optimal,
            "ROUTE_FEASIBLE": record.outcome.route_feasible,
            "TRACK_CONVERGED": record.outcome.track_converged,
            "SAMPLED_SAFE": record.outcome.sampled_safe,
            "ESTIMATED_DEPLOYMENT_SUCCESS": record.outcome.estimated_deployment_success,
            "TRUTH_VALIDATED_SUCCESS": record.outcome.truth_validated_success,
            "plan_optimal": record.outcome.plan_optimal,
            "route_feasible": record.outcome.route_feasible,
            "track_converged": record.outcome.track_converged,
            "sampled_safe": record.outcome.sampled_safe,
            "estimated_deployment_success": record.outcome.estimated_deployment_success,
            "truth_validated_success": record.outcome.truth_validated_success,
            "v2_1_routing_pipeline": record.method != "g6_fixed_resource_rerun",
        }
    )
    return value


def _deterministic_record_projection(row: Mapping[str, object]) -> dict[str, object]:
    """Remove explicitly nondeterministic performance fields for repro checks."""

    value = json.loads(json.dumps(_strict_jsonable(row), allow_nan=False))

    def scrub(item: object) -> object:
        if isinstance(item, dict):
            result: dict[str, object] = {}
            for raw_key, raw_value in item.items():
                key = str(raw_key)
                normalized = key.lower()
                if (
                    "runtime" in normalized
                    or "peak_memory" in normalized
                    or normalized in {
                        "actual_case_workers",
                        "case_process_thread_environment",
                        "execution_mode",
                        "worker_numeric_thread_limit",
                        "worker_start_method",
                    }
                ):
                    result[key] = None
                else:
                    result[key] = scrub(raw_value)
            return result
        if isinstance(item, list):
            return [scrub(value) for value in item]
        return item

    projected = scrub(value)
    assert isinstance(projected, dict)
    return projected


def _distribution(values: Sequence[float | None], *, direction: str) -> dict[str, object]:
    present = np.asarray([float(value) for value in values if value is not None], dtype=float)
    missing = len(values) - len(present)
    if not len(present):
        return {
            "n_total": len(values), "n_observed": 0, "n_missing": missing,
            "median": None, "worst_5_percent_mean": None,
            "analysis_population": "observed_records_only_descriptive",
        }
    tail_count = max(1, int(np.ceil(0.05 * len(present))))
    ordered = np.sort(present)
    tail = ordered[:tail_count] if direction == "higher" else ordered[-tail_count:]
    return {
        "n_total": len(values),
        "n_observed": len(present),
        "n_missing": missing,
        "mean": float(np.mean(present)),
        "median": float(np.median(present)),
        "worst_5_percent_mean": float(np.mean(tail)),
        "analysis_population": "observed_records_only_descriptive",
        "primary_inference_permitted": missing == 0,
    }


def aggregate_records(records: Sequence[G7Record]) -> dict[str, object]:
    result: dict[str, object] = {}
    keys = sorted({(record.scenario, record.method, str(record.resource_regime)) for record in records})
    for scenario, method, regime in keys:
        selected = [
            record for record in records
            if record.scenario == scenario and record.method == method and str(record.resource_regime) == regime
        ]
        estimated = sum(record.outcome.estimated_deployment_success for record in selected)
        truth = sum(record.outcome.truth_validated_success for record in selected)
        blocked = [
            record for record in selected
            if record.metadata.get("case_cohort") == "blocked_supplement"
            and record.metadata.get("initial_layout") == "one_sided"
        ]
        resources = [
            record.metadata.get("resource", {})
            if isinstance(record.metadata.get("resource", {}), Mapping)
            else {}
            for record in selected
        ]
        resource_status_counts: dict[str, int] = {}
        for record, resource in zip(selected, resources, strict=True):
            status = str(resource.get("status") or _failure_status(record))
            resource_status_counts[status] = resource_status_counts.get(status, 0) + 1
        item = {
            "scenario": scenario,
            "method": method,
            "resource_regime": regime,
            "record_count": len(selected),
            "estimated_success_count": estimated,
            "estimated_success_rate": estimated / len(selected) if selected else None,
            "truth_success_count": truth,
            "truth_success_rate": truth / len(selected) if selected else None,
            "blocked_route_timeout_count": sum(
                record.outcome.controller_terminal_state == "TIMEOUT" for record in blocked
            ),
            "blocked_route_timeout_denominator": len(blocked),
            "blocked_route_timeout_rate": (
                sum(record.outcome.controller_terminal_state == "TIMEOUT" for record in blocked) / len(blocked)
                if blocked else None
            ),
            "truth_coverage": _distribution(
                [record.metrics.truth_coverage for record in selected], direction="higher"
            ),
            "maximum_consecutive_arc_gap": _distribution(
                [record.metrics.maximum_consecutive_arc_gap for record in selected], direction="lower"
            ),
            "tracking_rmse": _distribution(
                [record.metrics.tracking_rmse for record in selected], direction="lower"
            ),
            "minimum_intersample_clearance": _distribution(
                [record.metrics.minimum_intersample_clearance for record in selected], direction="higher"
            ),
            "active_guide_count": _distribution(
                [float(record.metrics.active_guide_count) for record in selected], direction="lower"
            ),
            "nominal_resource_count": _distribution(
                [
                    None if resource.get("nominal_count") is None
                    else float(resource["nominal_count"])
                    for resource in resources
                ],
                direction="lower",
            ),
            "robust_resource_count": _distribution(
                [
                    None if resource.get("robust_count") is None
                    else float(resource["robust_count"])
                    for resource in resources
                ],
                direction="lower",
            ),
            "resource_status_composition": {
                "denominator": len(selected),
                "counts": dict(sorted(resource_status_counts.items())),
                "rates": {
                    status: count / len(selected) if selected else None
                    for status, count in sorted(resource_status_counts.items())
                },
                "tracked_failure_states": [
                    "RESOURCE_UNCERTAIN",
                    "HYSTERESIS_GAP_DEGRADED",
                    "CAPACITY_SHORTFALL",
                ],
            },
            "path_length": _distribution(
                [record.metrics.path_length for record in selected], direction="lower"
            ),
            "control_energy": _distribution(
                [record.metrics.control_energy for record in selected], direction="lower"
            ),
            "runtime": runtime_percentiles([record.metrics.runtime_ms for record in selected]),
            "peak_memory": _distribution(
                [None if record.metrics.peak_memory_bytes is None else float(record.metrics.peak_memory_bytes) for record in selected],
                direction="lower",
            ),
            "failure_composition": failure_rate_composition(record.outcome for record in selected),
        }
        result[f"{scenario}|{method}|{regime}"] = item
    return {"schema": "abcg-v2.1-g7-aggregate-v1", "groups": result}


def _pair_id(record: G7Record) -> str:
    return str(record.metadata.get("case_id"))


def _paired_statistics(records: Sequence[G7Record], config: G7EvaluationConfig) -> dict[str, object]:
    pairs = matched_same_resource_pairs(
        records,
        baseline_method="straight_hungarian",
        candidate_method="visibility_hungarian",
    )
    ids = [_pair_id(left) for left, _ in pairs]
    estimated = paired_binary_summary(
        ids,
        [left.outcome.estimated_deployment_success for left, _ in pairs],
        [right.outcome.estimated_deployment_success for _, right in pairs],
        direction="higher_is_better",
        event_name="ESTIMATED_DEPLOYMENT_SUCCESS",
        seed=71,
        resamples=config.bootstrap_resamples,
    )
    truth = paired_binary_summary(
        ids,
        [left.outcome.truth_validated_success for left, _ in pairs],
        [right.outcome.truth_validated_success for _, right in pairs],
        direction="higher_is_better",
        event_name="TRUTH_VALIDATED_SUCCESS",
        seed=73,
        resamples=config.bootstrap_resamples,
    )
    g6_blocked_comparator_pairs = matched_same_resource_pairs(
        records,
        baseline_method="g6_fixed_resource_rerun",
        candidate_method="visibility_hungarian",
    )
    blocked_pairs = [
        (left, right) for left, right in g6_blocked_comparator_pairs
        if left.metadata.get("case_cohort") == "blocked_supplement"
        and left.scenario in config.blocked_scenarios
        and left.metadata.get("initial_layout") == "one_sided"
    ]
    blocked_timeout = paired_binary_summary(
        [_pair_id(left) for left, _ in blocked_pairs],
        [left.outcome.controller_terminal_state == "TIMEOUT" for left, _ in blocked_pairs],
        [right.outcome.controller_terminal_state == "TIMEOUT" for _, right in blocked_pairs],
        direction="lower_is_better",
        event_name="one_sided_u_c_blocked_route_TIMEOUT",
        seed=79,
        resamples=config.bootstrap_resamples,
    )
    continuous: dict[str, object] = {}
    for name, direction, getter, seed in (
        ("truth_coverage", "higher_is_better", lambda value: value.metrics.truth_coverage, 83),
        ("maximum_consecutive_arc_gap", "lower_is_better", lambda value: value.metrics.maximum_consecutive_arc_gap, 89),
        ("tracking_rmse", "lower_is_better", lambda value: value.metrics.tracking_rmse, 97),
        ("minimum_intersample_clearance", "higher_is_better", lambda value: value.metrics.minimum_intersample_clearance, 101),
        ("path_length", "lower_is_better", lambda value: value.metrics.path_length, 103),
        ("control_energy", "lower_is_better", lambda value: value.metrics.control_energy, 107),
        ("runtime_ms", "lower_is_better", lambda value: value.metrics.runtime_ms, 109),
        ("active_guide_count", "lower_is_better", lambda value: float(value.metrics.active_guide_count), 113),
        (
            "peak_memory_bytes",
            "lower_is_better",
            lambda value: None if value.metrics.peak_memory_bytes is None else float(value.metrics.peak_memory_bytes),
            127,
        ),
    ):
        continuous[name] = paired_continuous_summary(
            ids,
            [getter(left) for left, _ in pairs],
            [getter(right) for _, right in pairs],
            direction=direction,
            seed=seed,
            resamples=config.bootstrap_resamples,
        )
    primary = {
        "estimated_success": estimated,
        "truth_success": truth,
        "blocked_timeout": blocked_timeout,
    }
    p_values: dict[str, float] = {}
    protocol_failures: list[str] = []
    for name, summary in primary.items():
        p_value = summary["one_sided_test"]["p_value"]
        if p_value is None or summary["one_sided_test"].get("status") != "OK":
            # Keep the preregistered family intact.  A conservative p=1 is an
            # explicit protocol failure, never a silently removed hypothesis.
            p_values[name] = 1.0
            protocol_failures.append(f"primary_hypothesis_insufficient_data:{name}")
        else:
            p_values[name] = float(p_value)
    holm = holm_adjustment(p_values)
    ofat: dict[str, object] = {}
    endpoint_specs = (
        ("truth_coverage", "higher_is_better", lambda value: value.metrics.truth_coverage),
        ("maximum_consecutive_arc_gap", "lower_is_better", lambda value: value.metrics.maximum_consecutive_arc_gap),
        ("tracking_rmse", "lower_is_better", lambda value: value.metrics.tracking_rmse),
        ("minimum_intersample_clearance", "higher_is_better", lambda value: value.metrics.minimum_intersample_clearance),
        ("path_length", "lower_is_better", lambda value: value.metrics.path_length),
        ("control_energy", "lower_is_better", lambda value: value.metrics.control_energy),
        ("runtime_ms", "lower_is_better", lambda value: value.metrics.runtime_ms),
        ("active_guide_count", "lower_is_better", lambda value: float(value.metrics.active_guide_count)),
        (
            "peak_memory_bytes",
            "lower_is_better",
            lambda value: None if value.metrics.peak_memory_bytes is None else float(value.metrics.peak_memory_bytes),
        ),
    )
    dimensions = {
        "straight_hungarian": "route:straight_vs_visibility_graph",
        "boundary_corridor_hungarian": "route:boundary_corridor_vs_visibility_graph",
        "visibility_cyclic": "assignment:cyclic_vs_hungarian",
        "visibility_phase0": "phase:zero_vs_optimized",
        "visibility_uncertainty_none": "uncertainty:none_vs_stability_heuristic",
        "visibility_uncertainty_calibrated": "uncertainty:calibrated_tube_vs_stability_heuristic",
        "visibility_qp": "safety:qp_vs_dykstra_closed_loop_ablation",
    }
    for method_index, method in enumerate(OFAT_METHODS):
        if not any(record.method == method for record in records):
            continue
        ablation_pairs = matched_same_resource_pairs(
            records,
            baseline_method="visibility_hungarian",
            candidate_method=method,
        )
        ablation_ids = [_pair_id(left) for left, _ in ablation_pairs]
        binary = {
            "estimated_success": paired_binary_summary(
                ablation_ids,
                [left.outcome.estimated_deployment_success for left, _ in ablation_pairs],
                [right.outcome.estimated_deployment_success for _, right in ablation_pairs],
                direction="higher_is_better",
                event_name="ESTIMATED_DEPLOYMENT_SUCCESS",
                seed=401 + 31 * method_index,
                resamples=config.bootstrap_resamples,
            ),
            "truth_success": paired_binary_summary(
                ablation_ids,
                [left.outcome.truth_validated_success for left, _ in ablation_pairs],
                [right.outcome.truth_validated_success for _, right in ablation_pairs],
                direction="higher_is_better",
                event_name="TRUTH_VALIDATED_SUCCESS",
                seed=409 + 31 * method_index,
                resamples=config.bootstrap_resamples,
            ),
            "controller_timeout": paired_binary_summary(
                ablation_ids,
                [left.outcome.controller_terminal_state == "TIMEOUT" for left, _ in ablation_pairs],
                [right.outcome.controller_terminal_state == "TIMEOUT" for _, right in ablation_pairs],
                direction="lower_is_better",
                event_name="CONTROLLER_TIMEOUT",
                seed=419 + 31 * method_index,
                resamples=config.bootstrap_resamples,
            ),
        }
        ablation_continuous: dict[str, object] = {}
        for endpoint_index, (name, direction, getter) in enumerate(endpoint_specs):
            ablation_continuous[name] = paired_continuous_summary(
                ablation_ids,
                [getter(left) for left, _ in ablation_pairs],
                [getter(right) for _, right in ablation_pairs],
                direction=direction,
                seed=431 + 31 * method_index + endpoint_index,
                resamples=config.bootstrap_resamples,
            )
        ofat[method] = {
            "reference_method": "visibility_hungarian",
            "candidate_method": method,
            "ablation_dimension": dimensions[method],
            "difference_definition": "candidate_ablation_minus_visibility_hungarian",
            "pair_count": len(ablation_pairs),
            "binary": binary,
            "continuous": ablation_continuous,
        }
    return {
        "schema": "abcg-v2.1-g7-paired-statistics-v1",
        "baseline_method": "straight_hungarian",
        "candidate_method": "visibility_hungarian",
        "pair_count": len(pairs),
        "deployment_pair_count": len(pairs),
        "blocked_timeout_baseline_method": "g6_fixed_resource_rerun",
        "blocked_timeout_pair_count": len(blocked_pairs),
        "blocked_timeout_pair_ids": [_pair_id(left) for left, _ in blocked_pairs],
        "binary_all_failures_retained": True,
        "primary_binary": primary,
        "holm": holm,
        "protocol_failures": protocol_failures,
        "continuous": continuous,
        "ofat_ablations": ofat,
    }


def _replay_backend_sampled_safe(
    item: Mapping[str, object],
    backend: str,
    config: G7EvaluationConfig,
) -> bool:
    """Apply the frozen sampled-safety predicate to one identical replay result."""

    certificate = item.get(backend)
    if not isinstance(certificate, Mapping):
        return False
    zoh = certificate.get("zoh")
    if not isinstance(zoh, Mapping):
        return False
    try:
        primal = float(certificate.get("primal_residual", np.inf))
        kkt = float(certificate.get("kkt_residual", np.inf))
        clearance = float(zoh.get("minimum_clearance", -np.inf))
    except (TypeError, ValueError):
        return False
    return bool(
        certificate.get("feasible", False)
        and np.isfinite(primal)
        and primal <= config.safety_primal_tolerance
        and np.isfinite(kkt)
        and kkt <= config.safety_kkt_tolerance
        and zoh.get("safe", False)
        and np.isfinite(clearance)
        and clearance >= -config.geometry_clearance_tolerance
    )


def _identical_replay_rows(records: Sequence[G7Record]) -> list[tuple[str, Mapping[str, object]]]:
    rows: list[tuple[str, Mapping[str, object]]] = []
    for record in records:
        if record.method != "visibility_hungarian":
            continue
        replay = record.metadata.get("identical_problem_replay", ())
        if not isinstance(replay, Sequence) or isinstance(replay, (str, bytes)):
            continue
        for ordinal, item in enumerate(replay):
            if not isinstance(item, Mapping):
                continue
            pair_id = ":".join(
                (
                    _pair_id(record),
                    str(record.resource_regime),
                    str(item.get("step_index", ordinal)),
                    str(ordinal),
                )
            )
            rows.append((pair_id, item))
    return rows


def _identical_replay_cases(records: Sequence[G7Record]) -> list[dict[str, object]]:
    """Group backend replays at the frozen episode/case pairing unit.

    Snapshot rows are instrumentation within an episode, not independent
    experimental units.  A backend passes one case only when every captured
    snapshot passes the sampled-safety predicate.  Missing or malformed
    replay payloads remain explicit incomplete cases.
    """

    cases: list[dict[str, object]] = []
    primary = sorted(
        (
            record for record in records
            if record.method == "visibility_hungarian"
            and record.resource_regime == ResourceRegime.SAME_RESOURCE
        ),
        key=lambda record: (_pair_id(record), record.scenario, record.seed),
    )
    for record in primary:
        control_called = bool(
            record.outcome.diagnostics.get("control_called", False)
            if isinstance(record.outcome.diagnostics, Mapping)
            else False
        )
        if not control_called:
            cases.append(
                {
                    "case_id": f"{_pair_id(record)}:{record.resource_regime}",
                    "scenario": record.scenario,
                    "seed": record.seed,
                    "eligible": False,
                    "noneligible_reason": "precontrol_terminal_no_projection_problem",
                    "snapshot_count": 0,
                    "snapshot_contract_complete": False,
                    "all_problem_sha256_match": False,
                    "snapshots": [],
                }
            )
            continue
        raw = record.metadata.get("identical_problem_replay", ())
        snapshots = (
            [item for item in raw if isinstance(item, Mapping)]
            if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes))
            else []
        )
        snapshot_contract_complete = bool(snapshots) and all(
            isinstance(item.get("dykstra"), Mapping)
            and isinstance(item.get("qp"), Mapping)
            and isinstance(item["dykstra"].get("zoh"), Mapping)
            and isinstance(item["qp"].get("zoh"), Mapping)
            and item.get("closed_loop_probe_matches_primary") is True
            for item in snapshots
        )
        cases.append(
            {
                "case_id": f"{_pair_id(record)}:{record.resource_regime}",
                "scenario": record.scenario,
                "seed": record.seed,
                "eligible": True,
                "noneligible_reason": None,
                "snapshot_count": len(snapshots),
                "snapshot_contract_complete": snapshot_contract_complete,
                "all_problem_sha256_match": bool(snapshots) and all(
                    bool(item.get("problem_sha256_match")) for item in snapshots
                ),
                "snapshots": snapshots,
            }
        )
    return cases


def _noninferiority(records: Sequence[G7Record], config: G7EvaluationConfig) -> dict[str, object]:
    results: dict[str, object] = {}
    primary_pairs = matched_same_resource_pairs(
        records,
        baseline_method="straight_hungarian",
        candidate_method="visibility_hungarian",
    )
    for scenario in ("circle", "ellipse"):
        selected = [(left, right) for left, right in primary_pairs if left.scenario == scenario]
        summary = paired_binary_summary(
            [_pair_id(left) for left, _ in selected],
            [left.outcome.estimated_deployment_success for left, _ in selected],
            [right.outcome.estimated_deployment_success for _, right in selected],
            event_name="ESTIMATED_DEPLOYMENT_SUCCESS",
            direction="higher_is_better",
            seed=211 + len(results),
            resamples=config.bootstrap_resamples,
        )
        if summary["bootstrap"]["status"] != "OK":
            decision: dict[str, object] = {"noninferior": False, "status": "NOT_EVALUABLE_NO_PAIRS"}
        else:
            decision = evaluate_noninferiority(
                summary["bootstrap"],
                NoninferioritySpec(
                    margin_magnitude=config.noninferiority_margin_magnitude,
                    direction="higher_is_better",
                ),
                all_pairs_complete=bool(summary["all_pairs_complete"]),
            )
        results[f"{scenario}_estimated_success"] = {"summary": summary, "decision": decision}

    replay_cases = _identical_replay_cases(records)
    eligible_cases = [item for item in replay_cases if bool(item["eligible"])]
    complete_cases = [
        item for item in eligible_cases if bool(item["snapshot_contract_complete"])
    ]
    case_coverage_complete = bool(eligible_cases) and len(complete_cases) == len(eligible_cases)
    all_problem_sha256_match = bool(complete_cases) and all(
        bool(item["all_problem_sha256_match"]) for item in complete_cases
    )
    backend_summary = paired_binary_summary(
        [str(item["case_id"]) for item in complete_cases],
        [
            all(_replay_backend_sampled_safe(snapshot, "dykstra", config) for snapshot in item["snapshots"])
            for item in complete_cases
        ],
        [
            all(_replay_backend_sampled_safe(snapshot, "qp", config) for snapshot in item["snapshots"])
            for item in complete_cases
        ],
        event_name="CASE_LEVEL_ALL_CAPTURED_SNAPSHOTS_SAMPLED_SAFE",
        direction="higher_is_better",
        seed=223,
        resamples=config.bootstrap_resamples,
    )
    if not case_coverage_complete:
        backend_decision: dict[str, object] = {
            "noninferior": False,
            "status": "NOT_EVALUABLE_REPLAY_CASE_COVERAGE_INCOMPLETE",
        }
    elif len(complete_cases) < MIN_BACKEND_REPLAY_CASES:
        backend_decision = {
            "noninferior": False,
            "status": "NOT_EVALUABLE_INSUFFICIENT_CASES",
        }
    elif not all_problem_sha256_match:
        backend_decision = {
            "noninferior": False,
            "status": "NOT_EVALUABLE_IDENTICAL_PROBLEM_CONTRACT_FAILED",
        }
    elif backend_summary["bootstrap"]["status"] != "OK":
        backend_decision = {"noninferior": False, "status": "NOT_EVALUABLE_NO_PAIRS"}
    else:
        backend_decision = evaluate_noninferiority(
            backend_summary["bootstrap"],
            NoninferioritySpec(
                margin_magnitude=config.noninferiority_margin_magnitude,
                direction="higher_is_better",
            ),
            all_pairs_complete=bool(backend_summary["all_pairs_complete"]),
        )
    results["qp_vs_dykstra_identical_problem_sampled_safe"] = {
        "identical_problem_snapshot_replay": True,
        "paired_unit": "episode_case_all_captured_snapshots_must_pass",
        "total_primary_case_count": len(replay_cases),
        "noneligible_precontrol_case_count": len(replay_cases) - len(eligible_cases),
        "eligible_case_count": len(eligible_cases),
        "complete_case_count": len(complete_cases),
        "missing_case_count": len(eligible_cases) - len(complete_cases),
        "case_coverage_complete": case_coverage_complete,
        "minimum_complete_case_count": MIN_BACKEND_REPLAY_CASES,
        "all_problem_sha256_match": all_problem_sha256_match,
        "closed_loop_outcomes_not_used_for_backend_noninferiority": True,
        "summary": backend_summary,
        "decision": backend_decision,
    }
    return {
        "schema": "abcg-v2.1-g7-noninferiority-v1",
        "margin_magnitude": config.noninferiority_margin_magnitude,
        "candidate_minus_baseline_decision_threshold": -config.noninferiority_margin_magnitude,
        "results": results,
    }


def _failure_status(record: G7Record) -> str:
    if record.outcome.truth_validated_success:
        return "TRUTH_VALIDATED_SUCCESS"
    if record.outcome.estimated_deployment_success:
        return "ESTIMATED_DEPLOYMENT_SUCCESS_ONLY"
    raw = str(
        record.outcome.failure_reason
        or record.outcome.controller_terminal_state
        or "UNSPECIFIED_FAILURE"
    ).upper()
    return raw


def _failure_composition_records(records: Sequence[G7Record]) -> dict[str, object]:
    counts: dict[str, int] = {}
    for record in records:
        key = _failure_status(record)
        counts[key] = counts.get(key, 0) + 1
    total = len(records)
    estimated_count = sum(record.outcome.estimated_deployment_success for record in records)
    truth_count = sum(record.outcome.truth_validated_success for record in records)
    return {
        "denominator": total,
        "total": total,
        "n_total": len(records),
        "counts": dict(sorted(counts.items())),
        "rates": {
            status: (count / total if total else None)
            for status, count in sorted(counts.items())
        },
        "estimated_deployment_success_count": estimated_count,
        "estimated_deployment_success_rate": estimated_count / total if total else None,
        "truth_validated_success_count": truth_count,
        "truth_validated_success_rate": truth_count / total if total else None,
        "all_records_accounted_for": sum(counts.values()) == len(records),
    }


def _v2_1_records(records: Sequence[G7Record]) -> list[G7Record]:
    return [record for record in records if record.method != "g6_fixed_resource_rerun"]


def _g6_tracking_comparator(records: Sequence[G7Record]) -> dict[str, object]:
    selected = [record for record in records if record.method == "g6_fixed_resource_rerun"]
    blocked = [
        record for record in selected
        if record.metadata.get("case_cohort") == "blocked_supplement"
        and record.metadata.get("initial_layout") == "one_sided"
    ]

    def composition(values: Sequence[G7Record]) -> tuple[dict[str, int], dict[str, float | None]]:
        counts: dict[str, int] = {}
        for record in values:
            terminal = str(record.outcome.controller_terminal_state)
            counts[terminal] = counts.get(terminal, 0) + 1
        denominator = len(values)
        rates = {
            key: (count / denominator if denominator else None)
            for key, count in sorted(counts.items())
        }
        return dict(sorted(counts.items())), rates

    counts, rates = composition(selected)
    blocked_counts, blocked_rates = composition(blocked)
    blocked_timeout_count = sum(
        record.outcome.controller_terminal_state == "TIMEOUT" for record in blocked
    )
    return {
        "schema": "abcg-v2.1-g7-g6-tracking-comparator-v1",
        "label": "Frozen G6 fixed-resource straight-feedback adapter rerun on matched G7 holdout",
        "scope": "controller_tracking_terminal_comparator_only",
        "excluded_from_v2_1_deployment_success_and_failure_composition": True,
        "record_count": len(selected),
        "blocked_record_count": len(blocked),
        "controller_terminal_counts": counts,
        "controller_terminal_rates": rates,
        "blocked_controller_terminal_counts": blocked_counts,
        "blocked_controller_terminal_rates": blocked_rates,
        "blocked_timeout_count": blocked_timeout_count,
        "blocked_timeout_rate": blocked_timeout_count / len(blocked) if blocked else None,
        "all_records_accounted_for": sum(counts.values()) == len(selected),
        "all_blocked_records_accounted_for": sum(blocked_counts.values()) == len(blocked),
        "semantics": (
            "old controller CONVERGED means tracking only; no G6 adapter record is counted as "
            "ABCG-v2.1 ESTIMATED_DEPLOYMENT_SUCCESS or TRUTH_VALIDATED_SUCCESS"
        ),
    }


def _resource_pareto(records: Sequence[G7Record]) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    adaptive = [record for record in records if record.resource_regime == ResourceRegime.ADAPTIVE_RESOURCE]
    for scenario in sorted({record.scenario for record in adaptive}):
        for method in sorted({record.method for record in adaptive if record.scenario == scenario}):
            for active in sorted({
                record.metrics.active_guide_count
                for record in adaptive
                if record.scenario == scenario and record.method == method
            }):
                selected = [
                    record for record in adaptive
                    if record.scenario == scenario
                    and record.method == method
                    and record.metrics.active_guide_count == active
                ]
                resources = [
                    record.metadata.get("resource", {})
                    if isinstance(record.metadata.get("resource", {}), Mapping)
                    else {}
                    for record in selected
                ]
                def median(name: str) -> float | None:
                    values = [getattr(record.metrics, name) for record in selected]
                    finite = [float(value) for value in values if value is not None]
                    return float(np.median(finite)) if finite else None
                def resource_median(name: str) -> float | None:
                    values = [resource.get(name) for resource in resources]
                    finite = [float(value) for value in values if value is not None]
                    return float(np.median(finite)) if finite else None
                resource_status_counts: dict[str, int] = {}
                for record, resource in zip(selected, resources, strict=True):
                    status = str(resource.get("status") or _failure_status(record))
                    resource_status_counts[status] = resource_status_counts.get(status, 0) + 1
                rows.append(
                    {
                        "scenario": scenario,
                        "method": method,
                        "resource_regime": "adaptive_resource",
                        "aggregation": "median_by_scenario_method_active_count",
                        "denominator": len(selected),
                        "active_guide_count": active,
                        "nominal_resource_count": resource_median("nominal_count"),
                        "robust_resource_count": resource_median("robust_count"),
                        "resource_status_counts": dict(sorted(resource_status_counts.items())),
                        "truth_coverage": median("truth_coverage"),
                        "maximum_consecutive_arc_gap": median("maximum_consecutive_arc_gap"),
                        "path_length": median("path_length"),
                        "runtime_ms": median("runtime_ms"),
                        "failure_count": sum(not record.outcome.estimated_deployment_success for record in selected),
                    }
                )
    # Null-valued failed points remain visible but cannot be called Pareto-optimal.
    for row in rows:
        comparable = all(
            row[key] is not None
            for key in ("truth_coverage", "maximum_consecutive_arc_gap", "path_length", "runtime_ms")
        )
        dominated = False
        if comparable:
            for other in rows:
                if other is row or other["scenario"] != row["scenario"] or not all(
                    other[key] is not None
                    for key in ("truth_coverage", "maximum_consecutive_arc_gap", "path_length", "runtime_ms")
                ):
                    continue
                no_worse = bool(
                    int(other["active_guide_count"]) <= int(row["active_guide_count"])
                    and float(other["truth_coverage"]) >= float(row["truth_coverage"])
                    and float(other["maximum_consecutive_arc_gap"]) <= float(row["maximum_consecutive_arc_gap"])
                    and float(other["path_length"]) <= float(row["path_length"])
                    and float(other["runtime_ms"]) <= float(row["runtime_ms"])
                )
                strictly = bool(
                    int(other["active_guide_count"]) < int(row["active_guide_count"])
                    or float(other["truth_coverage"]) > float(row["truth_coverage"])
                    or float(other["maximum_consecutive_arc_gap"]) < float(row["maximum_consecutive_arc_gap"])
                    or float(other["path_length"]) < float(row["path_length"])
                    or float(other["runtime_ms"]) < float(row["runtime_ms"])
                )
                if no_worse and strictly:
                    dominated = True
                    break
        row["pareto_nondominated"] = comparable and not dominated
        row["pareto_status"] = "COMPARABLE" if comparable else "MISSING_ENDPOINTS_NOT_COMPARABLE"
    return {"schema": "abcg-v2.1-g7-resource-pareto-v1", "points": rows}


def _safety_comparison(records: Sequence[G7Record]) -> dict[str, object]:
    methods = ("visibility_hungarian", "visibility_qp")
    output: dict[str, object] = {}
    for method in methods:
        selected = [record for record in records if record.method == method]
        summaries = [record.metadata.get("safety_certificate_summary", {}) for record in selected]
        output[method] = {
            "record_count": len(selected),
            "backend": "dykstra" if method == "visibility_hungarian" else "slsqp_convex_qcqp",
            "feasible_count": sum(bool(summary.get("feasible")) for summary in summaries),
            "primal_residual": _distribution(
                [float(summary["max_primal_residual"]) if "max_primal_residual" in summary else None for summary in summaries],
                direction="lower",
            ),
            "kkt_residual": _distribution(
                [float(summary["max_kkt_residual"]) if "max_kkt_residual" in summary else None for summary in summaries],
                direction="lower",
            ),
            "minimum_clearance": _distribution(
                [float(summary["minimum_clearance"]) if "minimum_clearance" in summary else None for summary in summaries],
                direction="higher",
            ),
            "runtime": runtime_percentiles([record.metrics.runtime_ms for record in selected]),
            "control_adjustment": _distribution(
                [float(summary["control_adjustment"]) if "control_adjustment" in summary else None for summary in summaries],
                direction="lower",
            ),
            "same_formulation_and_configuration": True,
            "identical_instances": False,
        }
    replay = [item for _, item in _identical_replay_rows(records)]
    replay_cases = _identical_replay_cases(records)
    eligible_replay_cases = [item for item in replay_cases if bool(item["eligible"])]
    complete_replay_cases = [
        item for item in eligible_replay_cases if bool(item["snapshot_contract_complete"])
    ]

    def replay_backend_summary(backend: str) -> dict[str, object]:
        certificates = [
            item[backend]
            for item in replay
            if isinstance(item.get(backend), Mapping)
        ]
        zoh_certificates = [
            certificate["zoh"]
            for certificate in certificates
            if isinstance(certificate.get("zoh"), Mapping)
        ]
        denominator = len(replay)
        feasible_count = sum(bool(certificate.get("feasible")) for certificate in certificates)
        zoh_safe_count = sum(bool(zoh.get("safe")) for zoh in zoh_certificates)
        return {
            "backend": "dykstra" if backend == "dykstra" else "slsqp_convex_qcqp",
            "snapshot_count": denominator,
            "certificate_count": len(certificates),
            "feasible_count": feasible_count,
            "feasible_rate": feasible_count / denominator if denominator else None,
            "zoh_certificate_count": len(zoh_certificates),
            "zoh_safe_count": zoh_safe_count,
            "zoh_safe_rate": zoh_safe_count / denominator if denominator else None,
            "primal_residual": _distribution(
                [
                    float(certificate["primal_residual"])
                    if "primal_residual" in certificate else None
                    for certificate in certificates
                ],
                direction="lower",
            ),
            "kkt_residual": _distribution(
                [
                    float(certificate["kkt_residual"])
                    if "kkt_residual" in certificate else None
                    for certificate in certificates
                ],
                direction="lower",
            ),
            "runtime": runtime_percentiles(
                [
                    float(certificate["runtime_ms"])
                    if "runtime_ms" in certificate else None
                    for certificate in certificates
                ]
            ),
            "minimum_clearance": _distribution(
                [
                    float(zoh["minimum_clearance"])
                    if "minimum_clearance" in zoh else None
                    for zoh in zoh_certificates
                ],
                direction="higher",
            ),
            "control_adjustment": _distribution(
                [
                    float(certificate["control_adjustment"])
                    if "control_adjustment" in certificate else None
                    for certificate in certificates
                ],
                direction="lower",
            ),
        }

    replay_backends = {
        backend: replay_backend_summary(backend) for backend in ("dykstra", "qp")
    }
    replay_summary = {
        "capture_rule": replay[0]["capture_rule"] if replay else None,
        "snapshot_count": len(replay),
        "pairing_unit": "episode_case_all_captured_snapshots_must_pass",
        "total_primary_case_count": len(replay_cases),
        "noneligible_precontrol_case_count": len(replay_cases) - len(eligible_replay_cases),
        "eligible_case_count": len(eligible_replay_cases),
        "complete_case_count": len(complete_replay_cases),
        "missing_case_count": len(eligible_replay_cases) - len(complete_replay_cases),
        "minimum_complete_case_count": MIN_BACKEND_REPLAY_CASES,
        "case_coverage_complete": bool(eligible_replay_cases)
        and len(complete_replay_cases) == len(eligible_replay_cases),
        "identical_instances": True,
        "all_problem_sha256_match": bool(replay) and all(
            bool(item.get("problem_sha256_match")) for item in replay
        ),
        "backends": replay_backends,
        "dykstra_primal_residual": _distribution(
            [float(item["dykstra"]["primal_residual"]) for item in replay], direction="lower"
        ),
        "qp_primal_residual": _distribution(
            [float(item["qp"]["primal_residual"]) for item in replay], direction="lower"
        ),
        "dykstra_kkt_residual": _distribution(
            [float(item["dykstra"]["kkt_residual"]) for item in replay], direction="lower"
        ),
        "qp_kkt_residual": _distribution(
            [float(item["qp"]["kkt_residual"]) for item in replay], direction="lower"
        ),
        "dykstra_runtime": runtime_percentiles(
            [float(item["dykstra"]["runtime_ms"]) for item in replay]
        ),
        "qp_runtime": runtime_percentiles(
            [float(item["qp"]["runtime_ms"]) for item in replay]
        ),
        "applied_control_distance": _distribution(
            [float(item["applied_control_distance"]) for item in replay], direction="lower"
        ),
        "records": replay,
    }
    return {
        "schema": "abcg-v2.1-g7-safety-backend-comparison-v1",
        "identical_problem_replay": replay_summary,
        "closed_loop_ablation": {
            "claim": "same formulation and frozen configuration; post-first-control instances are not claimed identical",
            "methods": output,
        },
        # Compatibility alias retained for compact downstream consumers.
        "methods": output,
    }


def _blocked_timeout_pairs(
    records: Sequence[G7Record],
    config: G7EvaluationConfig,
) -> dict[str, object]:
    pairs = matched_same_resource_pairs(
        records,
        baseline_method="g6_fixed_resource_rerun",
        candidate_method="visibility_hungarian",
    )
    scenarios: dict[str, object] = {}
    for scenario in config.blocked_scenarios:
        selected = [
            (left, right) for left, right in pairs
            if left.scenario == scenario
            and left.metadata.get("case_cohort") == "blocked_supplement"
            and left.metadata.get("initial_layout") == "one_sided"
        ]
        pair_ids = [_pair_id(left) for left, _ in selected]
        summary = paired_binary_summary(
            pair_ids,
            [left.outcome.controller_terminal_state == "TIMEOUT" for left, _ in selected],
            [right.outcome.controller_terminal_state == "TIMEOUT" for _, right in selected],
            direction="lower_is_better",
            event_name="one_sided_blocked_route_TIMEOUT",
            seed=307 + len(scenarios),
            resamples=config.bootstrap_resamples,
        )
        scenarios[scenario] = {
            "pair_ids": sorted(pair_ids),
            "pair_id_digest": _canonical_hash(sorted(pair_ids)),
            "resource_regime": "same_resource",
            "denominator": len(selected),
            "baseline_method": "g6_fixed_resource_rerun",
            "candidate_method": "visibility_hungarian",
            "baseline_timeout_rate": summary["baseline_event_rate"],
            "candidate_timeout_rate": summary["candidate_event_rate"],
            "paired_difference": summary["paired_difference"]["mean"],
            "paired_bootstrap_ci95": [
                summary["paired_difference"]["ci_low"],
                summary["paired_difference"]["ci_high"],
            ],
            "summary": summary,
        }
    return {
        "baseline_label": "Frozen G6 fixed-resource straight-feedback adapter rerun on matched G7 holdout",
        "candidate_label": "ABCG-v2.1 visibility-graph routing",
        "scenarios": scenarios,
    }


def _readme_summary(
    records: Sequence[G7Record],
    aggregate: Mapping[str, object],
    resource_pareto: Mapping[str, object],
    gate: Mapping[str, object],
    config: G7EvaluationConfig,
    *,
    records_sha256: str,
    config_hash: str,
    frozen_sha: str,
    branch_sha: str,
) -> dict[str, object]:
    groups = aggregate["groups"]
    scenario_summary: dict[str, object] = {}
    same_resource: list[dict[str, object]] = []
    for scenario in config.scenarios:
        key = f"{scenario}|visibility_hungarian|same_resource"
        group = groups.get(key)
        if group is None:
            scenario_summary[scenario] = {
                "method": "visibility_hungarian",
                "resource_regime": "same_resource",
                "denominator": 0,
                "record_count": 0,
                "estimated_deployment_success_rate": None,
                "truth_validated_success_rate": None,
                "estimated_success_rate": None,
                "truth_success_rate": None,
                "blocked_route_timeout_rate": None,
                "truth_coverage": None,
                "maximum_consecutive_arc_gap": None,
                "gap": None,
                "active_guide_count": 0,
                "active_guides": None,
            }
        else:
            scenario_summary[scenario] = {
                "method": "visibility_hungarian",
                "resource_regime": "same_resource",
                "denominator": group["record_count"],
                "record_count": group["record_count"],
                "estimated_deployment_success_rate": group["estimated_success_rate"],
                "truth_validated_success_rate": group["truth_success_rate"],
                "estimated_success_rate": group["estimated_success_rate"],
                "truth_success_rate": group["truth_success_rate"],
                "blocked_route_timeout_rate": group["blocked_route_timeout_rate"],
                "truth_coverage": group["truth_coverage"]["median"],
                "maximum_consecutive_arc_gap": group["maximum_consecutive_arc_gap"]["median"],
                "gap": group["maximum_consecutive_arc_gap"]["median"],
                "active_guide_count": int(round(group["active_guide_count"]["median"] or 0)),
                "active_guides": group["active_guide_count"]["median"],
            }
    for group in groups.values():
        if (
            group["resource_regime"] != "same_resource"
            or group["method"] not in PRIMARY_METHODS
        ):
            continue
        same_resource.append(
            {
                "scenario": group["scenario"],
                "method": group["method"],
                "truth_coverage": group["truth_coverage"]["median"],
                "maximum_consecutive_arc_gap": group["maximum_consecutive_arc_gap"]["median"],
                "gap": group["maximum_consecutive_arc_gap"]["median"],
                "active_guide_count": int(round(group["active_guide_count"]["median"] or 0)),
                "active": group["active_guide_count"]["median"],
            }
        )
    blocked = _blocked_timeout_pairs(records, config)
    v2_records = _v2_1_records(records)
    g6_tracking = _g6_tracking_comparator(records)
    return {
        "schema": "abcg-v2.1-g7-readme-summary-v1",
        "split": "holdout",
        "pilot_data_used": False,
        "records_sha256": records_sha256,
        "record_count": len(records),
        "config_hash": config_hash,
        "base_sha": G6_BASE_SHA,
        "g6_implementation_freeze_sha": IMPLEMENTATION_FREEZE_SHA,
        "frozen_sha": frozen_sha,
        "branch_sha": branch_sha,
        "gate_status": gate["status"],
        "experiment_scale": {
            "unique_cases": len({_pair_id(record) for record in records}),
            "records": len(records),
            "total_records": len(records),
            "v2_1_deployment_records": len(v2_records),
            "g6_tracking_comparator_records": g6_tracking["record_count"],
            "v2_1_method_count": len({record.method for record in v2_records}),
            "g6_tracking_comparator_method_count": int(bool(g6_tracking["record_count"])),
            "general_seeds": list(config.holdout_general_seeds),
            "blocked_supplement_seeds": list(config.holdout_blocked_seeds),
        },
        "scenario_summary": scenario_summary,
        "same_resource": same_resource,
        "adaptive_pareto": list(resource_pareto["points"]),
        "failure_composition": _failure_composition_records(v2_records),
        "g6_tracking_comparator": g6_tracking,
        "blocked_timeout_paired": blocked,
        "g6_reference": {
            scenario: item["baseline_timeout_rate"]
            for scenario, item in blocked["scenarios"].items()
        },
        "g6_reference_semantics": (
            "Frozen G6 fixed-resource straight-feedback adapter rerun on matched G7 holdout; "
            "it preserves the old estimator/planner/controller with fixed m=8 and is not an exact "
            "historical adaptive-resource G6 run. Historical G6 seeds 0..29 remain reference-only"
        ),
        "success_semantics": SUCCESS_DEFINITION,
        "limitations": [
            "single_static_synthetic_point_cloud_guide_deployment_only",
            "does_not_prove_human_containment_or_evacuation_improvement",
            "does_not_prove_behavior_change_dynamic_multi_group_capability_or_safety_certification",
        ],
    }


_MEDIA_PAYLOAD_FIELDS = (
    "truth_boundary",
    "source_polygon",
    "targets",
    "initial_positions",
    "paths",
    "trajectories",
)


def _canonical_utf8_hash(value: object) -> str:
    payload = json.dumps(
        _strict_jsonable(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _media_payload_hash(media: Mapping[str, object]) -> str:
    projection = {field: media.get(field) for field in _MEDIA_PAYLOAD_FIELDS}
    return _canonical_utf8_hash(projection)


def _media_evidence(
    records: Sequence[G7Record],
    media_rows: Mapping[str, Mapping[str, object]],
    record_rows: Mapping[str, Mapping[str, object]],
    config: G7EvaluationConfig,
    *,
    records_sha256: str,
    config_hash: str,
    frozen_sha: str,
) -> dict[str, object]:
    def case_for(record: G7Record | None, rule: str) -> dict[str, object] | None:
        if record is None:
            return None
        record_id = _record_id(record)
        if record_id not in media_rows or record_id not in record_rows:
            return None
        media = dict(media_rows[record_id])
        source = record_rows[record_id]
        media.update(
            {
                "source_record_id": record_id,
                "source_record_sha256": _canonical_utf8_hash(source),
                "scenario": record.scenario,
                "seed": record.seed,
                "pair_id": _pair_id(record),
                "method": record.method,
                "route_variant": _public_route_variant(record.method),
                "resource_regime": str(record.resource_regime),
                "selection_rule": rule,
                "terminal_status": _failure_status(record),
                "controller_terminal_state": record.outcome.controller_terminal_state,
                "plan_optimal": record.outcome.plan_optimal,
                "route_feasible": record.outcome.route_feasible,
                "track_converged": record.outcome.track_converged,
                "sampled_safe": record.outcome.sampled_safe,
                "estimated_deployment_success": record.outcome.estimated_deployment_success,
                "truth_validated_success": record.outcome.truth_validated_success,
            }
        )
        return media

    ordered = sorted(_v2_1_records(records), key=_record_id)
    first_success = next((record for record in ordered if record.outcome.truth_validated_success), None)
    first_failure = next((record for record in ordered if not record.outcome.truth_validated_success), None)
    comparisons: dict[str, object] = {}
    for scenario in ("u_shape", "c_shape"):
        pairs = sorted(
            {
                (_pair_id(record), record.seed, str(record.resource_regime))
                for record in records
                if record.scenario == scenario
                and record.metadata.get("case_cohort") == "blocked_supplement"
                and record.method == "visibility_hungarian"
            }
        )
        before: G7Record | None = None
        after: G7Record | None = None
        if pairs:
            pair_id, seed, regime = pairs[0]
            before = next(
                (
                    record for record in records
                    if record.scenario == scenario
                    and record.seed == seed
                    and _pair_id(record) == pair_id
                    and str(record.resource_regime) == regime
                    and record.method == "g6_fixed_resource_rerun"
                ),
                None,
            )
            after = next(
                (
                    record for record in records
                    if record.scenario == scenario
                    and record.seed == seed
                    and _pair_id(record) == pair_id
                    and str(record.resource_regime) == regime
                    and record.method == "visibility_hungarian"
                ),
                None,
            )
        comparisons[f"{scenario}_comparison"] = {
            "before": case_for(before, "first_complete_blocked_pair_by_frozen_pair_id"),
            "after": case_for(after, "first_complete_blocked_pair_by_frozen_pair_id"),
        }
    return {
        "schema": "abcg-v2.1-g7-media-evidence-v1",
        "split": "holdout",
        "pilot_data_used": False,
        "records_sha256": records_sha256,
        "record_count": len(records),
        "config_hash": config_hash,
        "frozen_sha": frozen_sha,
        "selection_order": "record_id ascending; never optimize exemplar quality",
        "success_case": case_for(first_success, "first_v2_1_truth_success_by_frozen_record_id"),
        "failure_case": case_for(first_failure, "first_v2_1_truth_failure_by_frozen_record_id"),
        "u_shape_comparison": comparisons["u_shape_comparison"],
        "c_shape_comparison": comparisons["c_shape_comparison"],
    }


def _record_id(record: G7Record) -> str:
    method_order = {
        "g6_fixed_resource_rerun": 0,
        "straight_hungarian": 1,
        "visibility_hungarian": 2,
        "boundary_corridor_hungarian": 3,
    }
    return ":".join(
        (
            str(record.metadata.get("case_cohort")),
            record.scenario,
            str(record.seed),
            f"{method_order.get(record.method, 9):02d}",
            str(record.resource_regime),
            record.method,
        )
    )


def _gate_evidence(
    records: Sequence[G7Record],
    paired: Mapping[str, object],
    noninferiority: Mapping[str, object],
    safety: Mapping[str, object],
    config: G7EvaluationConfig,
    *,
    expected_record_count: int,
    calibration_status: str,
    g6_audit: Mapping[str, object],
    quick: bool,
) -> dict[str, object]:
    reasons: list[str] = []
    v2_records = _v2_1_records(records)
    g6_tracking = _g6_tracking_comparator(records)
    expected_case_count = len(evaluation_cases(config, "holdout"))
    expected_v2_count = expected_case_count * len(
        [method for method in evaluation_methods("holdout", quick=quick)
         if method != "g6_fixed_resource_rerun"]
    )
    expected_g6_count = (
        expected_case_count
        if "g6_fixed_resource_rerun" in evaluation_methods("holdout", quick=quick)
        else 0
    )
    if len(records) != expected_record_count:
        reasons.append("record_count_mismatch")
    if len(v2_records) != expected_v2_count:
        reasons.append("v2_1_deployment_record_count_mismatch")
    if int(g6_tracking["record_count"]) != expected_g6_count:
        reasons.append("g6_tracking_comparator_record_count_mismatch")
    if not bool(g6_audit.get("all_match")) or not bool(g6_audit.get("legacy_visual_overview_all_match")):
        reasons.append("frozen_g6_evidence_changed")
    if calibration_status != "CALIBRATED_TUBE":
        reasons.append("independent_uncertainty_calibration_not_passed")
    if not _failure_composition_records(v2_records)["all_records_accounted_for"]:
        reasons.append("failure_denominator_incomplete")
    if not bool(g6_tracking["all_records_accounted_for"]):
        reasons.append("g6_tracking_terminal_denominator_incomplete")
    holm = paired["holm"]
    reasons.extend(str(value) for value in paired.get("protocol_failures", ()))
    if not all(bool(value) for value in holm["reject"].values()):
        reasons.append("holm_adjusted_primary_superiority_not_passed")
    for name, item in noninferiority["results"].items():
        if not bool(item["decision"].get("noninferior")):
            reasons.append(f"noninferiority_not_passed:{name}")
    for endpoint, summary in paired["continuous"].items():
        if not bool(summary.get("primary_inference_permitted")):
            reasons.append(f"continuous_missing_primary_inference_forbidden:{endpoint}")
    replay = safety.get("identical_problem_replay", {})
    if not bool(replay.get("all_problem_sha256_match")):
        reasons.append("identical_problem_backend_replay_missing_or_sha_mismatch")
    if not bool(replay.get("case_coverage_complete")):
        reasons.append("identical_problem_backend_replay_case_coverage_incomplete")
    if int(replay.get("complete_case_count", 0)) < MIN_BACKEND_REPLAY_CASES:
        reasons.append("identical_problem_backend_replay_case_count_insufficient")
    if quick:
        status = "SMOKE_ONLY"
        reasons.append("quick_subset_is_not_formal_g7")
    else:
        status = "PASS" if not reasons else "FAIL"
    return {
        "schema": "abcg-v2.1-g7-gate-evidence-v1",
        "gate": "G7",
        "status": status,
        "formal": not quick,
        "expected_record_count": expected_record_count,
        "actual_record_count": len(records),
        "expected_v2_1_deployment_record_count": expected_v2_count,
        "actual_v2_1_deployment_record_count": len(v2_records),
        "expected_g6_tracking_comparator_record_count": expected_g6_count,
        "actual_g6_tracking_comparator_record_count": g6_tracking["record_count"],
        "all_failures_in_binary_denominator": True,
        "g6_tracking_comparator_separate_from_deployment_failure_denominator": True,
        "continuous_missing_policy": "complete-case exploratory only; any missing forbids primary/NI PASS",
        "calibration_status": calibration_status,
        "reasons": reasons,
        "limitations": [
            "not_human_safety_certification",
            "not_unconditional_continuous_time_safety_proof",
        ],
    }


def _g7_report(
    records: Sequence[G7Record],
    gate: Mapping[str, object],
    summary: Mapping[str, object],
    paired: Mapping[str, object],
    noninferiority: Mapping[str, object],
    aggregate: Mapping[str, object],
    resource_pareto: Mapping[str, object],
    safety: Mapping[str, object],
    failures: Mapping[str, object],
    snapshot: Mapping[str, object],
    config: G7EvaluationConfig,
) -> str:
    lines = [
        "# ABCG-v2.1 Step 1 G7 Proof-Strengthening Report",
        "",
        f"**G7 {gate['status']}**",
        "",
        f"Records: {len(records)}. Every failed episode remains in binary denominators.",
        "",
        f"Base SHA: `{summary['base_sha']}`; frozen SHA: `{summary['frozen_sha']}`; "
        f"config hash: `{summary['config_hash']}`.",
        "",
        f"General seeds: `{list(config.holdout_general_seeds)}`; blocked supplement seeds: "
        f"`{list(config.holdout_blocked_seeds)}`.",
        "",
        f"Environment: `{json.dumps(snapshot['environment'], ensure_ascii=False, sort_keys=True)}`.",
        "",
        "`CONVERGED` is tracking-only. It is not reported as overall deployment success.",
        "",
        "`g6_fixed_resource_rerun` is a frozen-G6-component fixed-resource straight-feedback adapter used only for matched blocked-route controller TIMEOUT. It is not an exact historical G6 run and is excluded from ABCG-v2.1 deployment-success inference.",
        "",
        "The frozen primary candidate uses an explicitly uncalibrated signed-normal bootstrap stability heuristic. It is not called a calibrated uncertainty tube. The calibrated-tube ablation remains in the formal denominator and returns RESOURCE_UNCERTAIN when independent calibration fails.",
        "",
        "## Scenario summary",
        "",
        "| Scenario | Estimated success | Truth success | Blocked TIMEOUT | Coverage median | Gap median | Active guides |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for scenario, item in summary["scenario_summary"].items():
        def show(value: object) -> str:
            return "NA" if value is None else f"{float(value):.4g}"
        lines.append(
            f"| {scenario} | {show(item['estimated_success_rate'])} | {show(item['truth_success_rate'])} | "
            f"{show(item['blocked_route_timeout_rate'])} | {show(item['truth_coverage'])} | "
            f"{show(item['gap'])} | {show(item['active_guides'])} |"
        )
    lines.extend(
        [
            "",
            "## Fixed-resource primary paired endpoints",
            "",
            "| Endpoint | Baseline rate | Candidate rate | Paired delta | Bootstrap 95% CI | One-sided p | Holm-adjusted p |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for name, item in paired["primary_binary"].items():
        difference = item["paired_difference"]
        adjusted = paired["holm"]["adjusted_p_values"].get(name)
        lines.append(
            f"| {name} | {item['baseline_event_rate']} | {item['candidate_event_rate']} | "
            f"{difference['mean']} | [{difference['ci_low']}, {difference['ci_high']}] | "
            f"{item['one_sided_test']['p_value']} | {adjusted} |"
        )
    lines.extend(
        [
            "",
            "## U/C blocked-route paired TIMEOUT",
            "",
            "| Scenario | n | G6 fixed-resource adapter rate | Visibility rate | Candidate-baseline delta | 95% CI |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for scenario, item in summary["blocked_timeout_paired"]["scenarios"].items():
        lines.append(
            f"| {scenario} | {item['denominator']} | {item['baseline_timeout_rate']} | "
            f"{item['candidate_timeout_rate']} | {item['paired_difference']} | "
            f"{item['paired_bootstrap_ci95']} |"
        )
    lines.extend(
        [
            "",
            "## Continuous paired endpoints",
            "",
            "| Endpoint | n total/complete/missing | Mean delta | Median delta | Worst 5% | 95% CI | Inference status |",
            "|---|---:|---:|---:|---:|---:|---|",
        ]
    )
    for name, item in paired["continuous"].items():
        difference = item["paired_difference"]
        lines.append(
            f"| {name} | {item['n_total']}/{item['n_complete_pairs']}/{item['n_missing_pairs']} | "
            f"{difference['mean']} | {difference['median']} | {difference['worst_5_percent_mean']} | "
            f"[{difference['ci_low']}, {difference['ci_high']}] | {item['inference_status']} |"
        )
    lines.extend(
        [
            "",
            "## Paired one-factor-at-a-time ablations",
            "",
            "Each row is candidate ablation minus the same frozen visibility/Hungarian/optimized-phase/uncalibrated-stability-heuristic/Dykstra reference.",
            "",
            "| Method | Dimension | n | Estimated success delta [95% CI] | Truth success delta [95% CI] | TIMEOUT delta [95% CI] | Coverage delta [95% CI] | Gap delta [95% CI] |",
            "|---|---|---:|---|---|---|---|---|",
        ]
    )
    for method, item in paired.get("ofat_ablations", {}).items():
        binary = item["binary"]
        continuous = item["continuous"]

        def interval(summary_item: Mapping[str, object]) -> str:
            difference = summary_item["paired_difference"]
            assert isinstance(difference, Mapping)
            return f"{difference.get('mean')} [{difference.get('ci_low')}, {difference.get('ci_high')}]"

        lines.append(
            f"| {method} | {item['ablation_dimension']} | {item['pair_count']} | "
            f"{interval(binary['estimated_success'])} | {interval(binary['truth_success'])} | "
            f"{interval(binary['controller_timeout'])} | {interval(continuous['truth_coverage'])} | "
            f"{interval(continuous['maximum_consecutive_arc_gap'])} |"
        )
    lines.extend(
        [
            "",
            "Any continuous endpoint with missing pairs is descriptive complete-case evidence only and cannot pass a primary or NI gate.",
            "",
            "## Noninferiority",
            "",
            f"Frozen margin magnitude: `{noninferiority['margin_magnitude']}`; candidate-minus-baseline threshold: "
            f"`{noninferiority['candidate_minus_baseline_decision_threshold']}`.",
            "",
        ]
    )
    for name, item in noninferiority["results"].items():
        lines.append(f"- {name}: `{json.dumps(item['decision'], ensure_ascii=False, sort_keys=True)}`")
    lines.extend(
        [
            "",
            "## Adaptive-resource Pareto evidence",
            "",
            "| Scenario | Method | n | Active | Nominal m | Robust m | Resource status | Coverage | Gap | Path | Runtime ms | Pareto |",
            "|---|---|---:|---:|---:|---:|---|---:|---:|---:|---:|---|",
        ]
    )
    for item in resource_pareto["points"]:
        lines.append(
            f"| {item['scenario']} | {item['method']} | {item['denominator']} | {item['active_guide_count']} | "
            f"{item['nominal_resource_count']} | {item['robust_resource_count']} | {item['resource_status_counts']} | "
            f"{item['truth_coverage']} | {item['maximum_consecutive_arc_gap']} | {item['path_length']} | "
            f"{item['runtime_ms']} | {item['pareto_status']}:{item['pareto_nondominated']} |"
        )
    lines.extend(
        [
            "",
            "## Frozen ablations",
            "",
            "| Method | Route / assignment / phase / uncertainty / safety | Estimated rate | Truth rate | Runtime P50/P95 | Peak memory median |",
            "|---|---|---:|---:|---:|---:|",
        ]
    )
    groups = aggregate["groups"]
    for method in PRIMARY_METHODS + OFAT_METHODS:
        selected = [value for value in groups.values() if value["method"] == method]
        if not selected:
            continue
        denominator = sum(int(value["record_count"]) for value in selected)
        estimated_rate = (
            sum(int(value["estimated_success_count"]) for value in selected) / denominator if denominator else None
        )
        truth_rate = sum(int(value["truth_success_count"]) for value in selected) / denominator if denominator else None
        runtimes = [record.metrics.runtime_ms for record in records if record.method == method]
        memories = [
            None if record.metrics.peak_memory_bytes is None else float(record.metrics.peak_memory_bytes)
            for record in records if record.method == method
        ]
        spec = _method_spec(method)
        lines.append(
            f"| {method} | {spec['route']} / {spec['assignment']} / {spec['phase']} / "
            f"{spec['uncertainty']} / {spec['safety']} | {estimated_rate} | {truth_rate} | "
            f"{runtime_percentiles(runtimes)['p50_ms']}/{runtime_percentiles(runtimes)['p95_ms']} | "
            f"{_distribution(memories, direction='lower')['median']} |"
        )
    lines.extend(
        [
            "",
            "## Safety backend comparison",
            "",
            f"`{json.dumps(safety, ensure_ascii=False, sort_keys=True)}`",
            "",
            "## Failure composition",
            "",
            f"Denominator: {failures['denominator']}; estimated success rate: "
            f"{failures['estimated_deployment_success_rate']}; truth success rate: "
            f"{failures['truth_validated_success_rate']}.",
            "",
            f"Counts/rates: `{json.dumps({'counts': failures['counts'], 'rates': failures['rates']}, ensure_ascii=False, sort_keys=True)}`.",
            "",
            "## G6 tracking-only comparator composition",
            "",
            f"`{json.dumps(summary['g6_tracking_comparator'], ensure_ascii=False, sort_keys=True)}`",
        ]
    )
    lines.extend(
        [
            "",
            "## Gate reasons",
            "",
            *([f"- {reason}" for reason in gate["reasons"]] or ["- All preregistered checks passed."]),
            "",
            "## Limitations",
            "",
            "These results apply only to guide deployment around one static synthetic point cloud. "
            "They do not prove human containment, improved evacuation, behavior change, dynamic or "
            "multi-group capability, or safety certification.",
            "",
        ]
    )
    return "\n".join(lines)


def _emergency_prepared_case(
    config: G7EvaluationConfig,
    case: Mapping[str, object],
    *,
    calibration_status: str,
    calibration_factor: float | None,
) -> _PreparedCase:
    """Create denominator-safe provenance when case preparation itself fails."""

    forced_layout = case.get("forced_layout")
    initial_guides = _one_sided_guides(config.available_guides)
    return _PreparedCase(
        scenario=str(case["scenario"]),
        seed=int(case["seed"]),
        cohort=str(case["cohort"]),
        initial_layout=("one_sided" if forced_layout == "one_sided" else "preparation_unavailable"),
        observation=np.empty((0, 2), dtype=float),
        initial_guides=initial_guides,
        boundary=BoundaryEstimateFailure(
            status="EVALUATION_ERROR",
            component_count=0,
            method="case_preparation",
            version=2,
            diagnostics={"reason": "case_preparation_failed"},
        ),
        stability_status="PREPARATION_FAILED",
        stability_score=None,
        raw_tube_max=None,
        calibration_factor=calibration_factor,
        calibration_status=calibration_status,
        route_cache={},
    )


def _with_preparation_cost(
    record: G7Record,
    *,
    runtime_ms: float,
    peak_memory_bytes: int,
) -> G7Record:
    """Add shared case preparation cost to each frozen method episode."""

    deployment_runtime = record.metrics.runtime_ms
    deployment_peak = record.metrics.peak_memory_bytes
    end_to_end_runtime = float(runtime_ms) + float(deployment_runtime or 0.0)
    end_to_end_peak = max(int(peak_memory_bytes), int(deployment_peak or 0))
    metadata = dict(record.metadata)
    metadata.update(
        {
            "runtime_scope": "observation_available_then_boundary_stability_plus_method_deployment",
            "preparation_runtime_ms": float(runtime_ms),
            "deployment_runtime_ms": deployment_runtime,
            "preparation_peak_memory_bytes": int(peak_memory_bytes),
            "deployment_peak_memory_bytes": deployment_peak,
            "end_to_end_peak_aggregation": "max_shared_preparation_and_method_deployment",
        }
    )
    return replace(
        record,
        metrics=replace(
            record.metrics,
            runtime_ms=end_to_end_runtime,
            peak_memory_bytes=end_to_end_peak,
        ),
        metadata=metadata,
    )


def _with_input_generation_metadata(
    record: G7Record,
    *,
    runtime_ms: float,
) -> G7Record:
    metadata = dict(record.metadata)
    metadata.update(
        {
            "input_generation_runtime_ms_excluded": float(runtime_ms),
            "algorithm_runtime_origin": "observation_available",
            "synthetic_truth_generation_excluded_from_algorithm_runtime": True,
        }
    )
    return replace(record, metadata=metadata)


_WORKER_THREAD_ENVIRONMENT: dict[str, str] = {
    "OMP_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "BLIS_NUM_THREADS": "1",
    "VECLIB_MAXIMUM_THREADS": "1",
    "NUMEXPR_NUM_THREADS": "1",
    "OMP_DYNAMIC": "FALSE",
    "MKL_DYNAMIC": "FALSE",
}


def _configure_case_worker() -> None:
    """Reassert one numeric-library thread inside each case process.

    The parent installs the same environment before Windows ``spawn`` so the
    limits are already visible when NumPy/SciPy DLLs load.  Reasserting them in
    the initializer also documents and preserves the contract if another
    process start method is used.
    """

    for name, value in _WORKER_THREAD_ENVIRONMENT.items():
        os.environ[name] = value


@contextmanager
def _worker_spawn_environment() -> Iterable[None]:
    """Temporarily install thread limits inherited by spawned workers."""

    previous = {name: os.environ.get(name) for name in _WORKER_THREAD_ENVIRONMENT}
    try:
        _configure_case_worker()
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _expand_case_failure(
    case_index: int,
    case: Mapping[str, object],
    config: G7EvaluationConfig,
    methods: Sequence[str],
    *,
    config_hash: str,
    branch_sha: str,
    frozen_sha: str,
    calibration_status: str,
    calibration_factor: float | None,
    error: Exception,
    exception_scope: str,
    input_generation_runtime_ms: float = 0.0,
    preparation_runtime_ms: float = 0.0,
    preparation_peak_memory_bytes: int = 0,
) -> tuple[int, list[tuple[G7Record, dict[str, object]]]]:
    """Expand one failed case to every frozen method denominator."""

    planning = _emergency_prepared_case(
        config,
        case,
        calibration_status=calibration_status,
        calibration_factor=calibration_factor,
    )
    evaluated: list[tuple[G7Record, dict[str, object]]] = []
    for method in methods:
        spec = _method_spec(method)
        regime = (
            ResourceRegime.SAME_RESOURCE
            if spec["resource"] == "fixed"
            else ResourceRegime.ADAPTIVE_RESOURCE
        )
        active_count = (
            min(config.fixed_active_guides, config.available_guides)
            if regime == ResourceRegime.SAME_RESOURCE
            else 0
        )
        record, media = _failure_record(
            planning,
            method=method,
            regime=regime,
            active_count=active_count,
            status="EVALUATION_ERROR",
            reason=f"{type(error).__name__}: {error}",
            config_hash=config_hash,
            branch_sha=branch_sha,
            frozen_sha=frozen_sha,
            runtime_ms=preparation_runtime_ms,
            peak_memory_bytes=preparation_peak_memory_bytes,
            diagnostics={
                "exception_scope": exception_scope,
                "exception_type": type(error).__name__,
                "runtime_scope": "case_failed_before_method_deployment",
                "preparation_runtime_ms": preparation_runtime_ms,
                "preparation_peak_memory_bytes": preparation_peak_memory_bytes,
                "adaptive_failure_active_count_semantics": (
                    "unknown_before_resource_planning_recorded_as_zero"
                    if regime == ResourceRegime.ADAPTIVE_RESOURCE else None
                ),
            },
        )
        record = _with_input_generation_metadata(
            record,
            runtime_ms=input_generation_runtime_ms,
        )
        evaluated.append((record, media))
    return case_index, evaluated


def _evaluate_deployment_case_impl(
    case_index: int,
    case: Mapping[str, object],
    config: G7EvaluationConfig,
    methods: Sequence[str],
    *,
    config_hash: str,
    branch_sha: str,
    frozen_sha: str,
    calibration_status: str,
    calibration_factor: float | None,
) -> tuple[int, list[tuple[G7Record, dict[str, object]]]]:
    """Evaluate a complete case in method order without writing shared files."""

    input_generation_start = perf_counter()
    input_generation_error: Exception | None = None
    try:
        input_config = _g6_config(
            config,
            str(case["scenario"]),
            int(case["seed"]),
            bootstrap=config.boundary_bootstrap_samples,
        )
        observation_truth = _observed_case(
            str(case["scenario"]),
            int(case["seed"]),
            input_config,
        )
    except Exception as error:
        input_generation_error = error
        observation_truth = (np.empty((0, 2), dtype=float), np.empty((0, 2), dtype=float))
    input_generation_runtime_ms = (perf_counter() - input_generation_start) * 1000.0

    preparation_error: Exception | None = None
    preparation_runtime_ms = 0.0
    preparation_peak = 0
    if input_generation_error is None:
        preparation_start = perf_counter()
        tracemalloc.start()
        try:
            planning, truth = _prepare_case(
                config,
                str(case["scenario"]),
                int(case["seed"]),
                str(case["cohort"]),
                forced_layout=(
                    None
                    if case["forced_layout"] is None
                    else str(case["forced_layout"])
                ),
                calibration_status=calibration_status,
                calibration_factor=calibration_factor,
                observation_truth=observation_truth,
            )
        except Exception as error:
            preparation_error = error
        finally:
            if tracemalloc.is_tracing():
                _, preparation_peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()
            preparation_runtime_ms = (perf_counter() - preparation_start) * 1000.0
    else:
        preparation_error = input_generation_error

    if preparation_error is not None:
        return _expand_case_failure(
            case_index,
            case,
            config,
            methods,
            config_hash=config_hash,
            branch_sha=branch_sha,
            frozen_sha=frozen_sha,
            calibration_status=calibration_status,
            calibration_factor=calibration_factor,
            error=preparation_error,
            exception_scope=(
                "input_generation"
                if input_generation_error is not None else "case_preparation"
            ),
            input_generation_runtime_ms=input_generation_runtime_ms,
            preparation_runtime_ms=preparation_runtime_ms,
            preparation_peak_memory_bytes=preparation_peak,
        )

    evaluated: list[tuple[G7Record, dict[str, object]]] = []
    for method in methods:
        record, media = evaluate_g7_method(
            planning,
            truth,
            config,
            method,
            config_hash=config_hash,
            branch_sha=branch_sha,
            frozen_sha=frozen_sha,
        )
        if method != "g6_fixed_resource_rerun":
            record = _with_preparation_cost(
                record,
                runtime_ms=preparation_runtime_ms,
                peak_memory_bytes=preparation_peak,
            )
        record = _with_input_generation_metadata(
            record,
            runtime_ms=input_generation_runtime_ms,
        )
        evaluated.append((record, media))
    return case_index, evaluated


def _evaluate_deployment_case(
    case_index: int,
    case: Mapping[str, object],
    config: G7EvaluationConfig,
    methods: Sequence[str],
    *,
    config_hash: str,
    branch_sha: str,
    frozen_sha: str,
    calibration_status: str,
    calibration_factor: float | None,
) -> tuple[int, list[tuple[G7Record, dict[str, object]]]]:
    """Denominator-safe process worker boundary."""

    try:
        result = _evaluate_deployment_case_impl(
            case_index,
            case,
            config,
            methods,
            config_hash=config_hash,
            branch_sha=branch_sha,
            frozen_sha=frozen_sha,
            calibration_status=calibration_status,
            calibration_factor=calibration_factor,
        )
    except Exception as error:
        result = _expand_case_failure(
            case_index,
            case,
            config,
            methods,
            config_hash=config_hash,
            branch_sha=branch_sha,
            frozen_sha=frozen_sha,
            calibration_status=calibration_status,
            calibration_factor=calibration_factor,
            error=error,
            exception_scope="case_worker_unhandled",
        )
    returned_index, evaluated = result
    observed_environment = {
        name: os.environ.get(name)
        for name in _WORKER_THREAD_ENVIRONMENT
    }
    annotated: list[tuple[G7Record, dict[str, object]]] = []
    for record, media in evaluated:
        metadata = dict(record.metadata)
        metadata["case_process_thread_environment"] = observed_environment
        annotated.append((replace(record, metadata=metadata), media))
    return returned_index, annotated


def _case_result_or_failure(
    future: Future[tuple[int, list[tuple[G7Record, dict[str, object]]]]],
    *,
    case_index: int,
    case: Mapping[str, object],
    config: G7EvaluationConfig,
    methods: Sequence[str],
    config_hash: str,
    branch_sha: str,
    frozen_sha: str,
    calibration_status: str,
    calibration_factor: float | None,
) -> tuple[int, list[tuple[G7Record, dict[str, object]]]]:
    """Resolve a future, rejecting process/serialization infrastructure faults.

    Ordinary case-level algorithm exceptions are caught *inside* the worker
    and expanded to every method.  A broken process, pickling failure, or
    malformed worker return means the experiment infrastructure itself is not
    trustworthy; the phase aborts before publishing evidence.
    """

    try:
        result = future.result()
        returned_index, evaluated = result
        if returned_index != case_index:
            raise RuntimeError(
                f"worker returned case index {returned_index}, expected {case_index}"
            )
        if len(evaluated) != len(methods):
            raise RuntimeError(
                f"worker returned {len(evaluated)} methods, expected {len(methods)}"
            )
        returned_methods = tuple(record.method for record, _ in evaluated)
        if returned_methods != tuple(methods):
            raise RuntimeError(
                f"worker method order {returned_methods!r} differs from {tuple(methods)!r}"
            )
        return result
    except Exception as error:
        raise RuntimeError(
            "case worker process/serialization infrastructure failure for "
            f"case_index={case_index}, scenario={case.get('scenario')!r}, "
            f"seed={case.get('seed')!r}; no evidence may be published"
        ) from error


def _execute_deployment_cases(
    cases: Sequence[Mapping[str, object]],
    config: G7EvaluationConfig,
    methods: Sequence[str],
    *,
    config_hash: str,
    branch_sha: str,
    frozen_sha: str,
    calibration_status: str,
    calibration_factor: float | None,
    workers: int | None,
) -> tuple[list[tuple[G7Record, dict[str, object]]], int, str]:
    """Evaluate cases serially or with a spawn-safe process pool.

    Results are always flattened by ``case_index`` then frozen ``method``
    order, never by completion time.
    """

    requested = config.parallel_workers if workers is None else workers
    if isinstance(requested, bool) or int(requested) != requested or int(requested) < 1:
        raise ValueError("workers must be a positive integer")
    actual_workers = min(int(requested), len(cases))
    if actual_workers < 1:
        raise ValueError("deployment phase requires at least one case")
    ordered: list[tuple[int, list[tuple[G7Record, dict[str, object]]]] | None] = [
        None
    ] * len(cases)
    if actual_workers == 1:
        for case_index, case in enumerate(cases):
            ordered[case_index] = _evaluate_deployment_case(
                case_index,
                case,
                config,
                methods,
                config_hash=config_hash,
                branch_sha=branch_sha,
                frozen_sha=frozen_sha,
                calibration_status=calibration_status,
                calibration_factor=calibration_factor,
            )
        mode = "serial_case_loop"
    else:
        spawn_context = multiprocessing.get_context("spawn")
        with _worker_spawn_environment():
            with ProcessPoolExecutor(
                max_workers=actual_workers,
                mp_context=spawn_context,
                initializer=_configure_case_worker,
            ) as executor:
                future_cases = {
                    executor.submit(
                        _evaluate_deployment_case,
                        case_index,
                        case,
                        config,
                        methods,
                        config_hash=config_hash,
                        branch_sha=branch_sha,
                        frozen_sha=frozen_sha,
                        calibration_status=calibration_status,
                        calibration_factor=calibration_factor,
                    ): (case_index, case)
                    for case_index, case in enumerate(cases)
                }
                for future in as_completed(future_cases):
                    case_index, case = future_cases[future]
                    ordered[case_index] = _case_result_or_failure(
                        future,
                        case_index=case_index,
                        case=case,
                        config=config,
                        methods=methods,
                        config_hash=config_hash,
                        branch_sha=branch_sha,
                        frozen_sha=frozen_sha,
                        calibration_status=calibration_status,
                        calibration_factor=calibration_factor,
                    )
        mode = "case_process_pool_spawn"

    flattened: list[tuple[G7Record, dict[str, object]]] = []
    for expected_index, result in enumerate(ordered):
        if result is None:
            raise RuntimeError(f"case {expected_index} produced no result")
        returned_index, evaluated = result
        if returned_index != expected_index:
            raise RuntimeError("case ordering invariant was violated")
        flattened.extend(evaluated)
    return flattened, actual_workers, mode


def _with_execution_metadata(
    record: G7Record,
    *,
    configured_workers: int,
    actual_workers: int,
    execution_mode: str,
) -> G7Record:
    metadata = dict(record.metadata)
    metadata.update(
        {
            "execution_mode": execution_mode,
            "configured_parallel_workers": int(configured_workers),
            "actual_case_workers": int(actual_workers),
            "case_parallelism_unit": "independent_scenario_seed_cohort_case",
            "record_order": "case_index_then_frozen_method_order",
            "runtime_measurement_semantics": (
                "per_episode_wall_latency_inside_case_process_under_frozen_case_concurrency"
            ),
            "gpu_used": False,
            "gpu_policy": "CPU-only NumPy/SciPy/Shapely geometry and solver pipeline",
            "worker_numeric_thread_limit": (
                1 if execution_mode == "case_process_pool_spawn" else None
            ),
            "worker_start_method": (
                "spawn" if execution_mode == "case_process_pool_spawn" else None
            ),
        }
    )
    return replace(record, metadata=metadata)


def run_deployment_phase(
    repo: str | Path,
    config: G7EvaluationConfig,
    output: str | Path,
    *,
    phase: str,
    quick: bool,
    config_hash: str,
    branch_sha: str,
    frozen_sha: str,
    calibration_status: str = "UNCALIBRATED_STABILITY",
    calibration_factor: float | None = None,
    verified_manifest: Mapping[str, object] | None = None,
    workers: int | None = None,
) -> dict[str, object]:
    if phase not in {"pilot", "holdout"}:
        raise ValueError("phase must be pilot or holdout")
    if (
        phase == "holdout"
        and not quick
        and workers is not None
        and workers != config.parallel_workers
    ):
        raise ValueError(
            "formal holdout --workers must equal the frozen "
            f"parallel_workers={config.parallel_workers}"
        )
    cases = evaluation_cases(config, phase)
    methods = evaluation_methods(phase, quick=quick)
    calculated_expected = len(cases) * len(methods)
    if phase == "holdout":
        if verified_manifest is None:
            raise ValueError("formal holdout requires a verified freeze manifest")
        if int(verified_manifest.get("expected_holdout_record_count", -1)) != calculated_expected:
            raise RuntimeError("holdout matrix does not match frozen expected record count")
    output_dir = Path(output)
    records: list[G7Record] = []
    media_by_id: dict[str, Mapping[str, object]] = {}
    deployment_wall_start = perf_counter()
    evaluated, actual_workers, execution_mode = _execute_deployment_cases(
        cases,
        config,
        methods,
        config_hash=config_hash,
        branch_sha=branch_sha,
        frozen_sha=frozen_sha,
        calibration_status=calibration_status,
        calibration_factor=calibration_factor,
        workers=workers,
    )
    deployment_phase_wall_runtime_ms = (perf_counter() - deployment_wall_start) * 1000.0
    for record, media in evaluated:
        record = _with_execution_metadata(
            record,
            configured_workers=config.parallel_workers,
            actual_workers=actual_workers,
            execution_mode=execution_mode,
        )
        record_id = _record_id(record)
        if record_id in media_by_id:
            raise RuntimeError(f"duplicate case/method record id: {record_id}")
        records.append(record)
        media_by_id[record_id] = media
    output_dir.mkdir(parents=True, exist_ok=True)

    if phase == "pilot":
        rows = []
        for record in records:
            row = _record_dict(record)
            row.update({"split": "pilot", "pilot_data_used": False})
            rows.append(row)
        evidence = {
            "schema": "abcg-v2.1-g7-pilot-evidence-v1",
            "split": "pilot",
            "formal": False,
            "quick": bool(quick),
            "diagnostic_only": True,
            "pilot_data_used": False,
            "pilot_data_used_for_formal_conclusion": False,
            "historical_g6_seeds_used": False,
            "seeds": list(config.pilot_seeds),
            "scenarios": list(config.blocked_scenarios),
            "methods": list(methods),
            "record_count": len(rows),
            "expected_record_count": len(cases) * len(methods),
            "config_hash": config_hash,
            "execution": {
                "execution_mode": execution_mode,
                "configured_parallel_workers": config.parallel_workers,
                "actual_case_workers": actual_workers,
                "case_parallelism_unit": "independent_scenario_seed_cohort_case",
                "record_order": "case_index_then_frozen_method_order",
                "deployment_phase_wall_runtime_ms": deployment_phase_wall_runtime_ms,
                "runtime_measurement_semantics": (
                    "per_episode_wall_latency_inside_case_process_under_frozen_case_concurrency"
                ),
                "gpu_used": False,
                "gpu_policy": "CPU-only NumPy/SciPy/Shapely geometry and solver pipeline",
                "worker_numeric_thread_limit": (
                    1 if execution_mode == "case_process_pool_spawn" else None
                ),
            },
            "records_sha256": _canonical_hash(rows),
            "deterministic_records_sha256": _canonical_hash(
                [_deterministic_record_projection(row) for row in rows]
            ),
            "failure_composition": _failure_composition_records(_v2_1_records(records)),
            "g6_tracking_comparator": _g6_tracking_comparator(records),
            "records": rows,
        }
        write_strict_json(output_dir / "pilot_evidence.json", evidence)
        return evidence

    assert verified_manifest is not None
    record_rows: dict[str, dict[str, object]] = {}
    compact_rows: list[dict[str, object]] = []
    for record in records:
        row = _record_dict(record)
        record_id = _record_id(record)
        if record_id not in media_by_id:
            raise RuntimeError(f"record {record_id!r} lacks a media provenance payload")
        row.update(
            {
                "record_id": record_id,
                "split": "holdout",
                "pilot_data_used": False,
                "frozen_sha": frozen_sha,
                "config_hash": config_hash,
                "pair_id": _pair_id(record),
                "route_variant": _public_route_variant(record.method),
                "media_payload_sha256": _media_payload_hash(media_by_id[record_id]),
                "blocked_route_episode": bool(
                    record.metadata.get("case_cohort") == "blocked_supplement"
                    and record.scenario in config.blocked_scenarios
                    and record.metadata.get("initial_layout") == "one_sided"
                ),
            }
        )
        record_rows[record_id] = row
        compact_rows.append(row)
    compact = {
        "schema": "abcg-v2.1-g7-records-compact-v1",
        "split": "holdout",
        "formal": not quick,
        "quick": bool(quick),
        "pilot_data_used": False,
        "frozen_sha": frozen_sha,
        "config_hash": config_hash,
        "record_count": len(compact_rows),
        "execution": {
            "execution_mode": execution_mode,
            "configured_parallel_workers": config.parallel_workers,
            "actual_case_workers": actual_workers,
            "case_parallelism_unit": "independent_scenario_seed_cohort_case",
            "record_order": "case_index_then_frozen_method_order",
            "deployment_phase_wall_runtime_ms": deployment_phase_wall_runtime_ms,
            "runtime_measurement_semantics": (
                "per_episode_wall_latency_inside_case_process_under_frozen_case_concurrency"
            ),
            "gpu_used": False,
            "gpu_policy": "CPU-only NumPy/SciPy/Shapely geometry and solver pipeline",
            "worker_numeric_thread_limit": (
                1 if execution_mode == "case_process_pool_spawn" else None
            ),
        },
        "deterministic_records_sha256": _canonical_hash(
            [_deterministic_record_projection(row) for row in compact_rows]
        ),
        "records": compact_rows,
    }
    compact_path = output_dir / "records_compact.json"
    write_strict_json(compact_path, compact)
    records_file_sha = _sha256(compact_path)

    v2_records = _v2_1_records(records)
    g6_tracking = _g6_tracking_comparator(records)
    aggregate = aggregate_records(v2_records)
    paired = _paired_statistics(records, config)
    noninferiority = _noninferiority(records, config)
    resource_pareto = _resource_pareto(records)
    safety = _safety_comparison(records)
    failures = _failure_composition_records(v2_records)
    g6_audit = audit_frozen_g6_evidence(repo)
    expected = int(verified_manifest["expected_holdout_record_count"])
    gate = _gate_evidence(
        records,
        paired,
        noninferiority,
        safety,
        config,
        expected_record_count=expected,
        calibration_status=calibration_status,
        g6_audit=g6_audit,
        quick=quick,
    )
    summary = _readme_summary(
        records,
        aggregate,
        resource_pareto,
        gate,
        config,
        records_sha256=records_file_sha,
        config_hash=config_hash,
        frozen_sha=frozen_sha,
        branch_sha=branch_sha,
    )
    media = _media_evidence(
        records,
        media_by_id,
        record_rows,
        config,
        records_sha256=records_file_sha,
        config_hash=config_hash,
        frozen_sha=frozen_sha,
    )
    snapshot = {
        "schema": "abcg-v2.1-g7-evaluation-snapshot-v1",
        "split": "holdout",
        "formal": not quick,
        "quick": bool(quick),
        "pilot_data_used": False,
        "base_sha": G6_BASE_SHA,
        "frozen_sha": frozen_sha,
        "branch_sha": branch_sha,
        "config_hash": config_hash,
        "records_sha256": records_file_sha,
        "total_record_count": len(records),
        "v2_1_deployment_record_count": len(v2_records),
        "g6_tracking_comparator_record_count": g6_tracking["record_count"],
        "environment": environment_snapshot(),
        "execution": {
            "execution_mode": execution_mode,
            "configured_parallel_workers": config.parallel_workers,
            "actual_case_workers": actual_workers,
            "case_parallelism_unit": "independent_scenario_seed_cohort_case",
            "record_order": "case_index_then_frozen_method_order",
            "deployment_phase_wall_runtime_ms": deployment_phase_wall_runtime_ms,
            "runtime_measurement_semantics": (
                "per_episode_wall_latency_inside_case_process_under_frozen_case_concurrency"
            ),
            "gpu_used": False,
            "gpu_policy": "CPU-only NumPy/SciPy/Shapely geometry and solver pipeline",
            "worker_numeric_thread_limit": (
                1 if execution_mode == "case_process_pool_spawn" else None
            ),
            "worker_start_method": (
                "spawn" if execution_mode == "case_process_pool_spawn" else None
            ),
        },
        "freeze_verification": verified_manifest.get("holdout_verification"),
        "truth_firewall": {
            "planner_inputs": ["observation", "estimated_boundary", "guide_initial_state"],
            "truth_usage": "post-terminal evaluator scoring only",
        },
    }
    outputs = {
        "aggregate.json": aggregate,
        "paired_stats.json": paired,
        "noninferiority.json": noninferiority,
        "resource_pareto.json": resource_pareto,
        "safety_comparison.json": safety,
        "failure_composition.json": failures,
        "g6_tracking_comparator.json": g6_tracking,
        "evaluation_snapshot.json": snapshot,
        "gate_evidence.json": gate,
        "readme_summary.json": summary,
        "media_evidence.json": media,
    }
    for name, value in outputs.items():
        write_strict_json(output_dir / name, value)
    write_strict_json(output_dir / "freeze_manifest.json", dict(verified_manifest))
    (output_dir / "G7_REPORT.md").write_text(
        _g7_report(
            records,
            gate,
            summary,
            paired,
            noninferiority,
            aggregate,
            resource_pareto,
            safety,
            failures,
            snapshot,
            config,
        ),
        encoding="utf-8",
    )
    return {
        "phase": "holdout",
        "formal": not quick,
        "status": gate["status"],
        "record_count": len(records),
        "expected_record_count": expected,
        "output": str(output_dir),
        "records_sha256": records_file_sha,
        "gate_reasons": gate["reasons"],
        "execution_mode": execution_mode,
        "configured_parallel_workers": config.parallel_workers,
        "actual_case_workers": actual_workers,
    }


def run_g7_phase(
    *,
    phase: str,
    repo: str | Path,
    config_path: str | Path,
    output: str | Path,
    quick: bool = False,
    pilot_evidence_path: str | Path | None = None,
    calibration_evidence_path: str | Path | None = None,
    freeze_manifest_path: str | Path | None = None,
    workers: int | None = None,
) -> dict[str, object]:
    """Execute exactly one protocol phase."""
    root = Path(repo).resolve()
    reject_g6_output(root, output)
    config = load_g7_config(config_path, quick=quick)
    config_hash = resolved_config_hash(config)
    phase_name = str(phase).lower()
    if phase_name == "calibration":
        return run_calibration(config, output, config_hash=config_hash, quick=quick)
    if phase_name == "freeze":
        if pilot_evidence_path is None or calibration_evidence_path is None:
            raise ValueError("freeze requires --pilot-evidence and --calibration-evidence")
        output_dir = Path(output)
        output_dir.mkdir(parents=True, exist_ok=True)
        manifest = create_freeze_manifest(
            root,
            config_path,
            output_dir / "freeze_manifest.json",
            pilot_evidence_path=pilot_evidence_path,
            calibration_evidence_path=calibration_evidence_path,
            quick=quick,
        )
        return {
            "phase": "freeze",
            "status": "FROZEN",
            "manifest": str(output_dir / "freeze_manifest.json"),
            "frozen_head": manifest["frozen_head"],
        }
    snapshot = _git_snapshot(root)
    if phase_name == "pilot":
        return run_deployment_phase(
            root,
            config,
            output,
            phase="pilot",
            quick=quick,
            config_hash=config_hash,
            branch_sha=str(snapshot["head"]),
            frozen_sha=str(snapshot["head"]),
            workers=workers,
        )
    if phase_name == "holdout":
        if freeze_manifest_path is None:
            raise ValueError("holdout requires --freeze-manifest")
        # Verification is intentionally completed before output is created.
        manifest = verify_freeze_manifest(
            root,
            config_path,
            freeze_manifest_path,
            quick=quick,
        )
        return run_deployment_phase(
            root,
            config,
            output,
            phase="holdout",
            quick=quick,
            config_hash=config_hash,
            branch_sha=str(manifest["frozen_head"]),
            frozen_sha=str(manifest["frozen_head"]),
            calibration_status=str(manifest.get("calibration_status")),
            calibration_factor=(
                None if manifest.get("calibration_factor") is None else float(manifest["calibration_factor"])
            ),
            verified_manifest=manifest,
            workers=workers,
        )
    raise ValueError("phase must be pilot, calibration, freeze, or holdout")


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the ABCG-v2.1 Step 1 G7 protocol")
    parser.add_argument("--phase", required=True, choices=("pilot", "calibration", "freeze", "holdout"))
    parser.add_argument("--config", default="configs/step1_g7.yaml")
    parser.add_argument("--output")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--pilot-evidence")
    parser.add_argument("--calibration-evidence")
    parser.add_argument("--freeze-manifest")
    parser.add_argument(
        "--workers",
        type=int,
        help=(
            "case process count; formal holdout must equal frozen "
            "execution.parallel_workers"
        ),
    )
    parser.add_argument("--quick", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    defaults = {
        "pilot": "runs/step1_g7/pilot",
        "calibration": "runs/step1_g7/calibration",
        "freeze": "runs/step1_g7/freeze",
        "holdout": "reports/step1_g7",
    }
    result = run_g7_phase(
        phase=args.phase,
        repo=args.repo,
        config_path=args.config,
        output=args.output or defaults[args.phase],
        quick=args.quick,
        pilot_evidence_path=args.pilot_evidence,
        calibration_evidence_path=args.calibration_evidence,
        freeze_manifest_path=args.freeze_manifest,
        workers=args.workers,
    )
    print(json.dumps(_strict_jsonable(result), ensure_ascii=False, allow_nan=False))
    return 0


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = [
    "ADAPTIVE_METHODS",
    "FREEZE_SCHEMA",
    "G6_BASE_SHA",
    "G6_COMPACT_EVIDENCE_SHA256",
    "G6_VISUAL_OVERVIEW_SHA256",
    "IMPLEMENTATION_FREEZE_SHA",
    "G7EvaluationConfig",
    "OFAT_METHODS",
    "PRIMARY_METHODS",
    "STATISTICS_PLAN",
    "SUCCESS_DEFINITION",
    "audit_frozen_g6_evidence",
    "aggregate_records",
    "build_argument_parser",
    "create_freeze_manifest",
    "evaluation_cases",
    "evaluation_methods",
    "evaluate_g7_method",
    "failure_rate_composition",
    "load_g7_config",
    "main",
    "matched_same_resource_pairs",
    "paired_bootstrap_interval",
    "reject_g6_output",
    "resolved_config_hash",
    "run_calibration",
    "run_deployment_phase",
    "run_g7_phase",
    "split_resource_regimes",
    "verify_freeze_manifest",
    "write_strict_json",
]


if __name__ == "__main__":
    raise SystemExit(main())
