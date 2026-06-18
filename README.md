# Crowd Management Simulation Prototype

This repository contains a research prototype for testing crowd-management ideas in a compact 2D simulator. The current implementation focuses on microscopic pedestrian motion, mobile guider influence, route-choice experiments, and reproducible evaluation reports.

The repository is not a full crowd-management system and does not yet implement a calibrated real-world crowd model. Its purpose is to provide a controlled simulation and visualization basis for deciding which guidance mechanisms are worth developing further.

## Current Scope

Implemented scope:

- microscopic agent-based pedestrian simulation;
- wall, boundary, exit, and pedestrian-pedestrian interaction handling;
- mobile guider entities that can influence compliant pedestrians;
- DBACT-style guider placement transferred from cooperative multi-agent guidance;
- static, random, nearest-exit, balanced-exit, split-flow, and density-aware comparison modes;
- two-exit bottleneck experiments for congestion and route-choice behavior;
- multi-seed evaluation tooling;
- 2D visualizations, dashboards, heatmaps, animations, and report artifacts;
- automated tests for core simulation, CLI scripts, visualization, and evaluation pipelines.

Currently out of scope:

- real-world deployment;
- hardware or robot experiments;
- calibrated empirical pedestrian behavior;
- hybrid micro-macro crowd modeling;
- exclusion-queue modeling;
- control-barrier-function controllers;
- LLM-based operational decision support.

## Research Progress

The project has progressed through four implementation stages.

| Stage | Main contribution |
| --- | --- |
| Stage 1 | Basic microscopic crowd simulator, baseline runs, guided runs, metrics, and simple visual outputs. |
| Stage 2 | Multi-seed one-exit evaluation framework and presentation-oriented visualization package. |
| Stage 3 | Two-exit bottleneck scenario and density-aware DBACT guidance that can create visible split-flow. |
| Stage 4 | Robust multi-seed density evaluation with fair baselines, ablations, composite scoring, and mechanism visualization. |

The latest tracked Stage 4 report evaluates 9 modes across 10 seeds in `configs/two_exit_bottleneck.yaml`.

Key Stage 4 aggregate results:

| Mode | Evacuation rate | Congestion | Cumulative congestion | Alternate-exit usage | Exit imbalance | Composite score |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `baseline` | 0.9994 | 2.2056 | 85.4368 | 0.0000 | 1.0000 | 0.3592 |
| `static` | 0.9994 | 2.2033 | 84.5823 | 0.0000 | 1.0000 | 0.3635 |
| `dbact` | 1.0000 | 2.4961 | 92.3552 | 0.0000 | 1.0000 | 0.2819 |
| `nearest_exit` | 1.0000 | 1.8076 | 68.0892 | 0.1559 | 0.6881 | 0.5650 |
| `balanced_exit_static` | 0.9997 | 1.4810 | 53.2548 | 0.5002 | 0.0222 | 0.8177 |
| `density_only` | 0.9997 | 1.1949 | 41.6274 | 0.4889 | 0.0266 | 0.9156 |
| `exit_pressure_only` | 0.9722 | 1.5553 | 62.2892 | 0.6686 | 0.3372 | 0.6741 |
| `split_flow_only` | 0.9997 | 1.4810 | 53.2548 | 0.5002 | 0.0222 | 0.8177 |
| `density_dbact` | 0.9928 | 1.5474 | 61.9751 | 0.6912 | 0.3824 | 0.6883 |

Interpretation:

- The basic DBACT-transfer mode runs correctly, but it is not yet stronger than simpler guidance methods in the tested scenarios.
- In the two-exit bottleneck, route choice and split-flow are the clearest mechanisms for congestion reduction.
- `density_dbact` produces strong alternate-exit usage and lower congestion than the single-exit-biased baseline, but the current full method is not yet better than the strongest simple ablations.
- `density_only`, `balanced_exit_static`, and `split_flow_only` are important baselines because they show that much of the current improvement can come from fair exit assignment rather than complex guider placement.
- The composite score is exploratory. It should be read together with evacuation rate, congestion, cumulative congestion, exit usage, and visual behavior.

The current result is useful feasibility evidence, not final validation of a crowd-management algorithm.

## Simulator Model

The simulator represents pedestrians as individual agents with:

- position and velocity;
- desired speed;
- personal radius;
- target exit;
- compliance with guidance;
- evacuation state.

Pedestrian motion combines:

- attraction toward the assigned exit;
- pedestrian-pedestrian repulsion;
- wall and boundary handling;
- optional influence from mobile guiders.

The crowd is modeled as an active group of moving pedestrians, not as a rigid object.

## Guidance Modes

The repository includes these main modes:

| Mode | Description |
| --- | --- |
| `baseline` | No mobile guider intervention. |
| `static` | Fixed guider placement. |
| `random` | Random guider motion. |
| `dbact` | Dynamic DBACT-style guider placement around the active crowd. |
| `nearest_exit` | Pedestrians use the nearest available exit. |
| `balanced_exit_static` | Simple balanced assignment between exits. |
| `density_only` | Exit choice driven by density-related behavior without full DBACT placement. |
| `exit_pressure_only` | Exit choice driven by pressure estimates. |
| `split_flow_only` | Direct split-flow baseline. |
| `density_dbact` | Density-aware DBACT variant for two-exit bottleneck guidance. |

## Repository Layout

```text
Crowd-Management/
|-- configs/
|   |-- simple_room.yaml
|   |-- two_exits.yaml
|   `-- two_exit_bottleneck.yaml
|-- reports/
|   |-- first_demo/
|   |-- guidance_baselines_v1/
|   |-- visualization_package_v1/
|   |-- multi_seed_eval_v1/
|   |-- density_dbact_v1/
|   |-- visualization_upgrade_v1/
|   `-- stage4_density_eval_v1/
|-- scripts/
|   |-- run_baseline.py
|   |-- run_guided.py
|   |-- run_multi_seed_eval.py
|   |-- run_density_dbact_experiment.py
|   |-- run_stage4_density_eval.py
|   |-- run_visualization_package.py
|   |-- compare_results.py
|   |-- render_animation.py
|   |-- render_dashboard.py
|   |-- render_heatmap_snapshot.py
|   `-- render_side_by_side.py
|-- src/
|   `-- crowd_management/
|       |-- crowd_model.py
|       |-- dbact_transfer.py
|       |-- density_dbact.py
|       |-- guidance_controller.py
|       |-- guider_model.py
|       |-- metrics.py
|       |-- replay.py
|       |-- types.py
|       |-- visualization.py
|       `-- advanced_visualization.py
|-- tests/
|-- outputs/
|-- environment.yml
|-- pyproject.toml
|-- requirements.txt
|-- TEST_REPORT.md
`-- README.md
```

## Setup

Python 3.12 or newer is required.

Install with pip:

```bash
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

Or create the Conda environment:

```bash
conda env create -f environment.yml
conda activate C-M
python -m pip install -e ".[dev]"
```

## Run Basic Simulations

Baseline:

```bash
python scripts/run_baseline.py \
  --config configs/simple_room.yaml \
  --output outputs/baseline
```

DBACT-style guidance:

```bash
python scripts/run_guided.py \
  --config configs/simple_room.yaml \
  --mode dbact \
  --output outputs/dbact
```

Static and random guider baselines:

```bash
python scripts/run_guided.py \
  --config configs/simple_room.yaml \
  --mode static \
  --output outputs/static

python scripts/run_guided.py \
  --config configs/simple_room.yaml \
  --mode random \
  --output outputs/random
```

Compare runs:

```bash
python scripts/compare_results.py \
  --runs outputs/baseline outputs/static outputs/random outputs/dbact \
  --labels baseline static random dbact \
  --output outputs/comparison
```

## Run Density-Aware Experiments

Smoke run:

```bash
python scripts/run_density_dbact_experiment.py \
  --config configs/two_exit_bottleneck.yaml \
  --modes baseline density_dbact \
  --steps 20 \
  --seed 0 \
  --output runs/density_dbact_smoke \
  --skip-video
```

Full Stage 3-style run:

```bash
python scripts/run_density_dbact_experiment.py \
  --config configs/two_exit_bottleneck.yaml \
  --modes baseline static dbact density_dbact \
  --steps 800 \
  --seed 0 \
  --output runs/density_dbact_v1 \
  --quality ultra
```

## Run Stage 4 Evaluation

Smoke run:

```bash
python scripts/run_stage4_density_eval.py \
  --config configs/two_exit_bottleneck.yaml \
  --modes baseline density_dbact nearest_exit \
  --seeds 0 1 \
  --steps 20 \
  --output runs/stage4_density_eval_smoke \
  --skip-video
```

Full evaluation:

```bash
python scripts/run_stage4_density_eval.py \
  --config configs/two_exit_bottleneck.yaml \
  --modes baseline static dbact nearest_exit balanced_exit_static density_only exit_pressure_only split_flow_only density_dbact \
  --seeds 0 1 2 3 4 5 6 7 8 9 \
  --steps 800 \
  --output runs/stage4_density_eval_v1 \
  --quality high
```

Important outputs:

- `summary/run_metrics.csv`
- `summary/aggregate_metrics.csv`
- `summary/composite_scores.csv`
- `summary/STAGE4_DENSITY_EVAL_REPORT.md`
- `summary/TEAMS_CHANNEL_REPORT.md`
- `comparison/robust_metrics_dashboard.png`
- `comparison/composite_score_mean_std.png`
- `comparison/tradeoff_scatter.png`
- `comparison/mechanism_timeline_density_dbact.png`
- `comparison/mechanism_snapshot_density_dbact.png`
- `comparison/baseline_vs_density_dbact_mechanism.mp4`
- `comparison/fair_baselines_comparison.mp4`

## Visualization

Build a presentation-ready visualization package:

```bash
python scripts/run_visualization_package.py \
  --config configs/simple_room.yaml \
  --modes baseline static random dbact \
  --steps 400 \
  --seed 0 \
  --output runs/visualization_package_v1 \
  --quality high
```

Render a single run:

```bash
python scripts/render_animation.py \
  --run outputs/dbact \
  --output outputs/dbact/dbact_animation.mp4 \
  --fps 15 \
  --heatmap
```

Render a side-by-side comparison:

```bash
python scripts/render_side_by_side.py \
  --runs outputs/baseline outputs/dbact \
  --labels baseline dbact \
  --output outputs/comparison/baseline_vs_dbact.mp4
```

Render a dashboard:

```bash
python scripts/render_dashboard.py \
  --runs outputs/baseline outputs/static outputs/random outputs/dbact \
  --labels baseline static random dbact \
  --output outputs/comparison/dashboard.png
```

If `ffmpeg` is unavailable, animation scripts fall back from MP4 to GIF where supported.

## Reports

Tracked report artifacts:

```text
reports/first_demo/FIRST_DEMO_REPORT.md
reports/guidance_baselines_v1/GUIDANCE_BASELINES_REPORT.md
reports/visualization_package_v1/VISUALIZATION_PACKAGE_REPORT.md
reports/multi_seed_eval_v1/MULTI_SEED_EVAL_REPORT.md
reports/density_dbact_v1/DENSITY_DBACT_REPORT.md
reports/visualization_upgrade_v1/VISUALIZATION_REPORT.md
reports/stage4_density_eval_v1/STAGE4_DENSITY_EVAL_REPORT.md
reports/stage4_density_eval_v1/TEAMS_CHANNEL_REPORT.md
reports/stage4_density_eval_v1/stage4_key_findings.md
```

Generated run directories under `runs/` and `outputs/` are ignored by Git except for selected report artifacts that are intentionally tracked.

## Test And Health Check

Run the test suite:

```bash
pytest
```

If the default system temporary directory is not writable, keep pytest temporary files inside the repository:

```bash
pytest --basetemp=.tmp/pytest-temp -o cache_dir=.tmp/pytest-cache
```

Additional checks:

```bash
python -m compileall src scripts
python -m pip check
```

Latest local health check:

```text
pytest --basetemp=.tmp\pytest-temp -o cache_dir=.tmp\pytest-cache: 18 passed
python -m compileall src scripts: passed
python -m pip check: no broken requirements
```

## Current Research Direction

The next useful work is validation rather than adding unrelated large systems. Priority items are:

1. parameter sweeps for compliance, guider influence radius, density weighting, and exit-pressure weighting;
2. harder bottleneck geometries where dynamic guider placement has more room to matter;
3. calibration or comparison against pedestrian-behavior literature or data;
4. clearer separation between route-choice effects and guider-placement effects;
5. stronger visual summaries for explaining mechanism behavior and failure cases.

More complex crowd models can be added later, but the current repository first establishes a reproducible simulation and evaluation baseline.
