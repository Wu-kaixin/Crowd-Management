<div align="center">

# 人群管理模擬原型

具備可重現實驗、量化指標、研究報告與視覺化成果的 2D 人群疏散模擬平台。

[English](README.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md)

![License](https://img.shields.io/badge/License-MIT-green.svg)
![Python](https://img.shields.io/badge/Python-3.12%2B-blue.svg)
![Tests](https://img.shields.io/badge/Tests-18%20passed-brightgreen.svg)
![Version](https://img.shields.io/badge/Version-0.1.0-informational.svg)
![Visualization](https://img.shields.io/badge/Visualization-Matplotlib-orange.svg)

</div>

Crowd Management Simulation Prototype 是一個輕量級研究原型，用於在進入更大型或真實世界系統之前，先測試人群疏散引導想法。專案聚焦於微觀行人運動、移動引導員影響、出口選擇、密度感知分流、可重現評估，以及可直接用於簡報或報告的視覺化成果。

> 本專案是研究原型，不是已經經過真實人群資料校準的部署級系統。

---

## 視覺展示

![Baseline vs DBACT animation](reports/media/baseline_vs_dbact.gif)

> 這是一個已提交到倉庫的 GIF 產物，位於 `reports/media/`。它不依賴本地 `runs/` 目錄，因此可以在 GitHub README 中直接顯示。

![Visualization dashboard](reports/visualization_upgrade_v1/dashboard.png)

> 儀表板展示多種引導模式的疏散率曲線、歸一化指標與最終狀態快照。

---

## 媒體圖庫

以下所有圖片與 GIF 都指向已提交的 `reports/` 路徑，因此 GitHub 可以直接渲染。

| 動態示範 | 儀表板 |
| --- | --- |
| <img src="reports/media/baseline_vs_dbact.gif" alt="Baseline vs DBACT animation" width="100%"> | <img src="reports/visualization_upgrade_v1/dashboard.png" alt="Visualization dashboard" width="100%"> |

| 最終快照 | 密度熱力圖 |
| --- | --- |
| <img src="reports/visualization_upgrade_v1/all_modes_grid.png" alt="Final snapshots for four modes" width="100%"> | <img src="reports/visualization_upgrade_v1/heatmap_snapshots.png" alt="Density heatmap snapshots" width="100%"> |

| 疏散曲線 | 最終指標 |
| --- | --- |
| <img src="reports/guidance_baselines_v1/evacuation_rate_comparison.png" alt="Evacuation rate comparison" width="100%"> | <img src="reports/guidance_baselines_v1/final_metrics_comparison.png" alt="Final metrics comparison" width="100%"> |

MP4 影片仍可由腳本產生，但預設會放在 `runs/`，而 `runs/` 會被 Git 忽略。若要在 GitHub 上穩定展示，建議使用已提交的 GIF/PNG，或把大型影片放到 GitHub Releases。

---

## 專案概覽

| 項目 | 內容 |
| --- | --- |
| 專案名稱 | Crowd Management Simulation Prototype |
| 目標 | 在受控 2D 疏散場景中比較不同人群引導策略。 |
| 核心技術 | Python 3.12、NumPy、PyYAML、Matplotlib、imageio-ffmpeg、Pytest |
| 主要場景 | `simple_room.yaml`、`two_exits.yaml`、`two_exit_bottleneck.yaml` |
| 輸出類型 | CSV 指標、JSON 摘要、replay 檔案、PNG 圖表、GIF 動畫、Markdown 報告 |

---

## 核心特性

- **微觀人群模擬**：每個行人都有位置、速度、期望速度、合規度、目標出口與疏散狀態。
- **多種引導模式**：支援 baseline、static、random、DBACT-style、nearest-exit、balanced split-flow、density-only、pressure-only 與 density-aware DBACT。
- **可重現評估**：提供單次實驗、多 seed 聚合、Stage 4 公平基線、消融實驗與綜合分數。
- **視覺化優先流程**：自動生成快照、熱力圖、儀表板、同步比較、動畫與報告圖。
- **已測試的 CLI 管線**：測試涵蓋模擬核心、密度感知引導、視覺化包、多 seed 評估與 Stage 4 smoke workflow。

---

## 實驗結果與視覺化

### Stage 4 密度感知 DBACT 評估

最新追蹤的 Stage 4 報告使用 `configs/two_exit_bottleneck.yaml`，在 10 個 seed 上評估 9 種模式。

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

**解讀重點**

- 目前分數最高的是簡單但公平的出口分配基線，例如 `density_only`。
- `density_dbact` 能產生明顯的備用出口使用與分流行為，但在目前參數下尚未超越最強的簡單消融基線。
- 綜合分數只是探索性指標，仍應搭配疏散率、擁堵、累積擁堵、出口使用率與視覺行為一起解讀。

---

## 快速開始

### 1. 下載倉庫

```bash
git clone https://github.com/Wu-kaixin/Crowd-Management.git
cd Crowd-Management
```

### 2. 建立環境

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

macOS / Linux:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

Conda:

```bash
conda env create -f environment.yml
conda activate C-M
```

### 3. 一行指令跑通 smoke experiment

```bash
python scripts/run_density_dbact_experiment.py --config configs/two_exit_bottleneck.yaml --modes baseline density_dbact --steps 20 --seed 0 --output runs/quick_density_dbact --skip-video --fast-test
```

重點輸出：

- `runs/quick_density_dbact/summary/metrics_summary.csv`
- `runs/quick_density_dbact/summary/DENSITY_DBACT_REPORT.md`
- `runs/quick_density_dbact/comparison/final_metrics_bar.png`
- `runs/quick_density_dbact/comparison/exit_usage_curve.png`

---

## 運作原理

1. **讀取場景設定**
   YAML 檔定義房間大小、出口、行人數量、速度分布、合規度、引導員數量與評估半徑。

2. **初始化個體行人**
   系統建立一群可單獨分析的行人 agent，而不是把人群視為剛體。

3. **推進微觀運動**
   每一步會組合目標吸引、行人間排斥、牆面處理、隨機噪聲與可選的引導員影響。

4. **更新引導策略**
   `dbact` 估計人群中心與擴散範圍，再安排引導員位置。`density_dbact` 進一步估計出口壓力，並將部分合規行人導向備用出口。

5. **保存 replay 與指標**
   每次運行會輸出 `metrics.json`、`timeseries.csv`、`trajectories.npz` 與 `replay.npz`，後續渲染不需要重新跑模擬。

6. **生成視覺化成果**
   腳本會輸出 PNG、GIF、儀表板、並排比較與 Markdown 報告。

---

## 倉庫結構

```text
Crowd-Management/
|-- configs/                         # 場景設定
|-- src/crowd_management/             # 模擬器、控制器、指標、replay、視覺化
|-- scripts/                          # 實驗與渲染 CLI
|-- reports/                          # 已提交的報告與 GitHub 可顯示媒體
|   |-- media/                        # README 使用的 GIF
|   |-- visualization_upgrade_v1/      # 儀表板、熱力圖、最終快照
|   |-- guidance_baselines_v1/         # 基線比較圖與指標
|   `-- stage4_density_eval_v1/        # Stage 4 聚合 CSV 與報告
|-- runs/                             # 本地生成結果，Git 忽略
|-- outputs/                          # 快速輸出，僅保留 .gitkeep
|-- tests/                            # 測試
|-- README.md
|-- README.zh-TW.md
`-- README.ja.md
```

---

## 常用指令

```bash
python scripts/run_baseline.py --config configs/simple_room.yaml --output outputs/baseline
python scripts/run_guided.py --config configs/simple_room.yaml --mode dbact --output outputs/dbact
python scripts/run_visualization_package.py --config configs/simple_room.yaml --modes baseline static random dbact --steps 400 --seed 0 --output runs/visualization_package_v1 --quality high
pytest --basetemp=.tmp/pytest-temp -o cache_dir=.tmp/pytest-cache
```

---

## 目前研究方向

下一步更適合做驗證與參數掃描，而不是直接堆疊不相關的大系統。建議優先探索合規度、引導半徑、密度權重、出口壓力權重、更困難的瓶頸幾何，以及路徑選擇效果與引導員佈局效果之間的分離。

---

## 貢獻與授權

歡迎透過 Issue 或 Pull Request 貢獻新場景、新指標、新視覺化與更嚴格的驗證實驗。

本專案採用 [MIT License](LICENSE)。
