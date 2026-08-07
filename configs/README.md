# configs/ — INPUT only

Scenario YAML for static containment and CI smoke. Not algorithm code.

| File | Consumed by | Scenario |
|------|-------------|----------|
| `static_crowd_circle.yaml` | `scripts/run_static_containment.py` | circle crowd (primary demo) |
| `static_crowd_ellipse.yaml` | `scripts/run_static_containment.py` | ellipse crowd |
| `static_crowd_nonconvex.yaml` | `scripts/run_static_containment.py` | nonconvex crowd |
| `static_crowd_two_clusters.yaml` | `scripts/run_static_containment.py` | two-cluster crowd |
| `static_crowd_capacity_shortfall.yaml` | `scripts/run_static_containment.py` | capacity-shortfall stress |
| `static_crowd_safety_infeasible.yaml` | `scripts/run_static_containment.py` | safety-infeasible stress |
| `static_crowd_timeout.yaml` | `scripts/run_static_containment.py` | timeout stress |
| `ci_smoke.yaml` | `scripts/run_ci_smoke.py` | CI smoke (short horizon) |

Map: [`docs/CODEMAP.zh.md`](docs/CODEMAP.zh.md)
