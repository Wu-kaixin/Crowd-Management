# Crowd Management

本專案是研究「未知靜態人群周圍 guide-agent 自適應部署」的 Python 模擬原型。

[English](README.md) | [Traditional Chinese](README.zh-TW.md) | [Japanese](README.ja.md)

> **本文件描述分支 `feature/jupedsim-step1`，不是已凍結的 `main` 發佈說明。**

主線方法仍是 **ABCG**。本分支新增：

- **JuPedSim 靜態人群源**（只生成有間距的行人中心點，Step 1 **不推進**行人動力學）
- **synthetic ↔ JuPedSim** 配對源魯棒性評估（`scripts/run_step1_source_pairing.py`）

`main` 上凍結提交 `f2494922…` 的 G0–G6 PASS / research-complete 主張**未被本分支重新凍結**；此處證據是探索性配對結果。

迷路時先看：**[docs/CODEMAP.zh.md](docs/CODEMAP.zh.md)**。

## 本地配對結果摘要

證據目錄：[`reports/step1_source_pairing/`](reports/step1_source_pairing/)

- 矩陣：3 形狀 × 2 源 × 20 seed = **120** 次 ABCG 運行
- 形狀：`circle` / `ellipse` / `irregular`
- 流水線啟動：120/120 成功寫出產物；**閉環並非全部成功**

| 來源 | `BOUNDARY_INVALID` | 邊界 `VALID` | `CONVERGED` | `TIMEOUT` |
| --- | ---: | ---: | ---: | ---: |
| synthetic (60) | 39 | 21 | 11 | 10 |
| jupedsim (60) | 23 | 37 | 32 | 5 |
| **合計 (120)** | **62** | **58** | **43** | **15** |

### 邊界無效原因

62 次 `BOUNDARY_INVALID` 中：

| 原因 | 次數 | 說明 |
| --- | ---: | --- |
| `alpha_insufficient_observation_coverage` | 61 | alpha-shape 候選存在，但觀測覆蓋率未過接受門檻（`min_observation_coverage=0.8`） |
| `multiple_significant_components` | 1 | 觀測連通分量超過單一分量 Step 1 範圍 |

邊界無效時**不會 silently 修復**：週期規劃與資源決策跳過（`PLAN_SKIPPED_BOUNDARY_INVALID` / `RESOURCE_SKIPPED_BOUNDARY_INVALID`），失敗計入分母。這是研究會計規則，不是隱藏錯誤。

在此基準設定下，JuPedSim 靜態佈點的邊界接受率與 `CONVERGED` 次數高於配對的 synthetic，但 irregular 對兩邊都難；許多「啟動成功」仍以 `BOUNDARY_INVALID` 或 `TIMEOUT` 結束。

詳細數字與配對差分見英文 [README.md](README.md) 與 `analysis.json` / `records.csv`。

## 視覺總覽

素材可用 `python scripts/build_readme_media.py` 重新生成。下列圖片仍是 `main` 的 Step 1 媒體，**不是**上述 JuPedSim 配對矩陣的新圖。詳見英文 README。

![ABCG static containment grid](reports/media/abcg_static_containment_grid.png)

![ABCG containment animation](reports/media/abcg_static_containment.gif)

![Step 1 G6 scenarios](reports/media/step1_g6_scenarios.png)

![Step 1 closed-loop tracking](reports/media/step1_closed_loop.gif)

正式 G6 報告（繼承自 `main`）：[G6_COMPLIANCE_REPORT.md](reports/step1_g6_compliance/G6_COMPLIANCE_REPORT.md)。

## 使用方式

```bash
conda env update -n abcg -f environment.yml
conda activate abcg
python -m pip install -e ".[dev]"

# JuPedSim 靜態煙霧測試
python scripts/jupedsim_static_smoke.py

# 配對源評估
python scripts/run_step1_source_pairing.py \
  --output reports/step1_source_pairing

python scripts/run_static_containment.py \
  --config configs/static_crowd_circle.yaml \
  --output runs/static_containment_circle \
  --methods random static_circle legacy_center_radius abcg

mkdir -p .tmp
pytest --basetemp=.tmp/pytest-temp -o cache_dir=.tmp/pytest-cache
```

JuPedSim 設定範例：`configs/jupedsim/static_polygon.yaml`、`configs/step1_benchmark/jupedsim_*.yaml`。

CI、測試數量與開發狀態以英文 [README.md](README.md) 的 Development Status 與 GitHub Actions badge 為準（目前 suite 標記為 **189**）。

## 研究封存

歷史快照索引：[docs/ARCHIVE_INDEX.md](docs/ARCHIVE_INDEX.md)。

```text
archive/legacy-evacuation-2026-07-21:legacy/evacuation_guidance/
archive/legacy-evacuation-2026-07-21:src/crowd_management/legacy/
archive/g7-proof-strengthening-failed-2026-07-20
```

JuPedSim 工作應經 review 合併；不要把本 feature 分支當成 `main`。
