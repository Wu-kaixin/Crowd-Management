"""Static containment overview figures for README media."""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.animation import PillowWriter

from crowd_management.containment_metrics import containment_summary
from crowd_management.controllers import ABCGController
from crowd_management.crowd import StaticCrowdConfig, generate_static_crowd, generate_static_crowd_truth

from .constants import MEDIA_DIR, ROOM, SCENARIOS
from .draw import draw_scene


def build_static_overview() -> list[tuple[str, np.ndarray, np.ndarray, object]]:
    cache: list[tuple[str, np.ndarray, np.ndarray, object]] = []
    summaries = []
    fig, axes = plt.subplots(2, 2, figsize=(11, 9))
    for ax, (name, raw, guide_count, bins, seed) in zip(axes.ravel(), SCENARIOS, strict=True):
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
        draw_scene(
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
        for name, crowd_points, guide_points, boundary_obj in cache:
            ax.clear()
            draw_scene(
                ax,
                crowd_points,
                guide_points,
                boundary_obj.boundary_points,  # type: ignore[attr-defined]
                boundary_obj.safety_points,  # type: ignore[attr-defined]
                title=f"ABCG containment: {name}",
                xlim=(5, 15),
                ylim=(2, 12),
                legend=True,
            )
            writer.grab_frame()
    plt.close(fig)
    return cache
