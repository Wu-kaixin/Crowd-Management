# Stage 4 Key Findings

- Stage 4 evaluated `4` modes across `2` seeds.
- Fair baselines were included so secondary-exit access is not exclusive to `density_dbact`.
- Composite score is heuristic and should be read together with congestion and exit-balance metrics.

## Aggregate Snapshot

| mode | final_evacuation_rate_mean | congestion_index_mean | cumulative_congestion_mean | exit_1_usage_ratio_mean | exit_imbalance_mean | composite_score_mean |
| --- | --- | --- | --- | --- | --- | --- |
| baseline | 0.0000 | 5.7478 | 2.0117 | 0.0000 | 0.0000 | -0.5241 |
| density_dbact | 0.0000 | 5.7286 | 2.0050 | 0.0000 | 0.0000 | -0.1534 |
| nearest_exit | 0.0000 | 5.7442 | 2.0105 | 0.0000 | 0.0000 | -0.4552 |
| balanced_exit_static | 0.0000 | 5.7433 | 2.0102 | 0.0000 | 0.0000 | -0.4379 |
