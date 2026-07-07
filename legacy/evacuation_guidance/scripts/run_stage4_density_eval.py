#!/usr/bin/env python
"""Stage 4 robust multi-seed density-aware DBACT evaluation."""
from __future__ import annotations

import argparse
import csv
import json
import shutil
from dataclasses import replace
from pathlib import Path
from statistics import mean, median, stdev
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Circle

from crowd_management.advanced_visualization import render_side_by_side_animation
from crowd_management.crowd_model import run_simulation
from crowd_management.metrics import load_timeseries, save_metrics
from crowd_management.replay import load_replay, save_replay
from crowd_management.types import SimulationConfig

DEFAULT_MODES = [
    "baseline",
    "static",
    "dbact",
    "nearest_exit",
    "balanced_exit_static",
    "density_only",
    "exit_pressure_only",
    "split_flow_only",
    "density_dbact",
]
RUN_FIELDS = [
    "mode",
    "seed",
    "final_evacuation_rate",
    "final_evacuated_count",
    "mean_speed",
    "congestion_index",
    "cumulative_congestion",
    "peak_near_collision_count",
    "final_time",
    "full_evacuation_time",
    "exit_0_usage_count",
    "exit_1_usage_count",
    "exit_0_usage_ratio",
    "exit_1_usage_ratio",
    "exit_imbalance",
    "main_exit_pressure_mean",
    "main_exit_pressure_peak",
    "secondary_exit_pressure_mean",
    "secondary_exit_pressure_peak",
    "output_dir",
]
AGGREGATE_METRICS = [
    "final_evacuation_rate",
    "final_evacuated_count",
    "congestion_index",
    "cumulative_congestion",
    "mean_speed",
    "exit_0_usage_ratio",
    "exit_1_usage_ratio",
    "exit_imbalance",
    "composite_score",
]
COLORS = {
    "baseline": "#6f7f95",
    "static": "#4f9d69",
    "dbact": "#4c78a8",
    "nearest_exit": "#8b5cf6",
    "balanced_exit_static": "#14b8a6",
    "density_only": "#f59e0b",
    "exit_pressure_only": "#ef4444",
    "split_flow_only": "#64748b",
    "density_dbact": "#dc2626",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Stage 4 robust density-aware DBACT evaluation.")
    parser.add_argument("--config", default="legacy/evacuation_guidance/configs/two_exit_bottleneck.yaml")
    parser.add_argument("--modes", nargs="+", default=DEFAULT_MODES)
    parser.add_argument("--seeds", nargs="+", type=int, default=list(range(10)))
    parser.add_argument("--steps", type=int, default=800)
    parser.add_argument("--output", default="runs/stage4_density_eval_v1")
    parser.add_argument("--quality", choices=("low", "medium", "high", "ultra"), default="high")
    parser.add_argument("--skip-video", action="store_true")
    parser.add_argument("--skip-heavy-plots", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def _json_default(value: Any) -> Any:
    if hasattr(value, "item"):
        return value.item()
    return value


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=_json_default)


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fieldnames})


def _load_json(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _exit_pressures(run_dir: Path) -> tuple[float, float, float, float]:
    replay = load_replay(run_dir)
    if len(replay.room.all_exits) < 2:
        return 0.0, 0.0, 0.0, 0.0
    pressures = np.zeros((len(replay.times), len(replay.room.all_exits)), dtype=float)
    for k in range(len(replay.times)):
        active = ~replay.pedestrian_evacuated[k]
        positions = replay.pedestrian_positions[k][active]
        for idx, exit_cfg in enumerate(replay.room.all_exits):
            if len(positions):
                dist = np.linalg.norm(positions - exit_cfg.center(replay.room.width), axis=1)
            else:
                dist = np.zeros(0, dtype=float)
            pressures[k, idx] = float(np.sum(dist < replay.metrics.exit_pressure_radius) / max(exit_cfg.width, 1e-6))
    return (
        float(np.mean(pressures[:, 0])),
        float(np.max(pressures[:, 0])),
        float(np.mean(pressures[:, 1])),
        float(np.max(pressures[:, 1])),
    )


def _row_from_metrics(mode: str, seed: int, run_dir: Path, metrics: dict[str, Any]) -> dict[str, Any]:
    usage_count = metrics.get("exit_usage_count") or {}
    usage_ratio = metrics.get("exit_usage_ratio") or {}
    p0_mean, p0_peak, p1_mean, p1_peak = _exit_pressures(run_dir)
    return {
        "mode": mode,
        "seed": seed,
        "final_evacuation_rate": metrics.get("final_evacuation_rate"),
        "final_evacuated_count": metrics.get("final_evacuated"),
        "mean_speed": metrics.get("mean_speed"),
        "congestion_index": metrics.get("congestion_index"),
        "cumulative_congestion": metrics.get("cumulative_congestion"),
        "peak_near_collision_count": metrics.get("peak_near_collision_count"),
        "final_time": metrics.get("final_time"),
        "full_evacuation_time": metrics.get("full_evacuation_time"),
        "exit_0_usage_count": usage_count.get("exit_0", 0),
        "exit_1_usage_count": usage_count.get("exit_1", 0),
        "exit_0_usage_ratio": usage_ratio.get("exit_0", 0.0),
        "exit_1_usage_ratio": usage_ratio.get("exit_1", 0.0),
        "exit_imbalance": metrics.get("exit_imbalance"),
        "main_exit_pressure_mean": p0_mean,
        "main_exit_pressure_peak": p0_peak,
        "secondary_exit_pressure_mean": p1_mean,
        "secondary_exit_pressure_peak": p1_peak,
        "output_dir": str(run_dir),
    }


def _run_one(config: SimulationConfig, config_path: Path, mode: str, seed: int, steps: int, output: Path, resume: bool) -> dict[str, Any]:
    run_dir = output / f"{mode}_seed_{seed}"
    if resume and (run_dir / "metrics.json").is_file() and (run_dir / "replay.npz").is_file():
        return _row_from_metrics(mode, seed, run_dir, _load_json(run_dir / "metrics.json"))
    cfg = replace(config, seed=seed)
    guided = mode != "baseline"
    guidance_mode = "dbact" if mode == "baseline" else mode
    history = run_simulation(cfg, guided=guided, steps=steps, guidance_mode=guidance_mode)
    metrics = save_metrics(history, cfg.metrics, run_dir)
    save_replay(history, cfg, run_dir, mode=mode, scenario=config_path.stem)
    return _row_from_metrics(mode, seed, run_dir, metrics)


def _add_composite_scores(rows: list[dict[str, Any]]) -> None:
    def values(key: str) -> np.ndarray:
        return np.asarray([float(row.get(key) or 0.0) for row in rows], dtype=float)

    congestion = values("congestion_index")
    cumulative = values("cumulative_congestion")
    near = values("peak_near_collision_count")

    def normalize(arr: np.ndarray) -> np.ndarray:
        span = float(arr.max() - arr.min()) if len(arr) else 0.0
        return np.zeros_like(arr) if span < 1e-12 else (arr - arr.min()) / span

    scores = (
        values("final_evacuation_rate")
        - 0.25 * normalize(congestion)
        - 0.25 * normalize(cumulative)
        - 0.20 * values("exit_imbalance")
        - 0.10 * normalize(near)
    )
    for row, score in zip(rows, scores):
        row["composite_score"] = float(score)


def _aggregate(rows: list[dict[str, Any]], modes: list[str]) -> list[dict[str, Any]]:
    aggregate_rows: list[dict[str, Any]] = []
    for mode in modes:
        mode_rows = [row for row in rows if row["mode"] == mode]
        out: dict[str, Any] = {"mode": mode}
        for metric in AGGREGATE_METRICS:
            vals = [float(row[metric]) for row in mode_rows if row.get(metric) is not None]
            if not vals:
                for suffix in ("mean", "std", "min", "max", "median"):
                    out[f"{metric}_{suffix}"] = None
                continue
            out[f"{metric}_mean"] = mean(vals)
            out[f"{metric}_std"] = stdev(vals) if len(vals) > 1 else 0.0
            out[f"{metric}_min"] = min(vals)
            out[f"{metric}_max"] = max(vals)
            out[f"{metric}_median"] = median(vals)
        aggregate_rows.append(out)
    return aggregate_rows


def _aggregate_fields() -> list[str]:
    fields = ["mode"]
    for metric in AGGREGATE_METRICS:
        fields.extend([f"{metric}_mean", f"{metric}_std", f"{metric}_min", f"{metric}_max", f"{metric}_median"])
    return fields


def _mean_std_plot(aggregate_rows: list[dict[str, Any]], metric: str, ylabel: str, path: Path) -> None:
    modes = [row["mode"] for row in aggregate_rows]
    means = [float(row.get(f"{metric}_mean") or 0.0) for row in aggregate_rows]
    stds = [float(row.get(f"{metric}_std") or 0.0) for row in aggregate_rows]
    fig, ax = plt.subplots(figsize=(10.5, 5.5))
    ax.bar(modes, means, yerr=stds, capsize=4, color=[COLORS.get(mode, "#64748b") for mode in modes])
    ax.set_ylabel(ylabel)
    ax.set_title(f"{ylabel}: mean +/- std across seeds")
    ax.grid(True, axis="y", alpha=0.28)
    ax.tick_params(axis="x", rotation=25)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _robust_dashboard(aggregate_rows: list[dict[str, Any]], path: Path) -> None:
    metrics = [
        ("final_evacuation_rate", "Final evacuation rate"),
        ("congestion_index", "Congestion index"),
        ("exit_1_usage_ratio", "Secondary exit usage"),
        ("composite_score", "Composite score"),
    ]
    modes = [row["mode"] for row in aggregate_rows]
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), squeeze=False)
    for ax, (metric, title) in zip(axes.ravel(), metrics):
        values = [float(row.get(f"{metric}_mean") or 0.0) for row in aggregate_rows]
        ax.bar(modes, values, color=[COLORS.get(mode, "#64748b") for mode in modes])
        ax.set_title(title)
        ax.grid(True, axis="y", alpha=0.25)
        ax.tick_params(axis="x", rotation=25)
    fig.suptitle("Stage 4 robust density-aware guidance dashboard", fontsize=14)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _tradeoff_scatter(rows: list[dict[str, Any]], path: Path) -> None:
    fig, ax = plt.subplots(figsize=(9, 5.8))
    for mode in sorted({row["mode"] for row in rows}):
        mode_rows = [row for row in rows if row["mode"] == mode]
        ax.scatter(
            [float(row.get("cumulative_congestion") or 0.0) for row in mode_rows],
            [float(row.get("final_evacuation_rate") or 0.0) for row in mode_rows],
            label=mode,
            s=44,
            alpha=0.8,
            color=COLORS.get(mode),
        )
    ax.set_xlabel("cumulative congestion")
    ax.set_ylabel("final evacuation rate")
    ax.set_title("Evacuation-congestion tradeoff")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _ablation_summary(aggregate_rows: list[dict[str, Any]], path: Path) -> None:
    ablations = ["density_only", "exit_pressure_only", "split_flow_only", "density_dbact"]
    rows = [row for row in aggregate_rows if row["mode"] in ablations]
    if not rows:
        return
    modes = [row["mode"] for row in rows]
    fig, ax = plt.subplots(figsize=(9.5, 5.5))
    x = np.arange(len(modes))
    width = 0.22
    for i, metric in enumerate(["congestion_index", "exit_imbalance", "composite_score"]):
        values = [float(row.get(f"{metric}_mean") or 0.0) for row in rows]
        ax.bar(x + (i - 1) * width, values, width=width, label=metric)
    ax.set_xticks(x)
    ax.set_xticklabels(modes, rotation=20)
    ax.set_title("Ablation summary")
    ax.grid(True, axis="y", alpha=0.25)
    ax.legend()
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _pressure_series(run_dir: Path) -> tuple[np.ndarray, np.ndarray]:
    replay = load_replay(run_dir)
    pressures = np.zeros((len(replay.times), len(replay.room.all_exits)), dtype=float)
    for k in range(len(replay.times)):
        active = ~replay.pedestrian_evacuated[k]
        positions = replay.pedestrian_positions[k][active]
        for idx, exit_cfg in enumerate(replay.room.all_exits):
            dist = np.linalg.norm(positions - exit_cfg.center(replay.room.width), axis=1) if len(positions) else np.zeros(0)
            pressures[k, idx] = float(np.sum(dist < replay.metrics.exit_pressure_radius) / max(exit_cfg.width, 1e-6))
    return replay.times, pressures


def _mechanism_timeline(run_dir: Path, path: Path) -> None:
    series = load_timeseries(run_dir / "timeseries.csv")
    times, pressures = _pressure_series(run_dir)
    fig, axes = plt.subplots(3, 1, figsize=(10, 8), sharex=True)
    axes[0].plot(series["time"], series.get("exit_0_usage_count", np.zeros_like(series["time"])), label="main exit", linewidth=2)
    axes[0].plot(series["time"], series.get("exit_1_usage_count", np.zeros_like(series["time"])), label="secondary exit", linewidth=2)
    axes[0].set_ylabel("usage count")
    axes[0].legend()
    axes[1].plot(times, pressures[:, 0], label="main pressure", linewidth=2)
    if pressures.shape[1] > 1:
        axes[1].plot(times, pressures[:, 1], label="secondary pressure", linewidth=2)
    axes[1].set_ylabel("pressure")
    axes[1].legend()
    axes[2].plot(series["time"], series["congestion_index"], color="#dc2626", linewidth=2)
    axes[2].set_ylabel("congestion")
    axes[2].set_xlabel("time [s]")
    for ax in axes:
        ax.grid(True, alpha=0.3)
    fig.suptitle("Density DBACT mechanism timeline")
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _mechanism_snapshot(run_dir: Path, path: Path) -> None:
    replay = load_replay(run_dir)
    series = load_timeseries(run_dir / "timeseries.csv")
    if "exit_1_usage_count" in series:
        idx = int(np.argmax(series["exit_1_usage_count"] > 0)) if np.any(series["exit_1_usage_count"] > 0) else len(replay.times) // 2
    else:
        idx = len(replay.times) // 2
    idx = min(idx + 20, len(replay.times) - 1)
    active = ~replay.pedestrian_evacuated[idx]
    positions = replay.pedestrian_positions[idx][active]
    fig, ax = plt.subplots(figsize=(11, 6.2))
    if len(positions):
        hist, _, _ = np.histogram2d(positions[:, 0], positions[:, 1], bins=60, range=[[0, replay.room.width], [0, replay.room.height]])
        ax.imshow(hist.T, extent=[0, replay.room.width, 0, replay.room.height], origin="lower", cmap="YlOrRd", alpha=0.45)
    target_ids = replay.target_exit_ids[idx][active] if replay.target_exit_ids.size else np.zeros(np.sum(active), dtype=int)
    colors = ["#2563eb" if target == 0 else "#dc2626" for target in target_ids]
    ax.scatter(positions[:, 0], positions[:, 1], s=14, c=colors, alpha=0.85, edgecolors="none")
    if replay.guider_positions.shape[1] > 0:
        guiders = replay.guider_positions[idx]
        ax.scatter(guiders[:, 0], guiders[:, 1], marker="^", s=90, c="#f97316", edgecolors="#7c2d12")
        for guider in guiders:
            ax.add_patch(Circle(guider, replay.room.metrics.influence_radius if hasattr(replay.room, "metrics") else 2.8, fill=False, edgecolor="#f97316", alpha=0.18))
    for exit_cfg in replay.room.all_exits:
        ax.plot([replay.room.width, replay.room.width + exit_cfg.depth], [exit_cfg.center_y, exit_cfg.center_y], color="#15803d", linewidth=5)
        ax.text(replay.room.width + exit_cfg.depth + 0.1, exit_cfg.center_y, exit_cfg.id, va="center")
    ax.annotate("split-flow guidance", xy=(replay.room.width * 0.58, replay.room.height * 0.75), xytext=(replay.room.width * 0.35, replay.room.height * 0.88), arrowprops={"arrowstyle": "->", "linewidth": 2})
    ax.set_xlim(0, replay.room.width + replay.room.exit_depth + 1.2)
    ax.set_ylim(0, replay.room.height)
    ax.set_aspect("equal", adjustable="box")
    ax.set_title(f"Density DBACT mechanism snapshot, t={replay.times[idx]:.1f}s")
    ax.set_xlabel("x [m]")
    ax.set_ylabel("y [m]")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _render_videos(output: Path, modes: list[str], quality: str) -> list[Path]:
    comparison = output / "comparison"
    fps = 30 if quality in {"high", "ultra"} else 12
    max_frames = 140 if quality == "low" else 220 if quality == "medium" else 360 if quality == "high" else 460
    outputs: list[Path] = []
    seed0 = lambda mode: output / f"{mode}_seed_0"
    if seed0("baseline").is_dir() and seed0("density_dbact").is_dir():
        outputs.append(
            render_side_by_side_animation(
                [seed0("baseline"), seed0("density_dbact")],
                ["baseline", "density_dbact"],
                comparison / "baseline_vs_density_dbact_mechanism.mp4",
                fps=fps,
                trail_length=12,
                heatmap=True,
                max_frames=max_frames,
            )
        )
    fair_modes = [mode for mode in ["nearest_exit", "balanced_exit_static", "split_flow_only", "density_dbact"] if seed0(mode).is_dir()]
    if len(fair_modes) == 4:
        outputs.append(
            render_side_by_side_animation(
                [seed0(mode) for mode in fair_modes],
                fair_modes,
                comparison / "fair_baselines_comparison.mp4",
                fps=fps,
                trail_length=12,
                heatmap=True,
                max_frames=max_frames,
            )
        )
    return outputs


def _make_plots(output: Path, rows: list[dict[str, Any]], aggregate_rows: list[dict[str, Any]], skip_heavy: bool) -> None:
    comparison = output / "comparison"
    _robust_dashboard(aggregate_rows, comparison / "robust_metrics_dashboard.png")
    _mean_std_plot(aggregate_rows, "final_evacuation_rate", "final evacuation rate", comparison / "evacuation_rate_mean_std.png")
    _mean_std_plot(aggregate_rows, "congestion_index", "congestion index", comparison / "congestion_index_mean_std.png")
    _mean_std_plot(aggregate_rows, "cumulative_congestion", "cumulative congestion", comparison / "cumulative_congestion_mean_std.png")
    _mean_std_plot(aggregate_rows, "exit_1_usage_ratio", "secondary exit usage ratio", comparison / "exit_usage_ratio_mean_std.png")
    _mean_std_plot(aggregate_rows, "exit_imbalance", "exit imbalance", comparison / "exit_imbalance_mean_std.png")
    _mean_std_plot(aggregate_rows, "composite_score", "composite score", comparison / "composite_score_mean_std.png")
    _ablation_summary(aggregate_rows, comparison / "ablation_summary.png")
    _tradeoff_scatter(rows, comparison / "tradeoff_scatter.png")
    density_run = output / "density_dbact_seed_0"
    if density_run.is_dir() and not skip_heavy:
        _mechanism_timeline(density_run, comparison / "mechanism_timeline_density_dbact.png")
        _mechanism_snapshot(density_run, comparison / "mechanism_snapshot_density_dbact.png")


def _markdown_table(rows: list[dict[str, Any]], fields: list[str]) -> str:
    header = "| " + " | ".join(fields) + " |"
    divider = "| " + " | ".join("---" for _ in fields) + " |"
    lines = [header, divider]
    for row in rows:
        values = []
        for field in fields:
            value = row.get(field)
            if isinstance(value, float):
                values.append(f"{value:.4f}")
            else:
                values.append(str(value))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def _write_reports(output: Path, modes: list[str], seeds: list[int], aggregate_rows: list[dict[str, Any]]) -> None:
    summary = output / "summary"
    report_dir = Path("reports") / "stage4_density_eval_v1"
    report_dir.mkdir(parents=True, exist_ok=True)
    key_fields = ["mode", "final_evacuation_rate_mean", "congestion_index_mean", "cumulative_congestion_mean", "exit_1_usage_ratio_mean", "exit_imbalance_mean", "composite_score_mean"]
    table = _markdown_table(aggregate_rows, key_fields)
    top = sorted(aggregate_rows, key=lambda row: float(row.get("composite_score_mean") or -999), reverse=True)[:3]
    top_table = _markdown_table(top, ["mode", "composite_score_mean", "congestion_index_mean", "exit_1_usage_ratio_mean"])
    report = f"""# Stage 4 Density-aware DBACT Evaluation Report

## 1. Purpose

Stage 4 turns the Stage 3 visible split-flow demo into a robust multi-seed evaluation with fair exit-choice baselines, ablations, a composite score, and mechanism visualization.

## 2. Background

Stage 2 videos looked similar in a simple one-exit room. Stage 3 introduced `two_exit_bottleneck` and `density_dbact`, producing visible split-flow. Stage 4 checks whether that result is robust across seeds and whether it beats simple fair baselines.

## 3. Scenario

Primary scenario: `legacy/evacuation_guidance/configs/two_exit_bottleneck.yaml`.

Seeds: `{seeds}`. Compared modes: `{modes}`.

## 4. Compared Methods

Methods include baseline/static/original DBACT, fair exit-choice baselines (`nearest_exit`, `balanced_exit_static`), ablations (`density_only`, `exit_pressure_only`, `split_flow_only`), and full `density_dbact`.

## 5. Metrics

Metrics include final evacuation rate, evacuation count, mean speed, congestion index, cumulative congestion, near-collision peak, exit usage ratios, exit imbalance, exit pressure, and composite score.

## 6. Multi-seed Results

{table}

## 7. Fair Baseline Results

Fair baselines can use the secondary exit, so they test whether density_dbact benefits only from exit-choice permission. Compare `density_dbact` against `nearest_exit` and `balanced_exit_static` in the aggregate table and tradeoff plots.

## 8. Ablation Results

The ablation plot compares `density_only`, `exit_pressure_only`, `split_flow_only`, and full `density_dbact`. If split-flow-only is close to density_dbact, the route-choice mechanism explains most of the benefit; if density_dbact improves congestion/balance further, the guider placement adds value.

## 9. Multi-objective Score

Composite score formula:

`score = final_evacuation_rate - 0.25*normalized_congestion_index - 0.25*normalized_cumulative_congestion - 0.20*exit_imbalance - 0.10*normalized_peak_near_collision_count`

The score is heuristic and for exploratory comparison only.

Top modes by mean score:

{top_table}

## 10. Mechanism Visualization

Mechanism plots show density field, exit pressure timeline, secondary-exit usage, and split-flow snapshot for `density_dbact`.

## 11. Interpretation

Density-aware DBACT should be interpreted as preliminary evidence in this two-exit bottleneck scenario, not as a universal crowd-management solution.

## 12. Limitations

- Simple microscopic behavior model
- Heuristic guider influence and exit-choice model
- Limited scenario geometry
- No real crowd calibration
- MP4 visualization uses CPU/Matplotlib rather than CUDA acceleration

## 13. Next Steps

Run broader parameter sweeps, calibrate pedestrian behavior, test stronger bottlenecks, and later connect to more realistic route-choice or exclusion-queue models.
"""
    findings = f"""# Stage 4 Key Findings

- Stage 4 evaluated `{len(modes)}` modes across `{len(seeds)}` seeds.
- Fair baselines were included so secondary-exit access is not exclusive to `density_dbact`.
- Composite score is heuristic and should be read together with congestion and exit-balance metrics.

## Aggregate Snapshot

{table}
"""
    teams = f"""# Crowd-Management Stage 4 Update

## Summary

Stage 4 upgrades the visible Stage 3 split-flow demo into a multi-seed evaluation with fair baselines, ablation modes, composite scoring, and mechanism visualization.

## Motivation

Stage 3 showed that `density_dbact` can redirect pedestrians to a secondary exit, but it was a single-seed result. Stage 4 asks whether that behavior is robust and whether it is better than simple exit-choice baselines.

## Method

The experiment uses `legacy/evacuation_guidance/configs/two_exit_bottleneck.yaml`, compares baseline/static/DBACT, fair baselines (`nearest_exit`, `balanced_exit_static`), ablations (`density_only`, `exit_pressure_only`, `split_flow_only`), and full `density_dbact`, and aggregates metrics across seeds.

## Key Results

{table}

## Interpretation

The key question is whether `density_dbact` reduces congestion and balances exits beyond what naive split-flow baselines achieve. The composite score is only a heuristic summary; congestion, cumulative congestion, and exit usage should be read directly.

## Limitations

This remains a heuristic simulator with a simplified pedestrian model, simplified exit-choice behavior, and no real-world calibration.

## Next Steps

Run parameter sweeps, test more bottleneck geometries, and prepare a compact presentation deck or paper-style experiment section.
"""
    outputs = {
        "STAGE4_DENSITY_EVAL_REPORT.md": report,
        "stage4_key_findings.md": findings,
        "TEAMS_CHANNEL_REPORT.md": teams,
    }
    for filename, text in outputs.items():
        (summary / filename).write_text(text, encoding="utf-8")
        (report_dir / filename).write_text(text, encoding="utf-8")


def run_stage4(
    config: str | Path,
    modes: list[str],
    seeds: list[int],
    steps: int,
    output: str | Path,
    quality: str,
    skip_video: bool,
    skip_heavy_plots: bool,
    overwrite: bool,
    resume: bool,
) -> dict[str, Any]:
    config_path = Path(config)
    output_path = Path(output)
    if overwrite and output_path.exists():
        shutil.rmtree(output_path)
    (output_path / "comparison").mkdir(parents=True, exist_ok=True)
    (output_path / "summary").mkdir(parents=True, exist_ok=True)
    cfg = SimulationConfig.from_yaml(config_path)

    rows: list[dict[str, Any]] = []
    for mode in modes:
        for seed in seeds:
            rows.append(_run_one(cfg, config_path, mode, seed, steps, output_path, resume=resume))
    _add_composite_scores(rows)
    aggregate_rows = _aggregate(rows, modes)

    _write_csv(output_path / "summary" / "run_metrics.csv", [*RUN_FIELDS, "composite_score"], rows)
    _write_json(output_path / "summary" / "run_metrics.json", {"config": str(config_path), "modes": modes, "seeds": seeds, "steps": steps, "runs": rows})
    _write_csv(output_path / "summary" / "aggregate_metrics.csv", _aggregate_fields(), aggregate_rows)
    _write_json(output_path / "summary" / "aggregate_metrics.json", {"modes": modes, "aggregate": aggregate_rows})
    _write_csv(output_path / "summary" / "composite_scores.csv", ["mode", "seed", "composite_score", "final_evacuation_rate", "congestion_index", "cumulative_congestion", "exit_imbalance"], rows)
    _make_plots(output_path, rows, aggregate_rows, skip_heavy_plots)
    videos = [] if skip_video else _render_videos(output_path, modes, quality)
    _write_reports(output_path, modes, seeds, aggregate_rows)

    report_dir = Path("reports") / "stage4_density_eval_v1"
    shutil.copyfile(output_path / "summary" / "aggregate_metrics.csv", report_dir / "aggregate_metrics.csv")
    shutil.copyfile(output_path / "summary" / "composite_scores.csv", report_dir / "composite_scores.csv")
    return {"run_count": len(rows), "videos": [str(path) for path in videos], "aggregate": aggregate_rows}


def main() -> None:
    args = parse_args()
    result = run_stage4(
        args.config,
        args.modes,
        args.seeds,
        args.steps,
        args.output,
        args.quality,
        args.skip_video,
        args.skip_heavy_plots,
        args.overwrite,
        args.resume,
    )
    print(f"Saved Stage 4 density evaluation to {args.output}")
    print(json.dumps(result, indent=2, default=_json_default))


if __name__ == "__main__":
    main()
