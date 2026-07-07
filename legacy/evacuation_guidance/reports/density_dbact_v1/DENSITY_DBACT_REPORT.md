# Density-Aware DBACT Guidance Report

## 1. Purpose

Stage 2 videos looked similar because `simple_room.yaml` gave every pedestrian the same obvious exit. Stage 3 introduces a stronger two-exit bottleneck scenario and a density-aware guidance mode so that route choice and congestion management become visible.

## 2. Scenario

Config: `configs\two_exit_bottleneck.yaml`. The room has a narrow main exit and an upper alternate exit. Baseline, static, and original DBACT primarily target the main exit; `density_dbact` can redirect part of the crowd toward the alternate exit.

## 3. Compared Modes

- `baseline`: no guider or default main-exit behavior
- `static`: fixed guiders
- `dbact`: original DBACT-transfer dynamic guider placement
- `density_dbact`: density-aware DBACT-transfer v2

## 4. Method

The density-aware controller estimates exit pressure from nearby active pedestrians, assigns the less pressured exit as a guidance target, arranges guiders along a visible diagonal guide line, and switches compliant pedestrians in the upper/high-pressure portion of the crowd toward the alternate exit.

## 5. Metrics

Metrics include final evacuation rate, final evacuated count, mean speed, congestion index, peak near-collision count, exit usage counts/ratios, exit imbalance, cumulative congestion, and final time.

## 6. Results

| Mode | Final rate | Evacuated | Mean speed | Congestion | Alt-exit count | Exit imbalance |
|---|---:|---:|---:|---:|---:|---:|
| baseline | 0.997 | 319 | 0.721 | 2.141 | 0 | 1.000 |
| static | 0.997 | 319 | 0.715 | 2.117 | 0 | 1.000 |
| dbact | 1.000 | 320 | 0.737 | 2.381 | 0 | 1.000 |
| density_dbact | 0.988 | 316 | 0.822 | 1.580 | 216 | 0.367 |

Generated outputs:

- `comparison/exit_usage_curve.png`
- `comparison/exit_pressure_curve.png`
- `comparison/congestion_curve.png`
- `comparison/evacuation_curve.png`
- `comparison/final_metrics_bar.png`
- `comparison/heatmap_snapshots.png`
- `comparison/four_modes_dashboard.png`
- `summary/metrics_summary.csv`
- `summary/metrics_summary.json`
- `comparison\baseline_vs_density_dbact.mp4`
- `comparison\dbact_vs_density_dbact.mp4`
- `comparison\four_or_five_modes_comparison.mp4`

## 7. Interpretation

If `density_dbact` shows higher alternate-exit usage and a visible split-flow pattern, this is preliminary evidence that density-aware guidance creates more meaningful behavior than geometric DBACT alone. The result is still not final validation.

## 8. Limitations

- Heuristic model
- Single seed unless multi-seed is run later
- Simple microscopic crowd behavior
- Simplified exit-choice model
- No real human data validation yet

## 9. Next Step

- Multi-seed evaluation on `two_exit_bottleneck`
- Parameter sweep for influence radius, compliance, and exit pressure weight
- More realistic bottleneck geometry
- Later connection to exclusion queue or behavior-change models
