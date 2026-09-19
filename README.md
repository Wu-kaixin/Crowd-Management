<div align="center">

# Crowd Management

面向未知人群周围自适应引导智能体部署的研究型仿真器。

![License](https://img.shields.io/badge/License-MIT-green.svg)
![Python](https://img.shields.io/badge/Python-3.12%2B-blue.svg)
![CI](https://github.com/Wu-kaixin/Crowd-Management/actions/workflows/ci.yml/badge.svg)
![Version](https://img.shields.io/badge/Version-0.1.0-informational.svg)
![Visualization](https://img.shields.io/badge/Visualization-Matplotlib-orange.svg)
![Branch](https://img.shields.io/badge/branch-STEP1--Research--Extension-orange.svg)

</div>

本文档描述分支 **`STEP1-Research-Extension`**，不是冻结的 `main` 发布说明。此前的 `main` 尖端保存在 `archive/main-2026-09-19`。

**Step 1：** 已知封闭环境边界 + 一个未知静态人群 + 全局观测 + 无限制引导通信 + 外部引导智能体。

环境边界已知。人群边界未知。

JuPedSim 生成几何只作为仿真器初始化数据与评估器真值，不暴露给 ABCG。控制器只接收观测到的行人位置及允许的属性。

Crowd Management 仍是用于**静态未知人群围堵**（ABCG）的 Python 研究原型。本分支保留 JuPedSim 静态源与源配对证据，并在已知 \(\partial\Omega_{\mathrm{env}}\)（封闭正方形/矩形）周围闭合 Step 1，同时提供实时可视化。JuPedSim **仅用于**放置物理间隔的行人中心；Step 1 **不推进行人动力学**。

> 仅供研究原型使用 — 不是经过标定的安全产品，也不是已认证控制器。
> 下方本地配对证据是探索性的；它**不能替代** `main` @ `f2494922…` 上冻结的 G6 research-complete 声明。

---

## 本分支改动

| 方面 | 本分支状态 |
| --- | --- |
| 人群源 | `crowd.source: synthetic \| jupedsim`（静态点云） |
| JuPedSim 角色 | 在多边形内按间距约束生成中心；评估器专用真值来自中心支撑几何 |
| 基准 | `configs/step1_known_boundary/`（正方形/矩形 × 人群形状 + 压力场景）；配对配置保留 |
| 评估 | `scripts/run_step1_known_boundary.py` + `scripts/analyze_step1_known_boundary.py`；配对脚本保留 |
| 可视化 | 默认实时 matplotlib 窗口；CI 用 `--headless` |
| `main` 上冻结的 G6 / PR6 | 仍是 Step-1 research-complete 基线；**此处不重跑 / 不重新冻结** |

入口：

```bash
# 单次已知边界实验（默认实时窗口）
python scripts/run_static_containment.py \
  --config configs/step1_known_boundary/square_irregular.yaml \
  --output runs/step1_square_irregular_seed0 \
  --methods abcg

# 无界面 CI / 无人值守
python scripts/run_static_containment.py \
  --config configs/step1_known_boundary/square_circle.yaml \
  --output runs/step1_square_circle_headless \
  --methods abcg \
  --headless

# JuPedSim 静态 smoke
python scripts/jupedsim_static_smoke.py

# 成对源评估（synthetic vs JuPedSim）
python scripts/run_step1_source_pairing.py \
  --output reports/step1_source_pairing

python scripts/analyze_step1_source_pairing.py \
  --records reports/step1_source_pairing/records.csv \
  --output reports/step1_source_pairing
```

---

## 本地成对结果（本工作树）

冻结的本地证据位于 [`reports/step1_source_pairing/`](reports/step1_source_pairing/)：

- 矩阵：**3 种形状 × 2 个源 × 20 个种子 = 120** 次 ABCG 运行
- 形状：`circle`、`ellipse`、`irregular`
- 源：`synthetic` vs `jupedsim`（名义上匹配几何 / 数量 / 房间 / 控制器；**不是**相同的点过程分布）
- 失败策略：无效 / 超时 / 跳过阶段**仍计入分母**
- 流水线启动成功：**120/120**（`run_success=True`）— 每个案例都产生了产物
- 闭环回合结果**并非**全部成功（见下）

### 回合与边界结果

| 源 | `BOUNDARY_INVALID` | `VALID` 边界 | `CONVERGED` | `TIMEOUT` |
| --- | ---: | ---: | ---: | ---: |
| synthetic (n=60) | 39 | 21 | 11 | 10 |
| jupedsim (n=60) | 23 | 37 | 32 | 5 |
| **全部 (n=120)** | **62** | **58** | **43** | **15** |

按形状 / 源（边界有效性）：

| 配对 | synthetic VALID | jupedsim VALID |
| --- | ---: | ---: |
| circle | 7/20 | 16/20 |
| ellipse | 7/20 | 13/20 |
| irregular | 7/20 | 8/20 |

一句话解读：在这些基准配置下，JuPedSim 静态放置比匹配的合成生成器有**更高的 alpha 边界接受率**，以及更多 `CONVERGED` 回合 — 但不规则几何对两种源都仍然困难，许多“成功启动”仍以 `BOUNDARY_INVALID` 或 `TIMEOUT` 结束。

### `BOUNDARY_INVALID` — 实际失败原因

在 **62** 个无效边界中（来自 `boundary_v2_status.json` 诊断）：

| 原因 | 次数 | 含义 |
| --- | ---: | --- |
| `alpha_insufficient_observation_coverage` | 61 | 已有 alpha-shape 候选，但观测覆盖仍低于接受门限（`min_observation_coverage=0.8`，半径搜索时选用阈值略高） |
| `multiple_significant_components` | 1 | 观测连通性分裂为多个显著分量（超出单分量 Step 1 范围） |

边界无效时，运行器**不会编造边界**：周期规划被跳过（`PLAN_SKIPPED_BOUNDARY_INVALID` / 资源 `RESOURCE_SKIPPED_BOUNDARY_INVALID`），回合状态保持 `BOUNDARY_INVALID`。这是有意的研究记账，不是静默修补。

诊断示例（irregular / synthetic / seed 0）：原始候选上 `observation_coverage_ratio=0.90`，但**重采样 / 接受**路径仍未过门限 → 状态 `BOUNDARY_INVALID`，原因为 `alpha_insufficient_observation_coverage`。

### 指标差值（成对，两侧都有数值时）

来自 [`analysis.json`](reports/step1_source_pairing/analysis.json)（JuPedSim − synthetic）：

- **circle 覆盖率**：均值 Δ ≈ −0.028（95% bootstrap CI ≈ [−0.048, −0.008]）；两侧都跑通时 JuPedSim 覆盖率略低。
- **circle 角度均匀性误差**：均值 Δ ≈ +0.117（CI ≈ [0.056, 0.175]）；JuPedSim 平均均匀性更差。
- **circle / ellipse 活跃引导数**：JuPedSim 往往激活**更多**引导（circle 均值 Δ ≈ +3.7）。
- 本矩阵中两侧安全违反计数均为 **0**；未记录 `safety_infeasible` 步。

这些只是源鲁棒性诊断。它们**不**证明 JuPedSim 动力学、人类遵从或部署安全性。

机器可读表：[`records.csv`](reports/step1_source_pairing/records.csv)、[`aggregate.json`](reports/step1_source_pairing/aggregate.json)、[`paired_deltas.csv`](reports/step1_source_pairing/paired_deltas.csv)。

---

## 可视化总览（继承自 `main`）

可用 `python scripts/build_readme_media.py` 重新生成素材。以下图是 `main` 上冻结的 Step-1 媒体；**不是**由上方 JuPedSim 配对矩阵重新生成。

### 静态围堵示例

![ABCG static containment grid](reports/media/abcg_static_containment_grid.png)

![ABCG containment animation](reports/media/abcg_static_containment.gif)

![ABCG metrics summary](reports/media/abcg_metrics_summary.png)

### 正式 G6 场景

![Step 1 G6 scenarios](reports/media/step1_g6_scenarios.png)

### 基线对比

![Step 1 baseline comparison](reports/media/step1_baseline_comparison.png)

### 闭环跟踪

![Step 1 closed-loop tracking](reports/media/step1_closed_loop.gif)

### 正式 G6 证据

![Step 1 G6 success rates](reports/media/step1_g6_success_rates.png)

![Step 1 failure gallery](reports/media/step1_failure_gallery.png)

文字报告：[G6_COMPLIANCE_REPORT.md](reports/step1_g6_compliance/G6_COMPLIANCE_REPORT.md)。

---

## 数学核验

核心数学恒等式与部分实现性质已在明确假设下，用 Wolfram Language 独立核验。这并不验证人群行为假设、人类遵从、真实世界有效性或部署安全性。

- 审计基准：`main` @ `491759761e44`，Mathematica 15.0.1（本地 Linux 内核；公开 CI 中不执行任何 Wolfram 计算）。
- 74 项 Wolfram `VerificationTest`，74 项通过；73 条编目声明：20 条符号证明，27 条精确核验，6 条在定义域内数值核验，8 条性质测试，另有 12 条明确记录为缺口、文档不一致、不可用 CAS 核验或不适用 — 从未当作已证明。
- 38 组成对重算中，Python 与 Wolfram 的最大相对偏差为 5.6e-16（冻结容差 1e-9）；安全投影 KKT 残差在 50 位认证参考解上 ≤ 3e-17。

![Mathematical verification status by module](reports/media/math_verification/mathematical_verification_summary.png)

完整报告：[docs/math/MATHEMATICAL_VERIFICATION_REPORT.md](docs/math/MATHEMATICAL_VERIFICATION_REPORT.md)。逐条证据：[docs/math/MATHEMATICAL_CLAIM_MATRIX.md](docs/math/MATHEMATICAL_CLAIM_MATRIX.md)。机器可读产物位于 `artifacts/math_verification/`。CI 只复核产物哈希与 SHA 新鲜度（`scripts/check_math_verification_freshness.py`），从不声称重新运行 Mathematica。

---

## 当前研究范围

- **输入：** 静态二维人群点云（本分支上为 `synthetic` 或 `jupedsim` 源）。
- **估计器：** v1 径向 + PR6 alpha-shape，带 bootstrap 置信度与显式无效状态（`BOUNDARY_INVALID` / `OFFSET_INVALID`）。
- **规划器：** 等弧长 / 置信门控周期 Lloyd（PR2）；边界无效时跳过。
- **资源与指派：** `ceil(L/g_req)`、滞回、预备量、带切换惩罚的指派（PR3）。
- **运动与安全：** `u_nom = sat(k_p(z-p))`，配合采样数据半空间投影（PR4/PR5）。
- **基线：** 随机、静态圆、旧版中心-半径、端点 ABCG。
- **评估：** 独立解析真值；`main` 上正式 G6 成对种子；本分支上的源配对；失败仍计入分母。

权威约定：[docs/RESEARCH_SPEC.md](docs/RESEARCH_SPEC.md)。

---

## 快速开始

```bash
conda env update -n abcg -f environment.yml
conda activate abcg
python -m pip install -e ".[dev]"
```

静态围堵（默认合成配置）：

```bash
python scripts/run_static_containment.py \
  --config configs/static_crowd_circle.yaml \
  --output runs/static_containment_circle \
  --methods random static_circle legacy_center_radius abcg
```

JuPedSim 静态配置示例：`configs/jupedsim/static_polygon.yaml` 或 `configs/step1_benchmark/jupedsim_*.yaml`。

测试与依赖检查：

```bash
mkdir -p .tmp
pytest --basetemp=.tmp/pytest-temp -o cache_dir=.tmp/pytest-cache
python -m pip check
```

正式 G6（冻结的 `main` 证据路径）：

```bash
python scripts/run_step1_g6_compliance.py \
  --output reports/step1_g6_compliance \
  --run-root runs/step1_g6_compliance
```

成对 PR6 诊断（边界/置信度；不能替代完整 G6）：

```bash
python scripts/run_step1_pr6_evaluation.py --output reports/step1_pr6_evaluation
```

CI smoke（极小确定性工作负载）：

```bash
python scripts/run_ci_smoke.py --output artifacts/ci_smoke
```

README 一致性门禁：

```bash
python scripts/check_readme_consistency.py
```

---

## 仓库结构

迷路时先看中文角色地图：[docs/CODEMAP.zh.md](docs/CODEMAP.zh.md)（核心 / 输入 / 输出）。

```text
Crowd-Management/
|-- configs/                    # 输入：场景 + step1_benchmark/ + jupedsim/
|-- docs/                       # RESEARCH_SPEC、CODEMAP.zh、架构、性能
|-- src/crowd_management/
|   |-- crowd/                  # 核心：合成 + JuPedSim 静态源 + 真值
|   |-- geometry/               # 核心：弧长 / 有效性
|   |-- estimation/             # 核心：边界估计器（显式 BOUNDARY_INVALID）
|   |-- controllers/            # 核心：ABCG 数学
|   |-- runtime/                # 编排：硬件感知 worker
|   |-- reporting/              # 输出辅助
|   |-- experiments/            # 编排：静态围堵运行器
|   |-- evaluation/             # 编排：G6 / PR6 + schema 校验
|   |-- containment_metrics.py
|   `-- containment_visualization.py
|-- scripts/                    # 入口：薄 CLI（含源配对 / JuPedSim smoke）
|-- runs/                       # 本地输出（gitignore）：原始实验转储
|-- reports/                    # 证据 / 媒体（配对摘要已入库）
|-- artifacts/, outputs/, .tmp/ # 本地临时输出
|-- tests/                      # 单元、回归、smoke
|-- .github/workflows/ci.yml
|-- pyproject.toml              # 本分支包含 jupedsim==1.4.2
`-- README.md
```

---

## 研究封存

历史分支快照索引见 [docs/ARCHIVE_INDEX.md](docs/ARCHIVE_INDEX.md)。

```text
archive/legacy-evacuation-2026-07-21:legacy/evacuation_guidance/
archive/legacy-evacuation-2026-07-21:src/crowd_management/legacy/
archive/g7-proof-strengthening-failed-2026-07-20
```

可用 `git switch archive/legacy-evacuation-2026-07-21`、`git switch archive/g7-proof-strengthening-failed-2026-07-20` 或 `git switch archive/main-2026-09-19` 查看。这些是历史/只读快照。Step 1 新方向的活跃工作在 `STEP1-Research-Extension`。

---

## 开发状态

- 分支：**`STEP1-Research-Extension`**（已知环境边界 + 未知静态人群）
- 方法族：ABCG 静态未知人群围堵
- 冻结的此前 `main`：`archive/main-2026-09-19`（G0–G6 research-complete @ `f2494922…`）；该线不在此重新冻结
- 本地配对快照：120 次运行；**62 次 `BOUNDARY_INVALID`**（多为 `alpha_insufficient_observation_coverage`）；**43 次 `CONVERGED`**；**15 次 `TIMEOUT`**
- 已知边界开发矩阵（本分支）：**2 种环境 × 4 种形状 × 5 个种子 = 40** 次 ABCG 运行；**32 次 `CONVERGED`**，**6 次 `BOUNDARY_INVALID`**，**2 次 `TIMEOUT`**。失败仍计入分母。Holdout 种子 100-119 尚未运行。
- 套件规模（权威；由 `scripts/check_readme_consistency.py` 同步）：
  <!-- TEST_COUNT_START -->
  212
  <!-- TEST_COUNT_END -->
- CI：Linux + Windows，见 [`.github/workflows/ci.yml`](.github/workflows/ci.yml)（单元测试、限定范围的 lint/类型检查、README 一致性、确定性 smoke、schema 回归）
- 正式 G6（继承证据）：600 条主记录 — [G6 报告](reports/step1_g6_compliance/G6_COMPLIANCE_REPORT.md)
- 本地性能说明：[docs/performance/final_report.md](docs/performance/final_report.md)（CI 墙钟时间**不是**正式证据）
- 架构维护说明：[docs/architecture/refactor_result.md](docs/architecture/refactor_result.md)

`main` 上的 research-complete 指在单一静态未知人群周围的仿真引导部署。本分支的 JuPedSim 配对**不**证明人类遵从、真实世界围堵、疏散收益、多人群动态，或连续时间安全证书。显式 `BOUNDARY_INVALID` 仍是结果的一部分，不是需要隐藏的缺陷。

## 许可证

[MIT License](LICENSE)。
