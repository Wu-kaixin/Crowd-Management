# Phase 0 baseline report

Measured on branch `perf-hardware-aware-refactor` at commit `83112be`
(algorithm code identical to `main` @ `d7bcc29`). Raw data:
`artifacts/performance/baseline.json`.

## Environment

| Item | Value |
| --- | --- |
| CPU | Intel Core Ultra 9 285H (16 physical cores, 16 logical CPUs, no SMT, hybrid P/E) |
| Affinity CPUs | 16 |
| Memory | 31.5 GiB total, ~16.6 GiB available at measurement time |
| OS | Windows 11 (10.0.26200) |
| Python | 3.12.13 (conda env `abcg`) |
| NumPy / SciPy | 2.5.1 / 1.18.0 |
| BLAS backend | scipy-openblas (two OpenBLAS pools, 16 threads each by default) |
| `OMP/MKL/OPENBLAS/NUMEXPR/VECLIB_*_THREADS` | all unset |
| multiprocessing start method | spawn |
| CUDA GPU | none detected |
| Parallelism in code | `ThreadPoolExecutor`, default `workers=4` |

## Workloads

All runs write to scratch directories (`.tmp/benchmarks/`); official results
under `reports/` were not touched. Result-file SHA256 hashes are recorded in
`baseline.json` as the consistency anchor for every later optimization.

| Workload | Command | Wall time | CPU time | CPU/wall | Peak RSS | Exit |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| small | `run_static_containment.py --config static_crowd_circle.yaml` (serial) | 7.6 s | 6.7 s | 0.88 | 138 MiB | 0 |
| standard | `run_step1_pr6_evaluation.py --seed-count 30` (workers=4) | 305.6 s | 306.4 s | **1.00** | 116 MiB | 0 |
| formal | `run_step1_g6_compliance.py` (defaults, workers=4) | 1725.2 s (28.8 min) | 1918.0 s | **1.11** | 159 MiB | 0 |

Formal per-record latency (600 primary records, `total_runtime_ms`):

| p50 | p90 | p95 | max | slowest record |
| ---: | ---: | ---: | ---: | --- |
| 8.52 s | 26.26 s | 29.35 s | 50.13 s | c_shape / seed 25 / uniform_arc |

## Key finding: the thread pool provides almost no parallelism

With `workers=4`, CPU time ÷ wall time is 1.00 (standard) and 1.11 (formal):
the four Python threads execute essentially serially under the GIL, and mean
machine utilization is ~7%. The dominant cost is Python bytecode, not
BLAS-heavy native sections. Consequently:

1. The largest available win is case-level **process** parallelism
   (up to ~16x theoretical on this machine), not thread tuning.
2. BLAS thread oversubscription is currently *not* the bottleneck, but it
   will become one as soon as multiple processes each spawn 16 OpenBLAS
   threads — thread governance must land together with the process pool.
3. Long-tail imbalance is real: p95/p50 ≈ 3.4, max/p50 ≈ 5.9, so dynamic
   scheduling (one case per task) matters once real parallelism exists.

## Baseline result hashes

See `artifacts/performance/baseline.json` → `entries[*].result_sha256`.
These SHA256 values define the Phase 0 output identity for `summary.json`
(small), the PR6 record/aggregate files (standard), and the G6 record/
aggregate/ablation/robustness files (formal).

Note: G6/PR6 outputs embed the evaluated git commit and dirty-worktree
status in `evaluation_snapshot.json` and reports, so hash comparisons across
commits must exclude commit-dependent fields; record-level scientific fields
are compared directly.
