from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.animation import PillowWriter

from crowd_management.containment_metrics import containment_summary
from crowd_management.controllers import ABCGController
from crowd_management.crowd import StaticCrowdConfig, generate_static_crowd, generate_static_crowd_truth


MEDIA_DIR = Path("reports/media")


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


def _closed(points: np.ndarray) -> np.ndarray:
    return np.vstack([points, points[0]])


def build_media() -> None:
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
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
        guide_points, boundary = controller.deploy(guide_count, crowd_points, room_size=np.array([20.0, 14.0]))
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

        ax.scatter(crowd_points[:, 0], crowd_points[:, 1], s=8, c="#4c78a8", alpha=0.48)
        ax.plot(*_closed(boundary.boundary_points).T, c="#1f4e79", lw=1.3)
        ax.plot(*_closed(boundary.safety_points).T, c="#f28e2b", lw=1.5, ls="--")
        ax.scatter(guide_points[:, 0], guide_points[:, 1], s=75, c="#e15759", edgecolor="white", lw=0.8)
        ax.set_title(
            f"{display_name}: coverage {metrics['coverage_ratio']:.2f}, "
            f"Euclidean distance {metrics['max_euclidean_boundary_distance']:.2f}"
        )
        ax.set_aspect("equal")
        ax.set_xlim(5, 15)
        ax.set_ylim(2, 12)
        ax.grid(alpha=0.18)

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
            ax.scatter(crowd_points[:, 0], crowd_points[:, 1], s=9, c="#4c78a8", alpha=0.5)
            ax.plot(*_closed(boundary.boundary_points).T, c="#1f4e79", lw=1.4, label="estimated boundary")
            ax.plot(*_closed(boundary.safety_points).T, c="#f28e2b", lw=1.5, ls="--", label="safety boundary")
            ax.scatter(guide_points[:, 0], guide_points[:, 1], s=80, c="#e15759", edgecolor="white", lw=0.8, label="guide agents")
            ax.set_title(f"ABCG containment: {name}")
            ax.set_xlim(5, 15)
            ax.set_ylim(2, 12)
            ax.set_aspect("equal")
            ax.grid(alpha=0.18)
            ax.legend(loc="upper right", fontsize=8)
            writer.grab_frame()
    plt.close(fig)


if __name__ == "__main__":
    build_media()
