<div align="center">

# Crowd Management

面向未知人群周围自适应引导智能体部署的研究型仿真器。

![License](https://img.shields.io/badge/License-MIT-green.svg)
![Python](https://img.shields.io/badge/Python-3.12%2B-blue.svg)
![CI](https://github.com/Wu-kaixin/Crowd-Management/actions/workflows/ci.yml/badge.svg)
![Version](https://img.shields.io/badge/Version-0.1.0-informational.svg)
![Visualization](https://img.shields.io/badge/Visualization-Matplotlib-orange.svg)

</div>

Crowd Management 是用于**静态未知人群围堵**的 Python 研究原型。人群表示为二维点云；仿真器估计其边界，并在偏移安全曲线周围布置引导智能体。

当前方法族为 **ABCG: Adaptive Boundary-Coverage Guidance**（边界估计、周期覆盖规划、自适应资源、保持身份的指派、实测反馈速度控制，以及采样数据安全投影）。自冻结提交 `f2494922b2431bfd9a37a247add8a79acfdc18ed` 起，PR0–PR6 与 G0–G6 全部通过。在该狭窄静态范围内，**ABCG-v2 Step 1 已达到 research-complete**。

疏散 / DBAct / density-DBAct 代码**不在** `main` 上。它们仅保存在 [`archive/legacy-evacuation-2026-07-21`](https://github.com/Wu-kaixin/Crowd-Management/tree/archive/legacy-evacuation-2026-07-21)，供复现使用。

> 仅供研究原型使用 — 不是经过标定的安全产品，也不是已认证控制器。

---

## 可视化总览

可用 `python scripts/build_readme_media.py` 重新生成素材。

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

- **输入：** 静态二维人群点云。
- **估计器：** v1 径向 + PR6 alpha-shape，带 bootstrap 置信度与显式无效状态。
- **规划器：** 等弧长 / 置信门控周期 Lloyd（PR2）。
- **资源与指派：** `ceil(L/g_req)`、滞回、预备量、带切换惩罚的指派（PR3）。
- **运动与安全：** `u_nom = sat(k_p(z-p))`，配合采样数据半空间投影（PR4/PR5）。
- **基线：** 随机、静态圆、旧版中心-半径、端点 ABCG。
- **评估：** 独立解析真值；正式 G6 成对种子；失败仍计入分母。

权威约定：[docs/RESEARCH_SPEC.md](docs/RESEARCH_SPEC.md)。

---

## 快速开始

```bash
conda env update -n abcg -f environment.yml
conda activate abcg
```

静态围堵：

```bash
python scripts/run_static_containment.py \
  --config configs/static_crowd_circle.yaml \
  --output runs/static_containment_circle \
  --methods random static_circle legacy_center_radius abcg
```

运行目录下的典型输出：`summary.json`、`manifest.json`、`crowd_truth.npz`、边界/规划/资源产物，以及各方法的指派/回合文件。

测试与依赖检查：

```bash
mkdir -p .tmp
pytest --basetemp=.tmp/pytest-temp -o cache_dir=.tmp/pytest-cache
python -m pip check
```

正式 G6：

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
|-- configs/                    # 输入：场景 + configs/ci_smoke.yaml
|-- docs/                       # RESEARCH_SPEC、CODEMAP.zh、架构、性能
|-- src/crowd_management/
|   |-- crowd/                  # 核心：生成器 + 真值
|   |-- geometry/               # 核心：弧长 / 有效性
|   |-- estimation/             # 核心：边界估计器
|   |-- controllers/            # 核心：ABCG 数学（算法从这里看）
|   |-- runtime/                # 编排：硬件感知 worker
|   |-- reporting/              # 输出辅助：JSON + 快照 I/O
|   |-- experiments/            # 编排：静态围堵运行器
|   |-- evaluation/             # 编排：G6 / PR6 + schema 校验
|   |-- containment_metrics.py
|   `-- containment_visualization.py
|-- scripts/                    # 入口：仅薄 CLI
|-- runs/                       # 本地输出（gitignore）：原始实验转储
|-- reports/                    # 证据 / 媒体（部分入库）
|-- artifacts/, outputs/, .tmp/ # 本地临时输出
|-- tests/                      # 单元、回归、smoke
|-- .github/workflows/ci.yml
|-- pyproject.toml
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

可用 `git switch archive/legacy-evacuation-2026-07-21` 或 `git switch archive/g7-proof-strengthening-failed-2026-07-20` 查看。这些是历史/只读快照；新工作从 `main` 开始。

---

## 开发状态

- 分支：**`main`**
- 方法族：ABCG 静态未知人群围堵
- Step 1：**research-complete**（上述冻结上的 G0–G6）
- 套件规模（权威；由 `scripts/check_readme_consistency.py` 同步）：
  <!-- TEST_COUNT_START -->
  180
  <!-- TEST_COUNT_END -->
- CI：Linux + Windows，见 [`.github/workflows/ci.yml`](.github/workflows/ci.yml)（单元测试、限定范围的 lint/类型检查、README 一致性、确定性 smoke、schema 回归）
- 正式 G6：保留 600 条主记录 — [G6 报告](reports/step1_g6_compliance/G6_COMPLIANCE_REPORT.md)
- 本地性能说明：[docs/performance/final_report.md](docs/performance/final_report.md)（CI 墙钟时间**不是**正式证据）
- 架构维护说明：[docs/architecture/refactor_result.md](docs/architecture/refactor_result.md)

research-complete 指在单一静态未知人群周围的仿真引导部署。它**不**证明人类遵从、真实世界围堵、疏散收益、多人群动态，或连续时间安全证书。

## 许可证

[MIT License](LICENSE)。
