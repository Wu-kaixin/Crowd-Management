# Test Report

Environment used in ChatGPT sandbox:

```text
Python: 3.13.x
Test command: PYTHONPATH=src pytest -q
Result: 6 passed in 0.58s
```

Smoke-test commands executed:

```bash
PYTHONPATH=src python scripts/run_baseline.py --config configs/simple_room.yaml --output outputs/baseline
PYTHONPATH=src python scripts/run_guided.py --config configs/simple_room.yaml --output outputs/guided
PYTHONPATH=src python scripts/compare_results.py --baseline outputs/baseline --guided outputs/guided --output outputs/comparison
```

Generated sample metrics:

```text
Baseline:
- final_evacuated: 159 / 160
- final_evacuation_rate: 0.99375
- final_time: 18.00 s
- mean_active_speed_over_time: 0.89116
- peak_congestion_index: 16.65

Guided:
- final_evacuated: 160 / 160
- final_evacuation_rate: 1.0
- full_evacuation_time: 17.85 s
- mean_active_speed_over_time: 0.89527
- peak_congestion_index: 16.65

Comparison:
- delta_final_evacuation_rate: +0.00625
- delta_mean_active_speed_over_time: +0.00411
- delta_peak_congestion_index: 0.0
```

Interpretation:

This is a feasibility baseline, not a final crowd model. The guided run shows a slight improvement under the current simple scenario. The important sprint result is that the project structure, baseline simulation, guided simulation, metrics, visualization, and comparison pipeline all run end-to-end.
