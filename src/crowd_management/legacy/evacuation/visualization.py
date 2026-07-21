"""Visualization utilities for quick crowd-management reports."""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.animation import FuncAnimation, PillowWriter

from .metrics import load_timeseries
from ...types import RoomConfig, SimulationHistory


def _draw_room(ax: plt.Axes, room: RoomConfig) -> None:
    ax.set_xlim(0, room.width + room.exit_depth + 0.3)
    ax.set_ylim(0, room.height)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("x [m]")
    ax.set_ylabel("y [m]")
    # Walls.
    ax.plot([0, room.width], [0, 0], linewidth=2)
    ax.plot([0, room.width], [room.height, room.height], linewidth=2)
    ax.plot([0, 0], [0, room.height], linewidth=2)
    # Right wall split by exit.
    ax.plot([room.width, room.width], [0, room.exit_y_min], linewidth=2)
    ax.plot([room.width, room.width], [room.exit_y_max, room.height], linewidth=2)
    ax.plot([room.width, room.width + room.exit_depth], [room.exit_y_min, room.exit_y_min], linestyle="--")
    ax.plot([room.width, room.width + room.exit_depth], [room.exit_y_max, room.exit_y_max], linestyle="--")
    ax.text(room.width + 0.05, room.exit_center_y, "EXIT", va="center", fontsize=9)


def save_snapshot(history: SimulationHistory, room: RoomConfig, path: str | Path, title: str = "Crowd simulation") -> None:
    data = history.as_arrays()
    positions = data["positions"][-1]
    evacuated = data["evacuated"][-1]
    fig, ax = plt.subplots(figsize=(9, 5))
    _draw_room(ax, room)
    active = ~evacuated
    ax.scatter(positions[active, 0], positions[active, 1], s=18, label="pedestrians")
    if np.any(evacuated):
        ax.scatter(positions[evacuated, 0], positions[evacuated, 1], s=12, alpha=0.35, label="evacuated")
    if "guider_positions" in data:
        guiders = data["guider_positions"][-1]
        if len(guiders):
            ax.scatter(guiders[:, 0], guiders[:, 1], marker="^", s=90, label="guiders")
    ax.set_title(title)
    ax.legend(loc="upper left")
    fig.tight_layout()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160)
    plt.close(fig)


def save_density_heatmap(history: SimulationHistory, room: RoomConfig, path: str | Path, bins: int = 50) -> None:
    data = history.as_arrays()
    positions = data["positions"][-1]
    evacuated = data["evacuated"][-1]
    active_positions = positions[~evacuated]
    fig, ax = plt.subplots(figsize=(9, 5))
    _draw_room(ax, room)
    if len(active_positions):
        ax.hist2d(
            active_positions[:, 0],
            active_positions[:, 1],
            bins=bins,
            range=[[0, room.width], [0, room.height]],
            cmap="viridis",
        )
    ax.set_title("Final active-pedestrian density")
    fig.tight_layout()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160)
    plt.close(fig)


def save_animation(
    history: SimulationHistory,
    room: RoomConfig,
    path: str | Path,
    title: str = "Crowd simulation",
    every: int = 4,
    fps: int = 12,
) -> None:
    data = history.as_arrays()
    positions = data["positions"]
    evacuated = data["evacuated"]
    frames = list(range(0, len(positions), max(1, every)))
    if frames[-1] != len(positions) - 1:
        frames.append(len(positions) - 1)

    fig, ax = plt.subplots(figsize=(8, 4.7))
    _draw_room(ax, room)
    ped_scatter = ax.scatter([], [], s=16, label="pedestrians")
    guider_scatter = ax.scatter([], [], marker="^", s=80, label="guiders")
    time_text = ax.text(0.02, 0.96, "", transform=ax.transAxes, va="top")
    ax.set_title(title)
    ax.legend(loc="upper left")

    has_guiders = "guider_positions" in data and len(data["guider_positions"])

    def update(frame_idx: int):
        k = frames[frame_idx]
        active = ~evacuated[k]
        ped_scatter.set_offsets(positions[k][active])
        if has_guiders:
            guider_scatter.set_offsets(data["guider_positions"][k])
        else:
            guider_scatter.set_offsets(np.zeros((0, 2)))
        time_text.set_text(f"t = {data['times'][k]:.1f}s, evacuated = {evacuated[k].sum()}/{evacuated.shape[1]}")
        return ped_scatter, guider_scatter, time_text

    ani = FuncAnimation(fig, update, frames=len(frames), interval=1000 / fps, blit=True)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    ani.save(path, writer=PillowWriter(fps=fps))
    plt.close(fig)


def save_timeseries_plot(timeseries_path: str | Path, output_path: str | Path, title: str) -> None:
    series = load_timeseries(timeseries_path)
    if not series:
        return
    fig, ax = plt.subplots(figsize=(8, 4.5))
    t = series["time"]
    for key in ["evacuation_rate", "mean_active_speed", "congestion_index"]:
        if key in series:
            ax.plot(t, series[key], label=key)
    ax.set_xlabel("time [s]")
    ax.set_title(title)
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=160)
    plt.close(fig)


def save_comparison_plot(baseline_csv: str | Path, guided_csv: str | Path, output_path: str | Path) -> None:
    baseline = load_timeseries(baseline_csv)
    guided = load_timeseries(guided_csv)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    if baseline:
        ax.plot(baseline["time"], baseline["evacuation_rate"], label="baseline evacuation rate")
    if guided:
        ax.plot(guided["time"], guided["evacuation_rate"], label="guided evacuation rate")
    ax.set_xlabel("time [s]")
    ax.set_ylabel("evacuation rate")
    ax.set_ylim(0.0, 1.02)
    ax.set_title("Baseline vs guided evacuation")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=160)
    plt.close(fig)
