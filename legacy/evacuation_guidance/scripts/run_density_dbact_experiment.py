#!/usr/bin/env python
"""Run Stage 3 density-aware DBACT split-flow experiments."""
from __future__ import annotations

import argparse
import csv
import json
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from crowd_management.advanced_visualization import render_dashboard, render_side_by_side_animation
from crowd_management.crowd_model import run_simulation
from crowd_management.metrics import load_timeseries, save_metrics
from crowd_management.replay import load_replay, save_replay
from crowd_management.types import PedestrianConfig, SimulationConfig
from crowd_management.visualization import save_density_heatmap, save_snapshot, save_timeseries_plot

MODES = ("baseline", "static", "random", "dbact", "density_dbact")
SUMMARY_FIELDS = [
    "mode",
    "final_evacuation_rate",
    "final_evacuated_count",
    "mean_speed",
    "congestion_index",
    "peak_near_collision_count",
    "final_time",
    "exit_0_usage_count",
    "exit_1_usage_count",
    "exit_0_usage_ratio",
    "exit_1_usage_ratio",
    "exit_imbalance",
    "cumulative_congestion",
    "output_dir",
]
COLORS = {
    "baseline": "#6f7f95",
    "static": "#4f9d69",
    "random": "#d08c36",
    "dbact": "#4c78a8",
    "density_dbact": "#dc2626",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run density-aware DBACT split-flow experiment.")
    parser.add_argument("--config", default="legacy/evacuation_guidance/configs/two_exit_bottleneck.yaml")
    parser.add_argument("--modes", nargs="+", choices=MODES, default=["baseline", "static", "dbact", "density_dbact"])
    parser.add_argument("--steps", type=int, default=800)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--agents", type=int, default=None)
    parser.add_argument("--output", default="runs/density_dbact_v1")
    parser.add_argument("--quality", choices=("quick", "high", "ultra"), default="high")
    parser.add_argument("--skip-video", action="store_true")
    parser.add_argument("--fast-test", action="store_true")
    return parser.parse_args()


def _json_default(value: Any) -> Any:
    if hasattr(value, "item"):
        return value.item()
    return value


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=_json_default)


def _metric(metrics: dict[str, Any], key: str) -> Any:
    if key == "final_evacuated_count":
        return metrics.get("final_evacuated")
    return metrics.get(key)


def _with_overrides(config: SimulationConfig, seed: int, agents: int | None, fast_test: bool) -> SimulationConfig:
    ped_count = agents
    if fast_test and ped_count is None:
        ped_count = min(60, config.pedestrians.count)
    pedestrians = config.pedestrians if ped_count is None else replace(config.pedestrians, count=int(ped_count))
    return replace(config, seed=seed, pedestrians=pedestrians)


def _run_mode(config_path: Path, config: SimulationConfig, mode: str, steps: int, output_dir: Path) -> dict[str, Any]:
    run_dir = output_dir / mode
    figures = run_dir / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    guided = mode != "baseline"
    guidance_mode = "dbact" if mode == "baseline" else mode
    history = run_simulation(config, guided=guided, steps=steps, guidance_mode=guidance_mode)
    metrics = save_metrics(history, config.metrics, run_dir)
    save_replay(history, config, run_dir, mode=mode, scenario=config_path.stem)
    save_snapshot(history, config.room, figures / "final_snapshot.png", title=mode)
    save_density_heatmap(history, config.room, figures / "density_heatmap.png")
    save_timeseries_plot(run_dir / "timeseries.csv", figures / "timeseries.png", title=f"{mode} time series")
    return metrics


def _summary_row(mode: str, metrics: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    usage_count = metrics.get("exit_usage_count") or {}
    usage_ratio = metrics.get("exit_usage_ratio") or {}
    return {
        "mode": mode,
        "final_evacuation_rate": _metric(metrics, "final_evacuation_rate"),
        "final_evacuated_count": _metric(metrics, "final_evacuated_count"),
        "mean_speed": _metric(metrics, "mean_speed"),
        "congestion_index": _metric(metrics, "congestion_index"),
        "peak_near_collision_count": _metric(metrics, "peak_near_collision_count"),
        "final_time": _metric(metrics, "final_time"),
        "exit_0_usage_count": usage_count.get("exit_0", 0),
        "exit_1_usage_count": usage_count.get("exit_1", 0),
        "exit_0_usage_ratio": usage_ratio.get("exit_0", 0.0),
        "exit_1_usage_ratio": usage_ratio.get("exit_1", 0.0),
        "exit_imbalance": metrics.get("exit_imbalance"),
        "cumulative_congestion": metrics.get("cumulative_congestion"),
        "output_dir": str(output_dir),
    }


def _write_summary_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _curve_plot(run_dirs: dict[str, Path], modes: list[str], key: str, ylabel: str, title: str, output_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(9.5, 5.2))
    for mode in modes:
        series = load_timeseries(run_dirs[mode] / "timeseries.csv")
        if series and key in series:
            ax.plot(series["time"], series[key], label=mode, linewidth=2.2, color=COLORS.get(mode))
    ax.set_xlabel("time [s]")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=190)
    plt.close(fig)


def _exit_usage_curve(run_dirs: dict[str, Path], modes: list[str], output_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(9.5, 5.2))
    for mode in modes:
        series = load_timeseries(run_dirs[mode] / "timeseries.csv")
        if "exit_1_usage_count" in series:
            ax.plot(series["time"], series["exit_1_usage_count"], label=f"{mode}: alternate", linewidth=2.1, color=COLORS.get(mode))
    ax.set_xlabel("time [s]")
    ax.set_ylabel("alternate-exit evacuated count")
    ax.set_title("Alternate-exit usage over time")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=190)
    plt.close(fig)


def _exit_pressure_series(run_dir: Path) -> tuple[np.ndarray, np.ndarray]:
    replay = load_replay(run_dir)
    exits = replay.room.all_exits
    pressures = np.zeros((len(replay.times), len(exits)), dtype=float)
    for k in range(len(replay.times)):
        active = ~replay.pedestrian_evacuated[k]
        positions = replay.pedestrian_positions[k][active]
        for idx, exit_cfg in enumerate(exits):
            center = exit_cfg.center(replay.room.width)
            dist = np.linalg.norm(positions - center, axis=1) if len(positions) else np.zeros(0, dtype=float)
            pressures[k, idx] = float(np.sum(dist < replay.metrics.exit_pressure_radius) / max(exit_cfg.width, 1e-6))
    return replay.times, pressures


def _exit_pressure_curve(run_dirs: dict[str, Path], modes: list[str], output_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(9.5, 5.2))
    for mode in modes:
        times, pressures = _exit_pressure_series(run_dirs[mode])
        if pressures.shape[1] > 0:
            ax.plot(times, pressures[:, 0], label=f"{mode}: main", linewidth=1.7, linestyle="--", color=COLORS.get(mode))
        if pressures.shape[1] > 1:
            ax.plot(times, pressures[:, 1], label=f"{mode}: alternate", linewidth=2.1, color=COLORS.get(mode))
    ax.set_xlabel("time [s]")
    ax.set_ylabel("exit pressure")
    ax.set_title("Exit pressure over time")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=190)
    plt.close(fig)


def _final_metrics_bar(rows: list[dict[str, Any]], output_path: Path) -> None:
    metrics = ["final_evacuation_rate", "mean_speed", "congestion_index", "exit_1_usage_count"]
    labels = [row["mode"] for row in rows]
    fig, axes = plt.subplots(2, 2, figsize=(11, 7.2), squeeze=False)
    for ax, metric in zip(axes.ravel(), metrics):
        values = [float(row.get(metric) or 0.0) for row in rows]
        ax.bar(labels, values, color=[COLORS.get(label, "#6f7f95") for label in labels])
        ax.set_title(metric)
        ax.grid(True, axis="y", alpha=0.25)
        ax.tick_params(axis="x", rotation=20)
    fig.suptitle("Density-aware guidance metrics", fontsize=14)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=190)
    plt.close(fig)


def _heatmap_snapshots(run_dirs: dict[str, Path], modes: list[str], output_path: Path) -> None:
    selected = [mode for mode in modes if mode in run_dirs]
    replays = {mode: load_replay(run_dirs[mode]) for mode in selected}
    if not replays:
        return
    end_time = min(float(replay.times[-1]) for replay in replays.values())
    times = [end_time * 0.35, end_time * 0.7, end_time]
    fig, axes = plt.subplots(len(selected), len(times), figsize=(4.3 * len(times), 3.1 * len(selected)), squeeze=False)
    for row, mode in enumerate(selected):
        replay = replays[mode]
        for col, t in enumerate(times):
            k = int(np.searchsorted(replay.times, t, side="left"))
            k = min(k, len(replay.times) - 1)
            active = ~replay.pedestrian_evacuated[k]
            hist, _, _ = np.histogram2d(
                replay.pedestrian_positions[k][active, 0],
                replay.pedestrian_positions[k][active, 1],
                bins=54,
                range=[[0, replay.room.width], [0, replay.room.height]],
            )
            ax = axes[row][col]
            ax.imshow(hist.T, extent=[0, replay.room.width, 0, replay.room.height], origin="lower", cmap="YlOrRd", interpolation="bilinear")
            ax.set_xlim(0, replay.room.width + replay.room.exit_depth)
            ax.set_ylim(0, replay.room.height)
            ax.set_aspect("equal", adjustable="box")
            ax.set_title(f"{mode} t={replay.times[k]:.1f}s", fontsize=10)
            for exit_cfg in replay.room.all_exits:
                ax.plot([replay.room.width, replay.room.width + exit_cfg.depth], [exit_cfg.center_y, exit_cfg.center_y], color="#15803d", linewidth=4)
    fig.suptitle("Density heatmap snapshots", fontsize=14)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=190)
    plt.close(fig)


def _render_videos(run_dirs: dict[str, Path], modes: list[str], comparison_dir: Path, quality: str) -> list[Path]:
    fps = 30
    max_frames = 260 if quality == "quick" else 420 if quality == "high" else 520
    trail_length = 8 if quality == "quick" else 12
    outputs: list[Path] = []
    pairs = [
        ("baseline", "density_dbact", "baseline_vs_density_dbact.mp4"),
        ("dbact", "density_dbact", "dbact_vs_density_dbact.mp4"),
    ]
    for left, right, filename in pairs:
        if left in run_dirs and right in run_dirs:
            outputs.append(
                render_side_by_side_animation(
                    [run_dirs[left], run_dirs[right]],
                    [left, right],
                    comparison_dir / filename,
                    fps=fps,
                    trail_length=trail_length,
                    heatmap=True,
                    max_frames=max_frames,
                )
            )
    if all(mode in run_dirs for mode in modes) and len(modes) in {2, 4}:
        outputs.append(
            render_side_by_side_animation(
                [run_dirs[mode] for mode in modes],
                modes,
                comparison_dir / "four_or_five_modes_comparison.mp4",
                fps=fps,
                trail_length=trail_length,
                heatmap=True,
                max_frames=max_frames,
            )
        )
    return outputs


def _report_text(config: str, rows: list[dict[str, Any]], generated: list[str]) -> str:
    table = ["| Mode | Final rate | Evacuated | Mean speed | Congestion | Alt-exit count | Exit imbalance |", "|---|---:|---:|---:|---:|---:|---:|"]
    for row in rows:
        table.append(
            f"| {row['mode']} | {float(row.get('final_evacuation_rate') or 0):.3f} | {int(row.get('final_evacuated_count') or 0)} | "
            f"{float(row.get('mean_speed') or 0):.3f} | {float(row.get('congestion_index') or 0):.3f} | "
            f"{int(row.get('exit_1_usage_count') or 0)} | {float(row.get('exit_imbalance') or 0):.3f} |"
        )
    files = "\n".join(f"- `{item}`" for item in generated)
    return f"""# Density-Aware DBACT Guidance Report

## 1. Purpose

Stage 2 videos looked similar because `simple_room.yaml` gave every pedestrian the same obvious exit. Stage 3 introduces a stronger two-exit bottleneck scenario and a density-aware guidance mode so that route choice and congestion management become visible.

## 2. Scenario

Config: `{config}`. The room has a narrow main exit and an upper alternate exit. Baseline, static, and original DBACT primarily target the main exit; `density_dbact` can redirect part of the crowd toward the alternate exit.

## 3. Compared Modes

- `baseline`: no guider or default main-exit behavior
- `static`: fixed guiders
- `dbact`: original DBACT-transfer dynamic guider placement
- `density_dbact`: density-aware DBACT-transfer v2

## 4. Method

The density-aware controller estimates exit pressure from nearby active pedestrians, assigns the less pressured exit as a guidance target, arranges guiders along a visible diagonal guide line, and switches compliant pedestrians in the upper/high-pressure portion of the crowd toward the alternate exit.

## 5. Metrics

Metrics include final evacuation rate, final evacuated count, mean speed, congestion index, peak near-collision count, exit usage counts/ratios, exit imbalance, cumulative congestion, and final time.

## 6. Results

{chr(10).join(table)}

Generated outputs:

{files}

## 7. Interpretation

If `density_dbact` shows higher alternate-exit usage and a visible split-flow pattern, this is preliminary evidence that density-aware guidance creates more meaningful behavior than geometric DBACT alone. The result is still not final validation.

## 8. Limitations

- Heuristic model
- Single seed unless multi-seed is run later
- Simple microscopic crowd behavior
- Simplified exit-choice model
- No real human data validation yet

## 9. Next Step

- Multi-seed evaluation on `two_exit_bottleneck`
- Parameter sweep for influence radius, compliance, and exit pressure weight
- More realistic bottleneck geometry
- Later connection to exclusion queue or behavior-change models
"""


def _write_report(output_dir: Path, rows: list[dict[str, Any]], generated: list[str], config: str) -> None:
    text = _report_text(config, rows, generated)
    summary_report = output_dir / "summary" / "DENSITY_DBACT_REPORT.md"
    summary_report.write_text(text, encoding="utf-8")
    if output_dir.name == "density_dbact_v1":
        report_path = Path("reports") / "density_dbact_v1" / "DENSITY_DBACT_REPORT.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(summary_report, report_path)


def run_experiment(
    config: str | Path,
    modes: list[str],
    steps: int,
    seed: int,
    agents: int | None,
    output: str | Path,
    quality: str,
    skip_video: bool,
    fast_test: bool,
) -> dict[str, Any]:
    config_path = Path(config)
    output_dir = Path(output)
    comparison_dir = output_dir / "comparison"
    summary_dir = output_dir / "summary"
    comparison_dir.mkdir(parents=True, exist_ok=True)
    summary_dir.mkdir(parents=True, exist_ok=True)
    base_config = _with_overrides(SimulationConfig.from_yaml(config_path), seed, agents, fast_test)

    run_dirs: dict[str, Path] = {}
    rows: list[dict[str, Any]] = []
    for mode in modes:
        metrics = _run_mode(config_path, base_config, mode, steps, output_dir)
        run_dirs[mode] = output_dir / mode
        rows.append(_summary_row(mode, metrics, run_dirs[mode]))

    _write_summary_csv(summary_dir / "metrics_summary.csv", rows)
    _write_json(summary_dir / "metrics_summary.json", {"config": str(config_path), "modes": modes, "seed": seed, "steps": steps, "runs": rows})

    _curve_plot(run_dirs, modes, "evacuation_rate", "evacuation rate", "Evacuation curve", comparison_dir / "evacuation_curve.png")
    _curve_plot(run_dirs, modes, "congestion_index", "congestion index", "Congestion curve", comparison_dir / "congestion_curve.png")
    _exit_usage_curve(run_dirs, modes, comparison_dir / "exit_usage_curve.png")
    _exit_pressure_curve(run_dirs, modes, comparison_dir / "exit_pressure_curve.png")
    _final_metrics_bar(rows, comparison_dir / "final_metrics_bar.png")
    _heatmap_snapshots(run_dirs, modes, comparison_dir / "heatmap_snapshots.png")
    render_dashboard([run_dirs[mode] for mode in modes], modes, comparison_dir / "four_modes_dashboard.png")
    video_outputs = [] if skip_video else _render_videos(run_dirs, modes, comparison_dir, quality)

    generated = [
        "comparison/exit_usage_curve.png",
        "comparison/exit_pressure_curve.png",
        "comparison/congestion_curve.png",
        "comparison/evacuation_curve.png",
        "comparison/final_metrics_bar.png",
        "comparison/heatmap_snapshots.png",
        "comparison/four_modes_dashboard.png",
        "summary/metrics_summary.csv",
        "summary/metrics_summary.json",
    ]
    generated.extend(str(path.relative_to(output_dir)) for path in video_outputs)
    _write_report(output_dir, rows, generated, str(config_path))
    return {"runs": rows, "generated_files": generated}


def main() -> None:
    args = parse_args()
    result = run_experiment(args.config, args.modes, args.steps, args.seed, args.agents, args.output, args.quality, args.skip_video, args.fast_test)
    print(f"Saved density-aware DBACT experiment to {args.output}")
    print(json.dumps(result, indent=2, default=_json_default))


if __name__ == "__main__":
    main()
