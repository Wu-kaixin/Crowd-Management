# Phase 1 profile report

Raw data: `artifacts/performance/profile.json` (laptop, Ultra 9 285H,
16C/16T) and `artifacts/performance/profile_desktop.json` (desktop,
24C/32T Raptor Lake, 64 GiB, CUDA GPU present). Probes are defined in
`scripts/profile_step1.py`; all measurements ran reduced-seed workloads in
scratch directories and never touched official results.

Both machines produce the same qualitative picture, so the conclusions
below are machine-independent unless a machine is named explicitly.

## 1. Where the time goes

cProfile over 16 primary G6 cases (workers=1, 184.6 s total):

| Rank | Function | Self time | Cumulative | Share of total |
| ---: | --- | ---: | ---: | ---: |
| 1 | `geometry/arclength.py:_cross` (99.9M calls) | 79.0 s | 79.0 s | 42.8 % |
| 2 | `controllers/safety.py:_build_velocity_halfspaces` (7 207 calls) | 26.3 s | 55.7 s | 30.2 % cum |
| 3 | `geometry/arclength.py:_segments_intersect` (25.0M calls) | 25.3 s | 110.5 s | 59.9 % cum |
| 4 | `numpy.linalg.norm` (14.5M calls, mostly 2-vectors) | 12.9 s | 26.4 s | 14.3 % cum |
| 5 | `geometry/arclength.py:has_self_intersections` (2 002 calls) | 8.5 s | 119.1 s | 64.5 % cum |

Full top-20 self/cumulative listings: `profile.json → cprofile.text_self`
/ `text_cumulative`.

Stage attribution (same 16 cases, direct stage timers):

| Stage | Share |
| --- | ---: |
| boundary estimation with bootstrap | 83.2 % |
| feedback episode incl. safety filter | 7.4 % |
| boundary estimation single pass | 5.7 % |
| case generation | 3.5 % |
| artifact serialization | 0.19 % |
| metrics (chamfer/hausdorff/crossings) | 0.04 % |
| periodic arc CVT planning | 0.005 % |
| Hungarian assignment | 0.001 % |

## 2. Answers to the audit checklist

1. **Python vs native time.** Only ~12 % of self time is native
   builtins/NumPy kernels; ~88 % is Python bytecode. The workload is
   GIL-bound, which is why the existing `ThreadPoolExecutor` cannot scale.
2. **Dominant hotspot.** `has_self_intersections` is a pure-Python
   O(K²) segment-intersection test (~65 % of total time). It is called
   once per candidate curve, but the bootstrap re-estimates the alpha
   geometry `bootstrap_samples` (30) times per case, and each attempt
   runs the test on curve + offset. `_cross` alone is called 100M times
   in 16 cases. This is fully vectorizable with NumPy broadcasting
   (or a sweep-line/spatial-hash approach) without changing the exact
   geometric predicate.
3. **Second hotspot.** `safety.py:_build_velocity_halfspaces` builds
   guide-pair and guide-crowd constraints in nested Python loops: 14.5M
   two-element `np.linalg.norm` calls, 14.5M `np.zeros(dimension)` row
   allocations per episode batch. Vectorizable with pairwise-difference
   broadcasting and preallocated constraint matrices; the constraint set
   and its ordering can be kept bit-identical.
4. **Repeated computation.** Boundary geometry is *not* recomputed per
   simulation step (it is static per case), but bootstrap resamples
   redo the full alpha pipeline including the O(K²) test; the pairwise
   distance matrix in `_bootstrap_boundary_confidence` and
   `_adaptive_alpha_curve` is rebuilt with full N×N broadcasting each
   time. No cross-case duplicate loading was observed.
5. **Small-object churn / copies.** Yes: per-constraint `np.zeros`
   rows, per-pair 2-vector norms, list-append-then-vstack patterns in
   the halfspace builder. No `np.concatenate`-in-loop or row-wise
   DataFrame growth was found elsewhere.
6. **Per-step file writes.** None. Serialization happens once per
   episode (0.19 % of time). No plotting occurs during formal
   simulation.
7. **Nested parallelism.** Present and measurably harmful: Python
   threads × two OpenBLAS pools (16 threads each on the laptop, 32 on
   the desktop) with all `*_NUM_THREADS` unset. See scaling below.
8. **Long tail / load imbalance.** Real: non-convex scenarios dominate
   (u_shape/c_shape bootstrap ≈ 8–11 s vs circle ≈ 2 s per case;
   formal-run record latencies p95/p50 ≈ 3.4, max/p50 ≈ 5.9). Dynamic
   scheduling matters once real parallelism exists.

## 3. Thread-scaling measurements

12 primary cases per configuration, `ThreadPoolExecutor`, wall seconds.

Desktop (24C/32T):

| Workers | BLAS default | BLAS = 1 |
| ---: | ---: | ---: |
| 1 | 154.4 | **98.1** |
| 4 | 205.4 | 210.0 |
| 16 | 128.7 | 149.7 |

Laptop (16C/16T): workers=1/4/16 with default BLAS gave 94.0 / 115.7 /
122.0 s; workers=1 with BLAS=1 gave 93.8 s. (The stored laptop value of
4 689 s for workers=4, BLAS=1 is a transient machine event — sleep or
throttling — not reproducible; the desktop re-measurement of the same
combination is 210 s, in line with its neighbours.)

Conclusions:

1. **Thread workers never help** — every multi-worker configuration is
   slower than or equal to one worker. Python-bytecode hotspots hold the
   GIL, so threads only add contention. Case-level parallelism must move
   to processes (`ProcessPoolExecutor`, spawn-safe on Windows).
2. **Default OpenBLAS threading is a net loss on the desktop**: capping
   BLAS to 1 thread made the single-worker run 1.57× faster (154 → 98 s).
   The arrays here are tiny (2-vectors, K×2 curves), so 32-thread BLAS
   pools only pay synchronization cost. Thread governance
   (`OMP/MKL/OPENBLAS/NUMEXPR/VECLIB_*_THREADS=1` before NumPy import in
   each worker) is a prerequisite for the process pool and already a
   free win for serial runs.
3. On the machine with `workers=4` today, CPU/wall ≈ 1.0–1.1 and mean
   machine utilization ≈ 7 % (baseline report): ~24× of headroom exists
   on the desktop for case-level process parallelism, bounded by the
   long-tail cases.

## 4. Optimization priorities implied by the data

Ordered by expected impact, all gated on unchanged scientific outputs:

1. Vectorize `has_self_intersections` (~65 % of runtime; exact same
   predicate, same tolerance semantics, same result).
2. Vectorize `_build_velocity_halfspaces` (~30 % of episode-heavy
   runtime; identical constraint rows and ordering).
3. Case-level `ProcessPoolExecutor` with per-worker BLAS=1 and
   dynamic (chunksize=1, unordered) scheduling, keeping the existing
   post-collection sort so official output ordering is unchanged.
4. BLAS=1 governance for serial paths (immediate 1.57× on desktop).

Items 1–2 shrink total CPU work; item 3 multiplies the remainder by up
to ~min(cases, cores). They compose.
