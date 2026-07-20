#!/usr/bin/env python
"""CLI entry point for the frozen ABCG-v2.1 Step 1 G7 protocol."""
from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src"
if str(SOURCE) not in sys.path:
    sys.path.insert(0, str(SOURCE))

from crowd_management.evaluation.step1_g7 import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
