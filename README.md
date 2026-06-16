# Crowd-Management Sprint

## Purpose

This repository is a simple crowd-management feasibility simulator. The current goal is to test whether an existing DBACT / cargo-guidance idea can be transferred to guider-based crowd management in a simple simulator.

Project background:

```text
Cooperative-Transport-Multi-Agent-System
        -> DBACT: Decentralized Boundary-Aware Cooperative Transportation
        -> Crowd-Management
```

This project is a crowd-management feasibility sprint derived from prior DBACT cargo-guidance work.

## Current Sprint Scope

The sprint target is:

```text
simple microscopic agent-based crowd model
+ guider-based crowd guidance
+ DBACT / cargo-guidance transfer feasibility test
+ baseline vs guided comparison
+ metrics
+ visualization
+ tests
```

No exclusion-queue mechanism at this stage.
No hybrid micro-macro model at this stage.
No CBF or LLM decision support at this stage.
No real-robot or hardware experiment is implemented in this sprint.

## Model

The first sprint uses a simple microscopic agent-based crowd model with social-force-like interactions.

Each pedestrian has:

- position and velocity;
- desired speed;
- target exit;
- personal radius;
- compliance to guidance.

Pedestrian motion is computed from:

- attraction toward the exit;
- pedestrian-pedestrian repulsion;
- wall repulsion and room boundary handling;
- optional mobile-guider influence.

## DBACT / Cargo-Guidance Transfer

The original cargo problem positions multiple agents around a passive object. In this sprint, the crowd is treated as an active deformable group, not as a rigid passive cargo.

The transferred idea is multi-agent positioning around a target group to generate a useful guidance field.

The current transfer implementation:

1. estimates the active crowd center and spread;
2. computes the direction from the crowd center to the exit;
3. places guiders behind and beside the active crowd;
4. uses those guiders to locally influence pedestrian desired directions.

The implementation is in:

```text
src/crowd_management/dbact_transfer.py
```

## Project Structure

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

Create and activate the project environment:

```bash
conda create -n C-M python=3.12 -y
conda activate C-M
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

For a non-interactive shell:

```bash
/home/kaixin/miniconda3/bin/conda run -n C-M python -m pip install -U pip
/home/kaixin/miniconda3/bin/conda run -n C-M python -m pip install -e ".[dev]"
```

## Run Simulations

Baseline, no guidance:

```bash
/home/kaixin/miniconda3/bin/conda run -n C-M python scripts/run_baseline.py --config configs/simple_room.yaml --output outputs/baseline
```

Guided case with transferred DBACT-style controller:

```bash
/home/kaixin/miniconda3/bin/conda run -n C-M python scripts/run_guided.py --config configs/simple_room.yaml --output outputs/guided --mode dbact
```

Compare first-demo baseline vs guided results:

```bash
/home/kaixin/miniconda3/bin/conda run -n C-M python scripts/compare_results.py --baseline outputs/baseline --guided outputs/guided --output outputs/comparison
```

## Guidance Modes

The guided runner supports three guider baselines:

- `static`: fixed guider placement, used to test whether stationary guidance points are already sufficient.
- `random`: random moving guiders, used to test whether moving guiders alone produce an advantage.
- `dbact`: dynamic DBACT-transfer placement around the active crowd, used as the main transferred method.

Run the four-method comparison:

```bash
/home/kaixin/miniconda3/bin/conda run -n C-M python scripts/run_baseline.py --config configs/simple_room.yaml --output outputs/baseline
/home/kaixin/miniconda3/bin/conda run -n C-M python scripts/run_guided.py --config configs/simple_room.yaml --output outputs/static --mode static
/home/kaixin/miniconda3/bin/conda run -n C-M python scripts/run_guided.py --config configs/simple_room.yaml --output outputs/random --mode random
/home/kaixin/miniconda3/bin/conda run -n C-M python scripts/run_guided.py --config configs/simple_room.yaml --output outputs/dbact --mode dbact
/home/kaixin/miniconda3/bin/conda run -n C-M python scripts/compare_results.py --runs outputs/baseline outputs/static outputs/random outputs/dbact --labels baseline static random dbact --output outputs/comparison
```

To save GIF animations, add `--animation` to `scripts/run_guided.py` or `scripts/run_baseline.py`. Animation is optional and is not required by tests.

## Outputs

Each run saves:

- `metrics.json`
- `timeseries.csv`
- `trajectories.npz`
- `timeseries.png`
- `final_snapshot.png`
- `density_heatmap.png`
- optional `animation.gif`

Comparison saves:

- `summary.json`
- `comparison.json`
- `metrics_comparison.csv` for multi-run comparisons
- `evacuation_rate_comparison.png`
- `final_metrics_comparison.png` for multi-run comparisons

The repository keeps only `outputs/.gitkeep`; generated run outputs are ignored.

## Tests

```bash
/home/kaixin/miniconda3/bin/conda run -n C-M pytest
```

Expected result for the current sprint implementation is shown in `TEST_REPORT.md` and should pass before committing changes.

## Next Steps

Near-term work should stay focused on the feasibility sprint:

1. run more baseline vs guided scenarios;
2. tune guider placement and influence parameters;
3. improve metrics for congestion and path efficiency;
4. document where the cargo-guidance transfer works and where it fails.

Exclusion queues, hybrid micro-macro modeling, CBF safety constraints, LLM decision support, and real-robot experiments are out of scope for this stage.
