# Crowd-Management Stage 4 Update

## Summary

Stage 4 upgrades the visible Stage 3 split-flow demo into a multi-seed evaluation with fair baselines, ablation modes, composite scoring, and mechanism visualization.

## Motivation

Stage 3 showed that `density_dbact` can redirect pedestrians to a secondary exit, but it was a single-seed result. Stage 4 asks whether that behavior is robust and whether it is better than simple exit-choice baselines.

## Method

The experiment uses `configs/two_exit_bottleneck.yaml`, compares baseline/static/DBACT, fair baselines (`nearest_exit`, `balanced_exit_static`), ablations (`density_only`, `exit_pressure_only`, `split_flow_only`), and full `density_dbact`, and aggregates metrics across seeds.

## Key Results

| mode | final_evacuation_rate_mean | congestion_index_mean | cumulative_congestion_mean | exit_1_usage_ratio_mean | exit_imbalance_mean | composite_score_mean |
| --- | --- | --- | --- | --- | --- | --- |
| baseline | 0.9988 | 2.2051 | 85.4759 | 0.0000 | 1.0000 | 0.3487 |
| static | 0.9988 | 2.2001 | 84.5981 | 0.0000 | 1.0000 | 0.3537 |
| dbact | 1.0000 | 2.4917 | 92.2167 | 0.0000 | 1.0000 | 0.2719 |
| nearest_exit | 1.0000 | 1.7827 | 67.7229 | 0.1575 | 0.6850 | 0.5654 |
| balanced_exit_static | 0.9994 | 1.4516 | 53.4892 | 0.4997 | 0.0256 | 0.8177 |
| density_only | 0.9994 | 1.1975 | 41.3473 | 0.4891 | 0.0231 | 0.9170 |
| exit_pressure_only | 0.9694 | 1.5653 | 62.6891 | 0.6647 | 0.3295 | 0.6647 |
| split_flow_only | 0.9994 | 1.4516 | 53.4892 | 0.4997 | 0.0256 | 0.8177 |
| density_dbact | 0.9925 | 1.5523 | 62.1684 | 0.6883 | 0.3766 | 0.6830 |

## Interpretation

The key question is whether `density_dbact` reduces congestion and balances exits beyond what naive split-flow baselines achieve. The composite score is only a heuristic summary; congestion, cumulative congestion, and exit usage should be read directly.

## Limitations

This remains a heuristic simulator with a simplified pedestrian model, simplified exit-choice behavior, and no real-world calibration.

## Next Steps

Run parameter sweeps, test more bottleneck geometries, and prepare a compact presentation deck or paper-style experiment section.
