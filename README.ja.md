# Crowd Management

このリポジトリは、「未知の群衆の周囲に guide agent を適応的に配置する」研究用シミュレーション基盤として再構成されました。

現在の中心は **ABCG: Adaptive Boundary-Coverage Guidance** です。

- 静的な未知群衆を点群として表現します。
- 群衆の中心と境界を推定します。
- 推定境界の外側に安全距離つきの境界を作ります。
- coverage control / CVT に基づいて複数の guide agents を配置します。
- coverage ratio、maximum boundary gap、radial deployment error、angular uniformity、guide-guide distance、guide-crowd safety violation で評価します。

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
