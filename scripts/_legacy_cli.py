from __future__ import annotations

import runpy
from pathlib import Path


def run_legacy_script(name: str) -> None:
    repo = Path(__file__).resolve().parents[1]
    runpy.run_path(str(repo / "legacy" / "evacuation_guidance" / "scripts" / name), run_name="__main__")
