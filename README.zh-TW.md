# Crowd Management

本專案已重構為研究「未知人群周圍 guide-agent 自適應部署」的模擬平台。

目前主線是 **ABCG: Adaptive Boundary-Coverage Guidance**：

- 從未知靜態人群點雲估計人群中心與邊界。
- 在估計邊界外建立安全距離邊界。
- 使用 coverage control / CVT 風格方法部署多個 guide agents。
- 用 coverage ratio、maximum boundary gap、radial deployment error、angular uniformity、guide-guide distance、guide-crowd safety violation 等指標評估。

舊的疏散、DBACT、density-DBACT 實驗已移至：

```text
legacy/evacuation_guidance/
```

新實驗入口：

```bash
python scripts/run_static_containment.py --config configs/static_crowd_circle.yaml --output runs/static_containment_circle --methods random static_circle legacy_center_radius abcg
```

測試：

```bash
pytest --basetemp=.tmp/pytest-temp -o cache_dir=.tmp/pytest-cache
```

詳細英文說明見 [README.md](README.md)。
