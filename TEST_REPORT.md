# Test Report

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
