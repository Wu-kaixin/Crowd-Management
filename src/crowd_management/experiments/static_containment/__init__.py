"""Static containment experiment package.

ROLE: ORCHESTRATION for one static-containment run.
  config.py     — INPUT: YAML → typed config
  methods.py    — baseline target placement
  runner.py     — pipeline glue (_run_method / summary assembly)
  artifacts.py  — OUTPUT writers (public names)
  manifest.py   — run_status state machine + manifest assembly
  records.py    — TypedDict contracts (summary / manifest)
Entry CLI: scripts/run_static_containment.py
"""

from .config import StaticContainmentConfig
from .manifest import build_manifest, resolve_run_status
from .records import MethodSummary, StaticManifest
from .runner import run_static_containment

__all__ = [
    "MethodSummary",
    "StaticContainmentConfig",
    "StaticManifest",
    "build_manifest",
    "resolve_run_status",
    "run_static_containment",
]
