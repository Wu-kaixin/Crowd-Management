"""Reporting helpers for auditable research outputs.

ROLE: OUTPUT HELPERS — JSON/CSV writers and git/environment snapshots.
No algorithms; used by experiments/ and evaluation/.
"""

from .jsonio import jsonable, write_json, write_records_csv
from .snapshot import (
    git_output,
    package_versions,
    python_environment,
    repository_snapshot,
    repository_state,
)

__all__ = [
    "git_output",
    "jsonable",
    "package_versions",
    "python_environment",
    "repository_snapshot",
    "repository_state",
    "write_json",
    "write_records_csv",
]
