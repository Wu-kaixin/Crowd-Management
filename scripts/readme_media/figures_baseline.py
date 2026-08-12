"""Baseline comparison and closed-loop GIF figures for README media."""

from __future__ import annotations

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
from crowd_management.crowd import StaticCrowdConfig, generate_static_crowd
from crowd_management.estimation import BoundaryEstimateFailure, estimate_boundary_v2

from .constants import G6_ROOM, MEDIA_DIR, ROOM
from .draw import draw_scene
from .geometry import boundary_config, closed_curve, g6_observation


def build_baseline_comparison() -> None:
    cfg = StaticCrowdConfig.from_dict(
        {
            "shape": "ellipse",
            "count": 220,
            "center": [10, 7],
            "axes": [3.2, 1.35],
            "rotation_deg": 24,
            "noise_std": 0.05,
        },
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
    for ax, (name, guides) in zip(axes.ravel(), methods, strict=True):
        metrics = containment_summary(
            guides,
            crowd,
            boundary,
            coverage_radius=1.3,
            min_crowd_distance=0.85,
        )
        draw_scene(
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


def build_closed_loop_gif() -> None:
    observation = g6_observation("ellipse", seed=7)
    estimate = estimate_boundary_v2(observation, boundary_config(), np.random.default_rng(7))
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
            ax.plot(*closed_curve(estimate.curve_points).T, c="#1f4e79", lw=1.2, label="boundary")
            ax.plot(*closed_curve(estimate.offset_points).T, c="#f28e2b", lw=1.3, ls="--", label="safety")
            ax.scatter(targets[:, 0], targets[:, 1], s=40, c="#bab0ac", marker="x", label="targets")
            ax.scatter(positions[:, 0], positions[:, 1], s=70, c="#e15759", edgecolor="white", lw=0.8, label="guides")
            for start, end in zip(frames[0], positions, strict=True):
                ax.plot([start[0], end[0]], [start[1], end[1]], c="#e15759", alpha=0.25, lw=0.8)
            ax.set_title(f"Step 1 closed-loop tracking · frame {index + 1}/{len(sample)}")
            ax.set_xlim(0.2, 9.8)
            ax.set_ylim(0.2, 9.8)
            ax.set_aspect("equal")
            ax.grid(alpha=0.18)
            ax.legend(loc="upper right", fontsize=7)
            writer.grab_frame()
    plt.close(fig)
