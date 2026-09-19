"""Pytest session defaults. ROLE: TEST HARNESS ONLY."""

from __future__ import annotations

import os

# Non-interactive backend so a forgotten live=True cannot hang Windows CI.
os.environ.setdefault("MPLBACKEND", "Agg")
