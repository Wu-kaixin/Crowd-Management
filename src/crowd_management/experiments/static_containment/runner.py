"""Top-level static containment runner."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
import yaml

from ...containment_metrics import containment_summary
from ...controllers import (
    ABCGv2Controller,
    PeriodicArcCVTConfig,
    ResourcePolicy,
    assign_guides_to_targets,
    plan_periodic_arc_coverage,
)
from ...crowd import generate_static_crowd, generate_static_crowd_truth
from ...estimation import BoundaryEstimateFailure, BoundaryEstimateV2, estimate_boundary_v2
from .artifacts import (
    _build_manifest,
    _save_assignment_artifacts,
    _save_boundary_v2_artifacts,
    _save_episode_artifacts,
    _save_periodic_plan_artifacts,
    _save_resource_decision,
)
from .config import StaticContainmentConfig
from .methods import _controller_targets


def run_static_containment(
    config_path: str | Path,
    output_dir: str | Path,
    methods: list[str] | None = None,
    save_plots: bool = True,
) -> dict[str, dict[str, float | int | str]]:
    config_path = Path(config_path)
    cfg = StaticContainmentConfig.from_yaml(config_path)
    crowd_points = generate_static_crowd(cfg.crowd)
    truth = generate_static_crowd_truth(cfg.crowd, safety_distance=cfg.safety_distance)
    boundary_v2 = estimate_boundary_v2(crowd_points, cfg.boundary_v2, np.random.default_rng(cfg.seed))
    resource_decision = (
        ResourcePolicy(cfg.resource_policy).decide(boundary_v2.length, cfg.guide_count)
        if isinstance(boundary_v2, BoundaryEstimateV2)
        else None
    )
    periodic_plan = (
        plan_periodic_arc_coverage(boundary_v2, resource_decision.active_count, PeriodicArcCVTConfig())
        if isinstance(boundary_v2, BoundaryEstimateV2)
        and resource_decision is not None
        and resource_decision.active_count > 0
        else None
    )
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(output / "crowd_points.npz", positions=crowd_points)
    np.savez_compressed(
        output / "crowd_truth.npz",
        crowd_points=crowd_points,
        boundary_points=truth.boundary_points,
        safety_points=truth.safety_points,
        component_ids=truth.component_ids,
        component_count=np.array(truth.component_count, dtype=int),
        truth_valid=np.array(truth.valid, dtype=bool),
        truth_status=np.array(truth.status),
        shape=np.array(truth.shape),
    )
    _save_boundary_v2_artifacts(output, boundary_v2)
    _save_resource_decision(output, resource_decision)
    _save_periodic_plan_artifacts(output, periodic_plan)

    methods = methods or ["random", "static_circle", "legacy_center_radius", "abcg"]
    resolved_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    with open(output / "config_resolved.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(resolved_config, f, sort_keys=False, allow_unicode=True)
    results: dict[str, dict[str, float | int | str]] = {}
    assignment_records: dict[str, dict[str, object]] = {}
    episode_records: dict[str, dict[str, object]] = {}
    for method in methods:
        targets, boundary = _controller_targets(method, cfg, crowd_points)
        initial_summary = containment_summary(
            targets,
            crowd_points,
            boundary,
            cfg.coverage_radius,
            cfg.safety_distance,
            truth_boundary=truth,
        )
        geometry_valid = isinstance(boundary_v2, BoundaryEstimateV2)
        plan_valid = periodic_plan is not None and periodic_plan.status == "VALID" and periodic_plan.converged
        resource_status = (
            resource_decision.status if resource_decision is not None else "RESOURCE_SKIPPED_BOUNDARY_INVALID"
        )
        assignment_result = (
            assign_guides_to_targets(targets, periodic_plan.target_xy, cfg.assignment)
            if plan_valid and periodic_plan is not None
            else None
        )
        if isinstance(boundary_v2, BoundaryEstimateFailure):
            episode_skipped_status = boundary_v2.status
        elif periodic_plan is None or not plan_valid:
            episode_skipped_status = "DEGRADED"
        elif assignment_result is None:
            episode_skipped_status = "ASSIGNMENT_INFEASIBLE"
        else:
            episode_skipped_status = "DEGRADED"
        episode_result = (
            ABCGv2Controller(cfg.motion, cfg.safety).run_fixed_target_episode(
                targets,
                periodic_plan.target_xy,
                assignment_result,
                precondition_status=resource_status,
                crowd_points=crowd_points,
                room_size=cfg.room_size,
            )
            if periodic_plan is not None and assignment_result is not None
            else None
        )
        final_guide_points = episode_result.positions[-1] if episode_result is not None else targets
        summary = containment_summary(
            final_guide_points,
            crowd_points,
            boundary,
            cfg.coverage_radius,
            cfg.safety_distance,
            truth_boundary=truth,
        )
        summary["metrics_position_source"] = (
            "episode_final_frame" if episode_result is not None else "endpoint_baseline_no_episode"
        )
        summary["initial_endpoint_coverage_ratio"] = initial_summary["coverage_ratio"]
        summary["initial_endpoint_max_euclidean_boundary_distance"] = initial_summary[
            "max_euclidean_boundary_distance"
        ]
        summary["boundary_v2_status"] = "VALID" if geometry_valid else boundary_v2.status
        summary["boundary_v2_method"] = boundary_v2.method
        summary["boundary_confidence_status"] = boundary_v2.diagnostics.get(
            "confidence_status", "not_available"
        )
        summary["periodic_plan_status"] = (
            periodic_plan.status if periodic_plan is not None else "PLAN_SKIPPED_BOUNDARY_INVALID"
        )
        summary["periodic_max_arc_gap"] = (
            float(periodic_plan.max_arc_gap) if periodic_plan is not None else "not_available"
        )
        summary["resource_status"] = resource_status
        summary["active_guide_count"] = resource_decision.active_count if resource_decision is not None else 0
        summary["reserve_guide_count"] = resource_decision.reserve_count if resource_decision is not None else 0
        summary["resource_unmet_target_count"] = (
            resource_decision.unmet_target_count if resource_decision is not None else 0
        )
        summary["assignment_status"] = (
            assignment_result.status if assignment_result is not None else "ASSIGNMENT_SKIPPED_PLAN_INVALID"
        )
        summary["assignment_switch_count"] = assignment_result.switch_count if assignment_result is not None else 0
        summary["episode_status"] = episode_result.status if episode_result is not None else episode_skipped_status
        summary["episode_control_steps"] = len(episode_result.applied_controls) if episode_result is not None else 0
        summary["episode_final_tracking_rmse"] = (
            float(episode_result.tracking_rmse[-1]) if episode_result is not None else "not_available"
        )
        summary["safety_filter_status"] = (
            episode_result.diagnostics.get("safety_filter_status", "not_available")
            if episode_result is not None
            else "not_available"
        )
        summary["safety_projected_steps"] = (
            int(episode_result.diagnostics.get("safety_projected_steps", 0))
            if episode_result is not None
            else 0
        )
        summary["safety_infeasible_steps"] = (
            int(episode_result.diagnostics.get("safety_infeasible_steps", 0))
            if episode_result is not None
            else 0
        )
        summary["safety_max_residual_after"] = (
            float(episode_result.diagnostics.get("safety_max_residual_after", 0.0))
            if episode_result is not None
            else "not_available"
        )
        summary["method_status"] = (
            "converged_pr5_safety_filtered_episode"
            if truth.valid
            and geometry_valid
            and resource_status == "VALID"
            and plan_valid
            and assignment_result is not None
            and assignment_result.status == "VALID"
            and episode_result is not None
            and episode_result.status == "CONVERGED"
            else "diagnostic_only"
        )
        results[method] = summary
        method_dir = output / method
        method_dir.mkdir(parents=True, exist_ok=True)
        assignment_records[method] = _save_assignment_artifacts(method_dir, assignment_result)
        episode_records[method] = _save_episode_artifacts(method_dir, episode_result, episode_skipped_status)
        np.savez_compressed(
            method_dir / "containment_state.npz",
            crowd_points=crowd_points,
            guide_points=final_guide_points,
            guide_initial_points=targets,
            guide_final_points=final_guide_points,
            boundary_points=boundary.boundary_points,
            safety_points=boundary.safety_points,
            center=boundary.center,
        )
        with open(method_dir / "metrics.json", "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        if save_plots:
            from ...containment_visualization import plot_static_containment

            plot_static_containment(
                crowd_points,
                final_guide_points,
                boundary,
                method_dir / "containment.png",
                title=f"{method}: static containment",
            )

    with open(output / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(
            _build_manifest(
                config_path,
                cfg,
                methods,
                truth,
                boundary_v2,
                resource_decision,
                periodic_plan,
                assignment_records,
                episode_records,
            ),
            f,
            indent=2,
        )

    with open(output / "summary.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    with open(output / "summary.csv", "w", encoding="utf-8", newline="") as f:
        fieldnames = ["method", *next(iter(results.values())).keys()]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for method, row in results.items():
            writer.writerow({"method": method, **row})
    return results
