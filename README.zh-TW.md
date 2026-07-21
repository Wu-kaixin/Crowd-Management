# Crowd Management

本專案是研究「未知靜態人群周圍 guide-agent 自適應部署」的 Python 模擬原型。

[English](README.md) | [Traditional Chinese](README.zh-TW.md) | [Japanese](README.ja.md)

主線方法：**ABCG: Adaptive Boundary-Coverage Guidance**（邊界估計、週期覆蓋規劃、資源分配、指派、速度回授與 sampled-data 安全投影）。凍結提交 `f2494922b2431bfd9a37a247add8a79acfdc18ed` 上 G0–G6 皆 PASS，**ABCG-v2 Step 1 為 research-complete**（僅限單一靜態人群模擬）。

舊疏散 / DBAct 程式不在 `main`，完整保存在 [`local-main-backup`](https://github.com/Wu-kaixin/Crowd-Management/tree/local-main-backup)。

## 視覺總覽

素材可用 `python scripts/build_readme_media.py` 重新生成。詳見英文 [README.md](README.md) 圖片區。

![ABCG static containment grid](reports/media/abcg_static_containment_grid.png)

![ABCG containment animation](reports/media/abcg_static_containment.gif)

![Step 1 G6 scenarios](reports/media/step1_g6_scenarios.png)

![Step 1 closed-loop tracking](reports/media/step1_closed_loop.gif)

正式 G6 報告：[G6_COMPLIANCE_REPORT.md](reports/step1_g6_compliance/G6_COMPLIANCE_REPORT.md)。

## 使用方式

```bash
conda env update -n abcg -f environment.yml
conda activate abcg

python scripts/run_static_containment.py \
  --config configs/static_crowd_circle.yaml \
  --output runs/static_containment_circle \
  --methods random static_circle legacy_center_radius abcg

python scripts/run_step1_g6_compliance.py \
  --output reports/step1_g6_compliance \
  --run-root runs/step1_g6_compliance

mkdir -p .tmp
pytest --basetemp=.tmp/pytest-temp -o cache_dir=.tmp/pytest-cache
```

CI、測試數量與開發狀態以英文 [README.md](README.md) 的 Development Status 與 GitHub Actions badge 為準（勿再手寫互相衝突的 passed 數字）。

## 舊版封存

```text
local-main-backup:legacy/evacuation_guidance/
local-main-backup:src/crowd_management/legacy/
```

`git switch local-main-backup` 可檢視。新工作請從 `main` 的 `scripts/run_static_containment.py` 開始。
