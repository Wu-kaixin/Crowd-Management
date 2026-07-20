# AGENTS.md

## Project Direction

This repository is now centered on **ABCG static unknown-crowd containment**.
The active workflow is not DBAct evacuation optimization. DBAct, density-DBAct,
and old evacuation-guidance material are archived under:

```text
legacy/evacuation_guidance/
src/crowd_management/legacy/evacuation/
```

New work should start from:

```text
scripts/run_static_containment.py
configs/static_crowd_*.yaml
src/crowd_management/controllers/abcg.py
```

ABCG-v2.1 proof-strengthening and G7 work starts from:

```text
scripts/run_step1_g7.py
scripts/build_step1_g7_media.py
configs/step1_g7.yaml
src/crowd_management/controllers/abcg_v2.py
src/crowd_management/evaluation/step1_g7.py
```

## Environment

This is a Python 3.12 CLI research simulator. There is no long-running server or
web app. Run experiments through scripts and inspect generated metrics/figures.

Preferred setup:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

Project Conda environment:

```bash
conda env update -n abcg -f environment.yml
conda run -n abcg python -m pip install -e ".[dev]"
```

## Testing

Standard command:

```bash
pytest --basetemp=.tmp/pytest-temp -o cache_dir=.tmp/pytest-cache
```

The historical G6 baseline had `95 passed`. The final post-Holdout
ABCG-v2.1 code/report tree has `279 passed in 154.16s`.

Dependency health command:

```bash
python -m pip check
```

The success message `No broken requirements found.` has exit code zero and is
not an error.

## Main Commands

Run ABCG static containment:

```bash
python scripts/run_static_containment.py --config configs/static_crowd_circle.yaml --output runs/static_containment_circle --methods random static_circle legacy_center_radius abcg
```

Run the PR6 held-out paired evaluation:

```bash
python scripts/run_step1_pr6_evaluation.py --output reports/step1_pr6_evaluation --seed-count 30
```

Run the ABCG-v2.1 G7 protocol in order, from a committed clean freeze for the
formal phases:

```bash
python scripts/run_step1_g7.py --phase pilot --output runs/step1_g7/pilot
python scripts/run_step1_g7.py --phase calibration --output runs/step1_g7/calibration
python scripts/run_step1_g7.py --phase freeze --output runs/step1_g7/freeze --pilot-evidence runs/step1_g7/pilot/pilot_evidence.json --calibration-evidence runs/step1_g7/calibration/calibration_evidence.json
python scripts/run_step1_g7.py --phase holdout --output reports/step1_g7 --freeze-manifest runs/step1_g7/freeze/freeze_manifest.json --workers 24
python scripts/build_step1_g7_media.py --input reports/step1_g7 --output reports/media/step1_g7
```

The recorded formal result under `reports/step1_g7/` is G7 `FAIL`, based on
330 records (300 ABCG-v2.1 deployment records plus 30 tracking-only G6
comparator records), frozen SHA
`dc73866254136b1e14237483bc4c8a0934e8732f`, config hash
`6e6a1459bcf845e5db6dd653d682f330cda66d4cef3ecba1df04aca4b7cb48ce`,
and records hash
`b8b5ddb9879c268e62447b89572b8dd8b9167f0096fdaa0b32099f1b88b91238`.

## Evidence Protection Rules

- Treat the historical G6 report, compact evidence, Visual Overview, and its
  media as read-only. Do not overwrite G6 evidence while working on G7.
- Formal G7 evidence must follow Pilot -> independent Calibration -> clean
  committed Freeze -> Holdout. Quick runs, pilot data, and historical G6 seeds
  are diagnostic only and cannot support the formal conclusion.
- The formal holdout worker count must match the frozen manifest (`24` for the
  recorded run). Preserve deterministic case/method ordering and retain every
  algorithm failure in the denominator.
- Do not compare the old G6 `CONVERGED` label directly with v2.1 deployment
  success. G6 `CONVERGED` is tracking-only; v2.1 uses a stricter layered
  success definition.
- Do not treat `0/6` blocked candidate timeouts as success: all six candidate
  blocked records were `ROUTE_INFEASIBLE`. Do not call
  `reports/media/step1_g7/success_case.gif` a success case; it is the explicit
  no-truth-success placeholder.
- Calibration is insufficient, the Holm-adjusted primary family failed, and
  primary inference for tracking RMSE and minimum intersample clearance is
  forbidden. Do not fill missing continuous endpoints or drop failed runs.
- The frozen `resource_pareto.json` `COMPARABLE` values are
  failure-inclusive exploratory labels. The corrected plot marks them with
  `X`, with `0/10` zero-failure groups; do not make a deployment Pareto claim.
- Renderer concavity, figure-semantics, and Git-blob-hash fixes were made after
  the formal run without rerunning the holdout. The formal evidence remains
  locked to `dc73866254136b1e14237483bc4c8a0934e8732f`. Any new formal code
  claim requires a new complete protocol and freeze; do not hand-edit the
  compact evidence to match later code.

Regenerate README media:

```bash
python scripts/build_readme_media.py
```

Legacy evacuation scripts remain as compatibility wrappers in `scripts/`, but
their original implementations and media are stored under
`legacy/evacuation_guidance/`.
