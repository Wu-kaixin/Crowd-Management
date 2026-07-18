<div align="center">

# Crowd Management

Research simulator for adaptive guide-agent deployment around unknown crowds.

[English](README.md) | [Traditional Chinese](README.zh-TW.md) | [Japanese](README.ja.md)

![License](https://img.shields.io/badge/License-MIT-green.svg)
![Python](https://img.shields.io/badge/Python-3.12%2B-blue.svg)
![Tests](https://img.shields.io/badge/Tests-93%20passed-brightgreen.svg)
![Version](https://img.shields.io/badge/Version-0.1.0-informational.svg)
![Visualization](https://img.shields.io/badge/Visualization-Matplotlib-orange.svg)

</div>

Crowd Management is a Python research prototype for studying how multiple guide agents can be deployed around an unknown crowd. The active scope is static containment: a crowd is represented as a point cloud, its boundary is estimated, and guide agents are placed around an offset safety boundary.

The current method family is **ABCG: Adaptive Boundary-Coverage Guidance**. It combines radial or alpha-shape boundary estimation, bootstrap uncertainty, periodic coverage planning, adaptive guide allocation, SciPy identity-preserving assignment, a measured-feedback `reset/step` velocity controller, and sampled-data velocity safety projection. PR0-PR6 implementation and formal G6 evaluation evidence are present in the working tree. The frozen-commit condition remains intentionally unmet until review is complete.

Previous evacuation-guidance experiments are preserved as legacy baselines. They are available for reproducibility, but they are not the main project direction.

> This repository is a research prototype. It is not a calibrated crowd-safety product, deployment planner, or safety-certified control system.

---

## Visual Overview

The active media below shows ABCG static containment on circular, elliptical, irregular, and two-cluster point clouds.

![ABCG static containment grid](reports/media/abcg_static_containment_grid.png)

![ABCG containment animation](reports/media/abcg_static_containment.gif)

![ABCG metrics summary](reports/media/abcg_metrics_summary.png)

Legacy evacuation, DBAct, and density-DBAct media are stored under `legacy/evacuation_guidance/` and are not used as the main README visuals.

---

## Active Research Scope

The current stage evaluates static unknown-crowd containment.

- **Input:** a static 2D crowd point cloud.
- **Estimator:** the preserved v1 radial estimator plus a PR6 alpha-shape estimator with adaptive radius/smoothing selection, ordered arc geometry, bootstrap uncertainty/confidence, normal offsets, and explicit invalid status.
- **Periodic planner:** PR2 provides deterministic equal-arc and confidence-gated periodic Lloyd plans with exact uniform-density `H`, cell masses, convergence history, and explicit invalid states.
- **Resources and assignment:** PR3 computes `ceil(L/g_req)`, applies count hysteresis and capacity clipping, keeps reserve guides explicit, and solves deterministic guide-target assignment with switch penalties.
- **Motion and safety controller:** PR4 supplies `u_nom = sat(k_p(z-p))` and explicit Euler integration. PR5 deterministically projects `u_nom` onto reachable guide-guide, guide-crowd, and room half-spaces together with per-guide speed balls. Every applied control, projection status, constraint count, type-specific maximum residual, and emergency stop is recorded.
- **Endpoint baselines:** ABCG weighted placement, random deployment, static circular deployment, and legacy center-radius deployment provide the PR4 initial positions.
- **Baselines:** random deployment, static circular deployment, and legacy center-radius deployment.
- **Evaluation:** analytic generator truth is isolated from every estimator and planner. Formal G6 uses circle, ellipse, held-out U/C shapes; five required methods; three initial layouts; 30 paired seeds; 30 boundary bootstrap replicas; radial/alpha/confidence/resource ablations; noise, dropout, and scale sweeps; double-cluster and narrow-neck stress cases; paired effect sizes; worst-5% statistics; real failure examples; and runtime/P95/memory evidence. Failed runs remain in the denominator.
- **Metrics:** primary containment metrics use the final episode frame; initial endpoint coverage and maximum Euclidean boundary distance are retained separately for audit. Safety-filter convergence and containment efficacy are reported separately: a feasible safety projection does not imply that an unsafe fixed target can be reached.

The authoritative PR0-PR6 scope and Gate definitions are in [docs/RESEARCH_SPEC.md](docs/RESEARCH_SPEC.md).

The next stages can add dynamic crowds, behavior response, local collision avoidance, route choice, and evacuation scenarios after the static containment layer is stable.

---

## Quick Start

Create or update the conda environment:

```bash
conda env update -n abcg -f environment.yml
conda activate abcg
```

Run the main static containment experiment:

```bash
python scripts/run_static_containment.py --config configs/static_crowd_circle.yaml --output runs/static_containment_circle --methods random static_circle legacy_center_radius abcg
```

Important outputs:

- `runs/static_containment_circle/summary.json`
- `runs/static_containment_circle/summary.csv`
- `runs/static_containment_circle/manifest.json`
- `runs/static_containment_circle/config_resolved.yaml`
- `runs/static_containment_circle/crowd_truth.npz`
- `runs/static_containment_circle/boundary_v2_status.json`
- `runs/static_containment_circle/boundary_v2.npz` when geometry is valid
- `runs/static_containment_circle/periodic_plan_status.json`
- `runs/static_containment_circle/periodic_plan.npz` when the PR2 plan is valid and converged
- `runs/static_containment_circle/resource_decision.json`
- `runs/static_containment_circle/<method>/assignment_status.json`
- `runs/static_containment_circle/<method>/assignment.npz` unless assignment is skipped or infeasible
- `runs/static_containment_circle/<method>/episode_status.json`
- `runs/static_containment_circle/<method>/episode.npz` when a finite episode trace exists, including PR5 per-frame safety arrays
- `runs/static_containment_circle/abcg/metrics.json`
- `runs/static_containment_circle/abcg/containment.png`

Regenerate README media:

```bash
python scripts/build_readme_media.py
```

Run tests:

```bash
pytest --basetemp=.tmp/pytest-temp -o cache_dir=.tmp/pytest-cache
```

Check dependency consistency:

```bash
python -m pip check
```

`No broken requirements found.` is pip's successful result, not an error.

Run the formal PR6/G6 closed-loop evaluation:

```bash
python scripts/run_step1_g6_compliance.py --output reports/step1_g6_compliance --run-root runs/step1_g6_compliance
```

The formal report is [reports/step1_g6_compliance/G6_COMPLIANCE_REPORT.md](reports/step1_g6_compliance/G6_COMPLIANCE_REPORT.md). The earlier boundary-only PR6 evaluator remains available as a compatibility diagnostic, but it is not sufficient by itself for formal G6. The formal source snapshot is deliberately marked `UNFROZEN_DIRTY_WORKTREE`; committing must happen only after the staged scope is reviewed.

---

## Repository Layout

```text
Crowd-Management/
|-- configs/                         # Active static containment scenarios
|-- docs/                            # Step 1 research contract and Gate status
|-- src/crowd_management/
|   |-- crowd/                        # Static crowd point-cloud generators
|   |-- geometry/                     # Closed-curve arc length and validity
|   |-- estimation/                   # Boundary and state estimation
|   |-- controllers/                  # ABCG, periodic CVT, resources, assignment, kinematics, and baselines
|   |-- experiments/                  # Experiment runners
|   |-- evaluation/                   # PR6 compatibility and formal G6 evaluation
|   |-- legacy/evacuation/            # Archived evacuation implementation
|   |-- containment_metrics.py        # Static containment metrics
|   `-- containment_visualization.py  # Static containment plotting
|-- scripts/
|   |-- run_static_containment.py     # Main experiment CLI
|   |-- run_step1_pr6_evaluation.py   # Paired robust-evaluation CLI
|   |-- run_step1_g6_compliance.py    # Formal G6 closed-loop evaluation CLI
|   |-- build_readme_media.py         # README media generation
|   `-- legacy wrappers               # Compatibility wrappers for archived scripts
|-- reports/
|   |-- media/                        # Active ABCG media
|   |-- step1_pr6_evaluation/         # Earlier boundary-only PR6 diagnostic
|   `-- step1_g6_compliance/          # Formal compact G6 evidence and gallery
|-- legacy/
|   `-- evacuation_guidance/           # Archived old configs, reports, media, and scripts
|-- tests/
|-- pyproject.toml
`-- README.md
```

---

## Legacy Archive

The earlier evacuation-guidance line is stored in:

```text
legacy/evacuation_guidance/
src/crowd_management/legacy/evacuation/
```

The archive contains old scenario files, reports, figures, GIF media, original script implementations, replay utilities, metrics, and evacuation controllers. Root-level compatibility wrappers remain for older commands, but new development should start from `scripts/run_static_containment.py`.

---

## Development Status

- Active branch: `main`.
- Active method family: ABCG static unknown-crowd containment.
- Step 1 delivery status: PR0-PR5 complete; PR6 formal-compliance implementation/evaluation complete in the working tree; only the user-deferred frozen-commit requirement remains pending.
- Pre-freeze local validation in Conda `abcg`: `95 passed`.
- Main committed media: PNG and GIF artifacts under `reports/media/`.

## License

This project is released under the [MIT License](LICENSE).
