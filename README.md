<div align="center">

# Crowd Management Simulation Prototype

面向人群疏散引导策略的可复现实验、评估与可视化原型

![License](https://img.shields.io/badge/License-MIT-green.svg)
![Python](https://img.shields.io/badge/Python-3.12%2B-blue.svg)
![Tests](https://img.shields.io/badge/Tests-18%20passed-brightgreen.svg)
![Version](https://img.shields.io/badge/Version-0.1.0-informational.svg)
![Visualization](https://img.shields.io/badge/Visualization-Matplotlib-orange.svg)

</div>

Crowd Management Simulation Prototype 是一个轻量级 2D 人群疏散研究原型，用于快速验证移动引导员、DBACT 风格群体引导、出口分流和密度感知策略在可控仿真场景中的表现。

![2D crowd-management visualization dashboard](reports/visualization_upgrade_v1/dashboard.png)

> 图注：四种引导模式的仪表盘示例，包含疏散率曲线、归一化指标对比和最终状态快照。它展示了本项目的核心产出形式：可复现实验、量化指标和可视化报告。

---

## 背景信息

| 项目项 | 内容 |
| --- | --- |
| 项目名称 | Crowd Management Simulation Prototype |
| 项目简介 | 一个用于测试人群疏散引导机制的微观 2D 仿真器，帮助研究者在真实部署前先比较不同引导策略的疏散效率、拥堵程度和出口分流效果。 |
| 核心技术栈 | Python 3.12、NumPy、PyYAML、Matplotlib、imageio-ffmpeg、Pytest |
| 核心场景 | `simple_room.yaml` 单出口房间、`two_exits.yaml` 预备双出口场景、`two_exit_bottleneck.yaml` 双出口瓶颈场景 |
| 现有可视化素材 | 仪表盘、四模式快照、密度热力图、疏散曲线、拥堵曲线、出口压力曲线、对比视频和多种 CSV/JSON 指标表 |

当前项目是研究原型，不是已校准的真实世界人群管理系统。它的价值在于提供一个端到端、可测试、可复现的实验平台，用来判断哪些引导机制值得继续深入。

---

## 目录

- [核心特性](#核心特性)
- [实验结果与数据展示](#实验结果与数据展示)
- [快速上手](#快速上手)
- [目录结构说明](#目录结构说明)
- [架构与原理](#架构与原理)
- [常用命令](#常用命令)
- [贡献与许可](#贡献与许可)

---

## 核心特性

- 🔬 **微观人群仿真**：每个行人都有位置、速度、目标出口、合规度和疏散状态，便于分析个体行为如何汇聚成群体拥堵。
- 🧭 **多策略引导对比**：支持 `baseline`、`static`、`random`、`dbact`、`nearest_exit`、`balanced_exit_static`、`density_only`、`split_flow_only` 和 `density_dbact` 等模式。
- 📊 **可复现实验评估**：内置单次实验、多 seed 聚合评估、Stage 4 双出口瓶颈鲁棒评估，并输出 CSV、JSON、Markdown 报告。
- 🔥 **丰富可视化产出**：自动生成最终快照、密度热力图、疏散曲线、拥堵曲线、仪表盘、并排动画和机制解释图。
- ✅ **测试覆盖关键链路**：测试覆盖配置加载、仿真核心、CLI 脚本、可视化包、多 seed 评估和 Stage 4 评估流程。

---

## 实验结果与数据展示

### Stage 4 双出口瓶颈评估

Stage 4 使用 `configs/two_exit_bottleneck.yaml`，在 10 个随机种子上比较 9 种策略。该阶段的重点不是证明某个方法已经“最好”，而是验证密度感知引导、出口分流和公平基线之间的真实差异。

| Mode | Evacuation Rate | Congestion | Cumulative Congestion | Alternate-exit Usage | Exit Imbalance | Composite Score |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `baseline` | 0.9994 | 2.2056 | 85.4368 | 0.0000 | 1.0000 | 0.3592 |
| `static` | 0.9994 | 2.2033 | 84.5823 | 0.0000 | 1.0000 | 0.3635 |
| `dbact` | 1.0000 | 2.4961 | 92.3552 | 0.0000 | 1.0000 | 0.2819 |
| `nearest_exit` | 1.0000 | 1.8076 | 68.0892 | 0.1559 | 0.6881 | 0.5650 |
| `balanced_exit_static` | 0.9997 | 1.4810 | 53.2548 | 0.5002 | 0.0222 | 0.8177 |
| `density_only` | 0.9997 | 1.1949 | 41.6274 | 0.4889 | 0.0266 | 0.9156 |
| `exit_pressure_only` | 0.9722 | 1.5553 | 62.2892 | 0.6686 | 0.3372 | 0.6741 |
| `split_flow_only` | 0.9997 | 1.4810 | 53.2548 | 0.5002 | 0.0222 | 0.8177 |
| `density_dbact` | 0.9928 | 1.5474 | 61.9751 | 0.6912 | 0.3824 | 0.6883 |

**读表方式：**

- `density_only` 当前综合分最高，说明在这个瓶颈场景中，合理的出口分配本身就能显著降低拥堵。
- `balanced_exit_static` 和 `split_flow_only` 是非常强的公平基线，提醒我们不要把“允许使用第二出口”误判成复杂引导算法的独有贡献。
- `density_dbact` 能产生明显的备用出口使用和分流行为，但在当前参数下还没有超过最强的简单消融基线。
- `baseline`、`static` 和原始 `dbact` 主要使用主出口，因此出口不平衡和累积拥堵更高。

### 代表性图表

![Final crowd-management snapshots](reports/visualization_upgrade_v1/all_modes_grid.png)

> 图注：四种基础模式的最终快照。蓝点表示未疏散行人，橙色三角形表示引导员，绿色标记表示引导目标或出口附近位置。

![Density heatmap snapshots](reports/visualization_upgrade_v1/heatmap_snapshots.png)

> 图注：DBACT 模式下的密度热力图快照。热力图用于定位拥堵区域，比单帧散点图更适合分析密度演化。

### 预留图表位

完整运行 Stage 4 后，以下图表会生成在 `runs/stage4_density_eval_v1/comparison/`，可按需复制到 `reports/stage4_density_eval_v1/` 作为长期展示素材。

![鲁棒指标仪表盘](runs/stage4_density_eval_v1/comparison/robust_metrics_dashboard.png)

> 该图用于比较疏散率、拥堵、备用出口使用率和综合分，适合放在论文或阶段报告的总览页。

![密度 DBACT 机制快照](runs/stage4_density_eval_v1/comparison/mechanism_snapshot_density_dbact.png)

> 该图用于展示 `density_dbact` 如何形成分流路径，并把一部分行人引导至备用出口。

![消融实验对比](runs/stage4_density_eval_v1/comparison/ablation_summary.png)

> 该图用于解释 `density_only`、`exit_pressure_only`、`split_flow_only` 和完整 `density_dbact` 之间的差异。

### 视频产物

以下视频由完整实验自动生成，文件位于本地 `runs/` 目录。由于 `runs/` 默认被 `.gitignore` 忽略，若要在 GitHub README 中直接播放，请先将精选视频移动到 `reports/` 或 GitHub Release。

<video controls width="100%" src="runs/stage4_density_eval_v1/comparison/baseline_vs_density_dbact_mechanism.mp4"></video>

> 视频说明：`baseline` 与 `density_dbact` 的并排机制对比，用于观察备用出口分流是否真实出现。

---

## 快速上手

### 1. 克隆仓库

```bash
git clone https://github.com/Wu-kaixin/Crowd-Management.git
cd Crowd-Management
```

### 2. 创建环境

使用 `venv`，Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

使用 `venv`，macOS / Linux：

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

使用 Conda：

```bash
conda env create -f environment.yml
conda activate C-M
```

### 3. 一行代码跑通模拟实验

```bash
python scripts/run_density_dbact_experiment.py --config configs/two_exit_bottleneck.yaml --modes baseline density_dbact --steps 20 --seed 0 --output runs/quick_density_dbact --skip-video --fast-test
```

运行后重点查看：

- `runs/quick_density_dbact/summary/metrics_summary.csv`
- `runs/quick_density_dbact/summary/DENSITY_DBACT_REPORT.md`
- `runs/quick_density_dbact/comparison/final_metrics_bar.png`
- `runs/quick_density_dbact/comparison/exit_usage_curve.png`

### 4. 运行测试

```bash
pytest --basetemp=.tmp/pytest-temp -o cache_dir=.tmp/pytest-cache
```

---

## 目录结构说明

```text
Crowd-Management/
|-- configs/
|   |-- simple_room.yaml              # 单出口基础疏散场景
|   |-- two_exits.yaml                # 预备双出口场景
|   `-- two_exit_bottleneck.yaml      # Stage 3/4 双出口瓶颈主场景
|-- src/
|   `-- crowd_management/
|       |-- crowd_model.py            # 微观行人仿真主循环
|       |-- dbact_transfer.py         # DBACT 风格群体引导目标生成
|       |-- density_dbact.py          # 密度感知与出口压力分流控制器
|       |-- guidance_controller.py    # 引导员对行人的局部影响模型
|       |-- guider_model.py           # 移动引导员动力学
|       |-- metrics.py                # 疏散率、拥堵、碰撞风险等指标
|       |-- replay.py                 # replay.npz 离线回放数据
|       |-- visualization.py          # 基础快照、热力图、曲线渲染
|       `-- advanced_visualization.py # 仪表盘、并排动画、机制图渲染
|-- scripts/
|   |-- run_baseline.py               # 无引导基线实验
|   |-- run_guided.py                 # static/random/dbact 引导实验
|   |-- run_density_dbact_experiment.py
|   |-- run_stage4_density_eval.py    # Stage 4 多 seed 鲁棒评估
|   |-- run_visualization_package.py  # 一键生成展示用图表和视频
|   |-- compare_results.py
|   |-- render_animation.py
|   |-- render_dashboard.py
|   |-- render_heatmap_snapshot.py
|   `-- render_side_by_side.py
|-- reports/
|   |-- first_demo/                   # 第一阶段基线与 guided 结果
|   |-- guidance_baselines_v1/        # baseline/static/random/dbact 对比
|   |-- visualization_upgrade_v1/     # 已跟踪的首页展示图片
|   |-- density_dbact_v1/             # Stage 3 密度感知 DBACT 报告
|   `-- stage4_density_eval_v1/       # Stage 4 聚合 CSV 与 Markdown 报告
|-- runs/                             # 本地完整实验输出，含视频，默认不提交
|-- outputs/                          # 快速单次运行输出，仅保留 .gitkeep
|-- tests/                            # 核心仿真、CLI 与可视化测试
|-- environment.yml                   # Conda 环境定义
|-- pyproject.toml                    # Python 包配置
|-- requirements.txt                  # 简化依赖列表
|-- TEST_REPORT.md                    # 最近一次测试与健康检查记录
`-- README.md
```

---

## 架构与原理

1. **读取场景配置**
   系统从 `configs/*.yaml` 读取房间尺寸、出口位置、行人数量、速度分布、合规度、引导员数量和评估指标半径。

2. **初始化微观行人群体**
   每个行人会获得初始位置、速度、期望速度、个人半径、合规度和目标出口。仿真过程中，行人不是一个整体，而是一组可单独分析的 agent。

3. **计算行人运动**
   `crowd_model.py` 在每个时间步组合三类力：朝目标出口移动的吸引项、行人之间的排斥项、墙体和边界约束项。若启用引导，还会叠加引导员产生的方向影响。

4. **更新引导策略**
   原始 `dbact` 会估计活跃人群中心和扩散半径，再把引导员布置在人群后侧或侧后方。`density_dbact` 进一步估计出口压力，并让部分合规行人切换到备用出口。

5. **记录 replay 与指标**
   每次运行都会保存 `metrics.json`、`timeseries.csv`、`trajectories.npz` 和 `replay.npz`。这些文件让后续渲染不必重新跑仿真。

6. **生成图表和报告**
   可视化脚本读取 replay 与指标，输出最终快照、密度热力图、疏散曲线、拥堵曲线、仪表盘、并排动画和 Markdown 报告。

---

## 常用命令

### 基础单次运行

```bash
python scripts/run_baseline.py --config configs/simple_room.yaml --output outputs/baseline
python scripts/run_guided.py --config configs/simple_room.yaml --mode dbact --output outputs/dbact
```

### 四模式展示包

```bash
python scripts/run_visualization_package.py --config configs/simple_room.yaml --modes baseline static random dbact --steps 400 --seed 0 --output runs/visualization_package_v1 --quality high
```

### Stage 3 密度感知 DBACT 实验

```bash
python scripts/run_density_dbact_experiment.py --config configs/two_exit_bottleneck.yaml --modes baseline static dbact density_dbact --steps 800 --seed 0 --output runs/density_dbact_v1 --quality high
```

### Stage 4 完整鲁棒评估

```bash
python scripts/run_stage4_density_eval.py --config configs/two_exit_bottleneck.yaml --modes baseline static dbact nearest_exit balanced_exit_static density_only exit_pressure_only split_flow_only density_dbact --seeds 0 1 2 3 4 5 6 7 8 9 --steps 800 --output runs/stage4_density_eval_v1 --quality high
```

### 单独渲染可视化

```bash
python scripts/render_animation.py --run outputs/dbact --output outputs/dbact/dbact_animation.gif --fps 15 --heatmap
python scripts/render_side_by_side.py --runs outputs/baseline outputs/dbact --labels baseline dbact --output outputs/comparison/baseline_vs_dbact.gif
python scripts/render_dashboard.py --runs outputs/baseline outputs/dbact --labels baseline dbact --output outputs/comparison/dashboard.png
```

如果本机没有可用的 `ffmpeg`，建议先使用 `--skip-video` 跑完整评估，或把单独渲染输出改为 `.gif`。

---

## 当前研究结论

| 阶段 | 主要贡献 | 结论摘要 |
| --- | --- | --- |
| Stage 1 | 基础微观仿真、baseline 与 guided 对比 | DBACT-transfer 管线可运行，但改进幅度较小。 |
| Stage 2 | 多 seed 评估与展示级可视化包 | 项目具备可复现实验和图表生成能力。 |
| Stage 3 | 双出口瓶颈与 `density_dbact` | 分流行为开始可见，备用出口使用率显著上升。 |
| Stage 4 | 公平基线、消融实验、综合评分 | 简单分流基线非常强，完整 `density_dbact` 仍需参数和机制改进。 |

下一步更值得投入的是验证与调参，而不是直接堆叠更复杂的系统：建议优先做合规度、引导半径、出口压力权重和不同瓶颈几何的参数扫描。

---

## 贡献与许可

欢迎通过 Issue 或 Pull Request 贡献新场景、新指标、新可视化图表或更严格的实验验证。建议贡献前先运行：

```bash
pytest --basetemp=.tmp/pytest-temp -o cache_dir=.tmp/pytest-cache
python -m compileall src scripts
python -m pip check
```

本项目使用 [MIT License](LICENSE) 开源。请在复用代码、图表或报告时保留原始许可信息。
