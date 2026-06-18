<div align="center">

# Crowd Management Simulation Prototype

Reproducible 2D crowd-evacuation experiments with metrics, reports, and visualizations.

[English](README.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md)

![License](https://img.shields.io/badge/License-MIT-green.svg)
![Python](https://img.shields.io/badge/Python-3.12%2B-blue.svg)
![Tests](https://img.shields.io/badge/Tests-18%20passed-brightgreen.svg)
![Version](https://img.shields.io/badge/Version-0.1.0-informational.svg)
![Visualization](https://img.shields.io/badge/Visualization-Matplotlib-orange.svg)

</div>

Crowd Management Simulation Prototype is a compact research simulator for testing crowd-evacuation guidance ideas before moving toward larger, real-world systems. It focuses on microscopic pedestrian motion, mobile guider influence, exit-choice behavior, density-aware split flow, reproducible evaluation, and presentation-ready visual outputs.

> This repository is a research prototype, not a calibrated real-world crowd-management product.

---

## Visual Showcase

![Baseline vs DBACT animation](reports/media/baseline_vs_dbact.gif)

> A tracked GIF artifact generated from replay data. Unlike local `runs/*.mp4` files, this file is committed under `reports/media/`, so it renders directly on GitHub.

![Visualization dashboard](reports/visualization_upgrade_v1/dashboard.png)

> Dashboard view with evacuation curves, normalized metrics, and final snapshots for multiple guidance modes.

---

## Media Gallery

All inline media below points to committed repository files under `reports/`, so GitHub can render them without local run artifacts.

| Animation | Dashboard |
| --- | --- |
| <img src="reports/media/baseline_vs_dbact.gif" alt="Baseline vs DBACT animation" width="100%"> | <img src="reports/visualization_upgrade_v1/dashboard.png" alt="Visualization dashboard" width="100%"> |

| Final Snapshots | Density Heatmap |
| --- | --- |
| <img src="reports/visualization_upgrade_v1/all_modes_grid.png" alt="Final snapshots for four modes" width="100%"> | <img src="reports/visualization_upgrade_v1/heatmap_snapshots.png" alt="Density heatmap snapshots" width="100%"> |

| Evacuation Curve | Final Metrics |
| --- | --- |
| <img src="reports/guidance_baselines_v1/evacuation_rate_comparison.png" alt="Evacuation rate comparison" width="100%"> | <img src="reports/guidance_baselines_v1/final_metrics_comparison.png" alt="Final metrics comparison" width="100%"> |

Generated MP4 videos are still supported by the scripts, but they are stored under `runs/` by default and are intentionally ignored by Git. For GitHub display, use committed GIF or PNG artifacts, or publish large videos through GitHub Releases.

---

## Project Snapshot

| Item | Details |
| --- | --- |
| Project name | Crowd Management Simulation Prototype |
| Purpose | Compare crowd-guidance strategies in controlled 2D evacuation scenarios. |
| Core stack | Python 3.12, NumPy, PyYAML, Matplotlib, imageio-ffmpeg, Pytest |
| Main scenarios | `simple_room.yaml`, `two_exits.yaml`, `two_exit_bottleneck.yaml` |
| Output types | CSV metrics, JSON summaries, replay files, PNG charts, GIF animations, Markdown reports |

---

## Features

- **Microscopic crowd simulation**: each pedestrian has position, velocity, desired speed, compliance, target exit, and evacuation state.
- **Multiple guidance modes**: baseline, static, random, DBACT-style, nearest-exit, balanced split-flow, density-only, pressure-only, and density-aware DBACT.
- **Reproducible evaluation**: single-run scripts, multi-seed aggregation, Stage 4 fair baselines, ablations, and composite scoring.
- **Visualization-first workflow**: snapshots, heatmaps, dashboards, synchronized comparisons, animations, and report-ready figures.
- **Tested CLI pipeline**: tests cover simulation, density-aware guidance, visualization packaging, multi-seed evaluation, and Stage 4 smoke workflows.

---

## Results & Visualizations

### Stage 4 Density-aware DBACT Evaluation

The latest tracked Stage 4 report evaluates 9 modes across 10 seeds in `configs/two_exit_bottleneck.yaml`.

| Mode | Evacuation Rate | Congestion | Cumulative Congestion | Alternate-exit Usage | Exit Imbalance | Composite Score |
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

**Interpretation**

- The strongest current scores come from simple, fair exit-assignment baselines such as `density_only`.
- `density_dbact` creates visible alternate-exit usage and split-flow behavior, but in the current parameter setting it does not yet beat the strongest simple ablations.
- The composite score is heuristic. Read it together with evacuation rate, congestion, cumulative congestion, exit usage, and visual behavior.

---

## Quick Start

### 1. Clone

```bash
git clone https://github.com/Wu-kaixin/Crowd-Management.git
cd Crowd-Management
```

### 2. Create an Environment

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

macOS / Linux:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

Conda:

```bash
conda env create -f environment.yml
conda activate C-M
```

### 3. One-line Smoke Experiment

```bash
python scripts/run_density_dbact_experiment.py --config configs/two_exit_bottleneck.yaml --modes baseline density_dbact --steps 20 --seed 0 --output runs/quick_density_dbact --skip-video --fast-test
```

Important outputs:

- `runs/quick_density_dbact/summary/metrics_summary.csv`
- `runs/quick_density_dbact/summary/DENSITY_DBACT_REPORT.md`
- `runs/quick_density_dbact/comparison/final_metrics_bar.png`
- `runs/quick_density_dbact/comparison/exit_usage_curve.png`

---

## How It Works

1. **Load scenario configuration**
   YAML files define room size, exits, pedestrian count, speed distribution, compliance, guider count, and metric radii.

2. **Initialize individual pedestrians**
   The simulator creates a population of individual agents rather than a rigid crowd object.

3. **Advance microscopic motion**
   Each step combines goal attraction, pedestrian-pedestrian repulsion, wall handling, optional noise, and optional guider influence.

4. **Update guidance**
   `dbact` estimates crowd center and spread, then places guiders around the active group. `density_dbact` additionally estimates exit pressure and redirects compliant pedestrians toward an alternate exit.

5. **Save replay and metrics**
   Each run writes `metrics.json`, `timeseries.csv`, `trajectories.npz`, and `replay.npz`, so visualizations can be rendered without re-running simulation.

6. **Render visual artifacts**
   Scripts generate PNG figures, GIF animations, dashboards, side-by-side comparisons, and Markdown reports.

---

## Repository Structure

```text
Crowd-Management/
|-- configs/                         # Scenario definitions
|-- src/crowd_management/             # Simulator, controllers, metrics, replay, visualization
|-- scripts/                          # CLI entry points for experiments and rendering
|-- reports/                          # Tracked reports and GitHub-renderable media
|   |-- media/                        # Tracked GIF assets for README display
|   |-- visualization_upgrade_v1/      # Dashboard, heatmaps, final snapshots
|   |-- guidance_baselines_v1/         # Baseline comparison figures and metrics
|   `-- stage4_density_eval_v1/        # Stage 4 aggregate CSV and reports
|-- runs/                             # Local generated runs, ignored by Git
|-- outputs/                          # Quick local outputs, ignored except .gitkeep
|-- tests/                            # Simulation, CLI, visualization, and evaluation tests
|-- environment.yml
|-- pyproject.toml
|-- README.md
|-- README.zh-TW.md
`-- README.ja.md
```

---

## Useful Commands

Run basic baseline and DBACT guidance:

```bash
python scripts/run_baseline.py --config configs/simple_room.yaml --output outputs/baseline
python scripts/run_guided.py --config configs/simple_room.yaml --mode dbact --output outputs/dbact
```

Build a visualization package:

```bash
python scripts/run_visualization_package.py --config configs/simple_room.yaml --modes baseline static random dbact --steps 400 --seed 0 --output runs/visualization_package_v1 --quality high
```

Run full Stage 4 evaluation:

```bash
python scripts/run_stage4_density_eval.py --config configs/two_exit_bottleneck.yaml --modes baseline static dbact nearest_exit balanced_exit_static density_only exit_pressure_only split_flow_only density_dbact --seeds 0 1 2 3 4 5 6 7 8 9 --steps 800 --output runs/stage4_density_eval_v1 --quality high
```

Render a GitHub-friendly GIF:

```bash
python scripts/render_side_by_side.py --runs runs/visualization_package_v1/baseline runs/visualization_package_v1/dbact --labels baseline dbact --output reports/media/baseline_vs_dbact.gif --fps 5
```

Run tests:

```bash
pytest --basetemp=.tmp/pytest-temp -o cache_dir=.tmp/pytest-cache
```

---

## Current Research Direction

The next useful work is validation, not adding unrelated large systems. Priority items are parameter sweeps for compliance, guider influence radius, density weighting, exit-pressure weighting, stronger bottleneck geometries, and clearer separation between route-choice effects and guider-placement effects.

---

## Contributing & License

Contributions are welcome through Issues and Pull Requests. New scenarios, stronger visualizations, more metrics, and better validation experiments are especially useful.

This project is released under the [MIT License](LICENSE).
