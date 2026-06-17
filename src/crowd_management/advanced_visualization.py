"""High-quality offline visualization for crowd-management replays."""
from __future__ import annotations

import json
from math import ceil
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
try:
    import imageio_ffmpeg

    matplotlib.rcParams["animation.ffmpeg_path"] = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    pass
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.animation import FFMpegWriter, FuncAnimation, PillowWriter
from matplotlib.patches import Rectangle

from .metrics import congestion_index, load_timeseries, near_collision_count
from .replay import ReplayData, load_replay
from .types import RoomConfig

EMPTY_OFFSETS = np.empty((0, 2), dtype=float)
PED_COLOR = "#2563eb"
EXIT_TARGET_COLORS = ["#2563eb", "#dc2626", "#16a34a", "#7c3aed"]
GUIDER_COLOR = "#f97316"
TARGET_COLOR = "#16a34a"
EXIT_COLOR = "#22c55e"
TRAIL_COLOR = "#60a5fa"


def _draw_room(ax: plt.Axes, room: RoomConfig) -> None:
    ax.set_xlim(0, room.width + room.exit_depth + 0.35)
    ax.set_ylim(0, room.height)
    ax.set_aspect("equal", adjustable="box")
    ax.set_facecolor("#f8fafc")
    ax.tick_params(labelsize=8)
    ax.grid(True, color="#e2e8f0", linewidth=0.5, alpha=0.7)
    ax.plot([0, room.width], [0, 0], color="#111827", linewidth=2.0)
    ax.plot([0, room.width], [room.height, room.height], color="#111827", linewidth=2.0)
    ax.plot([0, 0], [0, room.height], color="#111827", linewidth=2.0)
    exits = room.all_exits
    y_cursor = 0.0
    for exit_cfg in sorted(exits, key=lambda item: item.y_min):
        if exit_cfg.y_min > y_cursor:
            ax.plot([room.width, room.width], [y_cursor, exit_cfg.y_min], color="#111827", linewidth=2.0)
        y_cursor = max(y_cursor, exit_cfg.y_max)
        ax.add_patch(
            Rectangle(
                (room.width, exit_cfg.y_min),
                exit_cfg.depth,
                exit_cfg.width,
                facecolor=EXIT_COLOR,
                edgecolor="#15803d",
                alpha=0.38,
                linewidth=1.5,
            )
        )
        ax.text(room.width + exit_cfg.depth * 0.5, exit_cfg.center_y, exit_cfg.id.upper(), ha="center", va="center", fontsize=8, weight="bold", color="#14532d")
    if y_cursor < room.height:
        ax.plot([room.width, room.width], [y_cursor, room.height], color="#111827", linewidth=2.0)


def _load_metrics_json(run_dir: Path) -> dict:
    path = run_dir / "metrics.json"
    if not path.is_file():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_timeseries(run_dir: Path) -> dict[str, np.ndarray]:
    path = run_dir / "timeseries.csv"
    if not path.is_file():
        return {}
    return load_timeseries(path)


def _nearest_index(times: np.ndarray, time_value: float) -> int:
    if len(times) == 0:
        return 0
    idx = int(np.searchsorted(times, time_value, side="left"))
    if idx <= 0:
        return 0
    if idx >= len(times):
        return len(times) - 1
    before = idx - 1
    return before if abs(times[before] - time_value) <= abs(times[idx] - time_value) else idx


def _frame_metrics(replay: ReplayData, k: int, series: dict[str, np.ndarray]) -> dict[str, float]:
    if series:
        j = _nearest_index(series["time"], float(replay.times[k]))
        return {
            "evacuation_rate": float(series.get("evacuation_rate", [0.0])[j]),
            "mean_speed": float(series.get("mean_active_speed", [0.0])[j]),
            "congestion": float(series.get("congestion_index", [0.0])[j]),
            "near": float(series.get("near_collision_count", [0.0])[j]),
        }
    active = ~replay.pedestrian_evacuated[k]
    speeds = np.linalg.norm(replay.pedestrian_velocities[k], axis=1)
    mean_speed = float(speeds[active].mean()) if np.any(active) else 0.0
    return {
        "evacuation_rate": float(replay.pedestrian_evacuated[k].mean()),
        "mean_speed": mean_speed,
        "congestion": congestion_index(replay.pedestrian_positions[k], replay.pedestrian_evacuated[k], replay.metrics.congestion_radius),
        "near": float(near_collision_count(replay.pedestrian_positions[k], replay.pedestrian_evacuated[k], replay.metrics.near_collision_distance)),
    }


def _density_grid(replay: ReplayData, k: int, bins: int = 48) -> np.ndarray:
    room = replay.room
    active = ~replay.pedestrian_evacuated[k]
    positions = replay.pedestrian_positions[k][active]
    if len(positions) == 0:
        return np.zeros((bins, bins), dtype=float)
    hist, _, _ = np.histogram2d(
        positions[:, 0],
        positions[:, 1],
        bins=bins,
        range=[[0, room.width], [0, room.height]],
    )
    return hist.T


def _set_offsets(scatter, values: np.ndarray) -> None:
    scatter.set_offsets(values if len(values) else EMPTY_OFFSETS)


def _target_colors(replay: ReplayData, k: int, active: np.ndarray) -> list[str]:
    if replay.target_exit_ids.size == 0:
        return [PED_COLOR] * int(np.sum(active))
    target_ids = replay.target_exit_ids[k][active]
    return [EXIT_TARGET_COLORS[int(exit_id) % len(EXIT_TARGET_COLORS)] for exit_id in target_ids]


def _save_animation(ani: FuncAnimation, fig: plt.Figure, output_path: str | Path, fps: int, bitrate: int = 12000, dpi: int = 160) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.suffix.lower() == ".mp4" and FFMpegWriter.isAvailable():
        ani.save(output, writer=FFMpegWriter(fps=fps, bitrate=bitrate), dpi=dpi)
        plt.close(fig)
        return output
    if output.suffix.lower() == ".mp4":
        plt.close(fig)
        raise RuntimeError("MP4 rendering requires ffmpeg. Install ffmpeg or choose a .gif output for lightweight tests.")
    if output.suffix.lower() == ".gif":
        ani.save(output, writer=PillowWriter(fps=fps))
        plt.close(fig)
        return output
    fallback = output.with_suffix(".gif")
    ani.save(fallback, writer=PillowWriter(fps=fps))
    plt.close(fig)
    return fallback


def _frame_sequence(replay: ReplayData, fps: int, max_frames: int | None = None) -> list[int]:
    if len(replay.times) <= 1:
        return [0]
    dt = float(np.median(np.diff(replay.times)))
    every = max(1, int(round(1.0 / max(fps * dt, 1e-9))))
    frames = list(range(0, len(replay.times), every))
    if frames[-1] != len(replay.times) - 1:
        frames.append(len(replay.times) - 1)
    if max_frames and len(frames) > max_frames:
        pick = np.linspace(0, len(frames) - 1, max_frames).round().astype(int)
        frames = [frames[i] for i in pick]
    return frames


def _draw_static_frame(ax: plt.Axes, replay: ReplayData, k: int, title: str, heatmap: bool = True) -> None:
    _draw_room(ax, replay.room)
    if heatmap:
        grid = _density_grid(replay, k)
        ax.imshow(
            grid,
            extent=[0, replay.room.width, 0, replay.room.height],
            origin="lower",
            cmap="YlOrRd",
            alpha=0.35,
            vmin=0,
            vmax=max(3.0, float(grid.max())),
            interpolation="bilinear",
        )
    active = ~replay.pedestrian_evacuated[k]
    ax.scatter(replay.pedestrian_positions[k][active, 0], replay.pedestrian_positions[k][active, 1], s=14, c=_target_colors(replay, k, active), edgecolors="none", alpha=0.88, label="pedestrians")
    if replay.guider_positions.shape[1] > 0:
        guiders = replay.guider_positions[k]
        ax.scatter(guiders[:, 0], guiders[:, 1], marker="^", s=85, c=GUIDER_COLOR, edgecolors="#7c2d12", linewidths=0.6, label="guiders")
        targets = replay.guider_targets[k]
        ax.scatter(targets[:, 0], targets[:, 1], marker="x", s=45, c=TARGET_COLOR, linewidths=1.5, label="targets")
    evacuated = int(replay.pedestrian_evacuated[k].sum())
    total = int(replay.pedestrian_evacuated.shape[1])
    ax.set_title(f"{title}\nt={replay.times[k]:.1f}s evac={evacuated}/{total}", fontsize=10)


def render_run_animation(
    run_dir: str | Path,
    output_path: str | Path,
    fps: int = 15,
    trail_length: int = 10,
    heatmap: bool = False,
    label: str | None = None,
) -> Path:
    run = Path(run_dir)
    replay = load_replay(run)
    series = _load_timeseries(run)
    title = label or replay.mode
    frames = _frame_sequence(replay, fps=fps)
    fig, ax = plt.subplots(figsize=(10, 6))
    _draw_room(ax, replay.room)
    heat_artist = None
    if heatmap:
        heat_artist = ax.imshow(
            _density_grid(replay, frames[0]),
            extent=[0, replay.room.width, 0, replay.room.height],
            origin="lower",
            cmap="YlOrRd",
            alpha=0.36,
            vmin=0,
            vmax=8,
            interpolation="bilinear",
        )
    trail_scatter = ax.scatter([], [], s=7, c=TRAIL_COLOR, alpha=0.22, edgecolors="none")
    ped_scatter = ax.scatter([], [], s=16, c=PED_COLOR, alpha=0.9, edgecolors="none", label="pedestrians")
    guider_scatter = ax.scatter([], [], marker="^", s=92, c=GUIDER_COLOR, edgecolors="#7c2d12", linewidths=0.7, label="guiders")
    target_scatter = ax.scatter([], [], marker="x", s=48, c=TARGET_COLOR, linewidths=1.4, label="targets")
    info = ax.text(0.015, 0.985, "", transform=ax.transAxes, va="top", ha="left", fontsize=9, bbox={"facecolor": "white", "alpha": 0.78, "edgecolor": "none", "pad": 5})
    ax.legend(loc="lower right", fontsize=8, framealpha=0.78)
    ax.set_title(f"2D crowd evacuation replay: {title}", fontsize=12)
    fig.tight_layout()

    def update(frame_no: int):
        k = frames[frame_no]
        active = ~replay.pedestrian_evacuated[k]
        _set_offsets(ped_scatter, replay.pedestrian_positions[k][active])
        if trail_length > 0:
            start = max(0, k - trail_length)
            trail_parts = [replay.pedestrian_positions[j][~replay.pedestrian_evacuated[j]] for j in range(start, k + 1)]
            trail = np.vstack(trail_parts) if trail_parts else EMPTY_OFFSETS
            _set_offsets(trail_scatter, trail)
        if replay.guider_positions.shape[1] > 0:
            _set_offsets(guider_scatter, replay.guider_positions[k])
            _set_offsets(target_scatter, replay.guider_targets[k])
        else:
            _set_offsets(guider_scatter, EMPTY_OFFSETS)
            _set_offsets(target_scatter, EMPTY_OFFSETS)
        if heat_artist is not None:
            heat_artist.set_data(_density_grid(replay, k))
        metrics = _frame_metrics(replay, k, series)
        evacuated = int(replay.pedestrian_evacuated[k].sum())
        total = int(replay.pedestrian_evacuated.shape[1])
        info.set_text(
            f"Scenario: {replay.scenario}\n"
            f"Mode: {title}\n"
            f"Time: {replay.times[k]:.1f} s\n"
            f"Evacuated: {evacuated} / {total}\n"
            f"Rate: {metrics['evacuation_rate']:.3f}\n"
            f"Mean speed: {metrics['mean_speed']:.2f}\n"
            f"Congestion: {metrics['congestion']:.2f}\n"
            f"Near collisions: {metrics['near']:.0f}"
        )
        artists = [ped_scatter, guider_scatter, target_scatter, trail_scatter, info]
        if heat_artist is not None:
            artists.append(heat_artist)
        return artists

    ani = FuncAnimation(fig, update, frames=len(frames), interval=1000 / fps, blit=False)
    return _save_animation(ani, fig, output_path, fps=fps)


def render_density_overlay_animation(run_dir: str | Path, output_path: str | Path, fps: int = 15, trail_length: int = 10) -> Path:
    return render_run_animation(run_dir, output_path, fps=fps, trail_length=trail_length, heatmap=True)


def render_side_by_side_animation(
    run_dirs: list[str | Path],
    labels: list[str] | None,
    output_path: str | Path,
    fps: int = 15,
    trail_length: int = 8,
    heatmap: bool = True,
    max_frames: int | None = None,
) -> Path:
    runs = [Path(run) for run in run_dirs]
    replays = [load_replay(run) for run in runs]
    series_list = [_load_timeseries(run) for run in runs]
    labels = labels or [replay.mode for replay in replays]
    if len(labels) != len(replays):
        raise ValueError("labels must have the same length as run_dirs")
    if len(replays) not in {2, 4}:
        raise ValueError("render_side_by_side_animation supports exactly 2 or 4 runs")

    end_time = min(float(replay.times[-1]) for replay in replays)
    base_frames = _frame_sequence(replays[0], fps=fps, max_frames=max_frames)
    common_times = [float(replays[0].times[k]) for k in base_frames if float(replays[0].times[k]) <= end_time]
    if not common_times or common_times[-1] < end_time:
        common_times.append(end_time)

    rows, cols = (1, 2) if len(replays) == 2 else (2, 2)
    fig, axes_arr = plt.subplots(rows, cols, figsize=(10 * cols, 7.0 * rows), squeeze=False)
    axes = list(axes_arr.ravel())
    artists = []
    for ax, replay, label in zip(axes, replays, labels):
        _draw_room(ax, replay.room)
        ax.set_title(label, fontsize=12)
        heat_artist = None
        if heatmap:
            heat_artist = ax.imshow(
                _density_grid(replay, 0),
                extent=[0, replay.room.width, 0, replay.room.height],
                origin="lower",
                cmap="YlOrRd",
                alpha=0.34,
                vmin=0,
                vmax=8,
                interpolation="bilinear",
            )
        trail = ax.scatter([], [], s=6, c=TRAIL_COLOR, alpha=0.20, edgecolors="none")
        ped = ax.scatter([], [], s=14, c=PED_COLOR, alpha=0.88, edgecolors="none")
        guider = ax.scatter([], [], marker="^", s=78, c=GUIDER_COLOR, edgecolors="#7c2d12", linewidths=0.6)
        target = ax.scatter([], [], marker="x", s=38, c=TARGET_COLOR, linewidths=1.2)
        info = ax.text(0.015, 0.985, "", transform=ax.transAxes, va="top", ha="left", fontsize=8.5, bbox={"facecolor": "white", "alpha": 0.76, "edgecolor": "none", "pad": 4})
        artists.append({"heat": heat_artist, "trail": trail, "ped": ped, "guider": guider, "target": target, "info": info})
    fig.suptitle("Synchronized crowd-management comparison", fontsize=14)
    fig.tight_layout()

    def update(frame_no: int):
        time_value = common_times[frame_no]
        updated = []
        for replay, label, series, group in zip(replays, labels, series_list, artists):
            k = _nearest_index(replay.times, time_value)
            active = ~replay.pedestrian_evacuated[k]
            _set_offsets(group["ped"], replay.pedestrian_positions[k][active])
            group["ped"].set_color(_target_colors(replay, k, active))
            if trail_length > 0:
                start = max(0, k - trail_length)
                parts = [replay.pedestrian_positions[j][~replay.pedestrian_evacuated[j]] for j in range(start, k + 1)]
                _set_offsets(group["trail"], np.vstack(parts) if parts else EMPTY_OFFSETS)
            if replay.guider_positions.shape[1] > 0:
                _set_offsets(group["guider"], replay.guider_positions[k])
                _set_offsets(group["target"], replay.guider_targets[k])
            else:
                _set_offsets(group["guider"], EMPTY_OFFSETS)
                _set_offsets(group["target"], EMPTY_OFFSETS)
            if group["heat"] is not None:
                group["heat"].set_data(_density_grid(replay, k))
                updated.append(group["heat"])
            metrics = _frame_metrics(replay, k, series)
            evacuated = int(replay.pedestrian_evacuated[k].sum())
            total = int(replay.pedestrian_evacuated.shape[1])
            group["info"].set_text(
                f"{label}\n"
                f"t={replay.times[k]:.1f}s  evac={evacuated}/{total}\n"
                f"rate={metrics['evacuation_rate']:.3f}\n"
                f"speed={metrics['mean_speed']:.2f}\n"
                f"cong={metrics['congestion']:.2f}  near={metrics['near']:.0f}"
            )
            updated.extend([group["trail"], group["ped"], group["guider"], group["target"], group["info"]])
        return updated

    ani = FuncAnimation(fig, update, frames=len(common_times), interval=1000 / fps, blit=False)
    return _save_animation(ani, fig, output_path, fps=fps)


def render_grid_comparison(run_dirs: list[str | Path], labels: list[str], output_path: str | Path, heatmap: bool = True) -> Path:
    if len(run_dirs) != 4 or len(labels) != 4:
        raise ValueError("render_grid_comparison expects four runs and four labels")
    replays = [load_replay(run) for run in run_dirs]
    fig, axes = plt.subplots(2, 2, figsize=(13, 8), squeeze=False)
    for ax, replay, label in zip(axes.ravel(), replays, labels):
        _draw_static_frame(ax, replay, len(replay.times) - 1, label, heatmap=heatmap)
    handles, legend_labels = axes.ravel()[0].get_legend_handles_labels()
    if handles:
        fig.legend(handles, legend_labels, loc="lower center", ncol=4, fontsize=9)
    fig.suptitle("Final crowd-management snapshots", fontsize=14)
    fig.tight_layout(rect=[0, 0.04, 1, 0.96])
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=170)
    plt.close(fig)
    return output


def render_dashboard(run_dirs: list[str | Path], labels: list[str], output_path: str | Path) -> Path:
    if len(run_dirs) != len(labels):
        raise ValueError("labels must have the same length as run_dirs")
    runs = [Path(run) for run in run_dirs]
    replays = [load_replay(run) for run in runs]
    series_list = [_load_timeseries(run) for run in runs]
    summaries = [_load_metrics_json(run) for run in runs]
    cols = max(2, len(runs))
    fig = plt.figure(figsize=(4.2 * cols, 9.2))
    gs = fig.add_gridspec(2, cols, height_ratios=[1.0, 1.35])
    ax_curve = fig.add_subplot(gs[0, : max(1, cols // 2)])
    ax_metrics = fig.add_subplot(gs[0, max(1, cols // 2) :])

    for label, series in zip(labels, series_list):
        if series:
            ax_curve.plot(series["time"], series["evacuation_rate"], label=label, linewidth=2)
    ax_curve.set_title("Evacuation rate over time")
    ax_curve.set_xlabel("time [s]")
    ax_curve.set_ylabel("evacuation rate")
    ax_curve.set_ylim(0.0, 1.02)
    ax_curve.grid(True, alpha=0.3)
    ax_curve.legend(fontsize=8)

    metric_keys = ["final_evacuation_rate", "mean_speed", "congestion_index", "near_collision_count"]
    values = np.asarray([[float(summary.get(key, 0.0) or 0.0) for key in metric_keys] for summary in summaries], dtype=float)
    denom = np.maximum(values.max(axis=0), 1e-9)
    normalized = values / denom
    x = np.arange(len(labels))
    width = 0.18
    for i, key in enumerate(metric_keys):
        ax_metrics.bar(x + (i - 1.5) * width, normalized[:, i], width=width, label=key)
    ax_metrics.set_xticks(x)
    ax_metrics.set_xticklabels(labels, rotation=20)
    ax_metrics.set_ylim(0.0, 1.08)
    ax_metrics.set_title("Final metrics comparison (normalized)")
    ax_metrics.grid(True, axis="y", alpha=0.25)
    ax_metrics.legend(fontsize=7)

    for i, (replay, label) in enumerate(zip(replays, labels)):
        ax = fig.add_subplot(gs[1, i])
        _draw_static_frame(ax, replay, len(replay.times) - 1, label, heatmap=True)
        ax.set_xlabel("")
        ax.set_ylabel("")
    fig.suptitle("2D crowd-management visualization dashboard", fontsize=15)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=170)
    plt.close(fig)
    return output


def render_heatmap_snapshots(run_dir: str | Path, times: list[float], output_path: str | Path) -> Path:
    replay = load_replay(run_dir)
    if not times:
        times = [float(replay.times[-1])]
    n = len(times)
    cols = min(4, n)
    rows = ceil(n / cols)
    fig, axes = plt.subplots(rows, cols, figsize=(4.7 * cols, 4.1 * rows), squeeze=False)
    for ax in axes.ravel()[n:]:
        ax.axis("off")
    for ax, time_value in zip(axes.ravel(), times):
        k = _nearest_index(replay.times, float(time_value))
        _draw_static_frame(ax, replay, k, f"t={replay.times[k]:.1f}s", heatmap=True)
    fig.suptitle(f"Density heatmap snapshots: {replay.mode}", fontsize=14)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=170)
    plt.close(fig)
    return output
