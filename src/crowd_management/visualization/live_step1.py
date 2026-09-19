"""Realtime Step 1 viewer.

ROLE: VISUALIZATION ONLY. Must not be imported from controllers/.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np

from ..types import Array


@dataclass
class Step1Frame:
    """One viewer frame. Environment and estimated crowd remain distinct."""

    scenario_name: str
    seed: int
    time: float
    step: int
    environment_vertices: Array
    crowd_points: Array
    crowd_radii: Array | None
    crowd_demand: Array | None
    estimated_crowd_boundary: Array | None
    deployment_curve: Array | None
    target_positions: Array | None
    initial_guides: Array
    current_guides: Array
    active_ids: tuple[int, ...]
    reserve_ids: tuple[int, ...]
    trails: Array | None
    controller_state: str
    tracking_rmse: float | None = None
    active_guide_count: int = 0
    max_arc_gap: float | None = None
    min_guide_guide_distance: float | None = None
    min_guide_crowd_distance: float | None = None
    min_guide_wall_distance: float | None = None
    safety_status: str = "not_available"
    failed: bool = False
    failure_reason: str | None = None
    title_suffix: str = ""


class NullStep1Renderer:
    """Non-GUI renderer for tests and `--headless` numerical equivalence."""

    def __init__(self) -> None:
        self.frames: list[Step1Frame] = []
        self.closed = False

    def start(self, frame: Step1Frame) -> None:
        self.frames.append(frame)

    def update(self, frame: Step1Frame) -> None:
        self.frames.append(frame)

    def close(self) -> None:
        self.closed = True

    def save_final(self, path: str | Path, frame: Step1Frame | None = None) -> None:
        del path, frame


class Step1LiveRenderer:
    """Interactive matplotlib viewer. GUI refresh must not change controller dt."""

    def __init__(
        self,
        *,
        render_every: int = 1,
        max_fps: float = 20.0,
        show_trails: bool = True,
        block: bool = False,
    ) -> None:
        if render_every < 1:
            raise ValueError("render_every must be a positive integer.")
        if not np.isfinite(max_fps) or max_fps <= 0.0:
            raise ValueError("max_fps must be finite and positive.")
        self.render_every = int(render_every)
        self.max_fps = float(max_fps)
        self.show_trails = bool(show_trails)
        self.block = bool(block)
        self._plt: Any = None
        self._fig: Any = None
        self._ax: Any = None
        self._hud: Any = None
        self._artists: dict[str, Any] = {}
        self._last_draw = 0.0
        self._frame_count = 0
        self._min_interval = 1.0 / self.max_fps

    def _ensure_backend(self) -> Any:
        import matplotlib
        import matplotlib.pyplot as plt

        backend = str(matplotlib.get_backend()).lower()
        if backend == "agg":
            # Live mode requested an interactive window. Try a GUI backend
            # without forcing Agg globally for the rest of the process.
            for candidate in ("QtAgg", "TkAgg", "WXAgg"):
                try:
                    matplotlib.use(candidate, force=False)
                    import matplotlib.pyplot as plt_gui

                    return plt_gui
                except Exception:
                    continue
        return plt

    def start(self, frame: Step1Frame) -> None:
        self._plt = self._ensure_backend()
        self._fig, self._ax = self._plt.subplots(figsize=(9.2, 7.2))
        self._fig.canvas.manager.set_window_title(
            f"Step 1 | {frame.scenario_name} | seed {frame.seed}"
        ) if getattr(self._fig.canvas, "manager", None) is not None else None
        self._ax.set_aspect("equal", adjustable="box")
        self._ax.grid(True, alpha=0.18)
        env = np.vstack((frame.environment_vertices, frame.environment_vertices[0]))
        (self._artists["env"],) = self._ax.plot(
            env[:, 0],
            env[:, 1],
            color="#1b1b1b",
            linewidth=2.4,
            label="environment boundary",
        )
        crowd_colors = "#4c78a8"
        if frame.crowd_demand is not None:
            self._artists["crowd"] = self._ax.scatter(
                frame.crowd_points[:, 0],
                frame.crowd_points[:, 1],
                c=frame.crowd_demand,
                cmap="YlOrRd",
                s=18,
                alpha=0.85,
                label="static crowd / demand",
                zorder=3,
            )
        else:
            self._artists["crowd"] = self._ax.scatter(
                frame.crowd_points[:, 0],
                frame.crowd_points[:, 1],
                c=crowd_colors,
                s=16,
                alpha=0.7,
                label="static crowd",
                zorder=3,
            )
        (self._artists["crowd_boundary"],) = self._ax.plot(
            [],
            [],
            color="#2f4b7c",
            linewidth=2.0,
            label="estimated crowd boundary",
        )
        (self._artists["deployment"],) = self._ax.plot(
            [],
            [],
            color="#f58518",
            linewidth=2.0,
            linestyle="--",
            label="deployment curve",
        )
        self._artists["targets"] = self._ax.scatter(
            [],
            [],
            marker="+",
            s=70,
            c="#54a24b",
            label="guide targets",
            zorder=4,
        )
        self._artists["initial"] = self._ax.scatter(
            frame.initial_guides[:, 0],
            frame.initial_guides[:, 1],
            marker="o",
            facecolors="none",
            edgecolors="#9d755d",
            s=70,
            label="initial guides",
            zorder=4,
        )
        self._artists["active"] = self._ax.scatter(
            [],
            [],
            marker="^",
            s=90,
            c="#e45756",
            edgecolors="white",
            label="active guides",
            zorder=5,
        )
        self._artists["reserve"] = self._ax.scatter(
            [],
            [],
            marker="s",
            s=55,
            c="#9e9ac8",
            edgecolors="white",
            label="reserve guides",
            zorder=5,
        )
        (self._artists["trails"],) = self._ax.plot(
            [],
            [],
            color="#e45756",
            alpha=0.35,
            linewidth=1.0,
            label="guide trails",
        )
        self._hud = self._ax.text(
            0.98,
            0.98,
            "",
            transform=self._ax.transAxes,
            va="top",
            ha="right",
            fontsize=8.5,
            family="monospace",
            bbox={"facecolor": "white", "alpha": 0.86, "edgecolor": "#cccccc"},
        )
        self._ax.legend(loc="lower left", frameon=True, fontsize=8)
        self._draw(frame, force=True)
        self._plt.show(block=False)
        self._plt.pause(1.0e-3)

    def update(self, frame: Step1Frame) -> None:
        self._frame_count += 1
        if self._frame_count % self.render_every != 0 and not frame.failed:
            return
        now = perf_counter()
        if not frame.failed and now - self._last_draw < self._min_interval:
            return
        self._draw(frame)

    def _closed(self, points: Array | None) -> Array | None:
        if points is None or len(points) == 0:
            return None
        return np.vstack((points, points[0]))

    def _draw(self, frame: Step1Frame, force: bool = False) -> None:
        if self._ax is None or self._plt is None:
            self.start(frame)
            return
        crowd_b = self._closed(frame.estimated_crowd_boundary)
        if crowd_b is not None:
            self._artists["crowd_boundary"].set_data(crowd_b[:, 0], crowd_b[:, 1])
        deploy = self._closed(frame.deployment_curve)
        if deploy is not None:
            self._artists["deployment"].set_data(deploy[:, 0], deploy[:, 1])
        if frame.target_positions is not None and len(frame.target_positions):
            self._artists["targets"].set_offsets(frame.target_positions)
        guides = frame.current_guides
        active = np.array(frame.active_ids, dtype=int)
        reserve = np.array(frame.reserve_ids, dtype=int)
        if len(active):
            self._artists["active"].set_offsets(guides[active])
        else:
            self._artists["active"].set_offsets(np.empty((0, 2)))
        if len(reserve):
            self._artists["reserve"].set_offsets(guides[reserve])
        else:
            self._artists["reserve"].set_offsets(np.empty((0, 2)))
        if self.show_trails and frame.trails is not None and len(frame.trails) > 1:
            # trails shape (T, M, 2) → plot as faint polylines by flattening with NaN breaks
            pieces = []
            for guide_id in range(frame.trails.shape[1]):
                pieces.append(frame.trails[:, guide_id, :])
                pieces.append(np.array([[np.nan, np.nan]]))
            stacked = np.vstack(pieces) if pieces else np.empty((0, 2))
            self._artists["trails"].set_data(stacked[:, 0], stacked[:, 1])
        banner = ""
        if frame.failed:
            banner = f"FAILED: {frame.controller_state}\nreason: {frame.failure_reason or 'n/a'}\n"
        gap = frame.max_arc_gap if frame.max_arc_gap is not None else float("nan")
        min_gg = frame.min_guide_guide_distance
        min_gc = frame.min_guide_crowd_distance
        min_gw = frame.min_guide_wall_distance
        rmse = frame.tracking_rmse if frame.tracking_rmse is not None else float("nan")
        hud = (
            f"{banner}"
            f"seed {frame.seed}\n"
            f"t = {frame.time:.2f} s   step {frame.step}\n"
            f"state {frame.controller_state}\n"
            f"RMSE {rmse:.4f}\n"
            f"active {frame.active_guide_count}   gap {gap:.3f}\n"
            f"min gg {min_gg if min_gg is not None else float('nan'):.3f}\n"
            f"min gc {min_gc if min_gc is not None else float('nan'):.3f}\n"
            f"min gw {min_gw if min_gw is not None else float('nan'):.3f}\n"
            f"safety {frame.safety_status}"
        )
        self._hud.set_text(hud)
        if frame.failed:
            self._ax.set_facecolor("#fff4f4")
        self._fig.canvas.draw_idle()
        self._plt.pause(1.0e-3)
        self._last_draw = perf_counter()
        del force

    def save_final(self, path: str | Path, frame: Step1Frame | None = None) -> None:
        if self._fig is None:
            return
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        self._fig.savefig(output, dpi=160)
        del frame

    def close(self) -> None:
        if self._plt is None:
            return
        if self.block:
            self._plt.show()
        else:
            self._plt.pause(0.05)


def build_renderer(
    *,
    live: bool,
    render_every: int = 1,
    max_fps: float = 20.0,
    show_trails: bool = True,
) -> NullStep1Renderer | Step1LiveRenderer:
    if live:
        return Step1LiveRenderer(render_every=render_every, max_fps=max_fps, show_trails=show_trails)
    return NullStep1Renderer()
