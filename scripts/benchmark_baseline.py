"""Phase 0 baseline benchmark harness.

Runs representative workloads as subprocesses, samples CPU/RSS via psutil,
and records wall time, CPU time, peak memory, per-case latencies, and
SHA256 hashes of result files. Workload outputs go to a scratch directory
so official results under reports/ are never touched.

Usage:
    python scripts/benchmark_baseline.py --workload small standard formal \
        --label baseline --json artifacts/performance/baseline.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from crowd_management.runtime import hardware_metadata  # noqa: E402

HASHED_RESULT_FILES = {
    "small": ("summary.json",),
    "standard": (
        "records.json",
        "records.csv",
        "aggregate.json",
        "paired_comparisons.json",
        "gate_evidence.json",
    ),
    "formal": (
        "records.json",
        "records.csv",
        "aggregate.json",
        "paired_comparisons.json",
        "ablation_records.json",
        "ablation_aggregate.json",
        "robustness_records.json",
        "robustness_aggregate.json",
        "gate_evidence.json",
    ),
}


def _workload_command(
    name: str, out_dir: Path, workers: int | None, performance_mode: str | None = None
) -> list[str]:
    if name == "small":
        return [
            sys.executable,
            str(REPO / "scripts" / "run_static_containment.py"),
            "--config",
            str(REPO / "configs" / "static_crowd_circle.yaml"),
            "--output",
            str(out_dir),
            "--methods",
            "random",
            "static_circle",
            "legacy_center_radius",
            "abcg",
        ]
    if name == "standard":
        cmd = [
            sys.executable,
            str(REPO / "scripts" / "run_step1_pr6_evaluation.py"),
            "--output",
            str(out_dir),
            "--seed-count",
            "30",
        ]
        if workers is not None:
            cmd += ["--workers", str(workers)]
        return _append_mode(cmd, performance_mode)
    if name == "formal":
        cmd = [
            sys.executable,
            str(REPO / "scripts" / "run_step1_g6_compliance.py"),
            "--output",
            str(out_dir),
            "--run-root",
            str(out_dir / "run_artifacts"),
        ]
        if workers is not None:
            cmd += ["--workers", str(workers)]
        return _append_mode(cmd, performance_mode)
    raise ValueError(f"unknown workload: {name}")


def _append_mode(cmd: list[str], performance_mode: str | None) -> list[str]:
    if performance_mode is not None:
        cmd += ["--performance-mode", performance_mode]
    return cmd


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _monitor_process(command: list[str], log_path: Path) -> dict[str, Any]:
    """Run command, sampling the process tree for CPU and peak RSS."""
    import psutil

    log_path.parent.mkdir(parents=True, exist_ok=True)
    started_wall = time.perf_counter()
    with open(log_path, "w", encoding="utf-8") as log_file:
        process = psutil.Popen(command, cwd=REPO, stdout=log_file, stderr=subprocess.STDOUT)
        peak_rss = 0
        cpu_seconds = 0.0
        samples: list[float] = []
        logical = psutil.cpu_count(logical=True) or 1
        while process.poll() is None:
            try:
                tree = [process] + process.children(recursive=True)
                rss = 0
                cpu = 0.0
                for member in tree:
                    try:
                        rss += member.memory_info().rss
                        times = member.cpu_times()
                        cpu += times.user + times.system
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
                peak_rss = max(peak_rss, rss)
                cpu_seconds = max(cpu_seconds, cpu)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
            time.sleep(0.5)
        exit_code = process.wait()
    wall_seconds = time.perf_counter() - started_wall
    utilization = cpu_seconds / wall_seconds / logical if wall_seconds > 0 else None
    return {
        "wall_time_s": wall_seconds,
        "cpu_time_s": cpu_seconds,
        "peak_rss_bytes": peak_rss,
        "mean_cpu_utilization_fraction_of_machine": utilization,
        "exit_code": exit_code,
        "samples": len(samples),
    }


def _case_latencies(workload: str, out_dir: Path) -> dict[str, Any] | None:
    """Extract per-record runtimes when the workload reports them (G6 only)."""
    records_path = out_dir / "records.json"
    if workload != "formal" or not records_path.is_file():
        return None
    records = json.loads(records_path.read_text(encoding="utf-8"))
    latencies = sorted(
        float(record["total_runtime_ms"])
        for record in records
        if record.get("total_runtime_ms") is not None
    )
    if not latencies:
        return None
    import numpy as np

    array = np.asarray(latencies)
    slowest_record = max(
        (record for record in records if record.get("total_runtime_ms") is not None),
        key=lambda record: float(record["total_runtime_ms"]),
    )
    return {
        "record_count": len(array),
        "p50_ms": float(np.percentile(array, 50.0)),
        "p90_ms": float(np.percentile(array, 90.0)),
        "p95_ms": float(np.percentile(array, 95.0)),
        "max_ms": float(array[-1]),
        "slowest_record": {
            "scenario": slowest_record.get("scenario"),
            "seed": slowest_record.get("seed"),
            "method": slowest_record.get("method"),
            "total_runtime_ms": slowest_record.get("total_runtime_ms"),
        },
    }


def _result_hashes(workload: str, out_dir: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for name in HASHED_RESULT_FILES.get(workload, ()):
        path = out_dir / name
        if path.is_file():
            hashes[name] = _sha256(path)
    return hashes


def run_workload(
    workload: str,
    label: str,
    scratch: Path,
    workers: int | None,
    performance_mode: str | None = None,
) -> dict[str, Any]:
    out_dir = scratch / label / workload
    out_dir.mkdir(parents=True, exist_ok=True)
    command = _workload_command(workload, out_dir, workers, performance_mode)
    print(f"[{workload}] running: {' '.join(command[1:3])} ...", flush=True)
    measurement = _monitor_process(command, out_dir / "benchmark_stdout.log")
    entry = {
        "workload": workload,
        "label": label,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "git_sha": _git_sha(),
        "command": [Path(part).name if Path(part).exists() else part for part in command],
        "workers_argument": workers,
        "measurement": measurement,
        "case_latencies": _case_latencies(workload, out_dir),
        "result_sha256": _result_hashes(workload, out_dir),
    }
    print(
        f"[{workload}] wall={measurement['wall_time_s']:.1f}s "
        f"cpu={measurement['cpu_time_s']:.1f}s "
        f"peak_rss={measurement['peak_rss_bytes'] / 2**20:.0f}MiB "
        f"exit={measurement['exit_code']}",
        flush=True,
    )
    return entry


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Phase 0 baseline benchmarks.")
    parser.add_argument("--workload", nargs="+", choices=("small", "standard", "formal"), required=True)
    parser.add_argument("--label", default="baseline")
    parser.add_argument("--workers", type=int, default=None, help="Override --workers for evaluation workloads.")
    parser.add_argument(
        "--performance-mode",
        default=None,
        help="Forward --performance-mode to evaluation scripts (auto worker selection).",
    )
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--scratch", default=str(REPO / ".tmp" / "benchmarks"))
    parser.add_argument("--json", default=str(REPO / "artifacts" / "performance" / "baseline.json"))
    args = parser.parse_args()

    json_path = Path(args.json)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    document: dict[str, Any] = {"hardware": hardware_metadata(), "entries": []}
    if json_path.is_file():
        document = json.loads(json_path.read_text(encoding="utf-8"))
        document.setdefault("entries", [])
        document["hardware"] = hardware_metadata()

    for repeat in range(args.repeats):
        for workload in args.workload:
            label = args.label if args.repeats == 1 else f"{args.label}-r{repeat}"
            entry = run_workload(workload, label, Path(args.scratch), args.workers, args.performance_mode)
            document["entries"].append(entry)
            json_path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {json_path}")


if __name__ == "__main__":
    main()
