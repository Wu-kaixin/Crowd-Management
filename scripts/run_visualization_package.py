#!/usr/bin/env python
"""Build a presentation-ready visualization package for existing guidance modes."""
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
from crowd_management.types import SimulationConfig
from crowd_management.visualization import save_density_heatmap, save_snapshot, save_timeseries_plot

MODES = ("baseline", "static", "random", "dbact")
MODE_LABELS = {
    "baseline": "Baseline",
    "static": "Static",
    "random": "Random",
    "dbact": "DBACT-transfer",
}
MODE_TITLES = {
    "baseline": "Baseline: no guidance",
    "static": "Guided baseline: static guiders",
    "random": "Guided baseline: random moving guiders",
    "dbact": "Guided: transferred DBACT-style control",
}
SUMMARY_FIELDS = [
    "mode",
    "final_evacuation_rate",
    "final_evacuated_count",
    "mean_speed",
    "congestion_index",
    "peak_near_collision_count",
    "final_time",
    "output_dir",
]
PLOT_COLORS = {
    "baseline": "#6f7f95",
    "static": "#4f9d69",
    "random": "#d08c36",
    "dbact": "#4c78a8",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Stage 2 visualization package.")
    parser.add_argument("--config", default="configs/simple_room.yaml")
    parser.add_argument("--modes", nargs="+", choices=MODES, default=list(MODES))
    parser.add_argument("--steps", type=int, default=400)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--output", default="runs/visualization_package_v1")
    parser.add_argument("--quality", choices=("quick", "high"), default="high")
    parser.add_argument("--skip-video", action="store_true")
    parser.add_argument("--skip-heavy-plots", action="store_true")
    return parser.parse_args()


def _json_default(value: Any) -> Any:
    if hasattr(value, "item"):
        return value.item()
    return value


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=_json_default)


def _write_metrics_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _metric(metrics: dict[str, Any], key: str) -> Any:
    if key == "final_evacuated_count":
        return metrics.get("final_evacuated")
    return metrics.get(key)


def _run_mode(config_path: Path, base_config: SimulationConfig, mode: str, seed: int, steps: int, output_dir: Path) -> dict[str, Any]:
    run_dir = output_dir / mode
    figures_dir = run_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    cfg = replace(base_config, seed=seed)
    guided = mode != "baseline"
    guidance_mode = "dbact" if mode == "baseline" else mode
    history = run_simulation(cfg, guided=guided, steps=steps, guidance_mode=guidance_mode)
    metrics = save_metrics(history, cfg.metrics, run_dir)
    save_replay(history, cfg, run_dir, mode=mode, scenario=config_path.stem)
    save_snapshot(history, cfg.room, figures_dir / "final_snapshot.png", title=MODE_TITLES[mode])
    save_density_heatmap(history, cfg.room, figures_dir / "density_heatmap.png")
    save_timeseries_plot(run_dir / "timeseries.csv", figures_dir / "timeseries.png", title=f"{mode} time series")
    return metrics


def _load_series(run_dirs: dict[str, Path]) -> dict[str, dict[str, np.ndarray]]:
    return {mode: load_timeseries(run_dir / "timeseries.csv") for mode, run_dir in run_dirs.items()}


def _save_curve_plot(
    series_by_mode: dict[str, dict[str, np.ndarray]],
    modes: list[str],
    y_key: str,
    ylabel: str,
    title: str,
    output_path: Path,
) -> None:
    fig, ax = plt.subplots(figsize=(9.5, 5.2))
    for mode in modes:
        series = series_by_mode.get(mode, {})
        if series and y_key in series:
            ax.plot(series["time"], series[y_key], label=mode, linewidth=2.2, color=PLOT_COLORS.get(mode))
    ax.set_xlabel("time [s]")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def _save_final_metrics_bar(rows: list[dict[str, Any]], output_path: Path) -> None:
    metrics = ["final_evacuation_rate", "mean_speed", "congestion_index", "peak_near_collision_count"]
    labels = [row["mode"] for row in rows]
    fig, axes = plt.subplots(2, 2, figsize=(11, 7.2), squeeze=False)
    for ax, metric in zip(axes.ravel(), metrics):
        values = [float(row.get(metric) or 0.0) for row in rows]
        ax.bar(labels, values, color=[PLOT_COLORS.get(label, "#6f7f95") for label in labels])
        ax.set_title(metric)
        ax.grid(True, axis="y", alpha=0.25)
        ax.tick_params(axis="x", rotation=20)
    fig.suptitle("Final metrics by guidance mode", fontsize=14)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def _density_grid(replay, k: int, bins: int = 48) -> np.ndarray:
    active = ~replay.pedestrian_evacuated[k]
    positions = replay.pedestrian_positions[k][active]
    if len(positions) == 0:
        return np.zeros((bins, bins), dtype=float)
    hist, _, _ = np.histogram2d(
        positions[:, 0],
        positions[:, 1],
        bins=bins,
        range=[[0, replay.room.width], [0, replay.room.height]],
    )
    return hist.T


def _nearest_index(times: np.ndarray, value: float) -> int:
    idx = int(np.searchsorted(times, value, side="left"))
    if idx <= 0:
        return 0
    if idx >= len(times):
        return len(times) - 1
    before = idx - 1
    return before if abs(times[before] - value) <= abs(times[idx] - value) else idx


def _save_heatmap_snapshots(run_dirs: dict[str, Path], modes: list[str], output_path: Path) -> None:
    selected_modes = [mode for mode in modes if mode in run_dirs]
    replays = {mode: load_replay(run_dirs[mode]) for mode in selected_modes}
    if not replays:
        return
    end_time = min(float(replay.times[-1]) for replay in replays.values())
    times = [0.0, end_time * 0.5, end_time]
    fig, axes = plt.subplots(len(selected_modes), len(times), figsize=(4.2 * len(times), 3.2 * len(selected_modes)), squeeze=False)
    max_density = 1.0
    grids: dict[tuple[str, int], np.ndarray] = {}
    for mode, replay in replays.items():
        for col, time_value in enumerate(times):
            k = _nearest_index(replay.times, time_value)
            grid = _density_grid(replay, k)
            grids[(mode, col)] = grid
            max_density = max(max_density, float(grid.max()))
    for row, mode in enumerate(selected_modes):
        replay = replays[mode]
        for col, time_value in enumerate(times):
            ax = axes[row][col]
            k = _nearest_index(replay.times, time_value)
            ax.imshow(
                grids[(mode, col)],
                extent=[0, replay.room.width, 0, replay.room.height],
                origin="lower",
                cmap="YlOrRd",
                vmin=0.0,
                vmax=max_density,
                interpolation="bilinear",
            )
            ax.set_xlim(0, replay.room.width + replay.room.exit_depth)
            ax.set_ylim(0, replay.room.height)
            ax.set_aspect("equal", adjustable="box")
            ax.set_title(f"{mode} t={replay.times[k]:.1f}s", fontsize=10)
            ax.plot([0, replay.room.width], [0, 0], color="#111827", linewidth=1.3)
            ax.plot([0, replay.room.width], [replay.room.height, replay.room.height], color="#111827", linewidth=1.3)
            ax.plot([0, 0], [0, replay.room.height], color="#111827", linewidth=1.3)
            ax.plot([replay.room.width, replay.room.width], [0, replay.room.exit_y_min], color="#111827", linewidth=1.3)
            ax.plot([replay.room.width, replay.room.width], [replay.room.exit_y_max, replay.room.height], color="#111827", linewidth=1.3)
            ax.set_xlabel("x [m]")
            ax.set_ylabel("y [m]")
    fig.suptitle("Pedestrian density heatmap snapshots", fontsize=14)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def _render_videos(run_dirs: dict[str, Path], modes: list[str], comparison_dir: Path, quality: str) -> list[Path]:
    fps = 30 if quality == "high" else 10
    trail_length = 12 if quality == "high" else 4
    outputs: list[Path] = []
    if "baseline" in run_dirs and "dbact" in run_dirs:
        output = render_side_by_side_animation(
            [run_dirs["baseline"], run_dirs["dbact"]],
            ["baseline", "dbact"],
            comparison_dir / "baseline_vs_dbact.mp4",
            fps=fps,
            trail_length=trail_length,
            heatmap=True,
        )
        if output.suffix.lower() != ".mp4":
            raise RuntimeError("MP4 rendering requires ffmpeg. Install ffmpeg or rerun with --skip-video for tests.")
        outputs.append(output)
    if len(modes) == 4 and all(mode in run_dirs for mode in ("baseline", "static", "random", "dbact")):
        ordered = ["baseline", "static", "random", "dbact"]
        output = render_side_by_side_animation(
            [run_dirs[mode] for mode in ordered],
            ordered,
            comparison_dir / "four_modes_comparison.mp4",
            fps=fps,
            trail_length=trail_length,
            heatmap=True,
        )
        if output.suffix.lower() != ".mp4":
            raise RuntimeError("MP4 rendering requires ffmpeg. Install ffmpeg or rerun with --skip-video for tests.")
        outputs.append(output)
    return outputs


def _report_markdown(config: str, steps: int, seed: int, rows: list[dict[str, Any]], generated_files: list[str]) -> str:
    header = "| Mode | Final evacuation rate | Final evacuated count | Mean speed | Congestion index | Peak near collisions | Final time |\n"
    divider = "|---|---:|---:|---:|---:|---:|---:|\n"
    table_rows = []
    for row in rows:
        table_rows.append(
            f"| {row['mode']} | {float(row.get('final_evacuation_rate') or 0.0):.3f} | "
            f"{int(row.get('final_evacuated_count') or 0)} | {float(row.get('mean_speed') or 0.0):.3f} | "
            f"{float(row.get('congestion_index') or 0.0):.3f} | {float(row.get('peak_near_collision_count') or 0.0):.0f} | "
            f"{float(row.get('final_time') or 0.0):.2f} |"
        )
    files = "\n".join(f"- `{path}`" for path in generated_files)
    return f"""# Visualization Package Report

## 1. Purpose

This stage turns the current Crowd-Management feasibility sprint into a clear visualization and presentation package. It is not final proof that DBACT-transfer is better than all baselines; it builds a clean experimental demonstration framework for discussion.

## 2. Compared Modes

- `baseline`: no guider
- `static`: fixed guider placement
- `random`: random guider motion
- `dbact`: DBACT-transfer dynamic guider placement

## 3. Scenario

- Config: `{config}`
- Scenario: simple one-exit evacuation room
- Steps: `{steps}`
- Seed: `{seed}`

This scenario is useful for first visualization, but it is not sufficient to prove advanced crowd-guidance superiority.

## 4. Generated Outputs

{files}

## 5. Result Summary

{header}{divider}{chr(10).join(table_rows)}

## 6. Interpretation

The current pipeline can run stably and produces synchronized videos, dashboards, curves, heatmaps, and metrics summaries. Guidance modes may improve some metrics compared with baseline, but in the simple one-exit scenario DBACT-transfer may not clearly outperform static guidance. This stage is proof-of-execution and visualization quality, not proof-of-method.

## 7. Limitations

- Single seed only
- Simple one-exit room
- Pedestrian behavior model is simple
- Guider influence model is heuristic
- No exit-choice behavior yet
- No bottleneck or two-exit decision scenario yet
- No multi-seed statistical validation in this package

## 8. Next Step

1. Multi-seed evaluation
2. Bottleneck / two-exit scenario
3. Route-choice / exit-choice behavior
4. Density-aware DBACT-transfer v2
5. More realistic guider-pedestrian interaction model
"""


def _write_report(config: str, steps: int, seed: int, rows: list[dict[str, Any]], output_dir: Path, generated_files: list[str]) -> None:
    text = _report_markdown(config, steps, seed, rows, generated_files)
    summary_report = output_dir / "summary" / "VISUALIZATION_PACKAGE_REPORT.md"
    summary_report.parent.mkdir(parents=True, exist_ok=True)
    summary_report.write_text(text, encoding="utf-8")
    if output_dir.name == "visualization_package_v1":
        report_path = Path("reports") / "visualization_package_v1" / "VISUALIZATION_PACKAGE_REPORT.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(text, encoding="utf-8")


def run_visualization_package(
    config: str | Path,
    modes: list[str],
    steps: int,
    seed: int,
    output: str | Path,
    quality: str = "high",
    skip_video: bool = False,
    skip_heavy_plots: bool = False,
) -> dict[str, Any]:
    config_path = Path(config)
    output_dir = Path(output)
    comparison_dir = output_dir / "comparison"
    summary_dir = output_dir / "summary"
    comparison_dir.mkdir(parents=True, exist_ok=True)
    summary_dir.mkdir(parents=True, exist_ok=True)
    base_config = SimulationConfig.from_yaml(config_path)

    run_dirs: dict[str, Path] = {}
    rows: list[dict[str, Any]] = []
    for mode in modes:
        metrics = _run_mode(config_path, base_config, mode, seed, steps, output_dir)
        run_dir = output_dir / mode
        run_dirs[mode] = run_dir
        rows.append(
            {
                "mode": mode,
                "final_evacuation_rate": _metric(metrics, "final_evacuation_rate"),
                "final_evacuated_count": _metric(metrics, "final_evacuated_count"),
                "mean_speed": _metric(metrics, "mean_speed"),
                "congestion_index": _metric(metrics, "congestion_index"),
                "peak_near_collision_count": _metric(metrics, "peak_near_collision_count"),
                "final_time": _metric(metrics, "final_time"),
                "output_dir": str(run_dir),
            }
        )

    _write_metrics_csv(summary_dir / "metrics_summary.csv", rows)
    _write_json(summary_dir / "metrics_summary.json", {"config": str(config_path), "seed": seed, "steps": steps, "modes": modes, "runs": rows})

    series_by_mode = _load_series(run_dirs)
    _save_curve_plot(series_by_mode, modes, "evacuation_rate", "evacuation rate", "Evacuation rate over time", comparison_dir / "evacuation_curve.png")
    _save_curve_plot(series_by_mode, modes, "congestion_index", "congestion index", "Congestion over time", comparison_dir / "congestion_curve.png")
    _save_curve_plot(series_by_mode, modes, "mean_active_speed", "mean speed", "Mean active speed over time", comparison_dir / "mean_speed_curve.png")
    _save_final_metrics_bar(rows, comparison_dir / "final_metrics_bar.png")
    render_dashboard([run_dirs[mode] for mode in modes], modes, comparison_dir / "four_modes_dashboard.png")
    if not skip_heavy_plots:
        _save_heatmap_snapshots(run_dirs, modes, comparison_dir / "heatmap_snapshots.png")

    video_outputs: list[Path] = []
    if not skip_video:
        video_outputs = _render_videos(run_dirs, modes, comparison_dir, quality)

    generated_files = [
        "comparison/four_modes_dashboard.png",
        "comparison/evacuation_curve.png",
        "comparison/congestion_curve.png",
        "comparison/mean_speed_curve.png",
        "comparison/final_metrics_bar.png",
        "summary/metrics_summary.csv",
        "summary/metrics_summary.json",
    ]
    if not skip_heavy_plots:
        generated_files.append("comparison/heatmap_snapshots.png")
    generated_files.extend(str(path.relative_to(output_dir)) for path in video_outputs)
    _write_report(str(config_path), steps, seed, rows, output_dir, generated_files)
    if output_dir.name == "visualization_package_v1":
        report_src = output_dir / "summary" / "VISUALIZATION_PACKAGE_REPORT.md"
        report_dst = Path("reports") / "visualization_package_v1" / "VISUALIZATION_PACKAGE_REPORT.md"
        if report_src.resolve() != report_dst.resolve():
            report_dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(report_src, report_dst)

    return {"runs": rows, "generated_files": generated_files}


def main() -> None:
    args = parse_args()
    result = run_visualization_package(
        args.config,
        args.modes,
        args.steps,
        args.seed,
        args.output,
        args.quality,
        args.skip_video,
        args.skip_heavy_plots,
    )
    print(f"Saved visualization package to {args.output}")
    print(json.dumps(result, indent=2, default=_json_default))


if __name__ == "__main__":
    main()
