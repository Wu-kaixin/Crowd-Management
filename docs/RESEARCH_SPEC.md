# ABCG-v2 Step 1 Research and Development Specification

Status: PR0-PR5 complete; PR6 formal-compliance implementation and evaluation evidence complete in the working tree; only the user-deferred G6 frozen-commit requirement remains pending.
Authority: `AGENTS.md` and `ABCG-v2 Step 1 Core Development Specification` (2026-07-18).
Baseline: `main@fe4e7c1dd310c4eaef814c70e9edb34ec02227ae`.

## 1. Research scope

Step 1 studies guide-agent deployment around one static crowd under these
assumptions:

- The crowd's location, scale, and boundary are unknown before operation.
- A centralized, global 2D point-cloud observation is available during a run.
- The crowd is static and does not react to guide agents.
- Communication is unrestricted.
- The eventual control input is guide velocity, with `p_dot = u` and a speed
  limit.
- The output is a guide distribution around a safe offset of the estimated
  crowd boundary.

Autonomous search, dynamic/multiple crowds, split/merge tracking, crowd-guide
behavior response, local communication, video perception, frontends, hardware,
and human experiments are outside Step 1 Core.

The operational meaning of containment in Step 1 is geometric guide
distribution. It does not imply that people are surrounded, controlled,
redirected, evacuated, or made safer.

## 2. Claim and status discipline

Use the following labels in code comments, reports, and presentations:

- `CURRENT`: implemented and tested in the current repository.
- `DESIGNED`: specified here but not implemented.
- `THEORY-CONDITIONAL`: justified only under explicit assumptions.
- `EXPERIMENTAL`: requires paired experiments, uncertainty, and failure rates.
- `FUTURE`: outside Step 1.

The preserved `ABCGController.deploy()` remains an endpoint-planning baseline.
PR4 uses each baseline endpoint as an explicit initial guide state for the
fixed-target ABCG-v2 kinematic loop. PR5 separates nominal and applied control,
adds sampled-data safety projection, and retains explicit residual and
infeasibility evidence. It does not establish continuous-time forward
invariance.

## 3. Current implementation audit

| Component | CURRENT behavior | Required later work |
| --- | --- | --- |
| `controllers/abcg.py` | Preserved radial endpoint baseline used to initialize PR4 episodes | Remains a v1 endpoint component |
| `controllers/abcg_v2.py` | Instance-local `reset(...)`/`step(observation, guide_state, dt)` feedback API, saturated fixed-target velocity law, PR5 applied control, Euler integration, state machine, complete motion/safety traces | Fixed-target Step 1 controller |
| `controllers/coverage_cvt.py` | Preserved Euclidean sample assignment and projection | Remains a v1 endpoint component |
| `controllers/periodic_arc_cvt.py` | Periodic uniform-density Voronoi cells, exact `H`, relaxed Lloyd updates, confidence gain, equal-arc baseline, explicit invalid status | PR4 consumes its fixed targets |
| `controllers/resources.py` | `ceil(L/g_req)`, minimum count, bidirectional hysteresis, active/reserve/unmet counts, capacity status | PR4 propagates failures before motion |
| `controllers/assignment.py` | SciPy Hungarian assignment, switch penalty, reserve slots, unmet targets, explicit infeasibility | PR4 preserves guide-row identity in trajectories |
| `geometry/arclength.py` | Closure normalization, orientation, resampling, tangents/normals, periodic distance and true arc gap | No motion semantics |
| `estimation/boundary.py` | Preserved star-shaped radial v1 estimator | Remains the endpoint baseline |
| `estimation/boundary_v2.py` | Radial adapter plus alpha-shape reconstruction, adaptive candidate validation, bootstrap uncertainty/confidence, topology/coverage/offset/room checks, explicit invalid status | Current PR6 estimator |
| `controllers/safety.py` | Endpoint helpers plus deterministic ordered half-space/speed-ball velocity projection and emergency stop | No continuous-time guarantee |
| `experiments/static_containment.py` | Alpha/bootstrap boundary configuration, safety-filtered fixed-target episodes, complete upstream and failure artifacts | Current PR6 runner |
| `evaluation/step1_pr6.py` | Earlier held-out U/C boundary-only diagnostic retained for compatibility | Not sufficient alone for formal G6 |
| `evaluation/step1_g6.py` | Four-scenario/five-method paired closed-loop matrix, full artifact contract, ablations, robustness/stress scans, paired statistics, actual failures, runtime/P95/memory, repository/source snapshot | Formal G6 evaluator |
| `containment_metrics.py` | Final-episode-frame metrics plus initial endpoint audit metrics and true periodic `G` helper | Retained for endpoint and trajectory audit |

## 4. PR0 contract: specification and truth

PR0 establishes an auditable baseline without changing the endpoint planner.

### 4.1 Independent synthetic truth

`generate_static_crowd_truth()` builds evaluator-only analytic boundaries from
scenario generator parameters. Controller and estimator code must not receive
these objects.

- Circle and rotated ellipse truth are analytic.
- The nonconvex truth is the deterministic radial shape before observation
  noise and per-point radial jitter.
- Safety points are analytic normal offsets of truth samples.
- The two-cluster pressure scenario retains two separate components and returns
  `out_of_scope_multicomponent`; components are never joined into a fake Step 1
  contour.
- Truth samples are saved in `crowd_truth.npz` and used for the primary
  endpoint coverage diagnostics.

### 4.2 Metric naming

The historical `max_boundary_gap` value is not an arc gap. It is the maximum,
over sampled boundary points, of the Euclidean distance to the nearest guide.
Its correct name is:

```text
max_euclidean_boundary_distance
```

The Python function `max_boundary_gap()` remains temporarily available and
emits `DeprecationWarning`. Serialized results retain the old key with the same
value for compatibility. `max_consecutive_arc_gap` is not implemented in PR0;
it belongs to the later periodic-arc work and must not be fabricated from the
current estimator.

### 4.3 Run manifest

Every current static endpoint run writes:

```text
config_resolved.yaml
crowd_points.npz            # compatibility artifact
crowd_truth.npz             # evaluator-only analytic truth
boundary_v2_status.json     # always; VALID or explicit failure
boundary_v2.npz             # only when PR1 geometry is valid
periodic_plan_status.json   # always; valid, invalid, or explicitly skipped
periodic_plan.npz           # only when the PR2 plan is valid and converged
resource_decision.json      # always; active, reserve, unmet, capacity status
manifest.json
summary.json
summary.csv
<method>/containment_state.npz
<method>/metrics.json
<method>/assignment_status.json
<method>/assignment.npz     # unless skipped or infeasible
<method>/episode_status.json
<method>/episode.npz        # finite motion and PR5 per-frame safety trace
<method>/containment.png     # unless plots are disabled
```

The manifest records schema version, UTC creation time, fixed-target kinematic
scope, closed-loop flag, stop reason, Git commit/branch/dirty state, config
SHA-256, seed, Python and package versions, methods, truth status, episode
status, and limitations.

Current runs explicitly use:

```text
run_scope = alpha_bootstrap_safety_filtered_episode_with_pr6_evidence
closed_loop = true only when at least one control interval executes
stop_reason = hold_window_satisfied, timeout, or an explicit upstream failure
```

`closed_loop=true` means that the fixed-target feedback loop executed. PR5
safety evidence is carried separately by per-frame filter status and residuals;
neither flag alone is evidence of PR6 robust containment.

### 4.4 PR0 success and failure examples

Success: `static_crowd_circle.yaml` produces valid analytic truth, finite
metrics, a complete manifest, and artifacts for all endpoint baselines.

Explicit scope failure: `static_crowd_two_clusters.yaml` records
`out_of_scope_multicomponent` and `component_count = 2`. Diagnostic distances
may still be reported against the two separate components, but the episode is
not counted as a valid single-boundary Step 1 result. Its manifest uses
`run_status = evaluation_scope_failure` and the method output is
`diagnostic_only`.

### 4.5 PR1 arc-length and boundary-v2 contract

PR1 adds deterministic closed-curve geometry without changing the v1 endpoint
planner:

- `resample_closed_curve_by_arclength()` accepts implicit closure or one
  duplicated endpoint, rejects degenerate/self-intersecting curves, normalizes
  orientation counter-clockwise, and returns ordered points, increasing
  `arc_s`, closed length `L`, unit tangents, and outward unit normals.
- `periodic_arclength_distance()` implements the shortest distance on
  `[0, L)` and accepts coordinates outside the canonical interval by wrapping
  them. It is a geometry primitive, not yet a periodic coverage planner.
- `BoundaryEstimateV2` contains the required curve/offset geometry, component
  count, method/version, and diagnostics. PR1 uncertainty/confidence arrays are
  explicit neutral zero/one placeholders labelled
  `neutral_not_estimated_pr1`; they are not confidence evidence.
- The radial adapter checks observation shape/finiteness, significant connected
  components, observation coverage, curve topology, offset self-intersection,
  and optional room feasibility. It returns `OBSERVATION_INVALID`,
  `BOUNDARY_INVALID`, or `OFFSET_INVALID` instead of repairing or joining an
  invalid result silently.
- PR6 retains this radial adapter as an ablation baseline and adds alpha-shape
  reconstruction for non-star boundaries. Neither estimator joins significant
  disconnected components silently.

Static endpoint runs save the V2 geometry for audit, but the existing
`ABCGController.deploy()` still consumes its preserved v1 estimate. Synthetic
truth remains evaluator-only and is never passed into the V2 estimator.

### 4.6 PR2 periodic coverage contract

PR2 implements `plan_periodic_arc_coverage(boundary, m, config, init=None)` and
returns an auditable `CoveragePlan` containing sorted `target_s`, interpolated
offset `target_xy`, unwrapped periodic Voronoi bounds, cell masses, `H` history,
gain history, maximum consecutive arc gap, active count, convergence flag, and
explicit status.

- The primary density is fixed at `phi(s) = 1`; periodic cell costs are
  integrated analytically.
- Boundary confidence is averaged over each cell and clipped to
  `[eta_min, 1]` only as the relaxed Lloyd update gain. It is not a risk weight.
- Equal-arc targets provide the deterministic baseline and attain
  `H* = L^3 / (12 m^2)` for the uniform periodic problem.
- Duplicate sites/empty cells, invalid boundary contracts, invalid
  initialization, unexplained `H` increase, and iteration exhaustion retain
  explicit plan states; no NaN repair is used.
- The static runner saves this plan independently for audit. It does not route
  the plan into v1 endpoint controllers and therefore is not identity-aware or
  closed loop.

### 4.7 PR3 resources and identity contract

PR3 implements `ResourcePolicy` and `IdentityPreservingAssigner` as explicit,
state-free components. Callers pass the prior active count and prior
guide-to-target assignment rather than relying on hidden mutable state.

- Raw demand is `m_req = ceil(L/g_req)` with an enforced `m_min`.
- Separate increase/decrease margins retain the prior count near integer
  thresholds. The policy records both raw requested and hysteretic desired
  counts.
- `active = min(desired, M_available)`, while reserve and unmet counts remain
  explicit. Any unmet count returns `CAPACITY_SHORTFALL` instead of silently
  treating the clipped active count as adequate.
- Assignment minimizes squared distance plus `lambda_switch` when the current
  target/reserve identity differs from the prior assignment. A deterministic
  O(n^3) Hungarian implementation handles square and rectangular cases without
  adding SciPy.
- Guide rows preserve identity. `-1` means reserve for guide-to-target output;
  `-1` means unmet for target-to-guide output. Invalid inputs return
  `ASSIGNMENT_INFEASIBLE` with finite diagnostic arrays.
- Static runs use preserved endpoint outputs as explicit PR4 initial guide
  positions. Fixed PR2 targets and deterministic PR3 guide rows are retained
  throughout each complete position/control trace.

### 4.8 PR4 fixed-target motion and episode contract

PR4 implements `ABCGv2Controller.run_fixed_target_episode()` with immutable
fixed targets and explicit active/reserve guide rows.

- Active guides use `u_nom = sat_vmax(k_p(z_assigned-p))`; reserve guides use
  zero velocity. Saturation is enforced per guide without exceeding `v_max`.
- Positions use explicit Euler integration with `p(t+dt)=p(t)+dt*u_applied`.
  In PR4, `u_applied=u_nom`; the safety filter is explicitly
  `NOT_IMPLEMENTED_PR5`.
- Every episode records `T+1` positions and state/error/speed frames and `T`
  nominal/applied controls. Initial-only failure traces are retained rather
  than fabricated into motion evidence.
- `TRACK` enters `HOLD` only after tracking and speed tolerances pass. Every
  consecutive frame in the configured hold window must pass; a violation
  resets the window. Exhausting `max_steps` returns `TIMEOUT` with the complete
  trace.
- Capacity and assignment failures stop before motion and propagate as
  `CAPACITY_SHORTFALL` or `ASSIGNMENT_INFEASIBLE`.
- Main containment metrics use the final episode frame. Initial endpoint
  coverage and distance remain separately serialized, because motion to the
  resource-limited fixed targets can reduce endpoint coverage.

### 4.9 PR5 sampled-data velocity safety contract

For each frame, PR5 constructs deterministic linear constraints over the
stacked guide control. Constraints that cannot become active within one time
step under `v_max` are omitted without changing feasibility.

```text
n_ij^T (u_i-u_j) >= (d_GG-||p_i-p_j||)/dt
n_iq^T u_i         >= (d_GC-||p_i-q||)/dt
u_i,x >= (margin-p_i,x)/dt
-u_i,x >= (p_i,x-(room_x-margin))/dt
```

The corresponding two `y` room constraints are also applied. Normals point
from the other guide or fixed observed crowd point toward the guide. Coincident
points use a deterministic fallback normal; they are never divided by zero.

- Ordered Dykstra projections solve the intersection of these half-spaces and
  one `||u_i|| <= v_max` ball per guide without adding a numerical-optimizer
  dependency.
- `VALID` preserves a feasible nominal control exactly. `PROJECTED` records a
  changed feasible applied control. Failure to reduce all residuals below the
  configured tolerance returns `SAFETY_INFEASIBLE` and applies a finite
  zero-velocity emergency control for the recorded interval.
- A deterministic numerical distance buffer larger than the allowed
  velocity-residual displacement prevents strict downstream distance metrics
  from reporting a floating-point-only safety violation.
- Every control frame saves filter status, total and type-specific constraint
  counts, violated nominal count, projection sweeps, before/after maximum
  residuals, control adjustment, and emergency-stop flag.
- A converged hold frame must satisfy tracking, speed, and the PR5 residual
  tolerance. Safety infeasibility terminates immediately and is never converted
  to timeout or convergence.
- The constraints are sufficient for the sampled one-step linearized
  conditions against the fixed point cloud and room. They are not ORCA or CBF,
  and no continuous-time forward-invariance claim is made.

The default circle exposes an important target/filter conflict: several PR2
offset targets are closer than `0.85 m` to observed crowd points. The filter
remains feasible and finite but cannot meet tracking tolerance, so the episode
correctly ends in `TIMEOUT`. A separate feasible-target unit episode converges,
and an intentionally impossible crowd-clearance configuration returns
`SAFETY_INFEASIBLE` with a finite emergency trace.

### 4.10 PR6 alpha/bootstrap and robust-evaluation contract

PR6 reconstructs a concave boundary from accepted Delaunay triangles whose
circumradii pass an adaptive alpha-radius schedule. A candidate is accepted
only after closed-curve topology, observation coverage, normal-offset topology,
and optional room feasibility all pass. Nonmanifold or multiple significant
outer loops return an explicit boundary failure.

Bootstrap replicas resample the observed cloud with replacement, reconstruct
the boundary independently, and map replica-to-base nearest distances to
per-arc uncertainty. Confidence is a bounded exponential transform of that
uncertainty. Replicas that fail remain counted; insufficient successful
replicas return `BOUNDARY_INVALID/bootstrap_insufficient_success`. Confidence
gates the periodic Lloyd step size and is never interpreted as risk density.

The formal PR6/G6 evaluation uses evaluator-only truth for circle, ellipse,
held-out U, and held-out C scenarios. Seeds `0..29` are paired across the
current endpoint, uniform-angular, uniform-arc, fixed-count periodic CVT, and
full adaptive ABCG-v2 methods. Every method is executed through measured
feedback using `ABCGv2Controller.reset/step`; truth is never passed to an
estimator, planner, assignment, safety filter, or controller.

The matrix also includes balanced-perimeter, one-sided, and opposed-side
initial layouts; 30-replica boundary bootstrap; radial/no-bootstrap,
alpha/no-bootstrap, confidence-gain, and adaptive-resource ablations; three
levels each of noise, observation dropout, and scale; and explicit
double-cluster and narrow-neck stress cases. It reports mean, median, paired
bootstrap 95% intervals, paired effect size, worst 5%, failure rate, runtime
P95, and process peak memory. Invalid and terminal failures remain in the
denominator, and the gallery contains actual failures rather than relabelled
worst valid cases.

Each primary run writes the resolved config, manifest, observations,
versioned boundary, plan trace, trajectory, event stream, and metrics under
ignored `runs/step1_g6_compliance/`. Compact aggregate evidence and the source
snapshot are written under `reports/step1_g6_compliance/`. The snapshot remains
`UNFROZEN_DIRTY_WORKTREE`, so the final freeze requirement is still unmet.

## 5. Current PR6 mathematics and evidence contract

Periodic coverage, resource selection, identity assignment, and fixed-target
kinematics plus sampled-data velocity safety are CURRENT through PR5. Alpha
reconstruction, bootstrap confidence, and paired held-out evaluation are
CURRENT in PR6, subject to the unfrozen-snapshot limitation above.

### 5.1 Boundary and periodic coverage

For a valid ordered closed curve of length `L`:

```text
d_L(a, b) = min(|a-b|, L-|a-b|)
H(S) = integral_[0,L) min_i d_L(s, s_i)^2 phi(s) ds
```

PR1 implements `d_L`. PR2 implements and tests `H`, periodic Voronoi cells,
relaxed Lloyd updates, the uniform optimum, and `max_consecutive_arc_gap`.

The primary Step 1 experiment uses `phi(s) = 1`. Confidence is not used as a
risk weight. PR2 uses confidence only to gate the relaxed Lloyd gain;
uncertainty weighting remains an ablation.

### 5.2 Resources and identity

```text
m_req = ceil(L / g_req)
m_star = clip(m_req, m_min, M_available)
C_ik = ||p_i-z_k||^2 + lambda_switch I[k != previous(i)] + reserve cost
```

Resource shortage must return `capacity_shortfall`. Assignment must preserve
guide identity using a deterministic Hungarian solution with explicit reserve
and unmet-target semantics.

These equations and semantics are implemented in PR3. Hysteresis is tested
across repeated policy calls. PR4 consumes one resource decision and one fixed
identity-preserving assignment for each static episode; reassignment during a
dynamic episode is outside the fixed-target PR4 scope.

### 5.3 Motion and safety

```text
u_nom,i = sat_vmax(k_p (z_assigned,i - p_i))
p_i(t+dt) = p_i(t) + dt * u_applied,i(t)
```

PR4 implements nominal speed saturation and Euler integration. PR5 computes
`u_applied` using the ordered sampled-data projection specified above and
retains explicit constraint residuals and infeasibility. It is not called ORCA
or CBF. No forward-invariance claim is allowed without the required continuous
model, initial safety, persistent feasibility, differentiability, and
sampling-margin analysis.

### 5.4 State machine and stop conditions

The required states are:

```text
INIT, TRACK, HOLD, CONVERGED, DEGRADED,
BOUNDARY_INVALID, OFFSET_INVALID, CAPACITY_SHORTFALL,
ASSIGNMENT_INFEASIBLE, SAFETY_INFEASIBLE, TIMEOUT
```

For PR5, `CONVERGED` remains scoped to fixed-target tracking RMSE and speed,
with every hold frame additionally requiring a feasible safety result within
the residual tolerance. Instantaneous threshold crossing is insufficient.
Coverage and periodic-gap gates remain separate, so this state is not a claim
of robust containment efficacy.

## 6. Delivery sequence and gates

| PR | Scope | Gate | Current status |
| --- | --- | --- | --- |
| PR0 | Spec, independent truth, Euclidean metric rename, manifest | G0 | Complete |
| PR1 | Arc-length geometry, `BoundaryEstimateV2`, radial adapter, validity/status | G1-MVP | Complete |
| PR2 | Periodic CA-ALCC, `H` history, confidence gain, equal-arc baseline | G2 | Complete |
| PR3 | Adaptive resources, hysteresis, reserve, identity-preserving assignment | G3 | Complete |
| PR4 | `p_dot=u`, saturation, integrator, state machine, episode traces | G4 | Complete; 74 tests and six smoke paths pass |
| PR5 | Velocity safety projection, diagnostics, infeasible/emergency state | G5 | Complete; 82 tests and seven smoke scenarios pass |
| PR6 | Alpha/concave boundary, bootstrap confidence, formal paired closed-loop evaluation | G6 | Formal compliance complete in working tree; frozen commit pending |

No later PR may start when the current gate fails.

### Gate definitions

- G0: environment installs; full suite passes; legacy static endpoint smoke is
  reproducible; `TEST_REPORT.md` is current.
- G1: analytic length and periodic-distance tests pass; invalid topology is
  explicit; truth metrics remain independent.
- G2: uniform circle approaches equal spacing; `H` has no unexplained increase;
  seam and empty-cell tests pass.
- G3: resource boundary cases and hysteresis pass; assignment is deterministic.
- G4: complete position/control traces exist; fixed-target error decreases;
  hold and timeout are correct.
- G5: per-frame safety diagnostics are complete; conflicts and infeasibility
  are detected; no NaN occurs.
- G6: general held-out nonconvex shapes, four-scenario/five-method matrix,
  at least 30 paired seeds and 30 bootstrap replicas, ablations, noise/dropout/
  scale and double-cluster/narrow-neck stress evidence, mean/median/paired CI/
  effect-size/worst-5%/failure statistics, actual failure gallery, full run
  artifact contract, runtime/P95/memory evidence, and a frozen commit are
  present.

## 7. Verification commands

Use the `abcg` Conda environment and invoke pytest through its Python runtime:

```powershell
conda run --no-capture-output -n abcg python -m pytest `
  --basetemp=.tmp/pytest-temp -o cache_dir=.tmp/pytest-cache

conda run --no-capture-output -n abcg python -m pip check

conda run --no-capture-output -n abcg python scripts/run_static_containment.py `
  --config configs/static_crowd_circle.yaml `
  --output runs/static_containment_circle `
  --methods random static_circle legacy_center_radius abcg

conda run --no-capture-output -n abcg python scripts/run_step1_g6_compliance.py `
  --output reports/step1_g6_compliance `
  --run-root runs/step1_g6_compliance `
  --seed-count 30 `
  --bootstrap-samples 30
```

`pip check` succeeds with exit code zero and prints
`No broken requirements found.` when the environment is healthy.

The PR6 validation snapshot is recorded in `TEST_REPORT.md`. Generated `runs/`
remain untracked; compact formal G6 evidence is kept under `reports/`.

## 8. Prohibited shortcuts

- Do not use estimated boundary output as synthetic truth.
- Do not force disconnected clusters into one contour.
- Do not call an Euclidean nearest-point distance an arc gap.
- Do not hide invalid, infeasible, capacity, or timeout outcomes.
- Do not count only converged runs.
- Do not replace trajectory evidence with final positions.
- Do not treat bootstrap confidence as risk density or claim it improves the
  controller when the paired gain ablation reports slower convergence.
- Do not claim dynamic reassignment from fixed-target PR4 identity traces.
- Do not interpret `closed_loop=true` as a safety proof or full containment
  convergence; inspect the PR5 frame diagnostics and terminal state.
- Do not claim continuous-time trajectory safety or forward invariance from
  the sampled-data PR5 projection.
- Do not introduce frontend, video, dynamic crowd, local communication, or
  human-response work into Step 1 Core PRs.

## 9. Evidence boundary after PR6

PR0-PR6 establish a trustworthy endpoint baseline, independent synthetic
evaluator, ordered arc-length geometry, a radial V2 adapter, explicit
geometry/offset failures, an auditable uniform periodic coverage planner,
adaptive resource semantics, deterministic identity-aware assignment, and a
complete saturated fixed-target episode with sampled-data velocity projection,
per-frame residuals, hold/timeout semantics, and explicit finite emergency
stop. PR6 additionally establishes alpha-shape reconstruction and finite
bootstrap uncertainty on the evaluated synthetic cases, plus paired nonconvex
error and ablation evidence with confidence intervals and complete failure
accounting. It does not establish improved confidence-aware control, dynamic
reassignment, continuous-time trajectory safety, forward invariance, robust
containment convergence, real-sensor performance, or human containment
efficacy. The default static cases still time out when fixed targets conflict
with sampled-data clearance, and G6 remains formally incomplete until the
evaluation is reproduced from a reviewed frozen commit.
