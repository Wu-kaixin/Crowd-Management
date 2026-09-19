# configs/ — 仅作输入

静态围堵场景与 CI smoke 的 YAML。此处不是算法代码。

| 文件 | 调用方 | 场景 |
|------|-------------|----------|
| `static_crowd_circle.yaml` | `scripts/run_static_containment.py` | 圆形人群（主演示） |
| `static_crowd_ellipse.yaml` | `scripts/run_static_containment.py` | 椭圆人群 |
| `static_crowd_nonconvex.yaml` | `scripts/run_static_containment.py` | 非凸人群 |
| `static_crowd_two_clusters.yaml` | `scripts/run_static_containment.py` | 双簇人群 |
| `static_crowd_capacity_shortfall.yaml` | `scripts/run_static_containment.py` | 容量不足压力场景 |
| `static_crowd_safety_infeasible.yaml` | `scripts/run_static_containment.py` | 安全不可行压力场景 |
| `static_crowd_timeout.yaml` | `scripts/run_static_containment.py` | 超时压力场景 |
| `ci_smoke.yaml` | `scripts/run_ci_smoke.py` | CI smoke（短时域） |

地图：[`docs/CODEMAP.zh.md`](docs/CODEMAP.zh.md)
