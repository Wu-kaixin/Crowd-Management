"""Aligned signed-normal boundary stability for ABCG-v2.1.

Bootstrap curves are normalized to counter-clockwise orientation and a common
normalized arc-length grid before a deterministic cyclic phase alignment.  The
default output is deliberately named ``UNCALIBRATED_STABILITY``.  A symmetric
``CALIBRATED_TUBE`` is emitted only when separate labelled calibration shapes,
with disjoint curves and their own bootstrap replicas, pass the independence
and minimum-sample checks below.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Sequence

import numpy as np
from shapely.geometry import LineString, Polygon

from ..types import Array


StabilityDiagnostics = dict[str, object]


@dataclass(frozen=True)
class BoundaryStabilityConfig:
    """Numerical and evidence gates for aligned boundary stability."""

    sample_count: int = 256
    min_bootstrap_success_fraction: float = 0.7
    raw_tube_quantile: float = 0.95
    radius_floor: float = 1.0e-6
    stability_scale: float = 0.1
    phase_tie_tolerance: float = 1.0e-14
    calibration_target_coverage: float = 0.95
    min_calibration_shapes: int = 2
    min_calibration_replicas: int = 4

    def __post_init__(self) -> None:
        if (
            isinstance(self.sample_count, bool)
            or not isinstance(self.sample_count, (int, np.integer))
            or self.sample_count < 8
        ):
            raise ValueError("sample_count must be an integer of at least eight.")
        for name in (
            "min_bootstrap_success_fraction",
            "raw_tube_quantile",
            "calibration_target_coverage",
        ):
            value = float(getattr(self, name))
            if not 0.0 < value <= 1.0:
                raise ValueError(f"{name} must be in (0, 1].")
        for name in ("radius_floor", "stability_scale"):
            value = float(getattr(self, name))
            if not np.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and positive.")
        if not np.isfinite(self.phase_tie_tolerance) or self.phase_tie_tolerance < 0.0:
            raise ValueError("phase_tie_tolerance must be finite and non-negative.")
        for name in ("min_calibration_shapes", "min_calibration_replicas"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or value < 1:
                raise ValueError(f"{name} must be a positive integer.")


@dataclass(frozen=True)
class RegisteredBoundaryCurve:
    """One simple closed CCW curve on an exact normalized arc-length grid."""

    points: Array
    normalized_s: Array
    length: float
    tangents: Array
    outward_normals: Array
    sha256: str


@dataclass(frozen=True)
class AlignedBoundaryReplica:
    """One replica after deterministic cyclic phase registration."""

    aligned_points: Array
    signed_normal_displacement: Array
    tangential_residual: Array
    phase_shift_index: int
    phase_shift_fraction: float
    alignment_rmse: float
    max_abs_displacement: float


@dataclass(frozen=True)
class BoundaryCalibrationCase:
    """Independent labelled error case with its own bootstrap reconstruction.

    ``estimate_curve`` is the estimated curve to be evaluated against the
    separate ``reference_curve``.  ``bootstrap_replicas`` must have been
    produced independently for this calibration case.  A shape identifier may
    appear in several cases, but calibration is quantiled over unique shape
    identifiers and none may equal the deployment ``base_shape_id``.
    """

    shape_id: str
    reference_curve: Array
    estimate_curve: Array
    bootstrap_replicas: tuple[Array, ...]


@dataclass(frozen=True)
class BoundaryStabilityEstimate:
    """Signed displacement evidence and an optional independently calibrated tube."""

    base_curve: RegisteredBoundaryCurve
    signed_normal_displacement: Array
    tangential_residual: Array
    replica_phase_shift_index: Array
    replica_phase_shift_fraction: Array
    replica_alignment_rmse: Array
    replica_max_abs_displacement: Array
    raw_tube_radius: Array
    calibrated_tube_radius: Array | None
    max_abs_displacement: float
    stability_score: float
    bootstrap_success_count: int
    bootstrap_failure_count: int
    status: str
    calibration_factor: float | None
    calibration_pointwise_coverage: float | None
    calibration_simultaneous_coverage: float | None
    calibration_shape_ids: tuple[str, ...]
    diagnostics: StabilityDiagnostics = field(default_factory=dict)


@dataclass(frozen=True)
class BoundaryStabilityFailure:
    """Explicit invalid-curve or insufficient-bootstrap result."""

    status: str
    diagnostics: StabilityDiagnostics = field(default_factory=dict)


BoundaryStabilityResult = BoundaryStabilityEstimate | BoundaryStabilityFailure


@dataclass(frozen=True)
class _BootstrapSummary:
    base: RegisteredBoundaryCurve
    aligned: tuple[AlignedBoundaryReplica, ...]
    failed_count: int
    signed: Array
    tangential: Array
    raw_radius: Array


def _failure(status: str, reason: str, **diagnostics: object) -> BoundaryStabilityFailure:
    return BoundaryStabilityFailure(status=status, diagnostics={"reason": reason, **diagnostics})


def _closed_points(curve: Array) -> Array:
    points = np.asarray(curve, dtype=float)
    if points.ndim != 2 or points.shape[1:] != (2,) or not np.all(np.isfinite(points)):
        raise ValueError("curve must be a finite (N, 2) array.")
    if len(points) >= 2 and np.linalg.norm(points[-1] - points[0]) <= 1.0e-12:
        points = points[:-1]
    if len(points) < 3:
        raise ValueError("curve requires at least three distinct vertices.")
    segment_lengths = np.linalg.norm(np.roll(points, -1, axis=0) - points, axis=1)
    if np.any(segment_lengths <= 1.0e-12):
        raise ValueError("curve contains duplicate consecutive vertices.")
    line = LineString(np.vstack((points, points[0])))
    polygon = Polygon(points)
    if not line.is_simple or not polygon.is_valid or polygon.area <= 1.0e-14:
        raise ValueError("curve must form one valid simple polygon exterior.")
    successor = np.roll(points, -1, axis=0)
    signed_area = 0.5 * float(
        np.sum(points[:, 0] * successor[:, 1] - successor[:, 0] * points[:, 1])
    )
    if signed_area < 0.0:
        points = points[::-1].copy()
    # Canonicalize the input ring start before arc-length resampling.  Without
    # this step, rolling the same nonuniformly sampled curve changes the phase
    # of the resampling grid and can defeat calibration-overlap hashes.
    order = np.lexsort((points[:, 1], points[:, 0]))
    points = np.roll(points, -int(order[0]), axis=0)
    return points


def normalize_boundary_curve(
    curve: Array,
    sample_count: int = 256,
) -> RegisteredBoundaryCurve:
    """Normalize one closed curve to CCW and exact normalized arc coordinates."""

    if (
        isinstance(sample_count, bool)
        or not isinstance(sample_count, (int, np.integer))
        or sample_count < 8
    ):
        raise ValueError("sample_count must be an integer of at least eight.")
    points = _closed_points(curve)
    segment_vectors = np.roll(points, -1, axis=0) - points
    segment_lengths = np.linalg.norm(segment_vectors, axis=1)
    length = float(np.sum(segment_lengths))
    normalized_s = np.arange(int(sample_count), dtype=float) / int(sample_count)
    arc_targets = length * normalized_s
    cumulative = np.r_[0.0, np.cumsum(segment_lengths)]
    segment_ids = np.searchsorted(cumulative, arc_targets, side="right") - 1
    segment_ids = np.clip(segment_ids, 0, len(points) - 1)
    fraction = (arc_targets - cumulative[segment_ids]) / segment_lengths[segment_ids]
    resampled = points[segment_ids] + fraction[:, None] * segment_vectors[segment_ids]

    central = np.roll(resampled, -1, axis=0) - np.roll(resampled, 1, axis=0)
    tangent_norm = np.linalg.norm(central, axis=1)
    if np.any(tangent_norm <= 1.0e-12):
        raise ValueError("normalized curve produced a zero tangent.")
    tangents = central / tangent_norm[:, None]
    normals = np.column_stack((tangents[:, 1], -tangents[:, 0]))
    # The same closed curve may be supplied with any ring start vertex.  Hash
    # a quantized lexicographically canonical cyclic rotation so a mere
    # ``np.roll`` cannot masquerade as independent calibration evidence.
    quantized = np.round(np.asarray(resampled, dtype=float), decimals=10)
    canonical_start = min(
        range(len(quantized)),
        key=lambda index: tuple(np.roll(quantized, -index, axis=0).ravel()),
    )
    canonical_hash_points = np.roll(quantized, -canonical_start, axis=0)
    canonical_bytes = np.asarray(canonical_hash_points, dtype="<f8").tobytes(order="C")
    return RegisteredBoundaryCurve(
        points=resampled,
        normalized_s=normalized_s,
        length=length,
        tangents=tangents,
        outward_normals=normals,
        sha256=hashlib.sha256(canonical_bytes).hexdigest(),
    )


def align_boundary_replica(
    base_curve: RegisteredBoundaryCurve | Array,
    replica_curve: Array,
    *,
    sample_count: int | None = None,
    phase_tie_tolerance: float = 1.0e-14,
) -> AlignedBoundaryReplica:
    """Align a replica by exhaustive deterministic cyclic normalized-arc phase."""

    if isinstance(base_curve, RegisteredBoundaryCurve):
        base = base_curve
        count = len(base.points)
        if sample_count is not None and int(sample_count) != count:
            raise ValueError("sample_count must match the registered base curve.")
    else:
        count = 256 if sample_count is None else int(sample_count)
        base = normalize_boundary_curve(base_curve, count)
    if not np.isfinite(phase_tie_tolerance) or phase_tie_tolerance < 0.0:
        raise ValueError("phase_tie_tolerance must be finite and non-negative.")
    replica = normalize_boundary_curve(replica_curve, count)
    costs = np.empty(count, dtype=float)
    for shift in range(count):
        delta = np.roll(replica.points, shift, axis=0) - base.points
        costs[shift] = float(np.mean(np.sum(delta * delta, axis=1)))
    minimum = float(np.min(costs))
    candidates = np.flatnonzero(costs <= minimum + float(phase_tie_tolerance))
    shift = int(candidates[0])
    aligned = np.roll(replica.points, shift, axis=0)
    residual = aligned - base.points
    signed = np.sum(residual * base.outward_normals, axis=1)
    tangential = np.sum(residual * base.tangents, axis=1)
    return AlignedBoundaryReplica(
        aligned_points=aligned,
        signed_normal_displacement=signed,
        tangential_residual=tangential,
        phase_shift_index=shift,
        phase_shift_fraction=float(shift / count),
        alignment_rmse=float(np.sqrt(np.mean(np.sum(residual * residual, axis=1)))),
        max_abs_displacement=float(np.max(np.abs(signed))),
    )


def _bootstrap_summary(
    base_curve: Array,
    replicas: Sequence[Array],
    config: BoundaryStabilityConfig,
) -> _BootstrapSummary | BoundaryStabilityFailure:
    try:
        base = normalize_boundary_curve(base_curve, config.sample_count)
    except ValueError as error:
        return _failure("INVALID", str(error), stage="base_curve")
    total = len(replicas)
    if total == 0:
        return _failure("BOOTSTRAP_INSUFFICIENT", "no_bootstrap_replicas")
    aligned: list[AlignedBoundaryReplica] = []
    failures = 0
    for replica in replicas:
        try:
            aligned.append(
                align_boundary_replica(
                    base,
                    replica,
                    phase_tie_tolerance=config.phase_tie_tolerance,
                )
            )
        except ValueError:
            failures += 1
    minimum_success = int(np.ceil(config.min_bootstrap_success_fraction * total))
    if len(aligned) < minimum_success:
        return _failure(
            "BOOTSTRAP_INSUFFICIENT",
            "insufficient_valid_bootstrap_replicas",
            bootstrap_replica_count=total,
            bootstrap_success_count=len(aligned),
            bootstrap_failure_count=failures,
            minimum_success_count=minimum_success,
        )
    signed = np.asarray([item.signed_normal_displacement for item in aligned], dtype=float)
    tangential = np.asarray([item.tangential_residual for item in aligned], dtype=float)
    raw_radius = np.maximum(
        np.quantile(
            np.abs(signed),
            config.raw_tube_quantile,
            axis=0,
            method="higher",
        ),
        config.radius_floor,
    )
    return _BootstrapSummary(
        base=base,
        aligned=tuple(aligned),
        failed_count=failures,
        signed=signed,
        tangential=tangential,
        raw_radius=raw_radius,
    )


def _curve_hashes(curves: Sequence[Array], sample_count: int) -> set[str]:
    hashes: set[str] = set()
    for curve in curves:
        hashes.add(normalize_boundary_curve(curve, sample_count).sha256)
    return hashes


def _calibrate(
    deployment: _BootstrapSummary,
    deployment_replicas: Sequence[Array],
    base_shape_id: str | None,
    calibration_cases: Sequence[BoundaryCalibrationCase] | None,
    config: BoundaryStabilityConfig,
) -> tuple[Array | None, dict[str, object]]:
    if not calibration_cases:
        return None, {"calibration_rejection_reason": "no_independent_calibration_cases"}
    if base_shape_id is None or not str(base_shape_id).strip():
        return None, {"calibration_rejection_reason": "base_shape_id_is_required"}
    cases = tuple(calibration_cases)
    if any(not isinstance(case, BoundaryCalibrationCase) for case in cases):
        return None, {"calibration_rejection_reason": "invalid_calibration_case_type"}
    shape_ids = tuple(str(case.shape_id).strip() for case in cases)
    if any(not identifier for identifier in shape_ids):
        return None, {"calibration_rejection_reason": "calibration_shape_id_is_required"}
    if str(base_shape_id) in shape_ids:
        return None, {"calibration_rejection_reason": "calibration_shape_overlaps_deployment_shape"}
    unique_shape_ids = tuple(sorted(set(shape_ids)))
    if len(unique_shape_ids) < config.min_calibration_shapes:
        return None, {
            "calibration_rejection_reason": "insufficient_unique_calibration_shapes",
            "calibration_unique_shape_count": len(unique_shape_ids),
        }
    if any(len(case.bootstrap_replicas) < config.min_calibration_replicas for case in cases):
        return None, {
            "calibration_rejection_reason": "insufficient_replicas_in_calibration_case",
            "minimum_calibration_replicas": config.min_calibration_replicas,
        }

    try:
        deployment_hashes = {deployment.base.sha256} | _curve_hashes(
            deployment_replicas,
            config.sample_count,
        )
        calibration_curves: list[Array] = []
        for case in cases:
            calibration_curves.extend((case.reference_curve, case.estimate_curve))
            calibration_curves.extend(case.bootstrap_replicas)
        calibration_hashes = _curve_hashes(calibration_curves, config.sample_count)
    except ValueError:
        return None, {"calibration_rejection_reason": "invalid_curve_in_calibration_evidence"}
    if not deployment_hashes.isdisjoint(calibration_hashes):
        return None, {"calibration_rejection_reason": "calibration_curve_hash_overlap"}

    scores_by_shape: dict[str, list[float]] = {identifier: [] for identifier in unique_shape_ids}
    point_ratios: list[Array] = []
    case_records: list[tuple[Array, Array]] = []
    for case in cases:
        summary = _bootstrap_summary(case.estimate_curve, case.bootstrap_replicas, config)
        if isinstance(summary, BoundaryStabilityFailure):
            return None, {
                "calibration_rejection_reason": "calibration_case_bootstrap_invalid",
                "calibration_shape_id": case.shape_id,
                "calibration_case_failure": summary.status,
            }
        try:
            reference = align_boundary_replica(
                summary.base,
                case.reference_curve,
                phase_tie_tolerance=config.phase_tie_tolerance,
            )
        except ValueError:
            return None, {
                "calibration_rejection_reason": "calibration_reference_invalid",
                "calibration_shape_id": case.shape_id,
            }
        absolute_error = np.abs(reference.signed_normal_displacement)
        ratios = absolute_error / summary.raw_radius
        point_ratios.append(ratios)
        case_records.append((absolute_error, summary.raw_radius))
        scores_by_shape[str(case.shape_id)].append(float(np.max(ratios)))

    shape_scores = np.asarray(
        [max(scores_by_shape[identifier]) for identifier in unique_shape_ids],
        dtype=float,
    )
    shape_count = len(shape_scores)
    finite_sample_level = min(
        1.0,
        float(np.ceil((shape_count + 1) * config.calibration_target_coverage) / shape_count),
    )
    factor = float(np.quantile(shape_scores, finite_sample_level, method="higher"))
    calibrated_radius = factor * deployment.raw_radius
    all_ratios = np.concatenate(point_ratios)
    simultaneous_hits = [
        bool(np.all(error <= factor * radius + 1.0e-15))
        for error, radius in case_records
    ]
    return calibrated_radius, {
        "calibration_factor": factor,
        "calibration_shape_ids": unique_shape_ids,
        "calibration_unique_shape_count": len(unique_shape_ids),
        "calibration_case_count": len(cases),
        "calibration_target_coverage": float(config.calibration_target_coverage),
        "calibration_finite_sample_quantile": finite_sample_level,
        "calibration_pointwise_coverage": float(np.mean(all_ratios <= factor + 1.0e-15)),
        "calibration_simultaneous_coverage": float(np.mean(simultaneous_hits)),
        "calibration_independence_check": "shape_ids_and_registered_curve_hashes_disjoint",
    }


def estimate_boundary_stability(
    base_curve: Array,
    bootstrap_replicas: Sequence[Array],
    *,
    config: BoundaryStabilityConfig | None = None,
    base_shape_id: str | None = None,
    calibration_cases: Sequence[BoundaryCalibrationCase] | None = None,
) -> BoundaryStabilityResult:
    """Return aligned signed-normal evidence and, when justified, a tube.

    Calibration cases are optional.  Missing, overlapping, or insufficient
    cases leave the valid bootstrap result at ``UNCALIBRATED_STABILITY`` and
    set ``calibrated_tube_radius`` to ``None``.
    """

    cfg = config or BoundaryStabilityConfig()
    if not isinstance(cfg, BoundaryStabilityConfig):
        raise TypeError("config must be BoundaryStabilityConfig.")
    replicas = tuple(bootstrap_replicas)
    summary = _bootstrap_summary(base_curve, replicas, cfg)
    if isinstance(summary, BoundaryStabilityFailure):
        return summary

    signed_rms = float(np.sqrt(np.mean(summary.signed**2)))
    tangential_rms = float(np.sqrt(np.mean(summary.tangential**2)))
    success_fraction = len(summary.aligned) / len(replicas)
    stability_score = float(
        np.clip(
            success_fraction
            * np.exp(-(signed_rms + tangential_rms) / cfg.stability_scale),
            0.0,
            1.0,
        )
    )
    calibrated_radius, calibration = _calibrate(
        summary,
        replicas,
        base_shape_id,
        calibration_cases,
        cfg,
    )
    calibrated = calibrated_radius is not None
    aligned = summary.aligned
    shape_ids = tuple(calibration.get("calibration_shape_ids", ()))
    return BoundaryStabilityEstimate(
        base_curve=summary.base,
        signed_normal_displacement=summary.signed,
        tangential_residual=summary.tangential,
        replica_phase_shift_index=np.asarray(
            [item.phase_shift_index for item in aligned],
            dtype=int,
        ),
        replica_phase_shift_fraction=np.asarray(
            [item.phase_shift_fraction for item in aligned],
            dtype=float,
        ),
        replica_alignment_rmse=np.asarray(
            [item.alignment_rmse for item in aligned],
            dtype=float,
        ),
        replica_max_abs_displacement=np.asarray(
            [item.max_abs_displacement for item in aligned],
            dtype=float,
        ),
        raw_tube_radius=summary.raw_radius,
        calibrated_tube_radius=calibrated_radius,
        max_abs_displacement=float(np.max(np.abs(summary.signed))),
        stability_score=stability_score,
        bootstrap_success_count=len(aligned),
        bootstrap_failure_count=summary.failed_count,
        status="CALIBRATED_TUBE" if calibrated else "UNCALIBRATED_STABILITY",
        calibration_factor=(
            float(calibration["calibration_factor"])
            if calibrated
            else None
        ),
        calibration_pointwise_coverage=(
            float(calibration["calibration_pointwise_coverage"])
            if calibrated
            else None
        ),
        calibration_simultaneous_coverage=(
            float(calibration["calibration_simultaneous_coverage"])
            if calibrated
            else None
        ),
        calibration_shape_ids=shape_ids,
        diagnostics={
            "status": "CALIBRATED_TUBE" if calibrated else "UNCALIBRATED_STABILITY",
            "uncertainty_method": "normalized_arclength_cyclic_alignment_signed_normal",
            "stability_score_role": "uncalibrated_geometric_stability_only",
            "bootstrap_replica_count": len(replicas),
            "bootstrap_success_fraction": success_fraction,
            "raw_tube_quantile": float(cfg.raw_tube_quantile),
            "signed_normal_rms": signed_rms,
            "tangential_residual_rms": tangential_rms,
            **calibration,
        },
    )


estimate_boundary_uncertainty_v3 = estimate_boundary_stability


__all__ = [
    "AlignedBoundaryReplica",
    "BoundaryCalibrationCase",
    "BoundaryStabilityConfig",
    "BoundaryStabilityEstimate",
    "BoundaryStabilityFailure",
    "BoundaryStabilityResult",
    "RegisteredBoundaryCurve",
    "align_boundary_replica",
    "estimate_boundary_stability",
    "estimate_boundary_uncertainty_v3",
    "normalize_boundary_curve",
]
