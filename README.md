# Crowd-Management Feasibility Sprint

## Project Context

This repository is an early feasibility sprint related to the KAKENHI project [26H02177: 拡張排他待ち行列モデルを用いた渋滞・混雑の制御および行動変容方法の開発](https://kaken.nii.ac.jp/grant/KAKENHI-PROJECT-26H02177/).

It is not an implementation of the full KAKENHI project. In particular, this repository does not currently implement the extended exclusion-queue model described in the main project title.

The immediate purpose is narrower and more practical:

> Build a simple 2D crowd simulator, transfer an existing robot cargo-guidance / DBACT-style algorithm into it, and check whether the idea produces useful crowd-management behavior or at least a solid experimental basis.

The transferred robot-algorithm background is:

```text
Cooperative-Transport-Multi-Agent-System
        -> DBACT: Decentralized Boundary-Aware Cooperative Transportation
        -> Crowd-Management feasibility sprint
```

In other words, this repository asks a first-stage research question:

> Can a multi-agent positioning strategy originally developed for cooperative cargo guidance be reused as guider-based crowd guidance in a simple crowd simulator?

If the answer is no, that is still useful. The goal of this sprint is to gain evidence, understand failure modes, and decide what crowd-management method should be tried next.

## Current Research Decision

Based on the meeting direction, the current conclusion is clear:

- Do not implement an exclusion-queue mechanism at this stage.
- Do not implement a hybrid micro-macro crowd model at this stage.
- Do not keep focusing on the phrase `拡張排他待ち行列モデル` in the project title for the first 1-2 weeks.
- First fix a simple non-hybrid crowd model in simulation.
- Then apply the existing cargo-guidance / DBACT algorithm idea to that model.
- Produce simulation results and visual evidence quickly.

The action item is therefore:

```text
Choose a simple crowd model, implement and test the existing algorithm transfer within 1-2 weeks, and produce understandable simulation results.
```

Professor Ogura's meeting direction is treated here as the sprint rule: fix a simple crowd model first, apply the current algorithm, and see whether it works. Even if it does not work, the result is valuable because it provides experience and a solid basis for the next method.

## Current Sprint Scope

This repository currently focuses on:

```text
simple microscopic agent-based crowd model
+ guider-based crowd guidance
+ DBACT / cargo-guidance transfer feasibility test
+ baseline vs guided comparison
+ static / random / dbact guidance baselines
+ metrics
+ 2D visualization
+ tests
```

Out of scope for the current sprint:

```text
exclusion queue
hybrid micro-macro crowd model
CBF controller
LLM decision support
real robot / hardware experiment
large-scale city simulation
full integration with external crowd simulators
```

## Simulator Model

The current simulator uses a simple microscopic agent-based crowd model with social-force-like interactions.

Each pedestrian has:

- position and velocity;
- desired speed;
- target exit;
- personal radius;
- compliance to guidance;
- evacuated state.

Pedestrian motion is computed from:

- attraction toward the exit;
- pedestrian-pedestrian repulsion;
- wall and room-boundary handling;
- optional mobile-guider influence.

The crowd is treated as an active deformable group, not as a rigid passive cargo.

## DBACT / Cargo-Guidance Transfer

The original cargo-guidance problem positions multiple robots around a passive object. This sprint transfers only the high-level idea, not the hardware stack.

The transferred idea is:

> Multi-agent positioning around a target group may generate a useful guidance field.

The current DBACT-transfer mode:

1. estimates the active crowd center and spread;
2. computes the target direction from the crowd center to the exit;
3. places guiders behind and beside the active crowd;
4. moves guiders dynamically as the crowd changes;
5. lets nearby pedestrians blend their exit-seeking direction with the guider-suggested direction.

Main implementation:

```text
src/crowd_management/dbact_transfer.py
src/crowd_management/crowd_model.py
src/crowd_management/guidance_controller.py
```

## Guidance Baselines

To avoid claiming that improvement comes merely from adding guiders, the simulator compares four modes:

| Mode | Meaning |
|---|---|
| `baseline` | no guidance |
| `static` | fixed guider placement |
| `random` | random moving guiders |
| `dbact` | dynamic DBACT-transfer guider placement |

This comparison is important because the first useful research question is not whether the simulator can run. It is whether the transferred DBACT-style method is better than simpler guider baselines.

Current reports show that DBACT is technically runnable, but it is not yet clearly superior to static guidance in the simple one-exit scenario. That is a useful result: it suggests the next research target should be better guider-pedestrian interaction and better scenarios, not a more complex queue model.

## Visualization Priority

The current project value depends strongly on visualization.

For discussion with professors and for group meetings, the priority is now:

```text
high-quality 2D crowd-management visualization
```

The visual output should make the simulation understandable at a glance:

- top-down 2D room view;
- pedestrians as moving particles;
- guiders shown with a distinct color and marker;
- exit highlighted clearly;
- density heatmap or congestion overlay;
- time, evacuation count, evacuation rate, speed, congestion, and near-collision indicators;
- side-by-side comparison such as baseline vs dbact;
- dashboard figures for presentation.

The most important future visual deliverables are:

1. `baseline_vs_dbact` side-by-side video;
2. `dashboard.png` summary figure;
3. heatmap snapshots showing congestion regions;
4. four-mode comparison view: baseline / static / random / dbact.

The goal is not just to make the code run. The goal is to produce visual evidence that helps decide whether the robot-guidance transfer is promising or whether another crowd-management method should be used.

## Repository Structure

```text
Crowd-Management/
├── configs/
│   ├── simple_room.yaml
│   └── two_exits.yaml
├── src/
│   └── crowd_management/
│       ├── __init__.py
│       ├── types.py
│       ├── crowd_model.py
│       ├── guider_model.py
│       ├── guidance_controller.py
│       ├── dbact_transfer.py
│       ├── metrics.py
│       └── visualization.py
├── scripts/
│   ├── run_baseline.py
│   ├── run_guided.py
│   └── compare_results.py
├── tests/
│   └── test_simulation.py
├── reports/
│   ├── first_demo/
│   └── guidance_baselines_v1/
├── outputs/
│   └── .gitkeep
├── README.md
├── TEST_REPORT.md
├── environment.yml
├── requirements.txt
├── pyproject.toml
├── .gitignore
└── LICENSE
```

## Conda Setup

This project uses Conda. The expected environment name is `C-M`.

Create and install:

```bash
conda create -n C-M python=3.12 -y
conda activate C-M
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

For non-interactive shell use:

```bash
/home/kaixin/miniconda3/bin/conda run -n C-M python -m pip install -U pip
/home/kaixin/miniconda3/bin/conda run -n C-M python -m pip install -e ".[dev]"
```

## Run Simulations

Baseline, no guidance:

```bash
/home/kaixin/miniconda3/bin/conda run -n C-M python scripts/run_baseline.py \
  --config configs/simple_room.yaml \
  --output outputs/baseline
```

DBACT-transfer guidance:

```bash
/home/kaixin/miniconda3/bin/conda run -n C-M python scripts/run_guided.py \
  --config configs/simple_room.yaml \
  --output outputs/dbact \
  --mode dbact
```

Static and random guider baselines:

```bash
/home/kaixin/miniconda3/bin/conda run -n C-M python scripts/run_guided.py \
  --config configs/simple_room.yaml \
  --output outputs/static \
  --mode static

/home/kaixin/miniconda3/bin/conda run -n C-M python scripts/run_guided.py \
  --config configs/simple_room.yaml \
  --output outputs/random \
  --mode random
```

Compare all four methods:

```bash
/home/kaixin/miniconda3/bin/conda run -n C-M python scripts/compare_results.py \
  --runs outputs/baseline outputs/static outputs/random outputs/dbact \
  --labels baseline static random dbact \
  --output outputs/comparison
```

## Outputs

Each simulation run saves:

- `metrics.json`
- `timeseries.csv`
- `trajectories.npz`
- `replay.npz` for offline replay and visualization
- `timeseries.png`
- `final_snapshot.png`
- `density_heatmap.png`
- optional `animation.gif`

Comparison saves:

- `summary.json`
- `comparison.json`
- `metrics_comparison.csv`
- `evacuation_rate_comparison.png`
- `final_metrics_comparison.png`

Generated outputs are ignored by Git except selected report artifacts under `reports/`.

## Visualization

The project now supports high-quality offline 2D crowd-management visualization from saved replay data. Run simulations first so each run directory contains `replay.npz`, `metrics.json`, and `timeseries.csv`.

Single-run animation with density heatmap:

```bash
/home/kaixin/miniconda3/bin/conda run -n C-M python scripts/render_animation.py \
  --run outputs/dbact \
  --output outputs/dbact/dbact_animation.mp4 \
  --fps 15 \
  --heatmap
```

Baseline vs DBACT synchronized comparison:

```bash
/home/kaixin/miniconda3/bin/conda run -n C-M python scripts/render_side_by_side.py \
  --runs outputs/baseline outputs/dbact \
  --labels baseline dbact \
  --output outputs/comparison/baseline_vs_dbact.mp4
```

Four-run dashboard figure:

```bash
/home/kaixin/miniconda3/bin/conda run -n C-M python scripts/render_dashboard.py \
  --runs outputs/baseline outputs/static outputs/random outputs/dbact \
  --labels baseline static random dbact \
  --output outputs/comparison/dashboard.png
```

Selected heatmap snapshots:

```bash
/home/kaixin/miniconda3/bin/conda run -n C-M python scripts/render_heatmap_snapshot.py \
  --run outputs/dbact \
  --times 5 10 15 \
  --output outputs/dbact/heatmap_snapshots.png
```

If `ffmpeg` is unavailable, animation scripts automatically fall back from `.mp4` to `.gif`.

## Reports

Existing report artifacts:

```text
reports/first_demo/FIRST_DEMO_REPORT.md
reports/guidance_baselines_v1/GUIDANCE_BASELINES_REPORT.md
```

These reports should be read as feasibility evidence, not as final algorithm validation.

## Tests

Run tests with Conda:

```bash
/home/kaixin/miniconda3/bin/conda run -n C-M pytest
```

The latest verified result is recorded in:

```text
TEST_REPORT.md
```

## Near-Term Plan

The next stage should focus on visualization, not on adding model complexity.

Recommended next implementation targets:

1. replay data export for every run;
2. high-quality single-run evacuation animation;
3. baseline vs dbact side-by-side video;
4. density heatmap overlay;
5. final dashboard figure for presentation;
6. heatmap snapshots at selected times.

After the visualization is strong enough, the next research step is to improve the guider-pedestrian interaction model and test scenarios where crowd management matters more, such as two-exit or narrow-exit cases.

## Research Interpretation

A positive result would mean that DBACT-style guider placement shows useful transfer potential.

A weak or negative result is also useful. It means the direct cargo-guidance transfer is not enough, and the project should move toward other crowd-management methods or stronger behavior models.

The current sprint is therefore designed to create a reliable simulation and visualization basis before moving to more complex methods.
