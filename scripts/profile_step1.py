"""Phase 1 profiling harness for the Step 1 evaluation pipeline.

Three probes, all read-only with respect to the measured code:

1. cProfile over a reduced-but-representative PR6/G6 workload (workers=1)
   -> top cumulative / self time functions.
2. Stage timers calling the real pipeline functions directly
   (boundary estimation incl. bootstrap, planning, assignment, episode,
   metrics, serialization) -> per-stage attribution.
3. Thread-scaling probe: the same case batch under ThreadPoolExecutor
   with varying worker counts and BLAS thread caps -> answers whether
   hotspots release the GIL and whether BLAS threads oversubscribe.

Profiling workloads use reduced seed counts; they never overwrite
official results and are not used as scientific evidence.

Usage:
    python scripts/profile_step1.py --probe cprofile stages scaling
"""
from __future__ import annotations

import argparse
import cProfile
import io
import json
import pstats
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

ARTIFACTS = REPO / "artifacts" / "performance"


def _reduced_g6_config(seed_count: int = 4, workers: int = 1):
    from crowd_management.evaluation import G6EvaluationConfig

    return G6EvaluationConfig(seeds=tuple(range(seed_count)), workers=workers)


def _profile_cprofile(seed_count: int) -> dict[str, Any]:
    """cProfile the primary G6 case path (all scenarios x methods, workers=1)."""
    from crowd_management.evaluation import step1_g6

    config = _reduced_g6_config(seed_count=seed_count)
    snapshot = {"commit": "profiling", "source_sha256": "profiling"}
    cases = [(scenario, seed) for scenario in config.scenarios for seed in config.seeds]

    profiler = cProfile.Profile()
    with tempfile.TemporaryDirectory() as scratch:
        run_root = Path(scratch)
        profiler.enable()
        for scenario, seed in cases:
            step1_g6._run_primary_case(scenario, seed, config, run_root, snapshot)
        profiler.disable()

    stats = pstats.Stats(profiler)
    stats.dump_stats(ARTIFACTS / "profile_primary.pstats")

    def top(sort_key: str, count: int = 25) -> str:
        buffer = io.StringIO()
        pstats.Stats(profiler, stream=buffer).sort_stats(sort_key).print_stats(count)
        return buffer.getvalue()

    total_time = stats.total_tt
    entries = []
    for func, (cc, nc, tt, ct, _callers) in stats.stats.items():
        entries.append({"func": pstats.func_std_string(func), "ncalls": nc, "tottime": tt, "cumtime": ct})
    entries_self = sorted(entries, key=lambda item: -item["tottime"])[:20]
    entries_cum = sorted(entries, key=lambda item: -item["cumtime"])[:20]
    builtin_time = sum(item["tottime"] for item in entries if item["func"].startswith("{"))
    return {
        "cases": len(cases),
        "total_profiled_time_s": total_time,
        "native_builtin_self_time_s": builtin_time,
        "native_builtin_fraction": builtin_time / total_time if total_time else None,
        "top_self": entries_self,
        "top_cumulative": entries_cum,
        "text_cumulative": top("cumulative"),
        "text_self": top("tottime"),
    }


def _time_call(fn: Callable[[], Any], repeats: int = 3) -> tuple[float, Any]:
    best = float("inf")
    result = None
    for _ in range(repeats):
        started = time.perf_counter()
        result = fn()
        best = min(best, time.perf_counter() - started)
    return best, result


def _profile_stages(seed_count: int) -> dict[str, Any]:
    """Time each pipeline stage on representative cases using real functions."""
    import numpy as np

    from crowd_management.controllers import (
        AssignmentConfig,
        PeriodicArcCVTConfig,
        assign_guides_to_targets,
        plan_periodic_arc_coverage,
    )
    from crowd_management.estimation import estimate_boundary_v2
    from crowd_management.evaluation import step1_g6

    config = _reduced_g6_config(seed_count=seed_count)
    stage_totals: dict[str, float] = {}
    detail: list[dict[str, Any]] = []

    for scenario in config.scenarios:
        for seed in config.seeds:
            timings: dict[str, float] = {}

            started = time.perf_counter()
            observation, truth = step1_g6._observed_case(scenario, seed, config)
            timings["case_generation"] = time.perf_counter() - started

            rng = np.random.default_rng(42_000_019 + 4099 * seed)
            boundary_config = step1_g6._boundary_config(config)
            started = time.perf_counter()
            boundary = estimate_boundary_v2(observation, boundary_config, rng)
            timings["boundary_estimation_bootstrap"] = time.perf_counter() - started

            no_bootstrap_config = step1_g6._boundary_config(config, bootstrap_samples=0)
            started = time.perf_counter()
            estimate_boundary_v2(observation, no_bootstrap_config, np.random.default_rng(1))
            timings["boundary_estimation_single"] = time.perf_counter() - started

            from crowd_management.estimation import BoundaryEstimateV2

            if isinstance(boundary, BoundaryEstimateV2):
                started = time.perf_counter()
                plan = plan_periodic_arc_coverage(boundary, config.fixed_guide_count, PeriodicArcCVTConfig(max_iterations=200))
                timings["periodic_arc_cvt_planning"] = time.perf_counter() - started

                initial, _layout = step1_g6._initial_guides(seed, config.available_guides)
                started = time.perf_counter()
                assignment = assign_guides_to_targets(initial, plan.target_xy, AssignmentConfig(lambda_switch=0.25))
                timings["hungarian_assignment"] = time.perf_counter() - started

                if assignment.status == "VALID":
                    started = time.perf_counter()
                    trace, events, metrics = step1_g6._run_feedback_episode(observation, initial, plan.target_xy, assignment, config)
                    timings["feedback_episode_with_safety"] = time.perf_counter() - started

                    started = time.perf_counter()
                    step1_g6._curve_errors(boundary.curve_points, truth)
                    step1_g6._trajectory_crossings(trace["positions"], np.flatnonzero(np.asarray(assignment.guide_to_target) >= 0))
                    timings["metrics_curve_and_crossings"] = time.perf_counter() - started

                    with tempfile.TemporaryDirectory() as scratch:
                        run_dir = Path(scratch) / "run"
                        started = time.perf_counter()
                        step1_g6._save_run_artifacts(
                            run_dir,
                            {"scenario": scenario, "seed": seed},
                            observation,
                            truth,
                            boundary,
                            plan.target_xy,
                            plan.target_s,
                            plan.h_history,
                            assignment,
                            trace,
                            events,
                            metrics,
                            {"schema": "profiling"},
                        )
                        timings["artifact_serialization"] = time.perf_counter() - started

            for stage, seconds in timings.items():
                stage_totals[stage] = stage_totals.get(stage, 0.0) + seconds
            detail.append({"scenario": scenario, "seed": seed, "timings_s": timings})

    total = sum(stage_totals.values())
    return {
        "cases": len(detail),
        "stage_totals_s": dict(sorted(stage_totals.items(), key=lambda item: -item[1])),
        "stage_fractions": {
            stage: seconds / total for stage, seconds in sorted(stage_totals.items(), key=lambda item: -item[1])
        }
        if total
        else {},
        "detail": detail,
    }


def _profile_scaling(seed_count: int) -> dict[str, Any]:
    """Measure thread-pool scaling of the real primary-case workload."""
    from crowd_management.evaluation import step1_g6

    try:
        from threadpoolctl import threadpool_limits
    except ImportError:
        threadpool_limits = None

    config = _reduced_g6_config(seed_count=seed_count)
    snapshot = {"commit": "profiling", "source_sha256": "profiling"}
    cases = [(scenario, seed) for scenario in config.scenarios for seed in config.seeds]

    def run_batch(workers: int) -> float:
        with tempfile.TemporaryDirectory() as scratch:
            run_root = Path(scratch)
            started = time.perf_counter()
            with ThreadPoolExecutor(max_workers=workers) as executor:
                list(
                    executor.map(
                        lambda case: step1_g6._run_primary_case(case[0], case[1], config, run_root, snapshot),
                        cases,
                    )
                )
            return time.perf_counter() - started

    results: list[dict[str, Any]] = []
    worker_grid = [1, 4, 16]
    for blas_limit in (None, 1):
        if blas_limit is not None and threadpool_limits is None:
            continue
        for workers in worker_grid:
            if blas_limit is None:
                elapsed = run_batch(workers)
            else:
                with threadpool_limits(limits=blas_limit):
                    elapsed = run_batch(workers)
            results.append(
                {
                    "workers": workers,
                    "blas_threads": blas_limit or "default",
                    "cases": len(cases),
                    "wall_time_s": elapsed,
                }
            )
            print(f"workers={workers:2d} blas={blas_limit or 'default':>7} wall={elapsed:.2f}s", flush=True)
    baseline = next(item["wall_time_s"] for item in results if item["workers"] == 1)
    for item in results:
        item["speedup_vs_1_worker"] = baseline / item["wall_time_s"]
    return {"cases": len(cases), "results": results}


def main() -> None:
    parser = argparse.ArgumentParser(description="Profile the Step 1 evaluation pipeline.")
    parser.add_argument("--probe", nargs="+", choices=("cprofile", "stages", "scaling"), required=True)
    parser.add_argument("--seed-count", type=int, default=4)
    parser.add_argument("--json", default=str(ARTIFACTS / "profile.json"))
    args = parser.parse_args()

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    json_path = Path(args.json)
    document: dict[str, Any] = {}
    if json_path.is_file():
        document = json.loads(json_path.read_text(encoding="utf-8"))

    for probe in args.probe:
        print(f"== probe: {probe} (seed_count={args.seed_count}) ==", flush=True)
        started = time.perf_counter()
        if probe == "cprofile":
            document["cprofile"] = _profile_cprofile(args.seed_count)
        elif probe == "stages":
            document["stages"] = _profile_stages(args.seed_count)
        else:
            document["scaling"] = _profile_scaling(args.seed_count)
        print(f"== {probe} done in {time.perf_counter() - started:.1f}s ==", flush=True)
        json_path.write_text(json.dumps(document, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"wrote {json_path}")


if __name__ == "__main__":
    main()
