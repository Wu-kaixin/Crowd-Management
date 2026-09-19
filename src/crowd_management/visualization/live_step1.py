"""Realtime Step 1 viewer.

ROLE: VISUALIZATION ONLY. Must not be imported from controllers/.

Visual language matches the repository README closed-loop / ABCG media:
crowd (light blue), estimated boundary (navy), safety / deployment (orange dashed),
targets (gray ``x``), guides (red disks), clean legend, frame title.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np

from ..types import Array

_NONINTERACTIVE_BACKENDS = {"agg", "pdf", "svg", "ps", "cairo", "template"}


def display_is_unattended() -> bool:
    """True on CI or non-interactive matplotlib backends. A GUI must not block."""
    import os

    if os.environ.get("CI", "").strip().lower() in {"1", "true", "yes"}:
        return True
    backend = os.environ.get("MPLBACKEND", "").strip().lower()
    return backend in _NONINTERACTIVE_BACKENDS


# README / figures_baseline palette
_COLOR_CROWD = "#4c78a8"
_COLOR_CROWD_GROUPS = ("#4c78a8", "#59a14f", "#b07aa1", "#edc948", "#76b7b2")
_COLOR_BOUNDARY = "#1f4e79"
_COLOR_SAFETY = "#f28e2b"
_COLOR_TARGET = "#bab0ac"
_COLOR_GUIDE = "#e15759"
_COLOR_RESERVE = "#9e9ac8"
_COLOR_ENV = "#2c3e50"
_COLOR_TRAIL = "#e15759"
_COLOR_HUD = "#374151"


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
    max_steps: int = 0
    guide_body_radius: float = 0.12
    guide_halo_radius: float = 0.30
    min_guide_distance_req: float | None = None
    min_crowd_distance_req: float | None = None
    min_wall_distance_req: float | None = None
    guide_to_target: Array | None = None
    crowd_component_ids: Array | None = None
    crowd_group_count: int = 1


def _closed(points: Array | None) -> Array | None:
    if points is None or len(points) == 0:
        return None
    array = np.asarray(points, dtype=float)
    if not np.any(~np.isfinite(array)):
        return np.vstack((array, array[0]))
    # NaN-separated multi-rings: close each finite segment independently.
    pieces: list[Array] = []
    start = 0
    for index in range(len(array) + 1):
        is_break = index == len(array) or not np.all(np.isfinite(array[index]))
        if not is_break:
            continue
        if index > start:
            segment = array[start:index]
            pieces.append(segment)
            pieces.append(segment[:1])
            pieces.append(np.array([[np.nan, np.nan]], dtype=float))
        start = index + 1
    if not pieces:
        return None
    return np.vstack(pieces[:-1])


def _fmt(value: float | None, digits: int = 3) -> str:
    if value is None or not np.isfinite(value):
        return "n/a"
    return f"{value:.{digits}f}"


def _title_text(frame: Step1Frame) -> str:
    total = int(frame.max_steps) if frame.max_steps > 0 else max(int(frame.step), 1)
    state = str(frame.controller_state or "INIT")
    groups = int(frame.crowd_group_count)
    group_tag = f" · {groups} crowds" if groups > 1 else ""
    prefix = str(frame.title_suffix).strip() or "Step 1 closed-loop tracking"
    if frame.failed:
        return f"FAILED · {state}{group_tag} · frame {int(frame.step)}/{total}"
    return f"{prefix} · frame {int(frame.step)}/{total} · {state}{group_tag}"


def _hud_text(frame: Step1Frame) -> str:
    return "\n".join(
        [
            f"RMSE {_fmt(frame.tracking_rmse, 4)}",
            f"active {frame.active_guide_count}/{len(frame.current_guides)}",
            f"gap {_fmt(frame.max_arc_gap)} m",
            f"d_gg {_fmt(frame.min_guide_guide_distance)}",
            f"d_gc {_fmt(frame.min_guide_crowd_distance)}",
            f"d_gw {_fmt(frame.min_guide_wall_distance)}",
            f"safety {frame.safety_status}",
        ]
    )


def _crowd_point_colors(frame: Step1Frame) -> list[str] | str:
    labels = frame.crowd_component_ids
    if labels is not None and len(labels) == len(frame.crowd_points) and int(frame.crowd_group_count) > 1:
        return [_COLOR_CROWD_GROUPS[int(i) % len(_COLOR_CROWD_GROUPS)] for i in labels]
    return _COLOR_CROWD


def style_axes(ax: Any, frame: Step1Frame) -> None:
    ax.set_aspect("equal", adjustable="box")
    ax.set_facecolor("white")
    ax.grid(True, alpha=0.18, color="#cfd4d8", linewidth=0.8)
    ax.set_axisbelow(True)
    xs = frame.environment_vertices[:, 0]
    ys = frame.environment_vertices[:, 1]
    pad_x = 0.03 * max(float(xs.max() - xs.min()), 1.0)
    pad_y = 0.03 * max(float(ys.max() - ys.min()), 1.0)
    ax.set_xlim(float(xs.min()) - pad_x, float(xs.max()) + pad_x)
    ax.set_ylim(float(ys.min()) - pad_y, float(ys.max()) + pad_y)


def draw_step1_scene(ax: Any, frame: Step1Frame, *, show_trails: bool = True) -> None:
    """One-shot draw matching the README closed-loop / ABCG look."""
    style_axes(ax, frame)

    env = _closed(frame.environment_vertices)
    if env is not None:
        ax.plot(env[:, 0], env[:, 1], color=_COLOR_ENV, linewidth=1.5, label="environment", zorder=1)

    if len(frame.crowd_points):
        colors = _crowd_point_colors(frame)
        multi = int(frame.crowd_group_count) > 1
        ax.scatter(
            frame.crowd_points[:, 0],
            frame.crowd_points[:, 1],
            s=12 if multi else 10,
            c=colors,
            alpha=0.55 if multi else 0.45,
            linewidths=0.0,
            label=f"crowd x{int(frame.crowd_group_count)}" if multi else "crowd",
            zorder=2,
        )

    crowd_b = _closed(frame.estimated_crowd_boundary)
    if crowd_b is not None:
        ax.plot(
            crowd_b[:, 0],
            crowd_b[:, 1],
            color=_COLOR_BOUNDARY,
            linewidth=1.4,
            label="boundary",
            zorder=3,
        )

    deploy = _closed(frame.deployment_curve)
    if deploy is not None:
        ax.plot(
            deploy[:, 0],
            deploy[:, 1],
            color=_COLOR_SAFETY,
            linewidth=1.5,
            linestyle="--",
            label="safety",
            zorder=4,
        )

    if show_trails and frame.trails is not None and len(frame.trails) > 1:
        for guide_id in range(frame.trails.shape[1]):
            path = frame.trails[:, guide_id, :]
            ax.plot(path[:, 0], path[:, 1], color=_COLOR_TRAIL, alpha=0.22, linewidth=0.9, zorder=3)

    if frame.target_positions is not None and len(frame.target_positions):
        ax.scatter(
            frame.target_positions[:, 0],
            frame.target_positions[:, 1],
            s=42,
            c=_COLOR_TARGET,
            marker="x",
            linewidths=1.1,
            label="targets",
            zorder=5,
        )

    guides = np.asarray(frame.current_guides, dtype=float)
    if len(guides):
        active = np.array(frame.active_ids, dtype=int)
        reserve = np.array(frame.reserve_ids, dtype=int)
        if len(active):
            ax.scatter(
                guides[active, 0],
                guides[active, 1],
                s=78,
                c=_COLOR_GUIDE,
                edgecolors="white",
                linewidths=0.85,
                label="guides",
                zorder=6,
            )
        if len(reserve):
            ax.scatter(
                guides[reserve, 0],
                guides[reserve, 1],
                s=55,
                c=_COLOR_RESERVE,
                edgecolors="white",
                linewidths=0.7,
                label="reserve",
                zorder=6,
            )
        if not len(active) and not len(reserve):
            ax.scatter(
                guides[:, 0],
                guides[:, 1],
                s=78,
                c=_COLOR_GUIDE,
                edgecolors="white",
                linewidths=0.85,
                label="guides",
                zorder=6,
            )

    ax.set_title(_title_text(frame), fontsize=11, color="#1f2937", pad=8)
    ax.legend(loc="upper right", fontsize=8, frameon=True, fancybox=False, edgecolor="#d1d5db")
    ax.text(
        0.02,
        0.02,
        _hud_text(frame),
        transform=ax.transAxes,
        va="bottom",
        ha="left",
        fontsize=8,
        fontfamily="monospace",
        color=_COLOR_HUD,
        linespacing=1.3,
        bbox={
            "boxstyle": "round,pad=0.35",
            "facecolor": (1.0, 1.0, 1.0, 0.88),
            "edgecolor": "#d1d5db",
            "linewidth": 0.7,
        },
        zorder=20,
    )


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
        block: bool = True,
    ) -> None:
        if render_every < 1:
            raise ValueError("render_every must be a positive integer.")
        if not np.isfinite(max_fps) or max_fps <= 0.0:
            raise ValueError("max_fps must be finite and positive.")
        self.render_every = int(render_every)
        self.max_fps = float(max_fps)
        self.show_trails = bool(show_trails)
        self.block = bool(block)
        self.closed = False
        self.backend_name = "unset"
        self._plt: Any = None
        self._fig: Any = None
        self._ax: Any = None
        self._hud: Any = None
        self._artists: dict[str, Any] = {}
        self._last_draw = 0.0
        self._frame_count = 0
        self._min_interval = 1.0 / self.max_fps
        self._legend = None

    def _ensure_backend(self) -> Any:
        import os

        import matplotlib

        env_backend = os.environ.get("MPLBACKEND", "").strip()
        candidates: list[str] = []
        if env_backend and env_backend.lower() not in {"agg", "pdf", "svg", "ps", "cairo", "template"}:
            candidates.append(env_backend)
        current = str(matplotlib.get_backend())
        if current.lower() not in {"agg", "pdf", "svg", "ps", "cairo", "template"}:
            candidates.append(current)
        candidates.extend(["QtAgg", "TkAgg", "Qt5Agg", "WXAgg"])

        errors: list[str] = []
        seen: set[str] = set()
        for name in candidates:
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            try:
                matplotlib.use(name, force=True)
                import matplotlib.pyplot as plt

                resolved = str(matplotlib.get_backend())
                if resolved.lower() in {"agg", "pdf", "svg", "ps", "cairo", "template"}:
                    raise RuntimeError(f"backend resolved to non-interactive {resolved!r}")
                self.backend_name = resolved
                return plt
            except Exception as exc:  # noqa: BLE001 — try next GUI backend
                errors.append(f"{name}: {type(exc).__name__}: {exc}")

        detail = "; ".join(errors) if errors else "no candidates"
        raise RuntimeError(
            "Live Step 1 visualization needs an interactive matplotlib backend "
            f"(QtAgg/TkAgg). Last errors: {detail}. "
            "For CI use --headless."
        )

    def start(self, frame: Step1Frame) -> None:
        self._plt = self._ensure_backend()
        print(
            f"[live] Opening Step 1 window (backend={self.backend_name}). "
            "Close the window after the run to continue.",
            flush=True,
        )
        self._fig, self._ax = self._plt.subplots(figsize=(7.6, 7.0))
        self._fig.patch.set_facecolor("white")
        manager = getattr(self._fig.canvas, "manager", None)
        if manager is not None and hasattr(manager, "set_window_title"):
            manager.set_window_title(f"Step 1 | {frame.scenario_name} | seed {frame.seed}")

        style_axes(self._ax, frame)

        env = _closed(frame.environment_vertices)
        (self._artists["env"],) = self._ax.plot(
            env[:, 0] if env is not None else [],
            env[:, 1] if env is not None else [],
            color=_COLOR_ENV,
            linewidth=1.5,
            label="environment",
            zorder=1,
        )
        self._artists["crowd"] = self._ax.scatter(
            frame.crowd_points[:, 0],
            frame.crowd_points[:, 1],
            s=12 if int(frame.crowd_group_count) > 1 else 10,
            c=_crowd_point_colors(frame),
            alpha=0.55 if int(frame.crowd_group_count) > 1 else 0.45,
            linewidths=0.0,
            label=(
                f"crowd x{int(frame.crowd_group_count)}"
                if int(frame.crowd_group_count) > 1
                else "crowd"
            ),
            zorder=2,
        )
        (self._artists["boundary"],) = self._ax.plot(
            [],
            [],
            color=_COLOR_BOUNDARY,
            linewidth=1.4,
            label="boundary",
            zorder=3,
        )
        (self._artists["safety"],) = self._ax.plot(
            [],
            [],
            color=_COLOR_SAFETY,
            linewidth=1.5,
            linestyle="--",
            label="safety",
            zorder=4,
        )
        (self._artists["trails"],) = self._ax.plot(
            [],
            [],
            color=_COLOR_TRAIL,
            alpha=0.22,
            linewidth=0.9,
            zorder=3,
        )
        self._artists["targets"] = self._ax.scatter(
            [],
            [],
            s=42,
            c=_COLOR_TARGET,
            marker="x",
            linewidths=1.1,
            label="targets",
            zorder=5,
        )
        self._artists["guides"] = self._ax.scatter(
            [],
            [],
            s=78,
            c=_COLOR_GUIDE,
            edgecolors="white",
            linewidths=0.85,
            label="guides",
            zorder=6,
        )
        self._artists["reserve"] = self._ax.scatter(
            [],
            [],
            s=55,
            c=_COLOR_RESERVE,
            edgecolors="white",
            linewidths=0.7,
            label="reserve",
            zorder=6,
        )
        self._hud = self._ax.text(
            0.02,
            0.02,
            "",
            transform=self._ax.transAxes,
            va="bottom",
            ha="left",
            fontsize=8,
            fontfamily="monospace",
            color=_COLOR_HUD,
            linespacing=1.3,
            bbox={
                "boxstyle": "round,pad=0.35",
                "facecolor": (1.0, 1.0, 1.0, 0.88),
                "edgecolor": "#d1d5db",
                "linewidth": 0.7,
            },
            zorder=20,
        )
        self._legend = self._ax.legend(
            loc="upper right",
            fontsize=8,
            frameon=True,
            fancybox=False,
            edgecolor="#d1d5db",
        )
        self._fig.tight_layout(pad=0.55)
        self._draw(frame, force=True)
        self._plt.show(block=False)
        self._plt.pause(0.05)
        if manager is not None and hasattr(manager, "show"):
            manager.show()
        self._fig.canvas.flush_events()

    def update(self, frame: Step1Frame) -> None:
        self._frame_count += 1
        if self._frame_count % self.render_every != 0 and not frame.failed:
            return
        now = perf_counter()
        if not frame.failed and now - self._last_draw < self._min_interval:
            return
        self._draw(frame)

    def _draw(self, frame: Step1Frame, force: bool = False) -> None:
        if self._ax is None or self._plt is None:
            self.start(frame)
            return

        crowd_b = _closed(frame.estimated_crowd_boundary)
        if crowd_b is not None:
            self._artists["boundary"].set_data(crowd_b[:, 0], crowd_b[:, 1])
        else:
            self._artists["boundary"].set_data([], [])

        deploy = _closed(frame.deployment_curve)
        if deploy is not None:
            self._artists["safety"].set_data(deploy[:, 0], deploy[:, 1])
        else:
            self._artists["safety"].set_data([], [])

        if frame.target_positions is not None and len(frame.target_positions):
            self._artists["targets"].set_offsets(frame.target_positions)
        else:
            self._artists["targets"].set_offsets(np.empty((0, 2)))

        guides = np.asarray(frame.current_guides, dtype=float)
        active = np.array(frame.active_ids, dtype=int)
        reserve = np.array(frame.reserve_ids, dtype=int)
        if len(active) and len(guides):
            self._artists["guides"].set_offsets(guides[active])
        elif len(guides) and not len(reserve):
            self._artists["guides"].set_offsets(guides)
        else:
            self._artists["guides"].set_offsets(np.empty((0, 2)))
        if len(reserve) and len(guides):
            self._artists["reserve"].set_offsets(guides[reserve])
        else:
            self._artists["reserve"].set_offsets(np.empty((0, 2)))

        if self.show_trails and frame.trails is not None and len(frame.trails) > 1:
            pieces: list[Array] = []
            for guide_id in range(frame.trails.shape[1]):
                pieces.append(frame.trails[:, guide_id, :])
                pieces.append(np.array([[np.nan, np.nan]]))
            stacked = np.vstack(pieces)
            self._artists["trails"].set_data(stacked[:, 0], stacked[:, 1])
        else:
            self._artists["trails"].set_data([], [])

        self._ax.set_title(_title_text(frame), fontsize=11, color="#1f2937", pad=8)
        self._hud.set_text(_hud_text(frame))
        if frame.failed:
            self._ax.set_facecolor("#fff7f7")
        else:
            self._ax.set_facecolor("white")

        self._fig.canvas.draw_idle()
        self._plt.pause(1.0e-3)
        self._last_draw = perf_counter()
        del force

    def save_final(self, path: str | Path, frame: Step1Frame | None = None) -> None:
        if self._fig is None:
            return
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        self._fig.savefig(output, dpi=160, facecolor="white")
        del frame

    def close(self) -> None:
        if self.closed:
            return
        if self._plt is None or self._fig is None:
            self.closed = True
            return
        if self.block and not display_is_unattended():
            print("[live] Holding window open — close it to finish.", flush=True)
            self._plt.show(block=True)
        else:
            self._plt.pause(0.2)
        try:
            self._plt.close(self._fig)
        except Exception:
            pass
        self.closed = True


def build_renderer(
    *,
    live: bool,
    render_every: int = 1,
    max_fps: float = 20.0,
    show_trails: bool = True,
    block: bool = True,
) -> NullStep1Renderer | Step1LiveRenderer:
    if live:
        return Step1LiveRenderer(
            render_every=render_every,
            max_fps=max_fps,
            show_trails=show_trails,
            block=block,
        )
    return NullStep1Renderer()
