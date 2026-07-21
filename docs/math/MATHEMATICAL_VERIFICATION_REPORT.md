# Mathematical Verification Report — ABCG Static Containment (main)

Independent verification of the mathematical formulas, derivations, and
numerical properties present on the audited `main` branch, performed with a
local Wolfram Language kernel (Mathematica 15.0.0). All formal results were
produced by `wolframscript` executing the scripts under `wolfram/`; nothing in
this report is based on unexecuted reasoning.

| Field | Value |
| --- | --- |
| Audited `main` SHA | `93745582d849dafaa6251e9b2e12141be2117fe8` |
| Verification branch | `math-verification-main-v1` |
| Wolfram tests | 74 total, **74 passed, 0 failed** |
| Claims audited | 73 (see `MATHEMATICAL_CLAIM_MATRIX.csv`) |
| Execution status | `MATHEMATICA_EXECUTED` (local kernel via `wolframscript` 1.14.0) |
| Overall decision | **QUALIFIED_WITHIN_STATED_SCOPE** (layers A–D; see Section 21) |

---

## 1. Executive Summary

Every explicit or implicit mathematical claim found on the audited `main`
(73 claims across geometry, periodic coverage, resource allocation,
assignment, controller, safety projection, boundary estimation, containment
metrics, statistics, and documentation) was catalogued, classified, and — where
a computer algebra system can address it — independently verified in Wolfram
Language.

Outcome counts (each claim carries exactly one status):

| Status | Count |
| --- | --- |
| SYMBOLICALLY_PROVED | 20 |
| EXACTLY_VERIFIED | 27 |
| NUMERICALLY_VERIFIED_WITHIN_DOMAIN | 6 |
| PROPERTY_TESTED | 8 |
| COUNTEREXAMPLE_FOUND | 0 |
| IMPLEMENTATION_MISMATCH | 2 |
| ASSUMPTION_GAP | 4 |
| NOT_VERIFIABLE_BY_CAS | 3 |
| NOT_APPLICABLE | 3 |
| NOT_RUN | 0 |

Headline findings:

- **No mathematical error was found in any formula or derivation on `main`.**
  The maximum symbolic residual is exactly 0; the maximum cross-language
  (Python vs Wolfram) relative residual over 38 paired computations is
  5.6e-16, at float64 roundoff scale, against a frozen tolerance of 1e-9.
- The two `IMPLEMENTATION_MISMATCH` entries are **documentation errors, not
  algorithmic errors**: `docs/RESEARCH_SPEC.md` states the Hungarian solver is
  implemented "without adding SciPy" while the code imports
  `scipy.optimize.linear_sum_assignment` (DOC-001/ASG-005). The SciPy solver
  itself matched exhaustive enumeration exactly on every tested instance.
- The four `ASSUMPTION_GAP` entries are stated-scope issues, each with a
  concrete witness input recorded in `counterexamples.json`; none invalidates
  a result actually claimed by `main` (Section 18).
- Nothing in this report validates crowd-behavior assumptions, human
  compliance, bootstrap calibration, or real-world deployment safety
  (Section 20).

## 2. Scope

**In scope.** Formula correctness, symbolic derivations, convexity and KKT
conditions, exact finite enumeration, high-precision numerical residuals,
counterexample search, and Python-vs-Wolfram implementation consistency for
the code on `main` at SHA `9374558`. Only `main` was audited; the branches
`step1-proof-strengthening-v1`, `local-main-backup`, and legacy DBAct /
evacuation material were not used as sources of current definitions.

**Out of scope.** Algorithm changes, Step 2 work, G7, model validity, and
deployment validity. No controller, estimator, statistical procedure, or
formal result was modified. The verification branch adds only audit
artifacts, Wolfram scripts, figures, and this report.

## 3. Repository and Mathematica Provenance

Full provenance with SHA-256 hashes of every Wolfram script, input-case file,
and result file is in `artifacts/math_verification/provenance.json`. Key
fields:

| Item | Value |
| --- | --- |
| Repository | `https://github.com/Wu-kaixin/Crowd-Management` |
| Audited `main` SHA | `93745582d849dafaa6251e9b2e12141be2117fe8` |
| Verification branch / run head | `math-verification-main-v1` @ `2b7c1c1` |
| Mathematica | 15.0.0 for Microsoft Windows (64-bit) (May 19, 2026) |
| Kernel invocation | `wolframscript -file wolfram/verify_main.wls` (local kernel) |
| wolframscript | 1.14.0 |
| MCP server | `user-Wolfram` (local stdio); used for interactive health checks only — all formal results come from `wolframscript` runs |
| OS / Python / NumPy / SciPy | Windows 11 / 3.12.13 / 2.4.6 / 1.18.0 |
| Precision | WorkingPrecision 50, AccuracyGoal 40, PrecisionGoal 40; exact rational arithmetic wherever inputs permit |
| Random seeds | Wolfram `SeedRandom[20260721]`; Python case export seeds derived from base 20260721 (recorded per module in `cases/environment.json`) |

The kernel health check executed `$Version`, `$SystemID`, `1 + 1 == 2`, and
`FullSimplify[(x+y)^2 - (x^2 + 2 x y + y^2)] == 0` successfully before any
verification began, which is the basis for the `MATHEMATICA_EXECUTED` status.
No usernames, hostnames, license keys, or personal absolute paths are stored
in any committed artifact.

## 4. Verification Methodology

Five levels, applied per claim at the highest level the claim admits:

1. **L1 — syntax/dimension checks**: symbol definitions, units, array shapes,
   division-by-zero and domain guards (recorded in the claim matrix).
2. **L2 — symbolic equivalence**: `FullSimplify`, `Reduce`, `Resolve`,
   `Refine` under explicit `Assumptions`; a claim passes only if the
   difference simplifies to exactly 0 or the proposition to `True`.
3. **L3 — exact finite enumeration**: exhaustive permutation enumeration for
   assignment (n ≤ 7, up to 5040 permutations), integer grids for resource
   logic, rational arithmetic throughout.
4. **L4 — high-precision numerics**: WorkingPrecision 50, fixed seeds,
   sampling inside the domain, near boundaries, and at degenerate inputs.
5. **L5 — counterexample search**: `FindInstance`, `Reduce`, targeted
   adversarial inputs (e.g. the 1e-12 ceiling-guard witness in GEOM-003).

Cross-language protocol: Python exports raw inputs (never expected results)
to `artifacts/math_verification/cases/*.json` via
`scripts/export_math_verification_cases.py`; Wolfram recomputes each quantity
from those raw inputs using independently written implementations in
`wolfram/common.wl` and compares against the Python outputs. Absence of
numerical counterexamples is never reported as symbolic proof.

### Frozen tolerances

Tolerances were frozen in `wolfram/common.wl` before any comparison was run
and were not adjusted afterwards:

| Tolerance | Value | Unit | Applies to | Rationale |
| --- | --- | --- | --- | --- |
| `$tolExact` | 0 | — | symbolic identities | exact arithmetic admits no error |
| `$tolCross` | 1e-9 | relative | Python float64 vs Wolfram 50-digit recomputation | ~1e7 × float64 eps headroom, far below any physical significance |
| `$tolGeom` | 1e-9 | relative | geometric quantities (lengths, areas, distances) | same as cross-language |
| `$tolPrimal` | 1e-9 | m/s | constraint violation of accepted projections | matches code's own residual gate |
| `$tolKKT` | 1e-12 | mixed (m/s scale) | stationarity/complementarity at reference solutions | reference is exact-KKT-certified; tolerance covers final float rounding |
| `$tolProjectionDist` | 1e-6 | m/s | Dykstra output vs 50-digit reference | documented solver tolerance of the Python implementation |

Error reporting includes absolute, relative, maximum, median, and p95 values
(`numerical_results.json → error_summary`): over all 38 cross-language
residuals, max = 5.56e-16, median = 0, p95 = 3.86e-16.

## 5. Assumptions and Domains

Every claim row in the matrix carries its own `domain_assumptions`. The
recurring global assumptions are:

- Boundaries are closed polylines with finite positive length \(L > 0\);
  periodic arc-length parameterization on \([0, L)\).
- Uniform crowd density is assumed **only** for the analytic coverage optimum
  \(H^* = L^3/(12 m^2)\); the code's Lloyd iteration for non-uniform density
  is checked only as a property (monotone non-increase on tested cases).
- Controller derivations assume a fixed target, unsaturated control, and no
  active safety projection; the spec itself scopes them this way.
- Safety projection assumes a nonempty feasible set; infeasible instances are
  handled by the code's explicit `SAFETY_INFEASIBLE` path (SAF-011).
- All statistics claims are about implementation correctness on the exported
  fixed datasets, not about inferential adequacy (Section 15).

## 6. Mathematical Claim Matrix

The full matrix (73 rows; formula, symbols/units, domain, method, Wolfram
input file, status, limitations per row) lives at:

- `docs/math/MATHEMATICAL_CLAIM_MATRIX.csv` (machine-readable)
- `docs/math/MATHEMATICAL_CLAIM_MATRIX.md` (annotated)

Per-module status counts are visualized in
`reports/media/math_verification/mathematical_verification_summary.png`, and
the per-claim evidence classes in `assumption_and_limitation_matrix.png`.

## 7. Geometry Verification (GEOM-001…010)

Test file: `wolfram/tests/geometry.wlt` (TestIDs `GEOMETRY-*`). Highlights:

- **GEOM-001, shoelace area** (`GEOMETRY-AREA-001`): the discrete shoelace
  formula equals the cross-product triangle area symbolically; residual
  exactly 0.
- **GEOM-005, periodic distance** (`GEOMETRY-PDIST-001`): the code's
  `|Mod[d + L/2, L] - L/2|` equals `Min[d, L - d]` — proved by case-split
  `FullSimplify` on \([0, L/2)\) and \([L/2, L)\) plus a Mod-shift lemma.
- **Arc length, cumulative parameterization, closure** (GEOM-002/004/006):
  Wolfram recomputed polyline lengths for circle, ellipse, convex polygon,
  nonconvex polygon, and degenerate (repeated-point, nearly-collinear)
  curves from the raw exported vertices; max relative residual vs Python
  2.83e-16.
- **Tangent/normal estimation** (GEOM-007/008, `GEOMETRY-TANGENT-001`):
  central-difference tangents converge at the expected \(O(h^2)\) rate on a
  non-affine wavy curve \(r(t) = 2 + \tfrac{2}{5}\sin 3t\); normal
  orientation convention matches the code. (An ellipse is unsuitable for
  this test: uniform-parameter central differences on any affine image of a
  circle are exactly parallel to the tangent, hiding the convergence order.)
- **GEOM-003, sampling-count guard**: `ASSUMPTION_GAP` — see Section 18.

## 8. Periodic Coverage Derivation (COV-001…007)

Test file: `wolfram/tests/periodic_coverage.wlt` (TestIDs `PERIODIC-*`).

Starting from the periodic Voronoi cell integral definition (not from the
documented result), Wolfram derived:

- **Cell integral** (`PERIODIC-CELL-001`): \(\int_{lo}^{hi}(s-c)^2\,ds =
  \frac{(hi-c)^3-(lo-c)^3}{3}\), residual exactly 0.
- **H\* closed form** (`PERIODIC-HSTAR-001`): for \(m\) equal cells on a
  loop of length \(L\), \(m \int_{-L/2m}^{L/2m} t^2\,dt = \frac{L^3}{12m^2}\),
  residual exactly 0 under \(L>0, m>0\).
- **Optimality of equal spacing** (`PERIODIC-OPT-002`): with gap fractions
  \(g_i \ge 0,\ \sum g_i = 1\), `Resolve[ForAll[g, ..., Total[g^3] >= 1/m^2], Reals]`
  returned `True` for \(m = 2..6\), combined with the cubic scaling lemma
  that reduces the general objective to \(\sum g_i^3\). Equal spacing is the
  minimizer of this restricted (uniform-density, equal-cell) problem.
- **Cross-check**: 21 exported site configurations; Wolfram's independent
  cell-integral evaluation matched Python's `uniform_coverage_cost` with max
  relative residual 1.92e-16.
- The uniform-density conclusion is **not** extrapolated to non-uniform
  densities (COV-007 records this as an explicit scope statement in the
  spec); Lloyd iteration on non-uniform cases is `PROPERTY_TESTED` only
  (COV-005: objective non-increasing on tested runs).

Figure: `periodic_coverage_formula.png` (H vs m, linearity in \(1/m^2\),
gap \(G = L/m\), analytic-vs-numeric residual at float64 roundoff).

## 9. Resource-Allocation Verification (RES-001…006)

Test file: `wolfram/tests/resources.wlt` (TestIDs `RESOURCE-*`).

- **Ceiling guarantee** (`RESOURCE-CEILING-001`, RES-001): for \(L>0,
  g_{req}>0\), \(m = \lceil L/g_{req} \rceil\) satisfies \(L/m \le g_{req}\)
  and \(m-1\) fails the requirement — proved with `Reduce`/`Simplify` over
  the ceiling axioms \(x \le \lceil x \rceil < x+1\).
- **Hysteresis loop-exit invariant** (`RESOURCE-HYST-002`, RES-003): verified
  by exhaustive enumeration on the exported integer grid (240 cases, exact
  arithmetic, 0 violations): hysteresis may hold the count within its
  configured margin but never violates the exit invariant.
- Capacity clipping, minimum-count clamp, and boundary conditions
  (L = 0, g_req ≤ 0, capacity 0 / short) match Python exactly on all 240
  integer cases (`implementation_comparison.json → resources: exact match`).
- The `CAPACITY_SHORTFALL` region (required m > available M) is surfaced by
  the code as an explicit status, and is drawn in `guide_resource_bound.png`
  together with the rounding discontinuities of \(\lceil L/g_{req}\rceil\)
  and the realized-gap-vs-threshold curve.

## 10. Assignment Optimality (ASG-001…005)

Test file: `wolfram/tests/assignment.wlt` (TestIDs `ASSIGNMENT-*`).

- The cost model (squared Euclidean distance + switch penalty on the
  augmented matrix with reserve and dummy columns) was re-implemented
  independently in `wolfram/common.wl` (`augmentedCostMatrix`).
- **Brute force vs SciPy** (`ASSIGNMENT-BRUTEFORCE-001`): for all 24 exported
  instances (n = 1..7 square, plus rectangular reserve/unmet cases), full
  permutation enumeration in exact rational arithmetic reproduced SciPy's
  optimal cost **exactly** (difference 0, not merely small). n = 7 enumerates
  5040 permutations.
- **Ties** (ASG-003, `ASSIGNMENT-TIE-001`): a symmetric instance with two
  optimal assignments of equal cost 4 demonstrates that determinism currently
  rests on SciPy solver internals; the `tie_tolerance` parameter is validated
  but unused. Recorded as `ASSUMPTION_GAP` (Section 18).
- **Dummy-cost domination** (ASG-004, `ASSIGNMENT-DOMINATE-001`):
  `unmet_target_cost = 1e6` dominates all real costs inside the configured
  room domain (max real cost 596.25 m² for the 20 m × 14 m room);
  `FindInstance` produced an out-of-domain witness (\(\|p-z\|^2 = 1002001\)
  at 1001 m separation), so the claim is domain-limited:
  `NUMERICALLY_VERIFIED_WITHIN_DOMAIN`.

Figure: `assignment_optimality_crosscheck.png`.

## 11. Controller Stability (CTRL-001…010)

Test file: `wolfram/tests/controller.wlt` (TestIDs `CONTROL-*`).

For the control law \(u_{nom} = \mathrm{sat}(k_p (z - p))\),
\(p_{k+1} = p_k + \Delta t\, u_k\), error \(e_k = z - p_k\), all proved
symbolically (residual exactly 0 / `Reduce` equivalence):

- **Error recursion** (`CONTROL-RECURSION-001`):
  \(e_{k+1} = (1 - k_p \Delta t)\, e_k\) (unsaturated, fixed target).
- **Stability region** (`CONTROL-STABILITY-001`):
  \(|1 - k_p \Delta t| < 1 \iff 0 < k_p \Delta t < 2\).
- **Monotone region** (`CONTROL-MONOTONE-001`):
  no-overshoot contraction \(\iff 0 < k_p \Delta t \le 1\) — this stricter
  region is what the code enforces; the production default
  \(k_p \Delta t = 0.15\) sits well inside it.
- **Lyapunov decrease** (`CONTROL-LYAPUNOV-001`): with
  \(V_k = \tfrac12\|e_k\|^2\), \(\Delta V = ((1-k_p\Delta t)^2 - 1)V < 0\)
  exactly on \(0 < k_p \Delta t < 2\).
- **Saturated dynamics** (`CONTROL-SATURATED-001`): while saturated,
  \(\|e_{k+1}\| = \|e_k\| - \Delta t\, v_{max}\) (for
  \(\Delta t\, v_{max} \le \|e_k\|\)), i.e. constant-rate approach.

Cross-check: three exported Python controller traces reproduced step-by-step
at 50-digit precision; max relative deviation 5.56e-16 (the largest
cross-language residual in the whole audit).

Explicit non-guarantees, kept out of the "proved" pile: convergence under a
moving waypoint (CTRL-010, not claimed by the spec), under active safety
projection (CTRL-007, `ASSUMPTION_GAP` as scoped), and the fact that
controller CONVERGED ≠ deployment success (CTRL-008, `NOT_VERIFIABLE_BY_CAS`).

Figures: `controller_stability_region.png`, `controller_lyapunov_validation.png`.

## 12. Safety Projection and KKT Validation (SAF-001…011)

Test file: `wolfram/tests/safety_projection.wlt` (TestIDs `SAFETY-*`).

The problem the code actually solves is
\(\min \tfrac12\|u - u_{nom}\|^2\) subject to half-space constraints
\(A u \ge b\) (guide–guide, guide–crowd, room walls) **and** per-guide speed
balls \(\|u_i\| \le v_{max}\). Because of the norm-ball constraints this is a
**strongly convex QCQP (SOCP-representable projection)**, not a pure linear
QP; the report and figures use that terminology.

Symbolically proved: objective Hessian = identity (`SAFETY-HESSIAN-001`),
strong convexity and feasible-set convexity (`SAFETY-CONVEX-001`), the
one-step sufficiency inequality \(\|x\| \ge n \cdot x\) for unit \(n\)
(`SAFETY-SUFFICIENT-001`), and the room-wall clamp identity
(`SAFETY-ROOM-001`). Half-space directions reconstructed independently from
raw positions match the code's matrices exactly (SAF-004).

Reference solutions: for each PROJECTED instance a 50-digit reference was
computed by exact active-set polishing — enumerate candidate active sets,
solve the exact KKT equality system on rationalized data, keep the feasible
solution with nonnegative multipliers and minimal objective. At these
certified KKT points, on all three exported instances:

| Instance | primal | stationarity | complementarity | \(\|u_{dykstra} - u_{ref}\|\) |
| --- | --- | --- | --- | --- |
| guide_pair_and_crowd_projected | 0 | 0 | 0 | 3.9e-17 |
| room_wall_and_speed_ball | 0 | 0 | 0 | 0 |
| three_guides_mixed | 0 | 3.0e-17 | 0 | 2.8e-17 |

All far below the frozen tolerances (KKT 1e-12, projection distance 1e-6
m/s). Python's own post-projection constraint residuals are 0. The
infeasible-input path returning `SAFETY_INFEASIBLE` was property-tested
(SAF-011).

Scope note (SAF-010): these are sampled-data checks of finite instances. No
continuous-time forward-invariance claim is made by `main`, and none is
certified here; small-instance optimization proofs do not establish safety
for all real-world scenarios.

Figures: `safety_projection_geometry.png`, `safety_kkt_residuals.png`.

## 13. Boundary Uncertainty Limitations (BND-001…006)

Test file: contributions in `geometry.wlt` and `statistics.wlt`.

Verified as mathematics/implementation: normalized arc-length registration
(BND-001), the circumradius formula \(R = \frac{abc}{2|\text{cross}|}\)
(`GEOMETRY-CIRCUM-001`, exact), monotonicity of the confidence transform
\(e^{-u/s}\) in \(u\) (`STAT-CONF-001`, exact), cyclic phase alignment and
bootstrap statistic implementations on fixed inputs (BND-005/006).

**Not verifiable by CAS** (BND-004): that the bootstrap uncertainty is
*calibrated* — i.e. that the confidence tube achieves its nominal empirical
coverage on real trajectories. `main` contains no held-out calibration
dataset, and no formula-level argument can substitute for one. This report
deliberately does **not** state "Mathematica proved the uncertainty is
calibrated"; the claim is marked `NOT_VERIFIABLE_BY_CAS` in the matrix.

## 14. Metrics Verification (MET-001…008)

Test file: `wolfram/tests/metrics.wlt` (TestIDs `METRIC-*`).

Coverage ratio, max consecutive arc gap, max Euclidean boundary distance,
tracking RMSE, clearance, path length, and control energy were each
recomputed from raw inputs and matched Python exactly or to ≤1.5e-16
relative. The telescoping identity — periodic gaps sum to \(L\)
(`METRIC-GAP-001`) — is symbolically proved. Invariance under rigid
transforms (rotation + translation), guide relabeling, and arc phase shifts
was checked at 50-digit precision: all 17 differences are 0 to working
precision (figure `metric_invariance_tests.png`; the frozen 1e-9 tolerance
line sits ~40 orders of magnitude above the observed values). Empty-input,
single-point, repeated-point, and reserve-guide semantics match the code's
documented behavior (MET-008 property-tested).

## 15. Statistical Implementation Verification (STAT-001…008)

Test file: `wolfram/tests/statistics.wlt` (TestIDs `STAT-*`).

On fixed exported datasets, Wolfram independently reimplemented and matched
(≤3.8e-16 relative): paired differences and summary statistics (including a
NumPy-compatible linear-interpolation percentile), the seeded bootstrap CI
(Python exports the actual resample index sets drawn by its seeded generator;
Wolfram independently recomputes the estimator on every fixed resample and
re-derives the percentile interval — the RNG itself is not re-implemented,
so verification covers the estimator and interval construction, not the
random stream), Cohen's \(d_z\), win rate, worst-5% aggregation, the failure-denominator
convention (failed runs remain in the denominator, STAT-DENOM checks), and
missing-pair handling (missing pairs are dropped pairwise and reported, not
silently imputed).

Three separate judgments, as required:

- **Implementation correctness**: verified on tested domain (above).
- **Inferential assumptions**: `ASSUMPTION_GAP` (STAT-008) — many paired
  comparisons are reported without multiplicity control, and n = 30 seeds is
  a modest sample. The docs never claim multiplicity control (STAT-007
  `NOT_APPLICABLE`), so this is a design limitation, not an error.
- **Sample-size limitation**: flagged alongside STAT-008; no CAS remedy.

## 16. Python–Mathematica Cross-Check

38 paired computations across 8 modules
(`implementation_comparison.json`):

| Module | Cases | Max relative residual | Verdict |
| --- | --- | --- | --- |
| geometry | 5 | 2.83e-16 | match |
| periodic coverage | 21 | 1.92e-16 | match |
| resources | 240 | 0 | exact (integer arithmetic) |
| assignment | 24 | 0 | exact (rational arithmetic) |
| controller | 3 | 5.56e-16 | match |
| safety projection | 3 | ≤3.9e-17 (distance) | match, KKT-certified |
| metrics | 5 | 1.54e-16 | match |
| statistics | 4 | 3.85e-16 | match |

Global error summary: max 5.56e-16, median 0, p95 3.86e-16 — all ≥7 orders
of magnitude inside the frozen 1e-9 tolerance. Figure:
`python_wolfram_crosscheck.png` (log-log with y = x reference).

## 17. Counterexamples and Failed Claims

**No Wolfram test failed (74/74), and no counterexample to any claim actually
made by `main` was found.** Four witness inputs demonstrating the boundaries
of over-broad readings are preserved verbatim in
`artifacts/math_verification/counterexamples.json`:

1. **GEOM-003**: \(L = 10\), spacing \(= \frac{10}{7}(1 - 10^{-14})\) — the
   1e-12 ceiling guard yields count 7 and realized spacing marginally above
   the requested spacing (relative excess ~1e-12).
2. **ASG-003**: guides \(\{(0,0),(2,0)\}\), targets \(\{(1,1),(1,-1)\}\) —
   two optimal assignments with equal cost 4; no documented tie rule.
3. **ASG-004**: \(p=(0,0), z=(1001,0)\) — a real cost (1002001 m²) exceeding
   the dummy cost 1e6, achievable only outside the configured room domain.
4. **DOC-001**: documentation-vs-code mismatch on the SciPy import (no
   mathematical content).

None was deleted, excluded from summaries, or silently "fixed"; no claim was
re-scoped except by explicitly recording the narrower domain in the matrix.

## 18. Assumption Gaps

| Claim | Gap | Impact | Suggested (not applied) remedy |
| --- | --- | --- | --- |
| GEOM-003 | 1e-12 ceiling guard can admit realized spacing ≈1e-12 relative above the requested maximum | numerically harmless; docstring guarantee is approximate, not strict | reword docstring to "approximate maximum spacing" or drop the guard |
| ASG-003 | exact-tie determinism relies on SciPy internals; `tie_tolerance` is validated but unused | reproducibility across SciPy versions not guaranteed at exact ties | document/freeze a lexicographic tie rule |
| CTRL-007 | fixed-target convergence proof does not apply when safety projection is active (\(u_{applied} \ne u_{nom}\)) | spec already scopes this; no false claim on `main` | none required; keep scope statement |
| STAT-008 | many paired comparisons, no multiplicity control, n = 30 seeds | inferential caution warranted; implementation itself is correct | pre-register primary endpoints or add Holm correction in future work |

Per instruction, none of these was fixed in this task; remedies await human
confirmation on a separate branch.

## 19. What Mathematica Proved

Under the stated assumptions, with exact arithmetic (residual exactly 0 or
proposition `True`):

- Shoelace area, periodic-distance, circumradius, and telescoping arc-gap
  identities.
- The periodic Voronoi cell integral, the closed form
  \(H^* = L^3/(12m^2)\), and optimality of equal spacing for the
  uniform-density equal-cell problem (m = 2..6 via `Resolve` + scaling lemma).
- The ceiling resource bound \(L/\lceil L/g_{req}\rceil \le g_{req}\) with
  minimality, and the hysteresis exit invariant on the tested grid.
- The error recursion, the exact stability (\(0 < k_p\Delta t < 2\)),
  monotone (\(\le 1\)), and Lyapunov-decrease equivalences, and the
  saturated-phase constant-rate identity.
- Identity Hessian, strong convexity, feasible-set convexity, the one-step
  sufficiency inequality, and the room-wall clamp for the safety projection.
- Monotonicity of the boundary confidence transform.

Additionally, with exact enumeration: SciPy assignment optimality on every
tested instance (n ≤ 7), and integer-exact resource logic on 240 cases. With
50-digit numerics: KKT certificates for all PROJECTED safety instances and
38/38 cross-language matches within 5.6e-16.

## 20. What Mathematica Did Not Prove

- That crowd-behavior modeling assumptions are correct, or that real people
  comply with guides.
- That the bootstrap uncertainty is calibrated (no held-out calibration data
  on `main`; BND-004).
- Continuous-time forward invariance / unconditional safety of the
  sampled-data projection (SAF-010).
- Controller convergence under moving waypoints or active projection
  (CTRL-007/010).
- That controller CONVERGED implies overall deployment success (CTRL-008).
- Statistical design adequacy (multiplicity, sample size; STAT-008).
- Anything about scenarios outside the tested domains (e.g. rooms much larger
  than 20 m × 14 m for the dummy-cost bound, ASG-004).

Wolfram tests passing does **not** qualify the system for real-world
deployment.

## 21. Overall Qualification Decision

| Layer | Verdict | Evidence |
| --- | --- | --- |
| A. FORMULA_CORRECTNESS | PASS | 20 symbolic proofs, 0 residual; no formula error found |
| B. DERIVATION_CORRECTNESS | PASS | H*, stability, Lyapunov, KKT chains re-derived from definitions |
| C. IMPLEMENTATION_CONSISTENCY | PASS (with 2 documentation mismatches noted) | 38/38 cross-checks ≤5.6e-16; exact matches for assignment/resources; DOC-001/ASG-005 are doc-only |
| D. NUMERICAL_ROBUSTNESS | PASS on tested domain | boundary/degenerate sampling, float64-scale residuals, KKT ≤3e-17 |
| E. ASSUMPTION_COMPLETENESS | PARTIAL | 4 documented assumption gaps (Section 18), all benign for current claims |
| F. MODEL_VALIDITY | NOT ASSESSABLE BY CAS | out of scope by construction |
| G. DEPLOYMENT_VALIDITY | NOT ASSESSABLE BY CAS | out of scope by construction |

**Overall status: `QUALIFIED_WITHIN_STATED_SCOPE`** — the mathematics on
`main` (formulas, derivations, implementation consistency, numerical
robustness) is qualified within the explicitly stated assumptions and tested
domains. This is **not** a `QUALIFIED_FOR_REAL_WORLD_DEPLOYMENT` statement,
and layers F–G remain outside what a computer algebra system can certify.

## 22. Reproduction Commands

From the repository root on `math-verification-main-v1` (requires a local
Wolfram kernel; results were produced with Mathematica 15.0.0 and
wolframscript 1.14.0):

```bash
# 1. Regenerate the deterministic input cases from Python (seed base 20260721)
python scripts/export_math_verification_cases.py

# 2. Run the full Wolfram verification suite (74 VerificationTests + residuals)
wolframscript -file wolfram/verify_main.wls

# 3. Summarize and gate on frozen tolerances (exits nonzero on any breach)
python scripts/compare_wolfram_results.py

# 4. Regenerate all verification figures (PNG 300dpi + PDF + data files)
wolframscript -file wolfram/figures.wls

# 5. Python baseline must remain green (168 tests)
pytest --basetemp=.tmp/pytest-temp -o cache_dir=.tmp/pytest-cache

# 6. Check verification freshness against the current base SHA
python scripts/check_math_verification_freshness.py
```

All artifacts referenced in this report are committed under
`artifacts/math_verification/` (JSON/CSV evidence) and
`reports/media/math_verification/` (figures + per-figure data), with SHA-256
hashes recorded in `provenance.json`.
