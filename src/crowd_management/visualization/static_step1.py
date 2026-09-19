"""Post-run Step 1 scene export.

ROLE: VISUALIZATION ONLY. Distinct environment vs crowd curves.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from .live_step1 import Step1Frame


def save_final_scene(frame: Step1Frame, output_path: str | Path) -> None:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8.0, 6.4))
    env = np.vstack((frame.environment_vertices, frame.environment_vertices[0]))
    ax.plot(env[:, 0], env[:, 1], color="#1b1b1b", linewidth=2.4, label="environment boundary")
    ax.scatter(frame.crowd_points[:, 0], frame.crowd_points[:, 1], s=14, c="#4c78a8", alpha=0.7, label="static crowd")
    if frame.estimated_crowd_boundary is not None and len(frame.estimated_crowd_boundary):
        curve = np.vstack((frame.estimated_crowd_boundary, frame.estimated_crowd_boundary[0]))
        ax.plot(curve[:, 0], curve[:, 1], color="#2f4b7c", linewidth=1.8, label="estimated crowd boundary")
    if frame.deployment_curve is not None and len(frame.deployment_curve):
        deploy = np.vstack((frame.deployment_curve, frame.deployment_curve[0]))
        ax.plot(deploy[:, 0], deploy[:, 1], color="#f58518", linestyle="--", linewidth=1.8, label="deployment curve")
    ax.scatter(
        frame.current_guides[:, 0],
        frame.current_guides[:, 1],
        s=80,
        c="#e45756",
        edgecolors="white",
        label="guides",
        zorder=5,
    )
    title = f"{frame.scenario_name} | seed {frame.seed} | {frame.controller_state}"
    if frame.failed:
        title = f"FAILED: {frame.controller_state}"
    ax.set_title(title)
    ax.set_aspect("equal", adjustable="box")
    ax.grid(True, alpha=0.2)
    ax.legend(loc="best", frameon=True, fontsize=8)
    fig.tight_layout()
    fig.savefig(output, dpi=160)
    plt.close(fig)
