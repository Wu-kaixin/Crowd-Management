# Test Report

Sections through **Gate result** preserve the 2026-07-18 historical G6
snapshot. The independent ABCG-v2.1 S0-S6 and formal G7 failure audit are
appended afterward; they do not rewrite the G6 evidence.

## Snapshot

- Date: 2026-07-18 (Asia/Tokyo)
- Repository baseline: `main@fe4e7c1dd310c4eaef814c70e9edb34ec02227ae`
- Delivery stage: **ABCG-v2 Step 1 research-complete**
- Environment: Conda `abcg`
- Python: `3.12.13`
- Platform: Windows 11
- Implementation freeze: `f2494922b2431bfd9a37a247add8a79acfdc18ed`
- Evaluation source SHA-256: `ec422534d59f1bfecee8a5c1693a1be0357d564f855dfccbfc399df2a3a562ed`
- Freeze status: `FROZEN_COMMIT`; evaluator-generated G0-G6 `PASS`

## Environment and dependency repair

Formal Step 1 uses public research dependencies instead of private library
internals:

- SciPy `1.18.0` supplies public Delaunay/Qhull and Hungarian assignment APIs.
- Shapely `2.1.2` supplies polygonization, curve/polygon validity, intersection,
  and offset validation.

The first editable-install attempt reached package download but failed with
Windows `WinError 5` while writing the Conda environment/user site. Re-running
the same scoped command with approved environment write permission completed
the installation:

```powershell
conda run -n abcg python -m pip install -e ".[dev]"
```

Dependency consistency was then checked with:

```powershell
conda run -n abcg python -m pip check
```

Result:

```text
No broken requirements found.
```

This message is pip's successful exit-zero result, not an error.

## Formal G6 command

```powershell
conda run -n abcg python scripts/run_step1_g6_compliance.py `
  --output E:\Crowd-Management-step1-artifacts\f2494922b2431bfd9a37a247add8a79acfdc18ed\report `
  --run-root E:\Crowd-Management-step1-artifacts\f2494922b2431bfd9a37a247add8a79acfdc18ed\runs `
  --seed-count 30 `
  --bootstrap-samples 30 `
  --observation-count 120 `
  --ci-resamples 2000 `
  --max-steps 160 `
  --workers 4
```

The formal matrix contains four scenarios, five methods, and 30 paired seeds:
600 primary closed-loop records. Every method receives the same observation
and initial guide state for a scenario/seed pair. Analytic truth remains in the
evaluator only. Every primary run writes the resolved config, manifest,
observation/truth evaluator bundle, boundary version, plan trace, measured
feedback trajectory, event stream, and metrics.

Additional evidence contains:

- 240 radial/alpha/bootstrap-confidence/resource ablation records;
- 540 nonconvex noise, observation-dropout, and scale records;
- double-cluster, capacity-shortfall, and narrow-neck stress cases;
- two visualized actual failures, not relabelled worst valid cases;
- mean, median, bootstrap 95% CI, paired effect size, worst 5%, failure rate,
  runtime P95, and process peak resident memory.

## Formal result

- Wall time: `1791.93 s`
- Process peak resident memory: `125,779,968 bytes`
- Primary method runtime: mean `13,290.78 ms`, median `8,531.90 ms`, P95
  `37,270.29 ms`, worst-5% mean `43,943.84 ms`
- Terminal accounting: `323 CONVERGED`, `242 TIMEOUT`,
  `5 SAFETY_INFEASIBLE`, `30 BOUNDARY_INVALID`
- All 600 primary records remain in the denominator.

Full ABCG-v2 outcomes:

| Scenario | Converged/total | Failure rate | Mean arc gap (m) | Mean truth coverage |
| --- | ---: | ---: | ---: | ---: |
| Circle | 18/30 | 0.400 | 2.031 | 0.819 |
| Ellipse | 26/30 | 0.133 | 2.049 | 0.848 |
| U shape | 9/30 | 0.700 | 2.099 | 0.496 |
| C shape | 5/30 | 0.833 | 2.120 | 0.508 |

These are compliance and failure-characterization results, not evidence that
ABCG-v2 dominates every baseline. The one-sided layout produced only 16
convergences across all 200 method/scenario runs, with 169 timeouts and five
safety-infeasible outcomes (ten additional runs had a shared invalid
boundary). A straight-line fixed-target controller cannot reliably route a
guide around an observed crowd when its assigned target lies on the opposite
side; the safety filter correctly prevents traversal through the crowd but is
not a path planner. Nonconvex U/C performance therefore remains a material
Step 1 limitation.

Three seeds in each nonconvex scenario produced an invalid shared boundary, so
all five paired methods failed explicitly for those pairs. The stress gallery
also preserves a double-cluster `BOUNDARY_INVALID` and a
`CAPACITY_SHORTFALL`. The narrow-neck stress case was valid at the formal
observation count and is retained as a stress result rather than mislabelled a
failure.

Primary compact artifacts retained for the frozen report:

- `reports/step1_g6_compliance/G6_COMPLIANCE_REPORT.md`
- `reports/step1_g6_compliance/gate_evidence.json`
- `reports/step1_g6_compliance/aggregate.json`
- `reports/step1_g6_compliance/paired_comparisons.json`
- `reports/step1_g6_compliance/ablation_aggregate.json`
- `reports/step1_g6_compliance/robustness_aggregate.json`
- `reports/step1_g6_compliance/stress_cases.json`
- `reports/step1_g6_compliance/failure_gallery.json`
- `reports/step1_g6_compliance/performance.json`
- `reports/step1_g6_compliance/evaluation_snapshot.json`
- `reports/step1_g6_compliance/preflight_evidence.json`

Raw `records.csv`, `records.json`, ablation/robustness rows, and the generated
gallery image remain reproducible external artifacts and are not versioned.

Large per-run traces remain under ignored `runs/step1_g6_compliance/` and are
not proposed for commit.

## Test suite and health checks

```powershell
conda run --no-capture-output -n abcg python -m pytest `
  --basetemp=.tmp/pytest-temp `
  -o cache_dir=.tmp/pytest-cache
```

Result:

```text
95 passed in 73.05s
```

Additional checks:

```powershell
conda run -n abcg python -m compileall -q src scripts
conda run -n abcg python -m pip check
```

Both exited zero. `pip check` printed `No broken requirements found.` Targeted
formal-G6 evidence-architecture checks also passed: `4 passed in 15.86s`.
The formal CLI repeated the full suite automatically: `95 passed in 75.17s`.

The first fresh-checkout attempt exposed that pytest 9 does not create the
missing parent of `--basetemp=.tmp/pytest-temp`: 75 tests passed and 19 setup
items failed with `FileNotFoundError` before their temporary directories could
be created. The formal preflight now creates only the ignored `.tmp/` parent,
has a regression test for this behavior, and does not alter test requirements.

## Gate result

All automatic formal G6 checks are true:

- public SciPy/Shapely research dependencies;
- instance-local measured-feedback `reset/step` API;
- four required scenarios and five required methods;
- at least 30 paired seeds and 30 bootstrap replicas;
- all 600 primary records accounted for, including every failure;
- required ablations and noise/dropout/scale scans;
- double-cluster and narrow-neck stress evidence;
- mean/median/CI/effect-size/worst-5%/failure statistics;
- actual failure gallery;
- runtime/P95/memory evidence;
- eight required artifacts for every primary run.

Evaluator-generated `gate_evidence.json` reports:

- `overall_status = PASS` and `g6_status = PASS`;
- `frozen_commit = PASS`;
- `evaluated_commit = f2494922b2431bfd9a37a247add8a79acfdc18ed`;
- G0, G1, G2, G3, G4, G5, and G6 all `PASS`;
- no false compliance checks and no `UNMET_*` value;
- 600 JSON records, 600 CSV rows, 600 run manifests/metrics, 323 successes,
  and 277 retained failures with matching counts.

The frozen implementation therefore satisfies the Step 1 research-complete
criterion. Final documentation HEAD is still subject to the second clean
checkout consistency run described in the freeze audit.

The evidence does not establish continuous-time safety, robust nonconvex
containment, dynamic crowds, local communication, real-sensor performance, or
human behavioral efficacy.

## ABCG-v2.1 S0-S6 validation history

ABCG-v2.1 proof-strengthening started from
`1c3642c1adef0f11e0bde7651e2da64afbc45a8b`. Historical G6 evidence at
implementation freeze `f2494922b2431bfd9a37a247add8a79acfdc18ed` remained
read-only and hash-audited throughout the work.

| Checkpoint | Full-suite result | Main verified contract |
| --- | ---: | --- |
| Baseline | `95 passed` | Clean starting point; compileall and pip check pass |
| S0 | `102 passed` | Layered evaluator success; controller convergence is tracking-only |
| S1 | `111 passed` | Registered boundary stability, calibration gates, canonical buffer |
| S2 | `138 passed` | Analytic equal arc, phase selection, explicit resource uncertainty |
| S3 | `156 passed` | Certified routing and geodesic/cyclic assignment |
| S4 | `166 passed` | Immutable waypoint execution and explicit no-progress/route failure |
| S5 | `189 passed` | Shared hashed QCQP, Dykstra/SLSQP certificates, dense ZOH checks |
| S6 pre-freeze | `276 passed` | 24-worker determinism, evidence/statistics/media protocol |

All recorded stage checkpoints also passed `compileall` and `pip check`; S3
and later recorded a clean `git diff --check`. The S6 pre-freeze run is not a
G7 PASS: it verifies the implementation and protocol before the formal
Holdout, whose result is reported separately below.

After the Holdout, the focused renderer and source-provenance regression set
passed:

```text
70 passed in 122.65s
```

The final full-suite result for the current post-Holdout working tree is
**PENDING MAIN-AGENT BACKFILL**. No final count or elapsed time is claimed in
this report until that run completes.

## Formal G7 protocol and command

The frozen protocol is `Pilot -> independent Calibration -> Freeze ->
Holdout`. Pilot, calibration, G7 Holdout, and historical G6 seeds are disjoint;
truth remains evaluator-only. The formal execution used 24 independent
case-level Windows spawn workers, one numeric-library thread per worker, and
no GPU. The formal geometry/optimization path is CPU-only NumPy/SciPy/Shapely,
GEOS/Qhull, Hungarian, Dykstra, and SLSQP.

The reproducible phase commands are:

```powershell
conda run --no-capture-output -n abcg python scripts/run_step1_g7.py `
  --phase pilot --config configs/step1_g7.yaml `
  --output runs/step1_g7/pilot --workers 24

conda run --no-capture-output -n abcg python scripts/run_step1_g7.py `
  --phase calibration --config configs/step1_g7.yaml `
  --output runs/step1_g7/calibration

conda run --no-capture-output -n abcg python scripts/run_step1_g7.py `
  --phase freeze --config configs/step1_g7.yaml `
  --output runs/step1_g7/freeze `
  --pilot-evidence runs/step1_g7/pilot/pilot_evidence.json `
  --calibration-evidence runs/step1_g7/calibration/calibration_evidence.json

conda run --no-capture-output -n abcg python scripts/run_step1_g7.py `
  --phase holdout --config configs/step1_g7.yaml `
  --output reports/step1_g7 `
  --freeze-manifest runs/step1_g7/freeze/freeze_manifest.json `
  --workers 24
```

Formal identities:

| Item | Value |
| --- | --- |
| Base SHA | `1c3642c1adef0f11e0bde7651e2da64afbc45a8b` |
| Historical G6 implementation freeze | `f2494922b2431bfd9a37a247add8a79acfdc18ed` |
| G7 frozen evaluator SHA | `dc73866254136b1e14237483bc4c8a0934e8732f` |
| Resolved config SHA-256 | `6e6a1459bcf845e5db6dd653d682f330cda66d4cef3ecba1df04aca4b7cb48ce` |
| Compact records SHA-256 | `b8b5ddb9879c268e62447b89572b8dd8b9167f0096fdaa0b32099f1b88b91238` |
| Formal denominator | `330 = 300 ABCG-v2.1 + 30 G6 adapter` |

The 30 `g6_fixed_resource_rerun` records are a tracking-only adapter assembled
from frozen G6 components on matched G7 inputs. They are not exact historical
G6 runs and are excluded from the 300-record ABCG-v2.1 deployment denominator.

## Formal G7 result: FAIL

`reports/step1_g7/gate_evidence.json` records `status = FAIL`. ABCG-v2.1 has
`0/300` estimated deployment successes and `0/300` truth-validated successes.
Every deployment record remains in the denominator:

| Terminal status | Count | Rate |
| --- | ---: | ---: |
| `ROUTE_INFEASIBLE` | 232 | 77.3% |
| `RESOURCE_UNCERTAIN` | 60 | 20.0% |
| `TIMEOUT` | 8 | 2.7% |

The formal gate failed because:

- independent uncertainty calibration returned
  `CALIBRATION_INSUFFICIENT` (`0.75` simultaneous validation coverage against
  the frozen `0.95` target);
- the Holm-adjusted primary superiority family did not pass;
- `tracking_rmse` has `30/0/30` total/complete/missing primary pairs; and
- `minimum_intersample_clearance` has `30/0/30` primary pairs.

The continuous missing-data contract permits descriptive complete-case output
only; either missing primary endpoint forbids primary and noninferiority PASS.

The matched blocked-route comparison must not be read as a success claim. The
G6 fixed-resource adapter has `TIMEOUT` in `5/6` U/C cases, versus `0/6` for
visibility routing, but all `6/6` visibility cases terminate
`ROUTE_INFEASIBLE` before control. Lower TIMEOUT incidence here means the
candidate failed at an earlier layer; it does not establish route feasibility,
tracking, sampled safety, or deployment success.

## Formal G7 evidence files

The compact formal evidence is retained under `reports/step1_g7/`:

- `G7_REPORT.md` and `gate_evidence.json`;
- `freeze_manifest.json` and `evaluation_snapshot.json`;
- `records_compact.json`, `aggregate.json`, and
  `failure_composition.json`;
- `paired_stats.json` and `noninferiority.json`;
- `g6_tracking_comparator.json`, `safety_comparison.json`, and
  `resource_pareto.json`;
- `readme_summary.json` and `media_evidence.json`.

The formal set is immutable evidence for the evaluated `dc738662...` freeze.
It must not be rewritten to make later code agree with the old manifest or to
change the gate. Generated media under `reports/media/step1_g7/` and the
post-run audit are derived interpretation artifacts, not a replacement
Holdout.

## Post-Holdout audit and provenance limitation

Three interpretation/provenance issues were corrected after the frozen run:

1. The renderer now validates that the hash-linked U/C evaluator truth is
   genuinely concave while preserving each method's actual estimate, which
   may validly be convex.
2. The blocked-route TIMEOUT figure now exposes candidate terminal
   composition and warns that reduced TIMEOUT alone is not deployment
   success.
3. Compact adaptive-resource media now compute failure counts and mark every
   failure-containing group with `X`.

The frozen `resource_pareto.json` calls finite failure-inclusive points
`COMPARABLE`. Every one of its ten grouped points contains failures, so none is
evidence of a deployment Pareto frontier. The regenerated compact media
honestly shows `0/10` zero-failure deployment-Pareto groups and uses `X` for
the frozen failure-inclusive outcomes; it does not modify the formal JSON.

The frozen source aggregate was computed from checkout-filtered Windows bytes.
It verified in that checkout, but the same commit could hash differently under
another CRLF policy. Post-run code instead hashes canonical Git blobs and has
a line-ending regression test.

At the user's instruction, the replacement freeze and Holdout were stopped.
No Holdout was rerun after these renderer and Git-blob changes. Consequently,
they cannot change, repair, or supersede the formal statistics, and no
post-Holdout performance claim is allowed. The formal conclusion remains
`dc738662...` **G7 FAIL**.

The G7 evidence is restricted to guide deployment around one static synthetic
point cloud under global observation. It does not establish human containment
or evacuation improvement, behavior change, dynamic or multiple crowds,
general path-planning completeness, safety certification, or unconditional
continuous-time safety.
