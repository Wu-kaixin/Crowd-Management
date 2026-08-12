"""README Visual Overview media builder package.

ROLE: media builder; reads reports/ and writes reports/media/.
OUTPUT: reports/media/ (PNG/GIF figures for README Visual Overview).

Outputs under ``reports/media/``:

- ``abcg_static_containment_grid.png`` / ``.gif`` / ``abcg_metrics_summary.png``
  illustrative static deployments on circle, ellipse, irregular, and two-cluster crowds
- ``step1_g6_scenarios.png`` formal G6 scenario shapes (circle, ellipse, U, C)
- ``step1_baseline_comparison.png`` random / static-circle / legacy / ABCG baselines
- ``step1_closed_loop.gif`` fixed-target feedback episode on an ellipse crowd
- ``step1_g6_success_rates.png`` committed G6 primary success rates
- ``step1_failure_gallery.png`` copy of the formal G6 actual-failure gallery
"""

from __future__ import annotations

from .constants import MEDIA_DIR
from .figures_baseline import build_baseline_comparison, build_closed_loop_gif
from .figures_g6 import build_g6_scenarios, build_g6_success_rates, copy_failure_gallery
from .figures_static import build_static_overview


def build_media() -> None:
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    build_static_overview()
    build_g6_scenarios()
    build_baseline_comparison()
    build_closed_loop_gif()
    build_g6_success_rates()
    copy_failure_gallery()


__all__ = ["build_media"]
