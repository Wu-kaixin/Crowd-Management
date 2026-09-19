# Step 1 implementation audit

Branch: `STEP1-新方向` (renamed from `feature/jupedsim-step1`; audit SHA `fe45551`)  
Date: 2026-09-19  
Frozen Step 1 definition for this rebuild:

> Known environment/venue boundary \(\partial\Omega_{\mathrm{env}}\).  
> Unknown crowd location, shape, scale, distribution, and crowd boundary \(\partial\Omega_c\).  
> JuPedSim may use a spawn polygon to generate experiments.  
> ABCG must not read that spawn polygon. Controller input is observed pedestrian points/attributes only.

This audit is the gate before code changes. It does not freeze scientific success rates.

## 1. What can be reused

The current branch is already closer to “known AABB room + unknown crowd” than to “unknown environment.” Keep the PR1–PR5 math and the JuPedSim static source.

| Area | Reuse as-is | Notes |
| --- | --- | --- |
| JuPedSim static placement | `crowd/jupedsim_static.py` | Only `jps.distribute_by_number`; no `Simulation`, no \(\dot x_j\) |
| Source protocol | `crowd/source.py` | `observe()` vs evaluator-only `truth()` |
| Heterogeneity attributes | `crowd/heterogeneity.py` | Static radius / desired_speed / time_gap; Step 2 dynamics remain unused |
| Crowd-boundary estimator | `estimation/boundary_v2.py` | Alpha/radial + bootstrap from **points only**; explicit `BOUNDARY_INVALID` |
| Coverage / resources / assignment | `periodic_arc_cvt.py`, `resources.py`, `assignment.py` | Planner consumes a closed offset curve, not spawn geometry |
| Closed-loop controller | `ABCGv2Controller.reset` / `step` | Measured-feedback API is the live-viz hook |
| Velocity safety core | `controllers/safety.py` | Guide–guide, guide–crowd, AABB wall half-spaces already exist |
| Episode facade | `run_fixed_target_episode` | Must stay numerically one path with `reset`/`step` |
| Pairing evidence | `reports/step1_source_pairing/` | Do not overwrite; pairing is no longer the main question |

JuPedSim spawn polygons stay inside the generator. Evaluator truth from the inward centre-support polygon stays evaluator-only.

## 2. What still belongs to the old semantics

The live pipeline does **not** currently treat the environment as a first-class closed venue \(\Omega_{\mathrm{env}}\). It treats a numeric box.

| Old / implicit object | Where | Problem |
| --- | --- | --- |
| `room.size: [W, H]` origin AABB | `experiments/static_containment/config.py` | No square/rectangle type, no vertices, no openings API |
| `crowd.region.vertices` | YAML + `StaticCrowdConfig` | Generator-side crowd occupancy; named like a known crowd region |
| YAML `crowd.center` / `crowd.radius` | `methods.py` `static_circle` | Baseline **leaks generator truth** into a controller |
| Heterogeneity sidecar | `runner.py` writes `crowd_attributes.npz` | Attributes never enter `CrowdObservation` or ABCG |
| `types.RoomConfig` exits / spawn_center | unused in this pipeline | Leftover evacuation semantics; do not revive |
| Research wording | README / `RESEARCH_SPEC.md` | “unknown crowd” without “known environment boundary” |

ABCG-v2 itself does **not** read spawn vertices. The gap is the missing explicit contract, not a silent spawn→estimator leak on the ABCG path.

Normal-offset deployment in `boundary_v2_from_curve` still belongs to the old geometry: pointwise \(p + d_s n(p)\). That is the main source of `OFFSET_INVALID` / self-intersection on concave and irregular crowds. It must not be “fixed” by loosening validity or falling back to spawn/room/truth.

## 3. What must change to known \(\partial\Omega_{\mathrm{env}}\) + unknown crowd

Required split:

```text
known environment boundary  !=  unknown crowd boundary
simulator spawn polygon     !=  controller observation
evaluator truth             !=  ABCG input
crowd-boundary estimate     !=  deployment curve
```

Concrete work:

1. Add `scenarios.RectangularScenario` for closed square/rectangle, `contains(margin)`, wall clearance, empty openings (Step 2 reserved).
2. Add `CrowdObservation(positions, observable_attributes)`. Reject spawn/truth/region/support polygons on the controller API.
3. Keep `crowd.spawn.vertices` / `crowd.region.vertices` as **private initialization**. Config compatibility: accept both keys.
4. Build \(\widehat{\Omega}_d = \widehat{\Omega}_c \oplus B_{d_s}\) with robust polygon buffering. Fail explicitly: `OFFSET_INVALID`, `OFFSET_OUTSIDE_WORKSPACE`, `DEPLOYMENT_INFEASIBLE`. No silent clip-to-success.
5. Guide workspace \(\Omega_g = \Omega_{\mathrm{env}} \ominus B_{m_w}\). Environment is for wall safety and feasibility, never a crowd-contour substitute.
6. Report separate minima: guide–guide, guide–crowd, guide–wall. Do not collapse to one mixed distance.
7. Wire wall constraints from the known rectangle (same AABB inequalities, now owned by the scenario).
8. Default CLI live visualization; `--headless` only for CI / unattended benchmarks.
9. New canonical configs under `configs/step1_known_boundary/` plus stress cases. Do not delete existing pairing configs or reports.

`boundary_v2_from_curve` normal offset remains for existing PR6 tests. The known-boundary pipeline uses a **separate** deployment-curve module.

## 4. Where real-time visualization is missing

There is no running-time viewer.

| Current path | Behavior |
| --- | --- |
| `containment_visualization.plot_static_containment` | Post-run PNG; no room, no trajectory, `plt.close` |
| `run_static_containment(..., save_plots=True)` | Writes `containment.png` after the episode |
| G6/PR6 reports | `matplotlib.use("Agg")` gallery PNGs |
| README GIFs | Offline frames from cached finals |
| `jupedsim_static_smoke.py` | Interactive snapshot, not a control loop |

`ABCGv2Controller.reset` / `step` already exist and must remain matplotlib-free. Live rendering belongs in `visualization/live_step1.py`, driven by the experiment runner.

Required window: environment polygon, static crowd, heterogeneity, estimated \(\partial\widehat{\Omega}_c\), deployment curve, targets, initial/current guides, trails, active/reserve, controller state, and the HUD listed in the task. Failure states still show at least one frame.

## 5. Files planned for modification

### Add

- `src/crowd_management/scenarios/__init__.py`
- `src/crowd_management/scenarios/base.py`
- `src/crowd_management/scenarios/rectangular.py`
- `src/crowd_management/crowd/observation.py`
- `src/crowd_management/geometry/deployment_curve.py`
- `src/crowd_management/visualization/__init__.py`
- `src/crowd_management/visualization/live_step1.py`
- `src/crowd_management/visualization/static_step1.py`
- `configs/step1_known_boundary/*.yaml`
- `scripts/run_step1_known_boundary.py`
- `scripts/analyze_step1_known_boundary.py`
- `tests/step1/test_truth_leakage.py`
- `tests/step1/test_known_boundary_scene.py`
- `tests/step1/test_deployment_curve.py`
- `tests/step1/test_live_visualization.py`
- `tests/step1/test_known_boundary_end_to_end.py`

### Change (small, compatible)

- `experiments/static_containment/config.py` — parse `scene` + `visualization`; keep `room.size`
- `crowd/static_crowd.py` — accept `crowd.spawn.vertices` alias
- `crowd/source.py` — expose `CrowdObservation` without removing `observe() -> ndarray`
- `controllers/abcg_v2.py` — `step` accepts observation arrays or `CrowdObservation`; optional episode callback; extra statuses
- `controllers/safety.py` — named wall-margin distances; min-distance reporters
- `experiments/static_containment/runner.py` — known-boundary path, live viewer, richer artifacts
- `experiments/static_containment/artifacts.py` — requested npz/json set
- `scripts/run_static_containment.py` — default live, `--headless`
- `README.md`, `docs/RESEARCH_SPEC.md`, `docs/CODEMAP.zh.md`

### Do not

- Modify `main` or `math-verification-main-v1`
- Merge to `main` or force-push
- Copy `ABCG-controller` wholesale
- Delete `reports/step1_source_pairing/`
- Feed spawn / truth / room polygon into ABCG as a crowd boundary
- Advance JuPedSim pedestrian dynamics
- Implement split/merge, multiple crowds, local sensing, wall-assisted containment
