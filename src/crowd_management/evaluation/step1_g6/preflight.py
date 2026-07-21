"""G6 preflight checks and process memory helpers."""
from __future__ import annotations

import ctypes
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from ...reporting import git_output


def _run_preflight_command(repo: Path, name: str, command: list[str]) -> dict[str, Any]:
    """Run one formal preflight command and retain an auditable compact result."""
    print(f"[G6 preflight] {name}: {' '.join(command)}", flush=True)
    started = time.perf_counter()
    result = subprocess.run(command, cwd=repo, check=False, capture_output=True, text=True)
    duration_s = time.perf_counter() - started
    stdout = result.stdout or ""
    stderr = result.stderr or ""
    if stdout:
        print(stdout.rstrip(), flush=True)
    if stderr:
        print(stderr.rstrip(), file=sys.stderr, flush=True)
    return {
        "name": name,
        "command": command,
        "return_code": int(result.returncode),
        "duration_s": duration_s,
        "stdout_tail": stdout[-8000:],
        "stderr_tail": stderr[-8000:],
    }


def run_g6_preflight(repo: str | Path | None = None) -> dict[str, Any]:
    """Run the mandatory G0-G5 environment and regression checks."""
    repository = Path(repo).resolve() if repo is not None else Path(__file__).resolve().parents[4]
    commit = git_output(repository, "rev-parse", "HEAD")
    dirty_before = bool(git_output(repository, "status", "--porcelain"))
    (repository / ".tmp").mkdir(parents=True, exist_ok=True)
    commands = [
        _run_preflight_command(
            repository,
            "pytest",
            [
                sys.executable,
                "-m",
                "pytest",
                "--basetemp=.tmp/pytest-temp",
                "-o",
                "cache_dir=.tmp/pytest-cache",
            ],
        ),
        _run_preflight_command(
            repository,
            "compileall",
            [sys.executable, "-m", "compileall", "-q", "src", "scripts"],
        ),
        _run_preflight_command(repository, "pip_check", [sys.executable, "-m", "pip", "check"]),
    ]
    dirty_after = bool(git_output(repository, "status", "--porcelain"))
    return {
        "schema": "abcg-v2-step1-preflight-v1",
        "evaluated_commit": commit,
        "python_executable": sys.executable,
        "python_version": platform.python_version(),
        "environment_name": "abcg" if "abcg" in str(sys.prefix).lower() else Path(sys.prefix).name,
        "repository_clean_before": not dirty_before,
        "repository_clean_after": not dirty_after,
        "commands": commands,
        "all_passed": all(command["return_code"] == 0 for command in commands),
    }


def _preflight_is_valid(preflight: dict[str, Any] | None, snapshot: dict[str, Any]) -> bool:
    if not isinstance(preflight, dict):
        return False
    commands = preflight.get("commands")
    if not isinstance(commands, list) or not all(isinstance(command, dict) for command in commands):
        return False
    return bool(
        preflight.get("schema") == "abcg-v2-step1-preflight-v1"
        and preflight.get("evaluated_commit") == snapshot["commit"]
        and preflight.get("repository_clean_before") is True
        and preflight.get("repository_clean_after") is True
        and preflight.get("all_passed") is True
        and {command.get("name") for command in commands} == {"pytest", "compileall", "pip_check"}
        and all(command.get("return_code") == 0 for command in commands)
    )


def _process_peak_memory_bytes() -> int:
    """Return process peak resident memory without tracing every allocation."""
    if platform.system() == "Windows":
        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong),
                ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        get_current_process = ctypes.windll.kernel32.GetCurrentProcess
        get_current_process.restype = ctypes.c_void_p
        get_process_memory_info = ctypes.windll.psapi.GetProcessMemoryInfo
        get_process_memory_info.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ProcessMemoryCounters),
            ctypes.c_ulong,
        ]
        get_process_memory_info.restype = ctypes.c_int
        process = get_current_process()
        success = get_process_memory_info(
            process,
            ctypes.byref(counters),
            counters.cb,
        )
        return int(counters.PeakWorkingSetSize) if success else 0
    try:
        import resource

        peak = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        return peak if platform.system() == "Darwin" else peak * 1024
    except (ImportError, OSError):
        return 0
