# Stage 4 Density-aware DBACT Evaluation Report

## 1. Purpose

Stage 4 turns the Stage 3 visible split-flow demo into a robust multi-seed evaluation with fair exit-choice baselines, ablations, a composite score, and mechanism visualization.

## 2. Background

Stage 2 videos looked similar in a simple one-exit room. Stage 3 introduced `two_exit_bottleneck` and `density_dbact`, producing visible split-flow. Stage 4 checks whether that result is robust across seeds and whether it beats simple fair baselines.

## 3. Scenario

Primary scenario: `configs/two_exit_bottleneck.yaml`.

Seeds: `[0, 1, 2, 3, 4, 5, 6, 7, 8, 9]`. Compared modes: `['baseline', 'static', 'dbact', 'nearest_exit', 'balanced_exit_static', 'density_only', 'exit_pressure_only', 'split_flow_only', 'density_dbact']`.

## 4. Compared Methods

Methods include baseline/static/original DBACT, fair exit-choice baselines (`nearest_exit`, `balanced_exit_static`), ablations (`density_only`, `exit_pressure_only`, `split_flow_only`), and full `density_dbact`.

## 5. Metrics

Metrics include final evacuation rate, evacuation count, mean speed, congestion index, cumulative congestion, near-collision peak, exit usage ratios, exit imbalance, exit pressure, and composite score.

## 6. Multi-seed Results

| mode | final_evacuation_rate_mean | congestion_index_mean | cumulative_congestion_mean | exit_1_usage_ratio_mean | exit_imbalance_mean | composite_score_mean |
| --- | --- | --- | --- | --- | --- | --- |
| baseline | 0.9994 | 2.2056 | 85.4368 | 0.0000 | 1.0000 | 0.3592 |
| static | 0.9994 | 2.2033 | 84.5823 | 0.0000 | 1.0000 | 0.3635 |
| dbact | 1.0000 | 2.4961 | 92.3552 | 0.0000 | 1.0000 | 0.2819 |
| nearest_exit | 1.0000 | 1.8076 | 68.0892 | 0.1559 | 0.6881 | 0.5650 |
| balanced_exit_static | 0.9997 | 1.4810 | 53.2548 | 0.5002 | 0.0222 | 0.8177 |
| density_only | 0.9997 | 1.1949 | 41.6274 | 0.4889 | 0.0266 | 0.9156 |
| exit_pressure_only | 0.9722 | 1.5553 | 62.2892 | 0.6686 | 0.3372 | 0.6741 |
| split_flow_only | 0.9997 | 1.4810 | 53.2548 | 0.5002 | 0.0222 | 0.8177 |
| density_dbact | 0.9928 | 1.5474 | 61.9751 | 0.6912 | 0.3824 | 0.6883 |

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
| density_only | 0.9156 | 1.1949 | 0.4889 |
| balanced_exit_static | 0.8177 | 1.4810 | 0.5002 |
| split_flow_only | 0.8177 | 1.4810 | 0.5002 |

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
