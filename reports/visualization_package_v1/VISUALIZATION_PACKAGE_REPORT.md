# Visualization Package Report

## 1. Purpose

This stage turns the current Crowd-Management feasibility sprint into a clear visualization and presentation package. It is not final proof that DBACT-transfer is better than all baselines; it builds a clean experimental demonstration framework for discussion.

## 2. Compared Modes

- `baseline`: no guider
- `static`: fixed guider placement
- `random`: random guider motion
- `dbact`: DBACT-transfer dynamic guider placement

## 3. Scenario

- Config: `configs\simple_room.yaml`
- Scenario: simple one-exit evacuation room
- Steps: `400`
- Seed: `0`

This scenario is useful for first visualization, but it is not sufficient to prove advanced crowd-guidance superiority.

## 4. Generated Outputs

- `comparison/four_modes_dashboard.png`
- `comparison/evacuation_curve.png`
- `comparison/congestion_curve.png`
- `comparison/mean_speed_curve.png`
- `comparison/final_metrics_bar.png`
- `summary/metrics_summary.csv`
- `summary/metrics_summary.json`
- `comparison/heatmap_snapshots.png`
- `comparison\baseline_vs_dbact.mp4`
- `comparison\four_modes_comparison.mp4`

## 5. Result Summary

| Mode | Final evacuation rate | Final evacuated count | Mean speed | Congestion index | Peak near collisions | Final time |
|---|---:|---:|---:|---:|---:|---:|
| baseline | 0.906 | 145 | 1.035 | 1.438 | 198 | 20.00 |
| static | 0.919 | 147 | 1.044 | 1.441 | 198 | 20.00 |
| random | 0.919 | 147 | 1.037 | 1.545 | 198 | 20.00 |
| dbact | 0.925 | 148 | 1.038 | 1.517 | 198 | 20.00 |

## 6. Interpretation

The current pipeline can run stably and produces synchronized videos, dashboards, curves, heatmaps, and metrics summaries. Guidance modes may improve some metrics compared with baseline, but in the simple one-exit scenario DBACT-transfer may not clearly outperform static guidance. This stage is proof-of-execution and visualization quality, not proof-of-method.

## 7. Limitations

- Single seed only
- Simple one-exit room
- Pedestrian behavior model is simple
- Guider influence model is heuristic
- No exit-choice behavior yet
- No bottleneck or two-exit decision scenario yet
- No multi-seed statistical validation in this package

## 8. Next Step

1. Multi-seed evaluation
2. Bottleneck / two-exit scenario
3. Route-choice / exit-choice behavior
4. Density-aware DBACT-transfer v2
5. More realistic guider-pedestrian interaction model
