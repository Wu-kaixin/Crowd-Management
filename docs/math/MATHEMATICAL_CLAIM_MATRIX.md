# Mathematical Claim Matrix — ABCG Static Containment (main)

Audited base: `origin/main` @ `491759761e441e83ee2f81ab5044b5b4f02a9347`.
Verification branch: `math-verification-main-v1`.
Machine-readable version: `MATHEMATICAL_CLAIM_MATRIX.csv` (same claim IDs).

Status vocabulary (only these values are used):

`SYMBOLICALLY_PROVED`, `EXACTLY_VERIFIED`, `NUMERICALLY_VERIFIED_WITHIN_DOMAIN`,
`PROPERTY_TESTED`, `COUNTEREXAMPLE_FOUND`, `IMPLEMENTATION_MISMATCH`,
`ASSUMPTION_GAP`, `NOT_VERIFIABLE_BY_CAS`, `NOT_APPLICABLE`, `NOT_RUN`.

All Wolfram evidence lives in `wolfram/` (tests) and
`artifacts/math_verification/` (results). Statuses in this file are kept in
sync with `artifacts/math_verification/summary.json` by
`scripts/check_math_verification_freshness.py`.

Scope guard: every status below refers to formula correctness, derivation
correctness, implementation consistency, or numerical robustness **within the
stated assumptions and tested domains**. No status certifies crowd-behavior
model validity or real-world deployment safety.

---

## A. Geometry — closed curves, arc length, periodic parameterization

| claim_id | Claim | Doc | Code | Assumptions / domain | Method (level) | Status |
|---|---|---|---|---|---|---|
| GEOM-001 | Shoelace signed area `A = 1/2 Σ (x_i y_{i+1} − x_{i+1} y_i)`; `A > 0` iff counter-clockwise | — (docstring `arclength.py:31`) | `geometry/arclength.py:30-34` | simple closed polygon, ≥3 distinct vertices | Symbolic identity on triangle/quad + exact rational polygons (L2/L3) | SYMBOLICALLY_PROVED |
| GEOM-002 | Closed length `L = Σ ‖p_{i+1} − p_i‖` (wrap-around); resampled curve preserves polygon perimeter | `docs/RESEARCH_SPEC.md:160-163` | `arclength.py:181-185` | finite, non-degenerate polygon | Exact rational polygons + cross-check vs Python (L3/L4) | EXACTLY_VERIFIED |
| GEOM-003 | Sample count `= max(3, ceil(L/spacing − 1e-12))`; realized spacing `L/count ≤ spacing` up to a frozen 1e-12 relative guard | docstring `arclength.py:151-153` | `arclength.py:187` | `spacing > 0`, finite `L > 0` | Symbolic ceiling inequality + boundary sampling (L2/L4) | ASSUMPTION_GAP |
| GEOM-004 | `arc_s = k·L/count`, `arc_s[0] = 0`, strictly increasing, `arc_s[-1] < L` | docstring `arclength.py:157-159` | `arclength.py:188` | as GEOM-003 | Exact enumeration (L3) | EXACTLY_VERIFIED |
| GEOM-005 | `d_L(a,b) = min(|a−b|, L−|a−b|)` equals implemented `|((a−b+L/2) mod L) − L/2|` | `RESEARCH_SPEC.md:349` | `arclength.py:210` | `L > 0`, finite inputs; equivalence claimed after wrapping `a−b` into `[0,L)` | Symbolic equivalence via Reduce + exhaustive rational enumeration (L2/L3) | SYMBOLICALLY_PROVED |
| GEOM-006 | `max_consecutive_arc_gap`: sort mod L, diff with seam; gaps sum to `L`; invariant to relabeling and global phase | `RESEARCH_SPEC.md:87-99` | `arclength.py:214-229` | non-empty finite coordinates, `L > 0` | Exact enumeration + invariance property tests (L3/L4) | EXACTLY_VERIFIED |
| GEOM-007 | For CCW curves the right-hand normal `(t_y, −t_x)` points outward | docstring `arclength.py:158-160` | `arclength.py:197` | smooth convex/star-shaped test curves | High-precision numeric: `n·(p−centroid) > 0` on circle/ellipse (L4) | NUMERICALLY_VERIFIED_WITHIN_DOMAIN |
| GEOM-008 | Central-difference tangents approximate true tangents with error `O(h²)` | — | `arclength.py:195-196` | analytic circle/ellipse, decreasing `h` | Convergence-order fit at 50-digit reference (L4) | NUMERICALLY_VERIFIED_WITHIN_DOMAIN |
| GEOM-009 | Orientation/on-segment predicate detects self-intersection of non-adjacent segments | `RESEARCH_SPEC.md:161` | `arclength.py:50-130` | atol = 1e-9 exact-arithmetic borderline cases | Exact case enumeration incl. touching/collinear (L3) | EXACTLY_VERIFIED |
| GEOM-010 | `L`, arc gaps, and coverage cost are invariant under translation/rotation of the curve; curve arrays are equivariant | — (implicit) | `arclength.py` (all) | rigid transforms only | Property test, 50-digit rotations (L4) | PROPERTY_TESTED |

## B. Periodic equal-arc coverage

| claim_id | Claim | Doc | Code | Assumptions / domain | Method (level) | Status |
|---|---|---|---|---|---|---|
| COV-001 | Cell integral `∫_l^r (s−c)² ds = ((r−c)³ − (l−c)³)/3` | — | `periodic_arc_cvt.py:150-153` | none (polynomial identity) | FullSimplify residual ≡ 0 (L2) | SYMBOLICALLY_PROVED |
| COV-002 | Equal-arc sites attain `H = L³/(12 m²)` for `phi ≡ 1` | `RESEARCH_SPEC.md:196-197` | `periodic_arc_cvt.py:262,381` | `L > 0`, integer `m ≥ 1`, uniform density, periodic 1-D arc, equal spacing | Symbolic derivation from cell integrals (L2) | SYMBOLICALLY_PROVED |
| COV-003 | Equal spacing is the global minimum of `H` over site configurations (uniform density): `H = Σ g_i³ /12`, minimized at `g_i = L/m` | implicit in "uniform optimum", `RESEARCH_SPEC.md:353-354` | — | fixed `m`, `Σ g_i = L`, `g_i ≥ 0`; proved per-`m` for m = 2..6, general `m` by power-mean argument checked for those cases | Resolve/Minimize per fixed m (L2), general m documented | SYMBOLICALLY_PROVED |
| COV-004 | Python `periodic_uniform_coverage_cost` equals the exact integral for arbitrary site sets | — | `periodic_arc_cvt.py:175-188` | valid sites, `L > 0` | Cross-language exact/50-digit comparison (L3/L4) | EXACTLY_VERIFIED |
| COV-005 | Relaxed Lloyd update never increases `H` beyond 1e-10 (guarded, returns `PLAN_INVALID_H_INCREASE` otherwise) | `RESEARCH_SPEC.md:198-200` | `periodic_arc_cvt.py:330-350` | gains in `[eta_min,1]`; guarded empirically, no symbolic monotonicity proof for relaxed gains | Property test on runs (L4) — a symbolic proof was not attempted | PROPERTY_TESTED |
| COV-006 | Equal-arc max consecutive gap `G = L/m` | implicit | `periodic_arc_cvt.py:164-172` | as COV-002 | Symbolic + exact enumeration (L2/L3) | SYMBOLICALLY_PROVED |
| COV-007 | Uniform-density optimum does **not** transfer to non-uniform densities; Lloyd/CVT results are numerical only | `RESEARCH_SPEC.md:356-358` | — | — | Scope statement; checked that code never claims otherwise | NOT_APPLICABLE |

## C. Adaptive guide count (resources)

| claim_id | Claim | Doc | Code | Assumptions / domain | Method (level) | Status |
|---|---|---|---|---|---|---|
| RES-001 | `m_req = ceil(L/g_req)` satisfies `L/m_req ≤ g_req`; minimality: `m_req − 1` (if ≥ 1) violates it | `RESEARCH_SPEC.md:210,362` | `resources.py:68` | `L > 0`, `g_req > 0` | Reduce/Resolve over reals+integers (L2) | SYMBOLICALLY_PROVED |
| RES-002 | `active = min(desired, available)`, `unmet = max(desired − available, 0)`; `unmet > 0 ⇒ CAPACITY_SHORTFALL` | `RESEARCH_SPEC.md:215-217` | `resources.py:86-90` | non-negative integers | Exhaustive small-integer enumeration (L3) | EXACTLY_VERIFIED |
| RES-003 | With increase-hysteresis active the realized desired-count gap obeys `L/desired ≤ g_req + h_inc/desired` | — (implicit in `RESEARCH_SPEC.md:211-214`) | `resources.py:71-84` | prior count provided; loop invariant | Symbolic loop-exit condition + enumeration (L2/L3) | SYMBOLICALLY_PROVED |
| RES-004 | Edge inputs rejected: `L ≤ 0`, non-finite, `g_req ≤ 0`, negative counts raise ValueError | — | `resources.py:18-26,58-66` | — | Python-side exact enumeration (L1/L3) | EXACTLY_VERIFIED |
| RES-005 | Hysteresis can hold `desired` above/below `m_req` only within the configured margins (never violates RES-003 bound) | `RESEARCH_SPEC.md:211-214` | `resources.py:71-84` | margins ≥ 0 | Exhaustive enumeration over integer grid (L3) | EXACTLY_VERIFIED |
| RES-006 | Reserve guides receive zero velocity and do not participate in coverage | `RESEARCH_SPEC.md:233-234` | `abcg_v2.py:167,178` | fixed-target episode | Cross-checked in exported episode traces (L3) | PROPERTY_TESTED |

## D. Guide-target assignment

| claim_id | Claim | Doc | Code | Assumptions / domain | Method (level) | Status |
|---|---|---|---|---|---|---|
| ASG-001 | Cost `C_ik = ‖p_i − z_k‖² + λ_switch · 1[k ≠ prev(i)]` as documented | `RESEARCH_SPEC.md:365-366` | `assignment.py:142-144` | finite (M,2)/(K,2) inputs | Cross-language recomputation of cost matrices (L3) | EXACTLY_VERIFIED |
| ASG-002 | SciPy Hungarian returns a **globally optimal** augmented-square assignment; equals brute-force permanent enumeration for n ≤ 7 | implicit ("minimizes", `RESEARCH_SPEC.md:218`) | `assignment.py:101-171` | square augmented matrix incl. reserve/unmet padding | Brute-force `Permutations` enumeration, exact rationals (L3) | EXACTLY_VERIFIED |
| ASG-003 | Ties: equal optimal cost may admit multiple assignments; implementation is deterministic for identical input but no documented tie rule beyond solver determinism | — | `assignment.py:19` (`tie_tolerance` unused in solve) | — | Enumeration of tie instances (L3); flagged as documentation gap | ASSUMPTION_GAP |
| ASG-004 | `unmet_target_cost = 1e6` dominates any real cost in the intended room domain (`max ‖p−z‖² ≈ 596 m²` for 20×14 room) | — | `assignment.py:18,169` | positions inside room ≤ 20×14 m; **not** guaranteed for arbitrary coordinates | Symbolic domination bound + counterexample search outside domain (L2/L5) | NUMERICALLY_VERIFIED_WITHIN_DOMAIN |
| ASG-005 | Doc states Hungarian "without adding SciPy" but implementation imports SciPy | `RESEARCH_SPEC.md:219-221` | `assignment.py:7,110` | — | Direct inspection | IMPLEMENTATION_MISMATCH |

## E. Velocity feedback controller

| claim_id | Claim | Doc | Code | Assumptions / domain | Method (level) | Status |
|---|---|---|---|---|---|---|
| CTRL-001 | Unsaturated fixed-target recursion: `e_{k+1} = (1 − k_p Δt) e_k` with `e = z − p` | `RESEARCH_SPEC.md:380-381` | `abcg_v2.py:177,189-198` | fixed target, no saturation, no safety projection | Symbolic (L2) | SYMBOLICALLY_PROVED |
| CTRL-002 | Asymptotic convergence iff `|1 − k_p Δt| < 1` ⇔ `0 < k_p Δt < 2` | — (derived) | — | as CTRL-001 | Reduce equivalence (L2) | SYMBOLICALLY_PROVED |
| CTRL-003 | Monotone, non-oscillatory contraction iff `0 < k_p Δt ≤ 1`; code enforces `k_p·Δt ≤ 1` | code error message | `abcg_v2.py:42-43` | as CTRL-001 | Reduce equivalence (L2) | SYMBOLICALLY_PROVED |
| CTRL-004 | Lyapunov `V = ½‖e‖²`: `ΔV = ½((1−k_pΔt)² − 1)‖e‖² < 0` for `0 < k_pΔt < 2`, `e ≠ 0` | — (derived) | — | as CTRL-001 | Symbolic sign analysis (L2) | SYMBOLICALLY_PROVED |
| CTRL-005 | Saturated regime: `‖e_{k+1}‖ = ‖e_k‖ − Δt·v_max` while `k_p‖e_k‖ > v_max` and `Δt·v_max ≤ ‖e_k‖` (error decreases linearly toward target) | — (derived) | `abcg_v2.py:177-186` | fixed target, exact saturation direction | Piecewise symbolic + high-precision simulation (L2/L4) | SYMBOLICALLY_PROVED |
| CTRL-006 | Saturation output satisfies `‖u‖ ≤ v_max` strictly after `nextafter` scaling | comment `abcg_v2.py:182-183` | `abcg_v2.py:179-186` | float64 arithmetic | Float boundary sampling (L4/L5) | NUMERICALLY_VERIFIED_WITHIN_DOMAIN |
| CTRL-007 | With safety projection, `u_applied ≠ u_nom` is possible; the fixed-target convergence proof does not apply to projected dynamics | `RESEARCH_SPEC.md:272-276` | `abcg_v2.py` episode loop | — | Scope statement, cross-checked with PROJECTED frames | ASSUMPTION_GAP |
| CTRL-008 | Controller `CONVERGED` ≠ overall deployment success (crowd containment efficacy is out of CAS scope) | `RESEARCH_SPEC.md:489-509` | — | — | Not a CAS-checkable claim | NOT_VERIFIABLE_BY_CAS |
| CTRL-009 | Python episode integrator reproduces the exact recursion (cross-check of exported traces at 50-digit precision) | — | `abcg_v2.py:189-198` | unsaturated + saturated segments, safety disabled | Cross-language trace comparison (L4) | EXACTLY_VERIFIED |
| CTRL-010 | Moving-waypoint case: fixed-target proof not applicable; no claim made in docs | `RESEARCH_SPEC.md:373-375` | — | — | Scope statement | NOT_APPLICABLE |

## F. Safety projection

| claim_id | Claim | Doc | Code | Assumptions / domain | Method (level) | Status |
|---|---|---|---|---|---|---|
| SAF-001 | Projection objective `½‖u − u_nom‖²` has Hessian `I` (strongly convex, modulus 1) | — (projection semantics) | `safety.py:321-346` | — | Symbolic Hessian (L2) | SYMBOLICALLY_PROVED |
| SAF-002 | Feasible set = intersection of half-spaces `a·u ≥ b` and balls `‖u_i‖ ≤ v_max` is closed convex | `RESEARCH_SPEC.md:258-271` | `safety.py:117-218` | — | Convexity of each set symbolically (ball via PSD Hessian) (L2) | SYMBOLICALLY_PROVED |
| SAF-003 | If feasible set non-empty, the projection is unique | — | — | strong convexity + convex feasible set | Standard theorem; premises CAS-verified (SAF-001/002) | SYMBOLICALLY_PROVED |
| SAF-004 | Code half-space rows realize `n_ij·(u_i − u_j) ≥ (d_GG + buffer − ‖p_i−p_j‖)/Δt` etc. with normals from j (or crowd point) toward i | `RESEARCH_SPEC.md:258-267` | `safety.py:141-202` | non-coincident points | Cross-language reconstruction of (A, b) on exported instances (L3) | EXACTLY_VERIFIED |
| SAF-005 | One-step sufficiency: half-space satisfaction ⇒ next-step distance ≥ `d + buffer` (via Cauchy–Schwarz `‖x‖ ≥ n·x`) | `RESEARCH_SPEC.md:285-288` | — | fixed crowd points, exact Euler step, one step only | Symbolic proof (L2) | SYMBOLICALLY_PROVED |
| SAF-006 | Room half-spaces keep `p + Δt·u` inside margins exactly (linear, no linearization error) | `RESEARCH_SPEC.md:261-263` | `safety.py:184-202` | one step | Symbolic (L2) | SYMBOLICALLY_PROVED |
| SAF-007 | Dykstra ordered projections converge to the exact projection onto the intersection (finite sweeps = approximation); solver output matches high-precision reference QCQP solution within tolerance | `RESEARCH_SPEC.md:269-271` | `safety.py:321-354` | non-empty interior instances; tested instances only | 50-digit reference solve + KKT residuals (L4) | NUMERICALLY_VERIFIED_WITHIN_DOMAIN |
| SAF-008 | KKT conditions hold at the reference solutions (stationarity, primal feasibility, complementarity) | — | — | tested instances | High-precision KKT residuals (L4) | NUMERICALLY_VERIFIED_WITHIN_DOMAIN |
| SAF-009 | Problem class is a strongly convex QCQP (ball constraints); it is **not** a pure linear-constraint QP | — (naming hygiene) | `safety.py` docstrings say "half-spaces + speed balls" (accurate) | — | Classification check | EXACTLY_VERIFIED |
| SAF-010 | No continuous-time forward-invariance claim is made or verified; sampled-data checks do not upgrade to continuous safety | `RESEARCH_SPEC.md:285-288,384-389` | — | — | Scope statement | NOT_VERIFIABLE_BY_CAS |
| SAF-011 | `SAFETY_INFEASIBLE` ⇒ finite zero-velocity emergency control (never NaN) | `RESEARCH_SPEC.md:272-276` | `safety.py:357-364` | — | Exported instance check (L3) | PROPERTY_TESTED |

## G. Boundary estimation and bootstrap uncertainty

| claim_id | Claim | Doc | Code | Assumptions / domain | Method (level) | Status |
|---|---|---|---|---|---|---|
| BND-001 | Per-arc uncertainty `= sqrt(mean_over_replicas(min-dist²))` (nearest-point RMS; no explicit phase registration) | `RESEARCH_SPEC.md:304-306` | `boundary_v2.py:726-747` | replica curves valid | Cross-language recomputation on fixed replicas (L3) | EXACTLY_VERIFIED |
| BND-002 | Confidence `= clip(exp(−u/scale), floor, 1)`, monotone non-increasing in `u`; `scale = max(spacing, median(u), 1e-12)` | `RESEARCH_SPEC.md:306-307` | `boundary_v2.py:748-760` | — | Symbolic monotonicity + cross-check (L2/L3) | EXACTLY_VERIFIED |
| BND-003 | Triangle circumradius `R = abc/(4·Area)`, implemented as `abc/(2·|cross|)` | — | `boundary_v2.py:299-313` | non-degenerate triangle | Symbolic identity (L2) | SYMBOLICALLY_PROVED |
| BND-004 | Bootstrap uncertainty is **calibrated** (confidence tube has empirical coverage) | — (not claimed in docs) | — | requires held-out calibration data absent from main | Cannot be established by CAS from formulas | NOT_VERIFIABLE_BY_CAS |
| BND-005 | Nearest-distance statistics are invariant under rigid transforms applied to both base and replica curves | — (implicit) | `boundary_v2.py:726-730` | rigid transforms | Property test at high precision (L4) | PROPERTY_TESTED |
| BND-006 | Bootstrap success accounting: failures stay counted; success < `ceil(fraction·samples)` ⇒ `BOUNDARY_INVALID` | `RESEARCH_SPEC.md:307-309` | `boundary_v2.py:732-744` | — | Integer enumeration of thresholds (L3) | EXACTLY_VERIFIED |

## H. Containment metrics

| claim_id | Claim | Doc | Code | Assumptions / domain | Method (level) | Status |
|---|---|---|---|---|---|---|
| MET-001 | `coverage_ratio = mean(min-dist ≤ r_cov)` ∈ [0,1]; rigid-transform and relabeling invariant | — | `containment_metrics.py:16-31` | non-empty inputs | Hand-computable examples + invariance (L3/L4) | EXACTLY_VERIFIED |
| MET-002 | `max_euclidean_boundary_distance = max_k min_i ‖b_k − g_i‖` (Euclidean diagnostic, **not** arc gap) | `RESEARCH_SPEC.md:85-99` | `containment_metrics.py:34-48` | non-empty inputs | Hand examples + invariance (L3/L4) | EXACTLY_VERIFIED |
| MET-003 | Arc-gap metric: gaps sum to `L`; max gap invariant under cyclic reindex and phase shift | `RESEARCH_SPEC.md:87-99` | `arclength.py:214-229` | `L > 0` | Symbolic + enumeration (L2/L3) | SYMBOLICALLY_PROVED |
| MET-004 | `tracking_rmse = sqrt(mean_active ‖p − z‖²)`; 0 when no active guides | — | `abcg_v2.py:201-205` | — | Hand examples (L3) | EXACTLY_VERIFIED |
| MET-005 | `path_length = Σ_t Σ_i ‖Δp‖`; `control_energy = Δt·Σ‖u‖²` | — | `step1_g6.py:470-481` | recorded traces | Cross-language recomputation (L3) | EXACTLY_VERIFIED |
| MET-006 | Edge semantics: single guide ⇒ `min_inter_guider_distance = ∞`; ≤1 point ⇒ `angular_uniformity_error = 0`; empty inputs raise | — | `containment_metrics.py:78-95` | — | Python-side enumeration (L3) | EXACTLY_VERIFIED |
| MET-007 | `angular_uniformity_error = mean|gap − 2π/M| / (2π/M)` on sorted angular gaps incl. seam | — | `containment_metrics.py:78-84` | ≥2 guides | Hand examples + invariance under rotation (L3/L4) | EXACTLY_VERIFIED |
| MET-008 | Final-frame metrics use the final episode frame; initial endpoint metrics serialized separately (semantics, not formula) | `RESEARCH_SPEC.md:248-250` | `step1_g6.py` | — | Inspection + trace check | PROPERTY_TESTED |

## I. Statistics

| claim_id | Claim | Doc | Code | Assumptions / domain | Method (level) | Status |
|---|---|---|---|---|---|---|
| STAT-001 | Summary stats: mean, median, `p95 = percentile(·, 95)` (NumPy linear interpolation), worst-5% mean = mean of worst `ceil(0.05 n)` in metric direction | `RESEARCH_SPEC.md:322-324` | `step1_g6.py:731-750` | n ≥ 1 | Cross-language recomputation with explicit NumPy quantile rule (L3) | EXACTLY_VERIFIED |
| STAT-002 | Percentile-bootstrap 95% CI of mean: resample means, percentiles 2.5/97.5 (indices exported from Python; Wolfram recomputes statistics) | `RESEARCH_SPEC.md:322-324` | `step1_g6.py:735-747,823-835` | given identical resample indices | Cross-language recomputation (L3) | EXACTLY_VERIFIED |
| STAT-003 | Paired effect size: Cohen's `d_z = mean(d)/std(d, ddof=1)`, `None` when `std = 0` | `RESEARCH_SPEC.md:322-324` | `step1_g6.py:826-836` | n ≥ 2 for std | Cross-language recomputation (L3) | EXACTLY_VERIFIED |
| STAT-004 | Win rate = fraction of paired differences favouring abcg_v2 in metric direction | — | `step1_g6.py:828,837` | — | Cross-language recomputation (L3) | EXACTLY_VERIFIED |
| STAT-005 | Failure denominator: every record counted; `failure_rate = mean(status ≠ CONVERGED)` incl. invalid/terminal failures | `RESEARCH_SPEC.md:324-325` | `step1_g6.py:773-799` | — | Synthetic-record property test (L3) | PROPERTY_TESTED |
| STAT-006 | Missing pairs are skipped and reported (`paired_count`, `missing_pair_count`), not imputed | — | `step1_g6.py:815-841` | — | Synthetic-record property test (L3) | PROPERTY_TESTED |
| STAT-007 | Holm (or any) multiple-testing correction | not claimed anywhere | absent | — | Repository-wide search: no such procedure exists; docs make no such claim | NOT_APPLICABLE |
| STAT-008 | Inferential design: many paired comparisons share seeds without multiplicity control; bootstrap CIs are per-comparison only; n = 30 seeds | — | `step1_g6.py:802-843` | — | Design assessment (not a formula error) | ASSUMPTION_GAP |

## Cross-cutting documentation claims

| claim_id | Claim | Doc | Code | Status |
|---|---|---|---|---|
| DOC-001 | "A deterministic O(n³) Hungarian implementation … **without adding SciPy**" contradicts `from scipy.optimize import linear_sum_assignment` | `RESEARCH_SPEC.md:219-221` | `assignment.py:7` | IMPLEMENTATION_MISMATCH |
| DOC-002 | Spec's explicit non-claims (no ORCA/CBF, no forward invariance, no containment-efficacy claim) are consistent with code and this audit | `RESEARCH_SPEC.md:285-288,489-509` | — | EXACTLY_VERIFIED |
