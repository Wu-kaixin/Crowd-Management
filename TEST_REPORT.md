# Test Report

## Environment

- Conda path: `/home/kaixin/miniconda3/bin/conda`
- Environment name: `C-M`
- Python: `3.12.13`
- Platform: Linux

## Commands

Editable install was refreshed with:

```bash
/home/kaixin/miniconda3/bin/conda run -n C-M python -m pip install -U pip
/home/kaixin/miniconda3/bin/conda run -n C-M python -m pip install -e ".[dev]"
```

Pytest command:

```bash
/home/kaixin/miniconda3/bin/conda run -n C-M pytest
```

Smoke-test commands:

```bash
/home/kaixin/miniconda3/bin/conda run -n C-M python scripts/run_baseline.py --config configs/simple_room.yaml --output outputs/baseline
/home/kaixin/miniconda3/bin/conda run -n C-M python scripts/run_guided.py --config configs/simple_room.yaml --output outputs/guided
/home/kaixin/miniconda3/bin/conda run -n C-M python scripts/compare_results.py --baseline outputs/baseline --guided outputs/guided --output outputs/comparison
```

## Result

Pytest result:

```text
6 passed in 0.86s
```

Smoke output checks passed for:

- `outputs/baseline/metrics.json`
- `outputs/guided/metrics.json`
- `outputs/comparison/summary.json`
- `outputs/comparison/evacuation_rate_comparison.png`

Generated sample metrics from this run:

```text
Baseline:
- final_evacuated: 149 / 160
- final_evacuation_rate: 0.93125
- final_time: 20.00 s
- mean_active_speed_over_time: 1.05445
- peak_congestion_index: 7.4625
- mean_path_length: 16.68246

Guided:
- final_evacuated: 150 / 160
- final_evacuation_rate: 0.93750
- final_time: 20.00 s
- mean_active_speed_over_time: 1.05781
- peak_congestion_index: 7.4625
- mean_path_length: 16.72593

Comparison:
- delta_final_evacuation_rate: +0.00625
- delta_mean_active_speed_over_time: +0.00336
- delta_peak_congestion_index: 0.0
```

## Notes

This is the first feasibility sprint for transferring DBACT / cargo-guidance ideas to a simple crowd-management simulator.

- No exclusion queue at this stage.
- No hybrid micro-macro model at this stage.
- No CBF or LLM decision support at this stage.
- No real-robot or hardware experiment at this stage.
