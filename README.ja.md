# Crowd Management

このリポジトリは、「未知の群衆の周囲に guide agent を適応的に配置する」研究用シミュレーション基盤として再構成されました。

[English](README.md) | [Traditional Chinese](README.zh-TW.md) | [Japanese](README.ja.md)

現在の中心は **ABCG: Adaptive Boundary-Coverage Guidance** です。

PR6 では alpha-shape による非凸境界推定、bootstrap 不確実性、U/C 型の留保形状に対する各 30 個の対応 seed、消融、95% 信頼区間、失敗ギャラリーを追加しました。クリーンな凍結コミット `f2494922b2431bfd9a37a247add8a79acfdc18ed` から G0-G6 がすべて PASS となり、**ABCG-v2 Step 1 は research-complete** です。これは静的な単一群衆のシミュレーションに限定され、動的群衆、人間行動、封じ込め効果、避難改善、無条件の安全性を証明するものではありません。

- 静的な未知群衆を点群として表現します。
- 群衆の中心と境界を推定します。
- 推定境界の外側に安全距離つきの境界を作ります。
- coverage control / CVT に基づいて複数の guide agents を配置します。
- coverage ratio、maximum Euclidean boundary distance、radial deployment error、angular uniformity、guide-guide distance、guide-crowd safety violation で評価します。従来の `max_boundary_gap` は互換用の非推奨名であり、弧長 gap ではありません。

## Visual Overview

Step 1 research-complete の可視化素材です。再生成は `python scripts/build_readme_media.py` です。

### 静的封じ込めの例

円・楕円・不規則・二クラスタ点群への ABCG 配置例。二クラスタは単一成分封じ込めの out-of-scope として明示します。

![ABCG static containment grid](reports/media/abcg_static_containment_grid.png)

![ABCG containment animation](reports/media/abcg_static_containment.gif)

![ABCG metrics summary](reports/media/abcg_metrics_summary.png)

### 正式 G6 シナリオ

主行列の評価器整合ジェネレータ：円、楕円、留保 U/C。alpha 境界と equal-arc 安全目標を示します。

![Step 1 G6 scenarios](reports/media/step1_g6_scenarios.png)

### ベースライン比較

同一の楕円観測に対する random / static-circle / legacy center-radius / ABCG の比較です。

![Step 1 baseline comparison](reports/media/step1_baseline_comparison.png)

### 閉ループ追従

固定目標フィードバック：片側初期配置から equal-arc 安全目標へ追従し、sampled-data 速度安全投影を適用します。

![Step 1 closed-loop tracking](reports/media/step1_closed_loop.gif)

### 正式 G6 証拠の要約

主行列の成功率（セルあたり 30 対応 seed、失敗は分母に残す）と凍結 G6 報告の実失敗ギャラリーです。

![Step 1 G6 success rates](reports/media/step1_g6_success_rates.png)

![Step 1 failure gallery](reports/media/step1_failure_gallery.png)

正式報告：[reports/step1_g6_compliance/G6_COMPLIANCE_REPORT.md](reports/step1_g6_compliance/G6_COMPLIANCE_REPORT.md)。

以前の DBAct 関連の画像、GIF、動画素材は `legacy/evacuation_guidance/` に移動しました。

## Usage

新しい実験の実行例：

```bash
python scripts/run_static_containment.py --config configs/static_crowd_circle.yaml --output runs/static_containment_circle --methods random static_circle legacy_center_radius abcg
```

正式 G6 閉ループ評価：

```bash
python scripts/run_step1_g6_compliance.py --output reports/step1_g6_compliance --run-root runs/step1_g6_compliance
```

README 用の画像と GIF を再生成：

```bash
python scripts/build_readme_media.py
```

テスト：

```bash
pytest --basetemp=.tmp/pytest-temp -o cache_dir=.tmp/pytest-cache
```

以前の evacuation / DBACT / density-DBACT 実験は、以下に移動しました。

```text
legacy/evacuation_guidance/
```

詳細は [README.md](README.md) を参照してください。
