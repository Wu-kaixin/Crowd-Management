"""PR6 paired held-out nonconvex boundary and confidence evaluation."""
from __future__ import annotations

import csv
import hashlib
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np

from ..controllers import PeriodicArcCVTConfig, equal_arc_target_s, plan_periodic_arc_coverage
from ..estimation import BoundaryEstimateFailure, BoundaryEstimateV2, BoundaryV2Config, estimate_boundary_v2
from ..geometry import resample_closed_curve_by_arclength
from ..types import Array


@dataclass(frozen=True)
class PR6EvaluationConfig:
    """Paired-seed PR6 evaluation configuration."""

    seeds: tuple[int, ...] = tuple(range(30))
    shapes: tuple[str, ...] = ("u_shape", "c_shape")
    observation_count: int = 280
    bootstrap_samples: int = 12
    confidence_interval_resamples: int = 2000
    alpha_scale: float = 2.5
    alpha_smoothing_passes: int = 5
    sample_spacing: float = 0.06
    required_arc_gap: float = 1.5
    max_guides: int = 12
    workers: int = 4

    def __post_init__(self) -> None:
        if len(self.seeds) == 0 or len(set(self.seeds)) != len(self.seeds):
            raise ValueError("seeds must be a non-empty unique tuple.")
        if any(isinstance(seed, bool) or int(seed) != seed for seed in self.seeds):
            raise ValueError("seeds must contain integers.")
        allowed = {"u_shape", "c_shape"}
        if len(self.shapes) == 0 or not set(self.shapes).issubset(allowed):
            raise ValueError("shapes must select u_shape and/or c_shape.")
        for name in ("observation_count", "confidence_interval_resamples", "max_guides", "workers"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or value < 1:
                raise ValueError(f"{name} must be a positive integer.")
        if self.bootstrap_samples < 1:
            raise ValueError("bootstrap_samples must be positive for PR6 evaluation.")
        for name in ("alpha_scale", "sample_spacing", "required_arc_gap"):
            value = float(getattr(self, name))
            if not np.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and positive.")
        if self.alpha_smoothing_passes < 0:
            raise ValueError("alpha_smoothing_passes must be non-negative.")


def _polygon_for_shape(shape: str) -> Array:
    if shape == "u_shape":
        return np.array(
            [[2.0, 2.0], [6.0, 2.0], [6.0, 6.0], [5.0, 6.0], [5.0, 3.0], [3.0, 3.0], [3.0, 6.0], [2.0, 6.0]],
            dtype=float,
        )
    if shape == "c_shape":
        return np.array(
            [[2.0, 2.0], [6.0, 2.0], [6.0, 3.0], [3.5, 3.0], [3.5, 5.0], [6.0, 5.0], [6.0, 6.0], [2.0, 6.0]],
            dtype=float,
        )
    raise ValueError(f"unsupported held-out shape: {shape}")


def _points_inside_polygon(points: Array, polygon: Array) -> Array:
    x = points[:, 0]
    y = points[:, 1]
    inside = np.zeros(len(points), dtype=bool)
    previous = polygon[-1]
    for current in polygon:
        crosses = (current[1] > y) != (previous[1] > y)
        denominator = previous[1] - current[1]
        if abs(denominator) > 1.0e-15:
            crossing_x = (previous[0] - current[0]) * (y - current[1]) / denominator + current[0]
            inside ^= crosses & (x < crossing_x)
        previous = current
    return inside


def _heldout_case(shape: str, seed: int, count: int, spacing: float) -> tuple[Array, Array]:
    polygon = _polygon_for_shape(shape)
    rng = np.random.default_rng(100_000 + int(seed) + (0 if shape == "u_shape" else 10_000))
    accepted: list[Array] = []
    accepted_count = 0
    while accepted_count < count:
        candidates = rng.uniform(np.min(polygon, axis=0), np.max(polygon, axis=0), size=(count, 2))
        batch = candidates[_points_inside_polygon(candidates, polygon)]
        accepted.append(batch)
        accepted_count += len(batch)
    observation = np.vstack(accepted)[:count]
    truth, _, _, _, _ = resample_closed_curve_by_arclength(polygon, spacing=spacing)
    return observation, truth


def _symmetric_curve_errors(estimate: Array, truth: Array) -> tuple[float, float]:
    distances = np.linalg.norm(estimate[:, None, :] - truth[None, :, :], axis=2)
    estimate_to_truth = np.min(distances, axis=1)
    truth_to_estimate = np.min(distances, axis=0)
    chamfer = 0.5 * (float(np.mean(estimate_to_truth)) + float(np.mean(truth_to_estimate)))
    hausdorff = max(float(np.max(estimate_to_truth)), float(np.max(truth_to_estimate)))
    return chamfer, hausdorff


def _truth_length(truth: Array) -> float:
    return float(np.sum(np.linalg.norm(np.roll(truth, -1, axis=0) - truth, axis=1)))


def _estimator_configs(config: PR6EvaluationConfig) -> dict[str, BoundaryV2Config]:
    common = {
        "safety_distance": 0.0,
        "sample_spacing": config.sample_spacing,
        "min_observation_coverage": 0.8,
    }
    return {
        "radial_neutral": BoundaryV2Config(
            estimator="radial",
            radial_bins=72,
            radial_smoothing_passes=3,
            bootstrap_samples=0,
            safety_distance=0.0,
            sample_spacing=config.sample_spacing,
            min_observation_coverage=0.6,
        ),
        "alpha_neutral": BoundaryV2Config(
            estimator="alpha",
            alpha_scale=config.alpha_scale,
            alpha_smoothing_passes=config.alpha_smoothing_passes,
            bootstrap_samples=0,
            **common,
        ),
        "alpha_bootstrap_gain": BoundaryV2Config(
            estimator="alpha",
            alpha_scale=config.alpha_scale,
            alpha_smoothing_passes=config.alpha_smoothing_passes,
            bootstrap_samples=config.bootstrap_samples,
            bootstrap_min_success_fraction=0.5,
            bootstrap_confidence_floor=0.15,
            **common,
        ),
    }


def _neutralize_confidence(boundary: BoundaryEstimateV2) -> BoundaryEstimateV2:
    return replace(
        boundary,
        confidence=np.ones_like(boundary.confidence),
        diagnostics={
            **boundary.diagnostics,
            "confidence_status": "bootstrap_computed_but_gain_ablated_pr6",
        },
    )


def _evaluate_boundary(
    boundary: BoundaryEstimateV2 | BoundaryEstimateFailure,
    truth: Array,
    planner_confidence: bool,
    config: PR6EvaluationConfig,
) -> tuple[dict[str, Any], Array | None]:
    if isinstance(boundary, BoundaryEstimateFailure):
        return {
            "valid": False,
            "boundary_status": boundary.status,
            "boundary_reason": str(boundary.diagnostics.get("reason", "unknown")),
            "boundary_method": boundary.method,
            "curve_chamfer": None,
            "curve_hausdorff": None,
            "length_relative_error": None,
            "confidence_mean": None,
            "confidence_min": None,
            "uncertainty_mean": None,
            "plan_status": "PLAN_SKIPPED_BOUNDARY_INVALID",
            "plan_h_initial": None,
            "plan_h_final": None,
            "plan_iterations": 0,
            "plan_max_arc_gap": None,
        }, None

    curve_chamfer, curve_hausdorff = _symmetric_curve_errors(boundary.curve_points, truth)
    truth_length = _truth_length(truth)
    planner_boundary = boundary if planner_confidence else _neutralize_confidence(boundary)
    guide_count = min(
        config.max_guides,
        max(3, int(np.ceil(boundary.length / config.required_arc_gap))),
    )
    equal = equal_arc_target_s(boundary.length, guide_count)
    phase = np.arange(guide_count, dtype=float)
    uneven = np.sort(
        np.mod(
            equal + 0.18 * (boundary.length / guide_count) * np.sin(2.0 * np.pi * phase / guide_count + 0.3),
            boundary.length,
        )
    )
    plan = plan_periodic_arc_coverage(
        planner_boundary,
        guide_count,
        PeriodicArcCVTConfig(
            max_iterations=300,
            h_tolerance=1.0e-8,
            target_tolerance=1.0e-6,
        ),
        init=uneven,
    )
    return {
        "valid": True,
        "boundary_status": "VALID",
        "boundary_reason": "valid",
        "boundary_method": boundary.method,
        "curve_chamfer": curve_chamfer,
        "curve_hausdorff": curve_hausdorff,
        "length_relative_error": abs(boundary.length - truth_length) / truth_length,
        "confidence_mean": float(np.mean(boundary.confidence)),
        "confidence_min": float(np.min(boundary.confidence)),
        "uncertainty_mean": float(np.mean(boundary.uncertainty)),
        "plan_status": plan.status,
        "plan_h_initial": float(plan.h_history[0]),
        "plan_h_final": float(plan.h_history[-1]),
        "plan_iterations": int(len(plan.gain_history)),
        "plan_max_arc_gap": float(plan.max_arc_gap),
    }, boundary.curve_points


def _percentile_interval(values: Array, rng: np.random.Generator, resamples: int) -> dict[str, float | int | None]:
    array = np.asarray(values, dtype=float)
    if len(array) == 0:
        return {"n": 0, "mean": None, "ci95_low": None, "ci95_high": None}
    indices = rng.integers(0, len(array), size=(resamples, len(array)))
    bootstrap_means = np.mean(array[indices], axis=1)
    return {
        "n": int(len(array)),
        "mean": float(np.mean(array)),
        "ci95_low": float(np.percentile(bootstrap_means, 2.5)),
        "ci95_high": float(np.percentile(bootstrap_means, 97.5)),
    }


def _aggregate_records(records: list[dict[str, Any]], config: PR6EvaluationConfig) -> dict[str, Any]:
    rng = np.random.default_rng(731_991)
    aggregate: dict[str, Any] = {}
    variants = sorted({str(record["variant"]) for record in records})
    for shape in config.shapes:
        aggregate[shape] = {}
        for variant in variants:
            subset = [record for record in records if record["shape"] == shape and record["variant"] == variant]
            valid = [record for record in subset if record["valid"]]
            aggregate[shape][variant] = {
                "run_count": len(subset),
                "valid_count": len(valid),
                "failure_count": len(subset) - len(valid),
                "failure_rate": float((len(subset) - len(valid)) / len(subset)),
                "curve_chamfer": _percentile_interval(
                    np.asarray([record["curve_chamfer"] for record in valid]),
                    rng,
                    config.confidence_interval_resamples,
                ),
                "curve_hausdorff": _percentile_interval(
                    np.asarray([record["curve_hausdorff"] for record in valid]),
                    rng,
                    config.confidence_interval_resamples,
                ),
                "length_relative_error": _percentile_interval(
                    np.asarray([record["length_relative_error"] for record in valid]),
                    rng,
                    config.confidence_interval_resamples,
                ),
                "plan_iterations": _percentile_interval(
                    np.asarray([record["plan_iterations"] for record in valid]),
                    rng,
                    config.confidence_interval_resamples,
                ),
            }
    return aggregate


def _paired_comparisons(records: list[dict[str, Any]], config: PR6EvaluationConfig) -> dict[str, Any]:
    rng = np.random.default_rng(812_377)
    by_key = {(record["shape"], record["seed"], record["variant"]): record for record in records}
    comparisons: dict[str, Any] = {}
    for shape in config.shapes:
        comparisons[shape] = {}
        for candidate, baseline in (
            ("alpha_neutral", "radial_neutral"),
            ("alpha_bootstrap_gain", "radial_neutral"),
            ("alpha_bootstrap_gain", "alpha_bootstrap_no_gain"),
        ):
            name = f"{candidate}_minus_{baseline}"
            comparisons[shape][name] = {}
            for metric in ("curve_chamfer", "curve_hausdorff", "plan_iterations"):
                differences: list[float] = []
                for seed in config.seeds:
                    candidate_record = by_key[(shape, seed, candidate)]
                    baseline_record = by_key[(shape, seed, baseline)]
                    if candidate_record[metric] is None or baseline_record[metric] is None:
                        continue
                    differences.append(float(candidate_record[metric]) - float(baseline_record[metric]))
                interval = _percentile_interval(np.asarray(differences), rng, config.confidence_interval_resamples)
                interval["win_rate_lower_is_better"] = (
                    float(np.mean(np.asarray(differences) < 0.0)) if differences else None
                )
                comparisons[shape][name][metric] = interval
    return comparisons


def _repository_snapshot(repo: Path, source_paths: list[Path]) -> dict[str, Any]:
    def git(*args: str) -> str:
        result = subprocess.run(["git", *args], cwd=repo, check=False, capture_output=True, text=True)
        return result.stdout.strip() if result.returncode == 0 else "unknown"

    digest = hashlib.sha256()
    for path in sorted(source_paths):
        digest.update(str(path.relative_to(repo)).encode("utf-8"))
        digest.update(path.read_bytes())
    dirty_entries = [line for line in git("status", "--porcelain").splitlines() if line]
    return {
        "commit": git("rev-parse", "HEAD"),
        "branch": git("branch", "--show-current"),
        "dirty": bool(dirty_entries),
        "dirty_entry_count": len(dirty_entries),
        "source_sha256": digest.hexdigest(),
        "frozen_commit": not dirty_entries,
        "freeze_status": "FROZEN_COMMIT" if not dirty_entries else "UNFROZEN_DIRTY_WORKTREE",
    }


def _save_failure_gallery(
    output: Path,
    records: list[dict[str, Any]],
    visuals: dict[tuple[str, int, str], tuple[Array, Array, Array | None]],
) -> list[dict[str, Any]]:
    selected = [record for record in records if not record["valid"]]
    selected.sort(key=lambda record: (str(record["shape"]), int(record["seed"]), str(record["variant"])))
    if len(selected) < 6:
        valid_worst = [record for record in records if record["valid"]]
        valid_worst.sort(key=lambda record: float(record["curve_hausdorff"]), reverse=True)
        selected.extend(valid_worst[: 6 - len(selected)])
    selected = selected[:6]

    gallery_records: list[dict[str, Any]] = []
    for record in selected:
        gallery_records.append(
            {
                "shape": record["shape"],
                "seed": record["seed"],
                "variant": record["variant"],
                "selection_role": "failure" if not record["valid"] else "worst_valid_case",
                "boundary_status": record["boundary_status"],
                "boundary_reason": record["boundary_reason"],
                "curve_hausdorff": record["curve_hausdorff"],
            }
        )

    os.environ.setdefault("MPLCONFIGDIR", str((output / ".mplconfig").resolve()))
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(2, 3, figsize=(13, 8))
    for axis, record in zip(axes.ravel(), selected, strict=False):
        observation, truth, estimate = visuals[(record["shape"], record["seed"], record["variant"])]
        axis.scatter(observation[:, 0], observation[:, 1], s=5, alpha=0.25, label="observation")
        axis.plot(*np.vstack((truth, truth[0])).T, color="black", linewidth=1.5, label="truth")
        if estimate is not None:
            axis.plot(*np.vstack((estimate, estimate[0])).T, color="tab:red", linewidth=1.2, label="estimate")
        axis.set_title(
            f"{record['shape']} seed={record['seed']}\n{record['variant']} {record['boundary_status']}"
        )
        axis.set_aspect("equal")
    for axis in axes.ravel()[len(selected) :]:
        axis.axis("off")
    handles, labels = axes.ravel()[0].get_legend_handles_labels()
    figure.legend(handles, labels, loc="lower center", ncol=3)
    figure.tight_layout(rect=(0.0, 0.05, 1.0, 1.0))
    figure.savefig(output / "failure_gallery.png", dpi=150)
    plt.close(figure)
    return gallery_records


def _write_markdown_report(
    output: Path,
    config: PR6EvaluationConfig,
    aggregate: dict[str, Any],
    paired: dict[str, Any],
    snapshot: dict[str, Any],
    gallery: list[dict[str, Any]],
) -> None:
    lines = [
        "# ABCG-v2 Step 1 PR6 Paired Robust Evaluation",
        "",
        f"- Paired seeds: {len(config.seeds)} (`{min(config.seeds)}` through `{max(config.seeds)}`)",
        f"- Held-out shapes: {', '.join(config.shapes)}",
        f"- Variants: radial neutral, alpha neutral, alpha bootstrap gain, alpha bootstrap gain ablated",
        f"- Repository freeze status: `{snapshot['freeze_status']}`",
        f"- Source SHA-256: `{snapshot['source_sha256']}`",
        "",
        "## Aggregate boundary error",
        "",
        "| Shape | Variant | Valid/total | Chamfer mean [95% CI] | Hausdorff mean [95% CI] |",
        "| --- | --- | --- | --- | --- |",
    ]
    for shape in config.shapes:
        for variant, values in aggregate[shape].items():
            chamfer = values["curve_chamfer"]
            hausdorff = values["curve_hausdorff"]
            lines.append(
                f"| {shape} | {variant} | {values['valid_count']}/{values['run_count']} | "
                f"{chamfer['mean']} [{chamfer['ci95_low']}, {chamfer['ci95_high']}] | "
                f"{hausdorff['mean']} [{hausdorff['ci95_low']}, {hausdorff['ci95_high']}] |"
            )
    lines.extend(
        [
            "",
            "## Evidence boundary",
            "",
            "Results are paired synthetic boundary-reconstruction evidence. They do not prove continuous-time safety,",
            "human containment efficacy, or performance on real sensor data. Invalid runs remain in the denominator.",
            "Confidence gates Lloyd step size only; it is not treated as risk density.",
            "The radial geometry baseline uses a relaxed 0.60 observation-coverage validity threshold versus 0.80",
            "for alpha variants so its non-star reconstruction error remains measurable; failure rates are not compared",
            "as though those thresholds were identical.",
            "",
            f"Failure gallery entries: {len(gallery)}.",
            "",
            "The complete paired differences and bootstrap confidence intervals are in `paired_comparisons.json`.",
            "G6 cannot be called fully frozen while the repository snapshot reports `UNFROZEN_DIRTY_WORKTREE`.",
        ]
    )
    (output / "PR6_EVALUATION_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _run_paired_case(
    shape: str,
    seed: int,
    config: PR6EvaluationConfig,
    estimator_configs: dict[str, BoundaryV2Config],
) -> tuple[list[dict[str, Any]], dict[tuple[str, int, str], tuple[Array, Array, Array | None]]]:
    observation, truth = _heldout_case(shape, seed, config.observation_count, config.sample_spacing / 2.0)
    estimates = {
        name: estimate_boundary_v2(
            observation,
            estimator_config,
            np.random.default_rng(10_000_000 + seed),
        )
        for name, estimator_config in estimator_configs.items()
    }
    variants: dict[str, tuple[BoundaryEstimateV2 | BoundaryEstimateFailure, bool]] = {
        "radial_neutral": (estimates["radial_neutral"], False),
        "alpha_neutral": (estimates["alpha_neutral"], False),
        "alpha_bootstrap_gain": (estimates["alpha_bootstrap_gain"], True),
        "alpha_bootstrap_no_gain": (estimates["alpha_bootstrap_gain"], False),
    }
    case_records: list[dict[str, Any]] = []
    case_visuals: dict[tuple[str, int, str], tuple[Array, Array, Array | None]] = {}
    for variant, (boundary, planner_confidence) in variants.items():
        values, curve = _evaluate_boundary(boundary, truth, planner_confidence, config)
        estimator_key = (
            "radial_neutral"
            if variant == "radial_neutral"
            else "alpha_neutral"
            if variant == "alpha_neutral"
            else "alpha_bootstrap_gain"
        )
        record = {
            "shape": shape,
            "seed": int(seed),
            "variant": variant,
            "min_observation_coverage": estimator_configs[estimator_key].min_observation_coverage,
            **values,
        }
        case_records.append(record)
        case_visuals[(shape, int(seed), variant)] = (observation, truth, curve)
    return case_records, case_visuals


def run_pr6_evaluation(output_dir: str | Path, config: PR6EvaluationConfig) -> dict[str, Any]:
    """Run paired PR6 variants and save finite auditable summaries."""
    if not isinstance(config, PR6EvaluationConfig):
        raise TypeError("config must be PR6EvaluationConfig.")
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    estimator_configs = _estimator_configs(config)
    records: list[dict[str, Any]] = []
    visuals: dict[tuple[str, int, str], tuple[Array, Array, Array | None]] = {}

    cases = [(shape, seed) for shape in config.shapes for seed in config.seeds]
    with ThreadPoolExecutor(max_workers=min(config.workers, len(cases))) as executor:
        case_results = list(
            executor.map(
                lambda case: _run_paired_case(case[0], case[1], config, estimator_configs),
                cases,
            )
        )
    for case_records, case_visuals in case_results:
        records.extend(case_records)
        visuals.update(case_visuals)
    records.sort(key=lambda record: (str(record["shape"]), int(record["seed"]), str(record["variant"])))

    aggregate = _aggregate_records(records, config)
    paired = _paired_comparisons(records, config)
    repo = Path(__file__).resolve().parents[3]
    source_paths = [
        repo / "src" / "crowd_management" / "estimation" / "boundary_v2.py",
        repo / "src" / "crowd_management" / "controllers" / "periodic_arc_cvt.py",
        Path(__file__).resolve(),
        repo / "scripts" / "run_step1_pr6_evaluation.py",
    ]
    snapshot = _repository_snapshot(repo, source_paths)

    with open(output / "records.json", "w", encoding="utf-8") as file:
        json.dump(records, file, indent=2)
    with open(output / "records.csv", "w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(records[0].keys()))
        writer.writeheader()
        writer.writerows(records)
    with open(output / "aggregate.json", "w", encoding="utf-8") as file:
        json.dump(aggregate, file, indent=2)
    with open(output / "paired_comparisons.json", "w", encoding="utf-8") as file:
        json.dump(paired, file, indent=2)
    with open(output / "evaluation_config.json", "w", encoding="utf-8") as file:
        json.dump(asdict(config), file, indent=2)
    with open(output / "evaluation_snapshot.json", "w", encoding="utf-8") as file:
        json.dump(snapshot, file, indent=2)

    gallery = _save_failure_gallery(output, records, visuals)
    with open(output / "failure_gallery.json", "w", encoding="utf-8") as file:
        json.dump(gallery, file, indent=2)
    _write_markdown_report(output, config, aggregate, paired, snapshot, gallery)

    evidence = {
        "paired_seed_count": len(config.seeds),
        "heldout_shape_count": len(config.shapes),
        "variant_count": len({record["variant"] for record in records}),
        "record_count": len(records),
        "all_records_accounted_for": len(records) == len(config.seeds) * len(config.shapes) * 4,
        "confidence_intervals_present": True,
        "failure_gallery_present": (output / "failure_gallery.png").is_file(),
        "frozen_commit": snapshot["frozen_commit"],
        "g6_status": "PASS" if snapshot["frozen_commit"] else "UNMET_FROZEN_COMMIT",
    }
    with open(output / "gate_evidence.json", "w", encoding="utf-8") as file:
        json.dump(evidence, file, indent=2)
    return evidence
