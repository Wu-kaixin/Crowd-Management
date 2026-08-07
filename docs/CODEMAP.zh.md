# 代码地图（CODEMAP）

一眼分清：**核心算法**、**实验编排**、**输入配置**、**运行输出**、**冻结证据**、**文档/测试**。

权威研究契约见 [`RESEARCH_SPEC.md`](RESEARCH_SPEC.md)。日常从哪里开工见根目录 [`AGENTS.md`](../AGENTS.md)。

---

## 0. 五秒心智模型

```text
configs/*.yaml          ──输入──►  scripts/*.py（薄 CLI）
                                       │
                                       ▼
                              experiments / evaluation（编排）
                                       │
                    ┌──────────────────┼──────────────────┐
                    ▼                  ▼                  ▼
              crowd/            estimation/         controllers/
           （生成点云）        （估边界）          （ABCG 核心数学）
                    │                  │                  │
                    └──────────────────┼──────────────────┘
                                       ▼
                              runs/ 或 reports/     ──输出──
                         （npz/json/png，多数不入库）
```

| 角色 | 目录 / 文件 | 你改它意味着什么 |
| --- | --- | --- |
| **核心算法** | `src/.../controllers/`, `estimation/`, `geometry/`, `crowd/` | 改科学结果；需重新跑评测 |
| **编排胶水** | `experiments/`, `evaluation/`, `runtime/`, `reporting/` | 改流程/并行/落盘，通常不改公式 |
| **入口 CLI** | `scripts/` | 只解析参数，逻辑在包内 |
| **输入** | `configs/*.yaml` | 场景与超参 |
| **本地输出** | `runs/`, `outputs/`, `.tmp/` | gitignore，可删可重跑 |
| **冻结证据** | `reports/`（部分入库） | 论文/README 用的固定结果与图 |
| **暂存 / 测临时** | `_stash/`（gitignore） | 证据备份 + pytest 工作目录（`.tmp` 被锁时用 `_stash/pytest_work`） |
| **勿碰（本分支）** | `src/.../legacy/` | 源码在 `local-main-backup`；本分支勿复活 |

---

## 1. 顶层目录

```text
Crowd-Management/
├── configs/          【输入】场景 YAML（circle / ellipse / 失败用例 / CI smoke）
├── scripts/          【入口】薄 CLI，几乎不含算法
├── src/crowd_management/   【包】核心 + 编排
├── tests/            【测试】step1 / regression / smoke / runtime
├── docs/             【文档】本文件、RESEARCH_SPEC、架构与性能笔记
├── reports/          【证据/媒体】G6/PR6 报告、README 图（部分入库）
├── runs/             【输出·本地】正式实验原始产物（gitignore）
├── artifacts/        【输出·本地】CI/性能临时产物
├── outputs/          【输出·本地】通用落盘占位（gitignore）
├── .tmp/             【输出·本地】pytest 临时目录
├── AGENTS.md         给 Agent / 新人的开工说明
├── pyproject.toml    包元数据与依赖
└── environment.yml   Conda 环境
```

---

## 2. 核心包 `src/crowd_management/`（按数据流）

静态围堵一次完整流水线（`run_static_containment`）：

```text
crowd 生成点云
  → estimation 估边界（boundary_v2）
  → resources 算要几个 guide
  → periodic_arc_cvt 在安全偏移曲线上布点
  → assignment 身份保持分配
  → abcg_v2 + safety 闭环速度控制
  → containment_metrics 算指标
  → artifacts 写入 runs/<run>/...
```

### 2.1 【核心】算法与几何

| 路径 | 职责 | 关键文件 |
| --- | --- | --- |
| `crowd/` | 静态人群点云生成 + 独立解析真值 | `static_crowd.py`, `truth.py` |
| `estimation/` | 边界估计 | `boundary.py`（v1 径向）, `boundary_v2.py`（PR6 alpha+bootstrap） |
| `geometry/` | 闭曲线弧长、重采样、自交等 | `arclength.py` |
| `controllers/` | **ABCG 数学核心**（优先读这里） | 见下表 |
| `containment_metrics.py` | 覆盖率等指标 | — |
| `containment_visualization.py` | 画 `containment.png` | — |
| `types.py` | 共享类型 | — |

#### `controllers/` 子模块（核心中的核心）

| 文件 | 角色 |
| --- | --- |
| `abcg_v2.py` | **主控制器**：固定目标闭环、`step` / episode |
| `abcg.py` | v1 端点基线（给 episode 初值） |
| `periodic_arc_cvt.py` | 等弧 / 周期 Lloyd 覆盖规划 |
| `resources.py` | `ceil(L/g_req)`、迟滞、容量不足状态 |
| `assignment.py` | Hungarian + switch penalty |
| `safety.py` | 采样数据半空间速度投影 |
| `static_circle.py` / `random_deployment.py` / `legacy_center_radius.py` / `coverage_cvt.py` | 对照基线 |

### 2.2 【编排】实验与评测（不是公式）

| 路径 | 职责 |
| --- | --- |
| `experiments/static_containment/` | 单次静态围堵：读 YAML → 跑方法 → 写 artifacts |
| `evaluation/step1_g6/` | 正式 G6 配对评测编排 |
| `evaluation/step1_pr6/` | PR6 边界/置信诊断评测 |
| `evaluation/shared/` | 评测共用：置信区间、曲线指标、统计 |
| `evaluation/schemas.py` + `schema_validation.py` | 结果 schema |
| `runtime/` | 硬件感知 worker、BLAS 线程、并行执行器 |
| `reporting/` | JSON/CSV 写出、git/环境快照 |

`experiments/static_containment/` 拆分：

| 文件 | 角色 |
| --- | --- |
| `config.py` | YAML → `StaticContainmentConfig` |
| `methods.py` | 方法名 → 基线目标点 |
| `runner.py` | 主流程 `run_static_containment` |
| `artifacts.py` | 落盘：boundary / plan / assignment / episode / manifest |

### 2.3 【遗留】

`legacy/`：本分支无活跃 `.py`（可能仅有 `__pycache__`）。旧疏散/DBAct 在分支 `local-main-backup`。

---

## 3. 【输入】`configs/`

| 文件 | 用途 |
| --- | --- |
| `static_crowd_circle.yaml` 等 | 日常演示场景（圆/椭圆/非凸/双团） |
| `static_crowd_capacity_shortfall.yaml` | 资源不足失败路径 |
| `static_crowd_safety_infeasible.yaml` | 安全投影不可行 |
| `static_crowd_timeout.yaml` | 未收敛/超时路径 |
| `ci_smoke.yaml` | CI 极小确定性 workload |

YAML 里常见块：`crowd`（输入点云形状）、`guiders`、`containment`、`boundary`、`resources`、`assignment`、`motion`、`safety`。这些是**超参输入**，不是算法本体。

---

## 4. 【入口】`scripts/`（薄 CLI）

| 脚本 | 调用的包 | 典型输出目录 |
| --- | --- | --- |
| `run_static_containment.py` | `experiments.static_containment` | `runs/static_containment_*` |
| `run_step1_g6_compliance.py` | `evaluation.step1_g6` | `reports/step1_g6_compliance` + `runs/...` |
| `run_step1_pr6_evaluation.py` | `evaluation.step1_pr6` | `reports/step1_pr6_evaluation` |
| `run_ci_smoke.py` | smoke 路径 | `artifacts/ci_smoke` |
| `build_readme_media.py` | 可视化 | `reports/media/` |
| `check_readme_consistency.py` | README `TEST_COUNT` 门禁 | — |
| `compare_results.py` / `profile_step1.py` / `benchmark_baseline.py` | 性能/对比工具 | — |

新人默认只记一条：

```bash
python scripts/run_static_containment.py \
  --config configs/static_crowd_circle.yaml \
  --output runs/static_containment_circle \
  --methods random static_circle legacy_center_radius abcg
```

---

## 5. 【输出】一次静态围堵 run 目录长什么样

`--output runs/foo` 之后大致为：

```text
runs/foo/
├── config_resolved.yaml      # 本次实际配置快照
├── crowd_points.npz          # 输入点云（生成结果）
├── crowd_truth.npz           # 独立真值边界（评测用，控制器看不到）
├── boundary_v2.npz + *_status.json
├── resource_decision.json
├── periodic_plan.npz + *_status.json
├── manifest.json             # 整次 run 状态机摘要（是否收敛/失败原因）
├── summary.json / summary.csv
└── <method>/                 # random | static_circle | ... | abcg
    ├── containment_state.npz
    ├── metrics.json
    ├── assignment.npz + assignment_status.json
    ├── episode.npz + episode_status.json
    └── containment.png
```

**读结果优先看**：`summary.json`（各方法指标）→ `manifest.json`（整 run 成败）→ 某方法下的 `metrics.json` / 图。

### `runs/` vs `reports/` vs `artifacts/` vs `outputs/`

| 目录 | 性质 | 是否入库 |
| --- | --- | --- |
| `runs/` | 原始实验落盘 | 否（gitignore） |
| `reports/` | 整理后的报告、媒体、冻结评测摘要 | 部分是（大 json/csv 常 ignore） |
| `artifacts/` | CI/性能临时 | 通常否 |
| `outputs/` | 通用输出占位 | 否 |

---

## 6. 【测试与文档】

| 路径 | 角色 |
| --- | --- |
| `tests/step1/` | ABCG 各 PR 单元/合规 |
| `tests/regression/` | 科学等价（如 worker 数不影响结果） |
| `tests/smoke/` | 确定性小跑 |
| `tests/runtime/` | 并行与线程限制 |
| `docs/RESEARCH_SPEC.md` | 研究范围与声称纪律 |
| `docs/architecture/` | 重构基线/计划/结果 |
| `docs/performance/` | 性能报告（非正式科学证据） |

---

## 7. 改代码时该碰哪里？

| 你想… | 去这里 |
| --- | --- |
| 改边界估计公式 | `estimation/boundary_v2.py` |
| 改闭环控制 / 安全投影 | `controllers/abcg_v2.py`, `safety.py` |
| 改覆盖规划 / 资源 / 分配 | `periodic_arc_cvt.py`, `resources.py`, `assignment.py` |
| 加新场景参数 | `configs/*.yaml` + `experiments/.../config.py` |
| 改落盘文件名或字段 | `experiments/.../artifacts.py` |
| 改 G6/PR6 评测协议 | `evaluation/step1_g6/` 或 `step1_pr6/` |
| 只换怎么从命令行启动 | `scripts/` |

**不要**把算法塞进 `scripts/`；**不要**把报告图当输入配置；**不要**在 `main` 上复活 `legacy` 疏散线。
