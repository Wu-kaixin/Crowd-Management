# Crowd Management

このリポジトリは、「未知の群衆の周囲に guide agent を適応的に配置する」研究用シミュレーション基盤として再構成されました。

現在の中心は **ABCG: Adaptive Boundary-Coverage Guidance** です。

PR6 では alpha-shape による非凸境界推定、bootstrap 不確実性、U/C 型の留保形状に対する各 30 個の対応 seed、消融、95% 信頼区間、失敗ギャラリーを追加しました。実装と評価結果は作業ツリーにありますが、評価時点が未コミットのため G6 の frozen-commit 条件は未達です。

- 静的な未知群衆を点群として表現します。
- 群衆の中心と境界を推定します。
- 推定境界の外側に安全距離つきの境界を作ります。
- coverage control / CVT に基づいて複数の guide agents を配置します。
- coverage ratio、maximum Euclidean boundary distance、radial deployment error、angular uniformity、guide-guide distance、guide-crowd safety violation で評価します。従来の `max_boundary_gap` は互換用の非推奨名であり、弧長 gap ではありません。

## Media

メイン README では、新しい ABCG の画像と GIF のみを表示します。以前の DBAct 関連の画像、GIF、動画素材は `legacy/evacuation_guidance/` に移動しました。

![ABCG static containment grid](reports/media/abcg_static_containment_grid.png)

![ABCG containment animation](reports/media/abcg_static_containment.gif)

![ABCG metrics summary](reports/media/abcg_metrics_summary.png)

## Usage

新しい実験の実行例：

```bash
python scripts/run_static_containment.py --config configs/static_crowd_circle.yaml --output runs/static_containment_circle --methods random static_circle legacy_center_radius abcg
```

PR6 の対応付き評価：

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
