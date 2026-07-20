"""Regenerate README Visual Overview media for ABCG-v2 Step 1.

Outputs under ``reports/media/``:

- ``abcg_static_containment_grid.png`` / ``.gif`` / ``abcg_metrics_summary.png``
  illustrative static deployments on circle, ellipse, irregular, and two-cluster crowds
- ``step1_g6_scenarios.png`` formal G6 scenario shapes (circle, ellipse, U, C)
- ``step1_baseline_comparison.png`` random / static-circle / legacy / ABCG baselines
- ``step1_closed_loop.gif`` fixed-target feedback episode on an ellipse crowd
- ``step1_g6_success_rates.png`` committed G6 primary success rates
- ``step1_failure_gallery.png`` copy of the formal G6 actual-failure gallery
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.animation import PillowWriter

from crowd_management.containment_metrics import containment_summary
from crowd_management.controllers import (
    ABCGController,
    ABCGv2Config,
    ABCGv2Controller,
    AssignmentConfig,
    LegacyCenterRadiusController,
    RandomDeploymentController,
    StaticCircleController,
    VelocitySafetyConfig,
    assign_guides_to_targets,
    integrate_guide_positions,
    plan_equal_arc_coverage,
)
from crowd_management.crowd import StaticCrowdConfig, generate_static_crowd, generate_static_crowd_truth
from crowd_management.estimation import BoundaryEstimateFailure, BoundaryV2Config, estimate_boundary_v2


MEDIA_DIR = Path("reports/media")
G6_REPORT_DIR = Path("reports/step1_g6_compliance")
ROOM = np.array([20.0, 14.0], dtype=float)
G6_ROOM = np.array([10.0, 10.0], dtype=float)

SCENARIOS = [
    ("Circle", {"shape": "circle", "count": 180, "center": [10, 7], "radius": 2.2, "noise_std": 0.05}, 8, 72, 0),
    (
        "Ellipse",
        {"shape": "ellipse", "count": 220, "center": [10, 7], "axes": [3.2, 1.35], "rotation_deg": 24, "noise_std": 0.05},
        9,
        96,
        1,
    ),
    (
        "Nonconvex",
        {"shape": "nonconvex", "count": 240, "center": [10, 7], "radius": 2.35, "radial_jitter": 0.09, "noise_std": 0.05},
        10,
        108,
        2,
    ),
    (
        "Two clusters",
        {"shape": "two_cluster", "count": 240, "center": [10, 7], "radius": 2.0, "lobe_offset": 1.25, "noise_std": 0.05},
        10,
        108,
        3,
    ),
]

G6_LABELS = {
    "circle": "Circle",
    "ellipse": "Ellipse",
    "u_shape": "Held-out U",
    "c_shape": "Held-out C",
}


def _closed(points: np.ndarray) -> np.ndarray:
    return np.vstack([points, points[0]])


def _polygon_for_shape(shape: str) -> np.ndarray:
    if shape == "u_shape":
        return np.array(
            [[2.0, 2.0], [8.0, 2.0], [8.0, 7.5], [6.6, 7.5], [6.6, 3.7], [3.4, 3.7], [3.4, 7.5], [2.0, 7.5]],
            dtype=float,
        )
    if shape == "c_shape":
        return np.array(
            [[2.0, 2.0], [8.0, 2.0], [8.0, 3.4], [4.0, 3.4], [4.0, 6.1], [8.0, 6.1], [8.0, 7.5], [2.0, 7.5]],
            dtype=float,
        )
    raise ValueError(f"unsupported polygon shape: {shape}")


def _inside_polygon(points: np.ndarray, polygon: np.ndarray) -> np.ndarray:
    x, y = points[:, 0], points[:, 1]
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


def _sample_polygon(polygon: np.ndarray, count: int, rng: np.random.Generator) -> np.ndarray:
    accepted: list[np.ndarray] = []
    total = 0
    while total < count:
        candidates = rng.uniform(np.min(polygon, axis=0), np.max(polygon, axis=0), size=(max(count, 64), 2))
        batch = candidates[_inside_polygon(candidates, polygon)]
        accepted.append(batch)
        total += len(batch)
    return np.vstack(accepted)[:count]


def _g6_observation(scenario: str, seed: int = 0, count: int = 120) -> np.ndarray:
    rng = np.random.default_rng(1_000_003 + 1009 * int(seed) + 65_537 * ("circle", "ellipse", "u_shape", "c_shape").index(scenario))
    if scenario == "circle":
        angles = rng.uniform(0.0, 2.0 * np.pi, count)
        radii = 2.0 * np.sqrt(rng.uniform(0.0, 1.0, count))
        return np.column_stack((5.0 + radii * np.cos(angles), 5.0 + radii * np.sin(angles)))
    if scenario == "ellipse":
        angles = rng.uniform(0.0, 2.0 * np.pi, count)
        radii = np.sqrt(rng.uniform(0.0, 1.0, count))
        return np.column_stack((5.0 + 2.5 * radii * np.cos(angles), 5.0 + 1.35 * radii * np.sin(angles)))
    return _sample_polygon(_polygon_for_shape(scenario), count, rng)


def _boundary_config() -> BoundaryV2Config:
    return BoundaryV2Config(
        estimator="alpha",
        safety_distance=0.8,
        sample_spacing=0.08,
        room_size=(10.0, 10.0),
        room_margin=0.2,
        alpha_scale=2.5,
        bootstrap_samples=0,
    )


def _draw_scene(
    ax,
    crowd_points: np.ndarray,
    guide_points: np.ndarray,
    boundary_points: np.ndarray | None = None,
    safety_points: np.ndarray | None = None,
    title: str = "",
    xlim: tuple[float, float] | None = None,
    ylim: tuple[float, float] | None = None,
    legend: bool = False,
) -> None:
    ax.scatter(crowd_points[:, 0], crowd_points[:, 1], s=8, c="#4c78a8", alpha=0.48, label="crowd")
    if boundary_points is not None and len(boundary_points):
        ax.plot(*_closed(boundary_points).T, c="#1f4e79", lw=1.3, label="estimated boundary")
    if safety_points is not None and len(safety_points):
        ax.plot(*_closed(safety_points).T, c="#f28e2b", lw=1.5, ls="--", label="safety boundary")
    ax.scatter(guide_points[:, 0], guide_points[:, 1], s=70, c="#e15759", edgecolor="white", lw=0.8, label="guides")
    ax.set_title(title, fontsize=10)
    ax.set_aspect("equal")
    if xlim is not None:
        ax.set_xlim(*xlim)
    if ylim is not None:
        ax.set_ylim(*ylim)
    ax.grid(alpha=0.18)
    if legend:
        ax.legend(loc="upper right", fontsize=7)


def _build_static_overview() -> list[tuple[str, np.ndarray, np.ndarray, object]]:
    cache = []
    summaries = []
    fig, axes = plt.subplots(2, 2, figsize=(11, 9))
    for ax, (name, raw, guide_count, bins, seed) in zip(axes.ravel(), SCENARIOS):
        cfg = StaticCrowdConfig.from_dict(raw, seed=seed)
        crowd_points = generate_static_crowd(cfg)
        safety_distance = 0.9 if name == "Nonconvex" else 0.85
        truth = generate_static_crowd_truth(cfg, safety_distance=safety_distance)
        display_name = name if truth.valid else f"{name}\n(out of scope)"
        controller = ABCGController(num_bins=bins, safety_distance=safety_distance, min_guider_distance=0.6)
        guide_points, boundary = controller.deploy(guide_count, crowd_points, room_size=ROOM)
        metrics = containment_summary(
            guide_points,
            crowd_points,
            boundary,
            coverage_radius=1.3,
            min_crowd_distance=safety_distance,
            truth_boundary=truth,
        )
        summaries.append((display_name, metrics))
        cache.append((display_name, crowd_points, guide_points, boundary))
        _draw_scene(
            ax,
            crowd_points,
            guide_points,
            boundary.boundary_points,
            boundary.safety_points,
            title=(
                f"{display_name}: coverage {metrics['coverage_ratio']:.2f}, "
                f"Euclidean distance {metrics['max_euclidean_boundary_distance']:.2f}"
            ),
            xlim=(5, 15),
            ylim=(2, 12),
        )
    fig.suptitle("ABCG static unknown-crowd containment", fontsize=15)
    fig.tight_layout()
    fig.savefig(MEDIA_DIR / "abcg_static_containment_grid.png", dpi=180)
    plt.close(fig)

    labels = [item[0] for item in summaries]
    coverage = [item[1]["coverage_ratio"] for item in summaries]
    gaps = [item[1]["max_euclidean_boundary_distance"] for item in summaries]
    x = np.arange(len(labels))
    fig, ax1 = plt.subplots(figsize=(9, 4.8))
    ax1.bar(x - 0.18, coverage, width=0.36, color="#59a14f", label="coverage ratio")
    ax1.set_ylim(0, 1.08)
    ax1.set_ylabel("Coverage ratio")
    ax1.set_xticks(x, labels)
    ax1.grid(axis="y", alpha=0.2)
    ax2 = ax1.twinx()
    ax2.bar(x + 0.18, gaps, width=0.36, color="#e15759", label="max Euclidean boundary distance")
    ax2.set_ylabel("Max Euclidean boundary distance")
    ax1.set_title("ABCG containment metrics across static unknown crowds")
    handles1, labels1 = ax1.get_legend_handles_labels()
    handles2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(handles1 + handles2, labels1 + labels2, loc="upper left")
    fig.tight_layout()
    fig.savefig(MEDIA_DIR / "abcg_metrics_summary.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(6.4, 5.4))
    writer = PillowWriter(fps=1)
    with writer.saving(fig, str(MEDIA_DIR / "abcg_static_containment.gif"), dpi=120):
        for name, crowd_points, guide_points, boundary in cache:
            ax.clear()
            _draw_scene(
                ax,
                crowd_points,
                guide_points,
                boundary.boundary_points,
                boundary.safety_points,
                title=f"ABCG containment: {name}",
                xlim=(5, 15),
                ylim=(2, 12),
                legend=True,
            )
            writer.grab_frame()
    plt.close(fig)
    return cache


def _build_g6_scenarios() -> None:
    # Seed 13 yields valid alpha geometry for all four formal G6 generators.
    scenario_seed = 13
    fig, axes = plt.subplots(2, 2, figsize=(11, 9))
    for ax, scenario in zip(axes.ravel(), ("circle", "ellipse", "u_shape", "c_shape")):
        observation = _g6_observation(scenario, seed=scenario_seed)
        estimate = estimate_boundary_v2(
            observation,
            _boundary_config(),
            np.random.default_rng(scenario_seed + 10),
        )
        if isinstance(estimate, BoundaryEstimateFailure):
            ax.scatter(observation[:, 0], observation[:, 1], s=8, c="#4c78a8", alpha=0.5)
            ax.set_title(f"{G6_LABELS[scenario]}: {estimate.status}")
            ax.set_aspect("equal")
            continue
        plan = plan_equal_arc_coverage(estimate, 8)
        guides = plan.target_xy if plan.status == "VALID" else estimate.offset_points[:: max(1, len(estimate.offset_points) // 8)][:8]
        _draw_scene(
            ax,
            observation,
            guides,
            estimate.curve_points,
            estimate.offset_points,
            title=f"G6 {G6_LABELS[scenario]} · alpha boundary + equal-arc guides",
            xlim=(0.5, 9.5),
            ylim=(0.5, 9.5),
        )
    fig.suptitle("Step 1 formal G6 scenarios (evaluator-matched generators)", fontsize=14)
    fig.tight_layout()
    fig.savefig(MEDIA_DIR / "step1_g6_scenarios.png", dpi=180)
    plt.close(fig)


def _build_baseline_comparison() -> None:
    cfg = StaticCrowdConfig.from_dict(
        {"shape": "ellipse", "count": 220, "center": [10, 7], "axes": [3.2, 1.35], "rotation_deg": 24, "noise_std": 0.05},
        seed=1,
    )
    crowd = generate_static_crowd(cfg)
    abcg = ABCGController(num_bins=96, safety_distance=0.85, min_guider_distance=0.6)
    abcg_guides, boundary = abcg.deploy(9, crowd, room_size=ROOM)
    methods = [
        ("Random", RandomDeploymentController(ROOM, seed=11).deploy(9, crowd)),
        ("Static circle", StaticCircleController(radius=3.4).deploy(9, crowd)),
        ("Legacy center-radius", LegacyCenterRadiusController(safety_distance=0.85).deploy(9, crowd)),
        ("ABCG", abcg_guides),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(11, 9))
    for ax, (name, guides) in zip(axes.ravel(), methods):
        metrics = containment_summary(
            guides,
            crowd,
            boundary,
            coverage_radius=1.3,
            min_crowd_distance=0.85,
        )
        _draw_scene(
            ax,
            crowd,
            guides,
            boundary.boundary_points,
            boundary.safety_points,
            title=f"{name}: coverage {metrics['coverage_ratio']:.2f}",
            xlim=(4.5, 15.5),
            ylim=(2.5, 11.5),
        )
    fig.suptitle("Baseline comparison on the same elliptical unknown crowd", fontsize=14)
    fig.tight_layout()
    fig.savefig(MEDIA_DIR / "step1_baseline_comparison.png", dpi=180)
    plt.close(fig)


def _build_closed_loop_gif() -> None:
    observation = _g6_observation("ellipse", seed=7)
    estimate = estimate_boundary_v2(observation, _boundary_config(), np.random.default_rng(7))
    if isinstance(estimate, BoundaryEstimateFailure):
        raise RuntimeError(f"closed-loop media requires a valid boundary, got {estimate.status}")
    plan = plan_equal_arc_coverage(estimate, 8)
    if plan.status != "VALID":
        raise RuntimeError(f"closed-loop media requires a valid plan, got {plan.status}")
    targets = plan.target_xy
    y = np.linspace(1.2, 8.8, 8)
    guides = np.column_stack((np.full(8, 0.7), y))
    assignment = assign_guides_to_targets(guides, targets, AssignmentConfig())
    controller = ABCGv2Controller(
        ABCGv2Config(dt=0.1, k_p=1.5, v_max=1.0, hold_steps=8, max_steps=120, tracking_rmse_tolerance=0.05),
        VelocitySafetyConfig(
            enabled=True,
            min_guide_distance=0.35,
            min_crowd_distance=0.8,
            room_margin=0.2,
        ),
    )
    controller.reset(targets, assignment, guides, room_size=G6_ROOM)
    frames = [guides.copy()]
    state = guides.copy()
    for _ in range(70):
        output = controller.step(observation, state, 0.1)
        state = integrate_guide_positions(state, output.safe_velocity, 0.1)
        frames.append(state.copy())
        if str(output.state) in {"CONVERGED", "TIMEOUT", "SAFETY_INFEASIBLE", "DEGRADED"} or any(
            event.startswith("terminal:") for event in output.events
        ):
            break

    fig, ax = plt.subplots(figsize=(6.2, 5.8))
    writer = PillowWriter(fps=8)
    sample = frames[::2] + [frames[-1]]
    with writer.saving(fig, str(MEDIA_DIR / "step1_closed_loop.gif"), dpi=110):
        for index, positions in enumerate(sample):
            ax.clear()
            ax.scatter(observation[:, 0], observation[:, 1], s=8, c="#4c78a8", alpha=0.45, label="crowd")
            ax.plot(*_closed(estimate.curve_points).T, c="#1f4e79", lw=1.2, label="boundary")
            ax.plot(*_closed(estimate.offset_points).T, c="#f28e2b", lw=1.3, ls="--", label="safety")
            ax.scatter(targets[:, 0], targets[:, 1], s=40, c="#bab0ac", marker="x", label="targets")
            ax.scatter(positions[:, 0], positions[:, 1], s=70, c="#e15759", edgecolor="white", lw=0.8, label="guides")
            for start, end in zip(frames[0], positions):
                ax.plot([start[0], end[0]], [start[1], end[1]], c="#e15759", alpha=0.25, lw=0.8)
            ax.set_title(f"Step 1 closed-loop tracking · frame {index + 1}/{len(sample)}")
            ax.set_xlim(0.2, 9.8)
            ax.set_ylim(0.2, 9.8)
            ax.set_aspect("equal")
            ax.grid(alpha=0.18)
            ax.legend(loc="upper right", fontsize=7)
            writer.grab_frame()
    plt.close(fig)


def _build_g6_success_rates() -> None:
    aggregate_path = G6_REPORT_DIR / "aggregate.json"
    if not aggregate_path.is_file():
        return
    aggregate = json.loads(aggregate_path.read_text(encoding="utf-8"))
    scenarios = ["circle", "ellipse", "u_shape", "c_shape"]
    methods = ["endpoint_abcg", "uniform_angular", "uniform_arc", "fixed_m_periodic", "abcg_v2"]
    method_labels = {
        "endpoint_abcg": "endpoint ABCG",
        "uniform_angular": "uniform angular",
        "uniform_arc": "uniform arc",
        "fixed_m_periodic": "fixed-m periodic",
        "abcg_v2": "ABCG-v2",
    }
    x = np.arange(len(scenarios))
    width = 0.15
    colors = ["#4c78a8", "#f28e2b", "#e15759", "#76b7b2", "#59a14f"]
    fig, ax = plt.subplots(figsize=(11, 5.2))
    for offset, method, color in zip(np.linspace(-2, 2, len(methods)), methods, colors):
        rates = [100.0 * float(aggregate[scenario][method]["success_count"]) / float(aggregate[scenario][method]["run_count"]) for scenario in scenarios]
        ax.bar(x + offset * width, rates, width=width, color=color, label=method_labels[method])
    ax.set_xticks(x, [G6_LABELS[name] for name in scenarios])
    ax.set_ylim(0, 105)
    ax.set_ylabel("Closed-loop success rate (%)")
    ax.set_title("Formal G6 primary matrix · success / 30 paired seeds (failures retained)")
    ax.grid(axis="y", alpha=0.2)
    ax.legend(loc="upper right", fontsize=8, ncol=2)
    fig.tight_layout()
    fig.savefig(MEDIA_DIR / "step1_g6_success_rates.png", dpi=180)
    plt.close(fig)


def _copy_failure_gallery() -> None:
    source = G6_REPORT_DIR / "failure_gallery.png"
    if source.is_file():
        shutil.copy2(source, MEDIA_DIR / "step1_failure_gallery.png")


def build_media() -> None:
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    _build_static_overview()
    _build_g6_scenarios()
    _build_baseline_comparison()
    _build_closed_loop_gif()
    _build_g6_success_rates()
    _copy_failure_gallery()


if __name__ == "__main__":
    build_media()
