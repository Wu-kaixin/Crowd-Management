"""G6 scenario and success-rate figures for README media."""

from __future__ import annotations

import json
import shutil

import matplotlib.pyplot as plt
import numpy as np

from crowd_management.controllers import plan_equal_arc_coverage
from crowd_management.estimation import BoundaryEstimateFailure, estimate_boundary_v2

from .constants import G6_LABELS, G6_REPORT_DIR, MEDIA_DIR
from .draw import draw_scene
from .geometry import boundary_config, g6_observation


def build_g6_scenarios() -> None:
    # Seed 13 yields valid alpha geometry for all four formal G6 generators.
    scenario_seed = 13
    fig, axes = plt.subplots(2, 2, figsize=(11, 9))
    for ax, scenario in zip(axes.ravel(), ("circle", "ellipse", "u_shape", "c_shape"), strict=True):
        observation = g6_observation(scenario, seed=scenario_seed)
        estimate = estimate_boundary_v2(
            observation,
            boundary_config(),
            np.random.default_rng(scenario_seed + 10),
        )
        if isinstance(estimate, BoundaryEstimateFailure):
            ax.scatter(observation[:, 0], observation[:, 1], s=8, c="#4c78a8", alpha=0.5)
            ax.set_title(f"{G6_LABELS[scenario]}: {estimate.status}")
            ax.set_aspect("equal")
            continue
        plan = plan_equal_arc_coverage(estimate, 8)
        guides = (
            plan.target_xy
            if plan.status == "VALID"
            else estimate.offset_points[:: max(1, len(estimate.offset_points) // 8)][:8]
        )
        draw_scene(
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


def build_g6_success_rates() -> None:
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
    for offset, method, color in zip(np.linspace(-2, 2, len(methods)), methods, colors, strict=True):
        rates = [
            100.0
            * float(aggregate[scenario][method]["success_count"])
            / float(aggregate[scenario][method]["run_count"])
            for scenario in scenarios
        ]
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


def copy_failure_gallery() -> None:
    source = G6_REPORT_DIR / "failure_gallery.png"
    if source.is_file():
        shutil.copy2(source, MEDIA_DIR / "step1_failure_gallery.png")
