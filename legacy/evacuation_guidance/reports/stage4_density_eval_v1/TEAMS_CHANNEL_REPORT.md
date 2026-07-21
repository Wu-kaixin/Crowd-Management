# Crowd-Management Stage 4 Update

## Summary

Stage 4 upgrades the visible Stage 3 split-flow demo into a multi-seed evaluation with fair baselines, ablation modes, composite scoring, and mechanism visualization.

## Motivation

Stage 3 showed that `density_dbact` can redirect pedestrians to a secondary exit, but it was a single-seed result. Stage 4 asks whether that behavior is robust and whether it is better than simple exit-choice baselines.

## Method

The experiment uses `legacy/evacuation_guidance/configs/two_exit_bottleneck.yaml`, compares baseline/static/DBACT, fair baselines (`nearest_exit`, `balanced_exit_static`), ablations (`density_only`, `exit_pressure_only`, `split_flow_only`), and full `density_dbact`, and aggregates metrics across seeds.

## Key Results

| mode | final_evacuation_rate_mean | congestion_index_mean | cumulative_congestion_mean | exit_1_usage_ratio_mean | exit_imbalance_mean | composite_score_mean |
| --- | --- | --- | --- | --- | --- | --- |
| baseline | 0.0000 | 5.7478 | 2.0117 | 0.0000 | 0.0000 | -0.5241 |
| density_dbact | 0.0000 | 5.7286 | 2.0050 | 0.0000 | 0.0000 | -0.1534 |
| nearest_exit | 0.0000 | 5.7442 | 2.0105 | 0.0000 | 0.0000 | -0.4552 |
| balanced_exit_static | 0.0000 | 5.7433 | 2.0102 | 0.0000 | 0.0000 | -0.4379 |

## Interpretation

The key question is whether `density_dbact` reduces congestion and balances exits beyond what naive split-flow baselines achieve. The composite score is only a heuristic summary; congestion, cumulative congestion, and exit usage should be read directly.

## Limitations

This remains a heuristic simulator with a simplified pedestrian model, simplified exit-choice behavior, and no real-world calibration.

## Next Steps

Run parameter sweeps, test more bottleneck geometries, and prepare a compact presentation deck or paper-style experiment section.
