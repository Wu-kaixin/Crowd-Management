# Stage 4 Density-aware DBACT Evaluation Report

## 1. Purpose

Stage 4 turns the Stage 3 visible split-flow demo into a robust multi-seed evaluation with fair exit-choice baselines, ablations, a composite score, and mechanism visualization.

## 2. Background

Stage 2 videos looked similar in a simple one-exit room. Stage 3 introduced `two_exit_bottleneck` and `density_dbact`, producing visible split-flow. Stage 4 checks whether that result is robust across seeds and whether it beats simple fair baselines.

## 3. Scenario

Primary scenario: `configs/two_exit_bottleneck.yaml`.

Seeds: `[0, 1]`. Compared modes: `['baseline', 'density_dbact', 'nearest_exit', 'balanced_exit_static']`.

## 4. Compared Methods

Methods include baseline/static/original DBACT, fair exit-choice baselines (`nearest_exit`, `balanced_exit_static`), ablations (`density_only`, `exit_pressure_only`, `split_flow_only`), and full `density_dbact`.

## 5. Metrics

Metrics include final evacuation rate, evacuation count, mean speed, congestion index, cumulative congestion, near-collision peak, exit usage ratios, exit imbalance, exit pressure, and composite score.

## 6. Multi-seed Results

| mode | final_evacuation_rate_mean | congestion_index_mean | cumulative_congestion_mean | exit_1_usage_ratio_mean | exit_imbalance_mean | composite_score_mean |
| --- | --- | --- | --- | --- | --- | --- |
| baseline | 0.0000 | 5.7478 | 2.0117 | 0.0000 | 0.0000 | -0.5241 |
| density_dbact | 0.0000 | 5.7286 | 2.0050 | 0.0000 | 0.0000 | -0.1534 |
| nearest_exit | 0.0000 | 5.7442 | 2.0105 | 0.0000 | 0.0000 | -0.4552 |
| balanced_exit_static | 0.0000 | 5.7433 | 2.0102 | 0.0000 | 0.0000 | -0.4379 |

## 7. Fair Baseline Results

Fair baselines can use the secondary exit, so they test whether density_dbact benefits only from exit-choice permission. Compare `density_dbact` against `nearest_exit` and `balanced_exit_static` in the aggregate table and tradeoff plots.

## 8. Ablation Results

The ablation plot compares `density_only`, `exit_pressure_only`, `split_flow_only`, and full `density_dbact`. If split-flow-only is close to density_dbact, the route-choice mechanism explains most of the benefit; if density_dbact improves congestion/balance further, the guider placement adds value.

## 9. Multi-objective Score

Composite score formula:

`score = final_evacuation_rate - 0.25*normalized_congestion_index - 0.25*normalized_cumulative_congestion - 0.20*exit_imbalance - 0.10*normalized_peak_near_collision_count`

The score is heuristic and for exploratory comparison only.

Top modes by mean score:

| mode | composite_score_mean | congestion_index_mean | exit_1_usage_ratio_mean |
| --- | --- | --- | --- |
| density_dbact | -0.1534 | 5.7286 | 0.0000 |
| balanced_exit_static | -0.4379 | 5.7433 | 0.0000 |
| nearest_exit | -0.4552 | 5.7442 | 0.0000 |

## 10. Mechanism Visualization

Mechanism plots show density field, exit pressure timeline, secondary-exit usage, and split-flow snapshot for `density_dbact`.

## 11. Interpretation

Density-aware DBACT should be interpreted as preliminary evidence in this two-exit bottleneck scenario, not as a universal crowd-management solution.

## 12. Limitations

- Simple microscopic behavior model
- Heuristic guider influence and exit-choice model
- Limited scenario geometry
- No real crowd calibration
- MP4 visualization uses CPU/Matplotlib rather than CUDA acceleration

## 13. Next Steps

Run broader parameter sweeps, calibrate pedestrian behavior, test stronger bottlenecks, and later connect to more realistic route-choice or exclusion-queue models.
