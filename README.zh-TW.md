# Crowd Management

本專案已重構為研究「未知人群周圍 guide-agent 自適應部署」的模擬平台。

[English](README.md) | [Traditional Chinese](README.zh-TW.md) | [Japanese](README.ja.md)

目前主線是 **ABCG: Adaptive Boundary-Coverage Guidance**：

PR6 已加入 alpha-shape 非凸邊界估計、bootstrap 不確定性、U/C 留出形狀各 30 個配對種子、消融、95% 信賴區間與失敗圖集。G0-G6 已從乾淨的凍結提交 `f2494922b2431bfd9a37a247add8a79acfdc18ed` 全部得到 PASS，**ABCG-v2 Step 1 已達 research-complete**。此結論僅限單一靜態人群模擬，不證明動態人群、真人行為、圍控成效、疏散改善或無條件安全性。

- 從未知靜態人群點雲估計人群中心與邊界。
- 在估計邊界外建立安全距離邊界。
- 使用 coverage control / CVT 風格方法部署多個 guide agents。
- 用 coverage ratio、maximum Euclidean boundary distance、radial deployment error、angular uniformity、guide-guide distance、guide-crowd safety violation 等指標評估。舊有 `max_boundary_gap` 僅為相容別名，並非弧長 gap。

## 視覺總覽

Step 1 research-complete 素材。可用 `python scripts/build_readme_media.py` 重新生成。

### 靜態圍控示例

圓形、橢圓、不規則與雙叢集點雲上的 ABCG 部署示意。雙叢集仍明確標為單一分量圍控的 out-of-scope。

![ABCG static containment grid](reports/media/abcg_static_containment_grid.png)

![ABCG containment animation](reports/media/abcg_static_containment.gif)

![ABCG metrics summary](reports/media/abcg_metrics_summary.png)

### 正式 G6 場景

主矩陣的評估器對齊生成器：圓、橢圓與留出 U/C，搭配 alpha 邊界與 equal-arc 安全目標。

![Step 1 G6 scenarios](reports/media/step1_g6_scenarios.png)

### 基線比較

同一橢圓觀測下比較 random、static-circle、legacy center-radius 與 ABCG。

![Step 1 baseline comparison](reports/media/step1_baseline_comparison.png)

### 閉環追蹤

固定目標回授：guide 從單側初始布局追蹤 equal-arc 安全目標，並套用 sampled-data 速度安全投影。

![Step 1 closed-loop tracking](reports/media/step1_closed_loop.gif)

### 正式 G6 證據摘要

主矩陣成功率（每格 30 個配對種子，失敗保留於分母）與凍結 G6 報告中的實際失敗圖集。

![Step 1 G6 success rates](reports/media/step1_g6_success_rates.png)

![Step 1 failure gallery](reports/media/step1_failure_gallery.png)

正式報告：[reports/step1_g6_compliance/G6_COMPLIANCE_REPORT.md](reports/step1_g6_compliance/G6_COMPLIANCE_REPORT.md)。

舊的 DBAct 圖片、GIF、影片素材已集中放入 `legacy/evacuation_guidance/`。

## 使用方式

新實驗入口：

```bash
python scripts/run_static_containment.py --config configs/static_crowd_circle.yaml --output runs/static_containment_circle --methods random static_circle legacy_center_radius abcg
```

執行正式 G6 閉環評估：

```bash
python scripts/run_step1_g6_compliance.py --output reports/step1_g6_compliance --run-root runs/step1_g6_compliance
```

重新生成 README 圖片與 GIF：

```bash
python scripts/build_readme_media.py
```

測試：

```bash
pytest --basetemp=.tmp/pytest-temp -o cache_dir=.tmp/pytest-cache
```

舊的疏散、DBACT、density-DBACT 實驗已移至：

```text
legacy/evacuation_guidance/
```

詳細英文說明見 [README.md](README.md)。
