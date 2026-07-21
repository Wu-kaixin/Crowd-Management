# Crowd Management

本リポジトリは、未知の静的群衆の周囲に guide agent を適応配置する研究用 Python シミュレータです。

[English](README.md) | [Traditional Chinese](README.zh-TW.md) | [Japanese](README.ja.md)

中心手法は **ABCG: Adaptive Boundary-Coverage Guidance** です（境界推定、周期被覆計画、資源配分、割当、速度フィードバック、sampled-data 安全投影）。凍結コミット `f2494922b2431bfd9a37a247add8a79acfdc18ed` で G0–G6 が PASS し、**ABCG-v2 Step 1 は research-complete** です（単一静的群衆シミュレーションに限定）。

旧 evacuation / DBAct 実装は `main` にはなく、[`local-main-backup`](https://github.com/Wu-kaixin/Crowd-Management/tree/local-main-backup) に保存されています。

## Visual Overview

媒体の再生成は `python scripts/build_readme_media.py`。詳細画像は英語 [README.md](README.md) を参照。

![ABCG static containment grid](reports/media/abcg_static_containment_grid.png)

![ABCG containment animation](reports/media/abcg_static_containment.gif)

![Step 1 G6 scenarios](reports/media/step1_g6_scenarios.png)

![Step 1 closed-loop tracking](reports/media/step1_closed_loop.gif)

正式 G6 報告：[G6_COMPLIANCE_REPORT.md](reports/step1_g6_compliance/G6_COMPLIANCE_REPORT.md)。

## Usage

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

CI・テスト件数・開発ステータスは英語 [README.md](README.md) の Development Status と GitHub Actions badge を正とします（矛盾する passed 数を手書きしないでください）。

## Legacy

```text
local-main-backup:legacy/evacuation_guidance/
local-main-backup:src/crowd_management/legacy/
```

`git switch local-main-backup` で閲覧。新規作業は `main` の `scripts/run_static_containment.py` から。
