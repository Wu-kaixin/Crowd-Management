"""Repository and environment snapshot helpers for auditable manifests."""

from __future__ import annotations

import hashlib
import importlib.metadata
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any


def git_output(repo: Path, *args: str) -> str:
    """Return stripped git stdout, or ``unknown`` when the command fails."""
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def repository_state(repo: Path | None = None) -> dict[str, str | bool]:
    """Compact commit/branch/dirty state used by experiment manifests."""
    repository = Path(repo).resolve() if repo is not None else Path(__file__).resolve().parents[3]
    return {
        "commit": git_output(repository, "rev-parse", "HEAD"),
        "branch": git_output(repository, "branch", "--show-current"),
        "dirty": bool(git_output(repository, "status", "--porcelain")),
    }


def package_versions(names: tuple[str, ...] | list[str]) -> dict[str, str]:
    """Map distribution names to installed versions (or ``not-installed``)."""
    versions: dict[str, str] = {}
    for distribution in names:
        try:
            versions[distribution] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            versions[distribution] = "not-installed"
    return versions


def repository_snapshot(
    repo: Path,
    source_paths: list[Path],
    *,
    include_environment: bool = True,
    package_names: tuple[str, ...] = ("numpy", "scipy", "shapely", "matplotlib", "PyYAML"),
) -> dict[str, Any]:
    """Commit-bound source digest used by formal G6/PR6 freeze checks."""
    digest = hashlib.sha256()
    for path in sorted(source_paths):
        digest.update(str(path.relative_to(repo)).encode("utf-8"))
        digest.update(path.read_bytes())
    dirty = [line for line in git_output(repo, "status", "--porcelain").splitlines() if line]
    snapshot: dict[str, Any] = {
        "commit": git_output(repo, "rev-parse", "HEAD"),
        "branch": git_output(repo, "branch", "--show-current"),
        "dirty": bool(dirty),
        "dirty_entry_count": len(dirty),
        "source_sha256": digest.hexdigest(),
        "frozen_commit": not dirty,
        "freeze_status": "FROZEN_COMMIT" if not dirty else "UNFROZEN_DIRTY_WORKTREE",
    }
    if include_environment:
        snapshot["python"] = platform.python_version()
        snapshot["platform"] = platform.platform()
        snapshot["packages"] = {name: importlib.metadata.version(name) for name in package_names}
    return snapshot


def python_environment(
    package_names: tuple[str, ...] = ("crowd-management", "numpy", "pyyaml", "matplotlib"),
) -> dict[str, Any]:
    """Environment block embedded in static-containment manifests."""
    return {
        "python": sys.version.split()[0],
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "packages": package_versions(package_names),
    }
