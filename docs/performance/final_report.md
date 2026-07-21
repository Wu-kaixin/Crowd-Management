# Final performance report (perf-hardware-aware-refactor)

Machine: desktop, Intel Raptor Lake 24C/32T (8P+16E), 63.8 GiB RAM,
Windows 11, Python 3.12.13 (conda `abcg`), NumPy 2.4.6, SciPy 1.18.0,
scipy-openblas. Raw data: `artifacts/performance/baseline_desktop.json`
(old code) and `artifacts/performance/comparison_desktop.json` (new code,
four worker configurations). Consistency tooling:
`scripts/compare_results.py`.

## What changed

1. **Vectorized `has_self_intersections`** (was ~65 % of total CPU:
   100M-call pure-Python O(K²) predicate) — same predicate, bitwise
   identical, locked by `tests/step1/test_hotspot_characterization.py`.
2. **Vectorized `_build_velocity_halfspaces`** (was ~30 % of episode
   cost) — identical constraint rows/ordering, bitwise-locked.
3. **`ThreadPoolExecutor` → dynamic `ProcessPoolExecutor`**
   (`runtime/executor.py`): one case per task, unordered completion with
   order-preserving collection, worker exceptions propagate.
4. **BLAS thread governance**: worker processes inherit
   `OMP/MKL/OPENBLAS/NUMEXPR/VECLIB_*_THREADS=1` before NumPy import,
   plus a threadpoolctl initializer; serial paths run under
   `threadpool_limits(1)` (measured 1.57x serial win on tiny arrays).
5. **Hardware-aware worker selection** (`--workers auto`, default;
   `--performance-mode conservative|balanced|maximum`; manual override
   `--workers N` kept). Balanced on this machine: 23 workers
   (physical−1), BLAS=1 each. The resolved plan and privacy-safe
   hardware metadata are printed at startup and written to
   `runtime_metadata.json` next to the results.

## Formal workload (G6 compliance, 30 seeds, 600 records)

| Configuration | Wall time | vs old default | CPU time | Peak RSS (tree) | p50 / p95 / max record |
| --- | ---: | ---: | ---: | ---: | --- |
| old code, thread pool, workers=4 | 2011.7 s | 1.0x | 1978.5 s | 387 MiB | 9.34 / 35.5 / 51.6 s |
| new code, workers=1 | 161.5 s | **12.5x** | 147.6 s | 310 MiB | 0.22 / 1.29 / 2.23 s |
| new code, workers=4 | 45.5 s | **44x** | 92.5 s | 440 MiB | 0.21 / 0.84 / 1.66 s |
| new code, auto balanced (23 w) | **27.1 s** | **74x** | 184.3 s | 2017 MiB | 0.41 / 1.82 / 2.20 s |
| new code, auto maximum (31 w) | 27.9 s | 72x | 218.3 s | 2749 MiB | 0.58 / 2.40 / 2.85 s |

## Standard workload (PR6 paired evaluation, 30 seeds)

| Configuration | Wall time | vs old default |
| --- | ---: | ---: |
| old code, thread pool, workers=4 | 320.5 s | 1.0x |
| new code, workers=1 | 26.3 s | 12.2x |
| new code, workers=4 | 8.6 s | 37x |
| new code, auto balanced | **5.6 s** | **57x** |
| new code, auto maximum | 5.7 s | 56x |

## Analysis

- The 12.2–12.5x single-worker speedup comes from the two hotspot
  vectorizations plus single-threaded BLAS; it requires no parallelism
  and applies on any machine.
- Process parallelism adds a further ~6x at 23 workers (parallel
  efficiency ~26 %: the residual is Windows spawn+import cost (~5 s),
  the serial preflight/aggregation/report phase, and the long-tail
  cases; per-record p95/p50 ≈ 4 so dynamic scheduling is already doing
  the load-balancing work).
- `maximum` (31 workers) is *not* faster than `balanced` (23): E-core
  contention and extra spawn overhead cancel the additional slots,
  which is why `balanced` remains the default.
- Peak RSS for the 23-worker run is ~2 GiB across the whole process
  tree (~85 MiB per worker) — comfortable here; the planner's memory
  cap reduces workers automatically on small-RAM machines.

## Scientific consistency (acceptance evidence)

- Full pytest suite: **168 passed** (was 77 before this branch; new
  tests: runtime module, executor, bitwise hotspot characterization).
- `compare_results.py` on formal outputs, old code (frozen commit
  1c3642c) vs new code, same seeds: `records.json`, `aggregate.json`,
  `paired_comparisons.json`, `ablation_records.json`,
  `ablation_aggregate.json`, `robustness_records.json`,
  `robustness_aggregate.json` — **all scientific fields identical**
  (runtimes/memory/commit fields excluded by design). The only
  differences are commit-derived gate fields (`frozen_commit`,
  preflight status), which report which commit was evaluated, not what
  was measured.
- workers=1 vs auto-maximum (new code): **bitwise identical including
  gate evidence** — worker count provably does not affect results.
- Vectorized kernels are locked to the original loop implementations
  bitwise by 68 characterization tests.
- No tolerance was widened anywhere; results are exact, not
  "within tolerance".

## Reproduction commands

```bash
# formal evaluation, hardware-adaptive (default)
python scripts/run_step1_g6_compliance.py

# explicit control
python scripts/run_step1_g6_compliance.py --workers 8
python scripts/run_step1_g6_compliance.py --performance-mode maximum

# PR6 standard evaluation
python scripts/run_step1_pr6_evaluation.py --output reports/step1_pr6_evaluation --seed-count 30

# re-run the acceptance comparison
python scripts/benchmark_baseline.py --workload formal --label check --performance-mode balanced --json artifacts/performance/comparison_desktop.json
python scripts/compare_results.py --reference <old_output_dir> --candidate <new_output_dir>
```

## Not implemented (and why)

- **Episode-level task granularity**: case-level parallelism already
  saturates the win; splitting below the paired-comparison unit risks
  seed-alignment semantics for no measured need.
- **Numba / sparse structures**: after vectorization the residual
  hotspots are NumPy-bound; no profiling evidence justifies the extra
  dependency.
- **Caching across bootstrap resamples**: each resample uses a
  different point subset, so the geometry genuinely differs; nothing
  invariant to cache without changing the estimator's definition.

## Known machine note

The G6 preflight shells out to the standard pytest command. A stale
`.tmp/pytest-temp` directory with a broken ACL (left by an earlier
sandboxed run) made preflight report failures during the comparison
runs on this desktop; it has been removed. This affected only the
`formal_preflight` gate field, never the evaluation records.
