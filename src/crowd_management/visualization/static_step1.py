"""Post-run Step 1 scene export.

ROLE: VISUALIZATION ONLY. Same visual language as the live viewer.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt

from .live_step1 import Step1Frame, draw_step1_scene


def save_final_scene(frame: Step1Frame, output_path: str | Path) -> None:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(7.6, 7.0))
    fig.patch.set_facecolor("white")
    draw_step1_scene(ax, frame, show_trails=True)
    fig.tight_layout(pad=0.55)
    fig.savefig(output, dpi=160, facecolor="white")
    plt.close(fig)
