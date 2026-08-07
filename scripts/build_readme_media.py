"""ROLE: ENTRY ONLY — regenerate README media via readme_media package.

OUTPUT: reports/media/ (PNG/GIF figures for README Visual Overview).
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from readme_media import build_media  # noqa: E402

if __name__ == "__main__":
    build_media()
