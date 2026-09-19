# Step 1 Core 闭合报告

日期：2026-09-19  
分支：`STEP1-Research-Extension`  
父提交：`8b15f82ad9e19de41920c638efac223c0c720840`  
本报告对应闭合提交（CI 修复 + 范围冻结 + holdout 证据）。  
权威范围：[`docs/RESEARCH_SPEC.md`](../../docs/RESEARCH_SPEC.md)、[`docs/STEP1_RESEARCH_ROADMAP.md`](../../docs/STEP1_RESEARCH_ROADMAP.md)

## 判定

| 项 | 状态 |
| --- | --- |
| 工程闭环（观测 → 估计 → 部署 → 指派 → 速度控制 → 安全 → 评价 → 画面） | **完成** |
| 开发集 40-run | **完成**（32/40 = 80.0%） |
| 独立 holdout 160-run（种子 100–119，未调参） | **已执行**（110/160 = 68.8%） |
| CI 可冻结（pytest / Linux / Windows / static-analysis / schema / smoke） | **本提交修复；推送后须全绿** |
| Step 1 Core 范围与 Extension / Step 2 分离 | **已写入规范** |
| 异质性 | **表示层接口完成；行为效果未验证（属 Step 2）** |
| git tag `step1-known-boundary-freeze` | **暂缓**（见下文） |

**Step 1 工程闭合已完成，独立实验已跑完。不能宣称 “Step 1 has been validated at 80%”。**  
正式独立数字是 holdout **110/160 = 68.8%**。失败全部留在分母。流水线没有崩溃：160 次均写出记录，边界有效 150/160。主要缺口是 **TIMEOUT**，不是软件挂掉。

因此本提交冻结的是 **Core 范围 + 未调参 holdout 证据**，不是 “论文成功率为开发集 80%” 的声明。

## 1. Step 1 Core 冻结范围

只把下面这一条当作论文基线：

- 已知封闭环境 \(\partial\Omega_{\mathrm{env}}\)：square / rectangle
- 未知单一静态人群 \(\partial\Omega_c\)
- 中等 **表示层** 异质性（`radius`、`desired_speed`、`time_gap`、可选 `demand`）
- 全局点云观测、无限制通信
- 速度控制的外部 guide，可行工作空间内随机未知初值

明确排除（本分支可以有代码，但不进 Core 冻结）：

| 内容 | 标签 |
| --- | --- |
| 多人群静态包围、`dispersed` 静态包络 | Step 1 Extension |
| gather-then-surround、行人运动 | Step 2 prototype |
| 去中心化 / 有限通信 | Step 3 DESIGNED |

异质性边界：

\[
\text{Step 1 heterogeneity = representation-level heterogeneity}
\]

\[
\text{behavioral heterogeneity = Step 2}
\]

开发集已记录：homogeneous vs heterogeneous 的 tracking RMSE 一致到 \(10^{-15}\)，因为静态人群下 `desired_speed` / `time_gap` 仍是 metadata。

## 2. 软件闭合（相对 `8b15f82`）

`8b15f82` 的 GitHub Checks：`tests-linux` 失败，`static-analysis` 失败，`tests-windows` 因 40 分钟超时被取消。根因不是算法，而是：

1. Ruff E501（`known_boundary.py` 超长行）
2. 闭合 mypy 未跑到：`static_containment` 的 diagnostics / scene 类型
3. CLI 默认打开实时窗口；`test_static_containment_cli_runs` 未传 `--headless`  
   Linux 无 GUI → 立即失败；Windows `plt.show(block=True)` → 卡满 40 分钟
4. README `TEST_COUNT` 仍写 230，收集结果为 237

本提交的修复（不改变 Core 控制器增益、容差或 `max_steps`）：

- CLI 测试加 `--headless`
- CI / pytest 设 `MPLBACKEND=Agg`；无人值守环境禁止卡住 live window
- Ruff / mypy / README 计数与 Core/Extension 文档

本地：`237 collected`；修复后相关测试通过。推送后以 GitHub `tests-linux`、`tests-windows`、`static-analysis`、`deterministic-smoke` 全绿为软件冻结条件。

## 3. 实验协议

矩阵来自 `configs/step1_known_boundary/benchmark_manifest.yaml`：

\[
2\ \text{environments} \times 4\ \text{shapes} \times 20\ \text{holdout seeds (100–119)} = 160
\]

开发集仍是种子 0–4 的 40 次，**holdout 前未再调参**。命令：

```text
python scripts/run_step1_known_boundary.py \
  --manifest configs/step1_known_boundary/benchmark_manifest.yaml \
  --seeds 100:119 \
  --output <scratch> \
  --headless --workers auto
```

原始 run 目录留在 `_stash/step1_holdout/`（gitignore）。入库证据：

- `reports/step1_known_boundary/records.csv`（开发 40）
- `reports/step1_known_boundary/holdout_records.csv`（holdout 160）
- `reports/step1_known_boundary/records_all.csv`（合计 200）
- `holdout_analysis/`、`combined_analysis/`

科学成功 = 有效边界、部署、资源、规划、指派、收敛、采样安全。失败（含 `BOUNDARY_INVALID`、`TIMEOUT`）全部计入每一个分母。

## 4. 开发集（n = 40，种子 0–4）

| 项目 | 结果 |
| --- | ---: |
| 执行成功 | 34/40 = 85.0% |
| 科学成功 | **32/40 = 80.0%** |
| 边界有效 | 34/40 = 85.0% |
| 收敛 | 32/40 = 80.0% |
| 采样安全 | 34/40 = 85.0% |
| `BOUNDARY_INVALID` | 6 |
| `TIMEOUT` | 2 |
| 成功 run 的 mean tracking RMSE | 0.00427（n = 32） |

按形状（科学成功）：concave 10/10，irregular 8/10，ellipse 8/10，circle 6/10。  
square / rectangle 均为 16/20。

## 5. Holdout（n = 160，种子 100–119）— 正式独立数字

| 项目 | 结果 |
| --- | ---: |
| 执行成功 | 150/160 = 93.8% |
| 科学成功 | **110/160 = 68.8%** |
| 边界有效 | 150/160 = 93.8% |
| 收敛 | 110/160 = 68.8% |
| 采样安全 | 150/160 = 93.8% |
| `BOUNDARY_INVALID` | 10 |
| `TIMEOUT` | **40** |
| 成功 run 的 mean tracking RMSE | **0.00442（n = 110）** |
| 含失败的 reported RMSE 均值 | 0.294（被 TIMEOUT 拉高，不当作成功指标） |

按环境：

| 环境 | 科学成功 |
| --- | ---: |
| square | 58/80 = 72.5% |
| rectangle | 52/80 = 65.0% |

按形状：

| Shape | 科学成功 | 边界有效 | 主要失败 |
| --- | ---: | ---: | --- |
| circle | **35/40 = 87.5%** | 38/40 | BOUNDARY_INVALID=2, TIMEOUT=3 |
| irregular | 29/40 = 72.5% | 40/40 | TIMEOUT=11 |
| ellipse | 26/40 = 65.0% | 34/40 | BOUNDARY_INVALID=6, TIMEOUT=8 |
| concave | **20/40 = 50.0%** | 38/40 | TIMEOUT=18, BOUNDARY_INVALID=2 |

开发集上最弱的是 circle（6/10）；holdout 上 circle 反而最强。开发集上 concave 10/10，holdout 掉到 50%，几乎全是 TIMEOUT。这是 **seed 分布下的运动超时**，不是边界估计整体崩掉。

成功闭合 run 的跟踪精度与开发集一致（RMSE ≈ 0.004）。

## 6. Failure audit（失败全部保留）

合计 200 次：科学成功 142/200 = 71.0%；`BOUNDARY_INVALID` 16；`TIMEOUT` 42。

Holdout `BOUNDARY_INVALID`（10）：

- square circle 116
- square ellipse 104, 105, 114
- square concave 101
- rectangle circle 116
- rectangle ellipse 104, 105, 114
- rectangle concave 101

Holdout `TIMEOUT`（40）集中在 concave（18）与 irregular（11），ellipse 8，circle 3。完整名单见 `holdout_records.csv` 中 `scientific_success=False`。

**未做的事：** 没有提高 `max_steps`、没有放宽 RMSE 容差、没有改估计器。这些若在看过 holdout 之后再做，会把 holdout 变成第二轮开发集。

## 7. 冻结建议

可以声称：

- Step 1 Core 实现已完成，并在开发集 40-run 与独立 holdout 160-run 上评价过。
- Holdout 科学成功率 **68.8%**；边界有效 **93.8%**；成功闭合时 tracking RMSE 与开发集同量级。
- 异质性是表示层接口，不是行为有效性证明。

不可以声称：

- “Step 1 has been validated” 且成功率为开发集 80%。
- ABCG 已证明对 heterogeneous *behavior* 有效。
- 多人群 / gather-then-surround 属于 Step 1 Core。

**git tag `step1-known-boundary-freeze`：** 等本提交的 GitHub CI 全绿之后，可以把该 SHA 标成软件基线，但标签说明必须写 holdout **110/160**，而不是开发集 32/40。若论文需要 holdout ≥ 开发集，下一步是 **failure audit 后另开开发轮**（不能再动这 20 个 holdout 种子）。

## 8. 下一步（已不在 Step 1 Core 加功能）

1. 推送本提交，确认 Linux / Windows / static-analysis / smoke 全绿。
2. 可选：对 TIMEOUT 做失败审计（不改参、不重跑 holdout 当调参）。
3. 然后才进入真正的 Step 2（行为异质性、gather、行人动力学）。
