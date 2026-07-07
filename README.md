<div align="center">

# Crowd Management

Adaptive guide-agent deployment around unknown crowds, with legacy evacuation-guidance experiments preserved for comparison.

Scientific Research Funding: Basic Research (A) ‘Development of Methods for Controlling Traffic Congestion and Crowding and Changing Behaviour Using an Extended Exclusion Queueing Model’ (Research Collaborator)

https://kaken.nii.ac.jp/grant/KAKENHI-PROJECT-26H02177/

[English](README.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md)

![License](https://img.shields.io/badge/License-MIT-green.svg)
![Python](https://img.shields.io/badge/Python-3.12%2B-blue.svg)
![Tests](https://img.shields.io/badge/Tests-23%20passed-brightgreen.svg)
![Version](https://img.shields.io/badge/Version-0.1.0-informational.svg)
![Visualization](https://img.shields.io/badge/Visualization-Matplotlib-orange.svg)

</div>

Crowd Management is a research simulator for studying adaptive guide-agent deployment around unknown crowds. The current main line is not to prove that a DBACT-style evacuation controller is superior. The refocused problem is more basic and more defensible: given an unknown crowd represented as a point cloud, estimate its boundary and deploy multiple guide agents around that boundary at a desired safety distance.

The new method family is **ABCG: Adaptive Boundary-Coverage Guidance**. It is grounded in the core literature on coverage control, centroidal Voronoi tessellations, shepherding, navigation fields, social-force crowd modeling, and collision-avoidance/safety control. Previous DBACT and density-aware evacuation work remains in the repository as a reproducible feasibility sprint and legacy baseline.

> This repository is a research prototype, not a calibrated real-world crowd-management product or safety-certified deployment system.

---

## Legacy Archive

The previous evacuation-guidance direction has been moved into a single archive:

- `legacy/evacuation_guidance/configs/`: old evacuation scenario files.
- `legacy/evacuation_guidance/reports/`: old Stage 1-4 reports, figures, CSV files, and GIF media.
- `legacy/evacuation_guidance/scripts/`: original old CLI implementations.
- `src/crowd_management/legacy/evacuation/`: old simulator, DBACT-style controller, density-DBACT controller, metrics, replay, and visualization code.

Root-level legacy scripts such as `scripts/run_guided.py` remain as compatibility wrappers, but new work should start from `scripts/run_static_containment.py`.

---

## Current Research Direction

The short-term target is **static unknown crowd containment**:

- Crowd state: one static point cloud, no evacuation, no crowd-guide interaction, no communication limits.
- Estimation: center and radial boundary estimation from observed pedestrian points.
- Deployment: guide agents cover an offset safety boundary using ABCG/CVT-style coverage control.
- Metrics: boundary coverage ratio, maximum boundary gap, radial deployment error, angular uniformity, minimum guide-guide distance, and guide-crowd safety violations.

Longer-term stages reintroduce dynamic crowds, behavior response, route choice, local collision avoidance, and evacuation management. The old DBACT line is not deleted, but it is no longer the main claim.

---

## Project Snapshot

| Item | Details |
| --- | --- |
| Project name | Crowd Management |
| Purpose | Study adaptive guide-agent deployment, beginning with static unknown-crowd containment. |
| Core stack | Python 3.12, NumPy, PyYAML, Matplotlib, imageio-ffmpeg, Pytest |
| Main new scenarios | `static_crowd_circle.yaml`, `static_crowd_ellipse.yaml`, `static_crowd_nonconvex.yaml`, `static_crowd_two_clusters.yaml` |
| Legacy scenarios | `legacy/evacuation_guidance/configs/simple_room.yaml`, `legacy/evacuation_guidance/configs/two_exits.yaml`, `legacy/evacuation_guidance/configs/two_exit_bottleneck.yaml` |
| Output types | CSV metrics, JSON summaries, replay files, PNG charts, GIF animations, Markdown reports |

---

## Features

- **Static containment core**: circle, ellipse, nonconvex, and two-cluster static crowd point-cloud scenarios.
- **Boundary estimation**: radial boundary estimates, safety-boundary offsets, and sample weights for boundary importance.
- **ABCG deployment**: CVT-style boundary coverage for guide-agent placement around unknown crowds.
- **Containment metrics**: coverage ratio, maximum boundary gap, radial error, angular uniformity, separation, and safety violations.
- **Microscopic crowd simulation**: each pedestrian has position, velocity, desired speed, compliance, target exit, and evacuation state.
- **Legacy guidance modes**: baseline, static, random, DBACT-style, nearest-exit, balanced split-flow, density-only, pressure-only, and density-aware DBACT.
- **Reproducible evaluation**: single-run scripts, multi-seed aggregation, Stage 4 fair baselines, ablations, and composite scoring.
- **Visualization-first workflow**: snapshots, heatmaps, dashboards, synchronized comparisons, animations, and report-ready figures.
- **Tested CLI pipeline**: tests cover simulation, density-aware guidance, visualization packaging, multi-seed evaluation, and Stage 4 smoke workflows.

---

## Static Containment Quick Start

Run the new ABCG static containment experiment:

```bash
python scripts/run_static_containment.py --config configs/static_crowd_circle.yaml --output runs/static_containment_circle --methods random static_circle legacy_center_radius abcg
```

Important outputs:

- `runs/static_containment_circle/summary.json`
- `runs/static_containment_circle/summary.csv`
- `runs/static_containment_circle/abcg/metrics.json`
- `runs/static_containment_circle/abcg/containment.png`

Run all tests:

```bash
pytest --basetemp=.tmp/pytest-temp -o cache_dir=.tmp/pytest-cache
```

---

## Legacy Results & Visualizations

### Stage 4 Density-aware DBACT Evaluation

This report is now treated as prior feasibility evidence, not the main method claim. It evaluates 9 modes across 10 seeds in `legacy/evacuation_guidance/configs/two_exit_bottleneck.yaml`.

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
python scripts/run_static_containment.py --config configs/static_crowd_circle.yaml --output runs/static_containment_circle --methods random static_circle legacy_center_radius abcg
```

Important outputs:

- `runs/static_containment_circle/summary.json`
- `runs/static_containment_circle/summary.csv`
- `runs/static_containment_circle/abcg/metrics.json`
- `runs/static_containment_circle/abcg/containment.png`

---

## How It Works

### New Static Containment Line

1. **Generate an unknown crowd point cloud**
   Static generators create circle, ellipse, irregular/nonconvex, and two-cluster crowds.

2. **Estimate the crowd boundary**
   The estimator computes a center, radial boundary samples, and an offset safety boundary.

3. **Deploy guide agents**
   `ABCGController` converts the safety boundary into a weighted coverage-control problem and places guide agents around it.

4. **Evaluate containment**
   The experiment reports coverage, gap, radial error, angular uniformity, separation, and guide-crowd safety violations.

### Legacy Evacuation Line

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
|-- src/crowd_management/
|   |-- crowd/                        # Static unknown-crowd point-cloud generators
|   |-- estimation/                   # Boundary and state estimation
|   |-- controllers/                  # ABCG, CVT, random/static/legacy deployment baselines
|   |-- experiments/                  # Static containment experiment runner
|   |-- containment_metrics.py        # Static containment metrics
|   |-- containment_visualization.py  # Static containment plots
|   |-- crowd_model.py                # Legacy evacuation simulator
|   |-- dbact_transfer.py             # Legacy DBACT-style baseline
|   `-- density_dbact.py              # Legacy density-aware evacuation baseline
|-- scripts/                          # CLI entry points for experiments and rendering
|-- legacy/
|   `-- evacuation_guidance/           # Archived old configs, reports, and CLI implementations
|-- reports/                          # New ABCG reports and committed media
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
python scripts/run_baseline.py --config legacy/evacuation_guidance/configs/simple_room.yaml --output outputs/baseline
python scripts/run_guided.py --config legacy/evacuation_guidance/configs/simple_room.yaml --mode dbact --output outputs/dbact
```

Build a visualization package:

```bash
python scripts/run_visualization_package.py --config legacy/evacuation_guidance/configs/simple_room.yaml --modes baseline static random dbact --steps 400 --seed 0 --output runs/visualization_package_v1 --quality high
```

Run full Stage 4 evaluation:

```bash
python scripts/run_stage4_density_eval.py --config legacy/evacuation_guidance/configs/two_exit_bottleneck.yaml --modes baseline static dbact nearest_exit balanced_exit_static density_only exit_pressure_only split_flow_only density_dbact --seeds 0 1 2 3 4 5 6 7 8 9 --steps 800 --output runs/stage4_density_eval_v1 --quality high
```

Render a GitHub-friendly GIF:

```bash
python scripts/render_side_by_side.py --runs runs/visualization_package_v1/baseline runs/visualization_package_v1/dbact --labels baseline dbact --output legacy/evacuation_guidance/reports/media/baseline_vs_dbact.gif --fps 5
```

Run tests:

```bash
pytest --basetemp=.tmp/pytest-temp -o cache_dir=.tmp/pytest-cache
```

---

## Literature-backed Roadmap

The refactor follows the V2 reading reports:

- Coverage control and CVT provide the main deployment theory for ABCG.
- Shepherding studies motivate multi-guide containment and later collect/drive extensions.
- Social-force, CA/floor-field, and navigation-field papers remain as dynamic-crowd and evacuation extensions.
- RVO/ORCA and safety-control ideas should be added before any future real-time moving-guide claim.
- Crowd disaster and congestion-risk papers motivate pressure, velocity variance, LOS, bottleneck, and failure-mode metrics.

---

## Contributing & License

Contributions are welcome through Issues and Pull Requests. New scenarios, stronger visualizations, more metrics, and better validation experiments are especially useful.

This project is released under the [MIT License](LICENSE).
