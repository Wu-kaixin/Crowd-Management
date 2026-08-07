# Crowd Management

鏈皥妗堟槸鐮旂┒銆屾湭鐭ラ潨鎱嬩汉缇ゅ懆鍦?guide-agent 鑷仼鎳夐儴缃层€嶇殑 Python 妯℃摤鍘熷瀷銆?
[English](README.md) | [Traditional Chinese](README.zh-TW.md) | [Japanese](README.ja.md)

涓荤窔鏂规硶锛?*ABCG: Adaptive Boundary-Coverage Guidance**锛堥倞鐣屼及瑷堛€侀€辨湡瑕嗚搵瑕忓妰銆佽硣婧愬垎閰嶃€佹寚娲俱€侀€熷害鍥炴巿鑸?sampled-data 瀹夊叏鎶曞奖锛夈€傚噸绲愭彁浜?`f2494922b2431bfd9a37a247add8a79acfdc18ed` 涓?G0鈥揋6 鐨?PASS锛?*ABCG-v2 Step 1 鐐?research-complete**锛堝儏闄愬柈涓€闈滄厠浜虹兢妯℃摤锛夈€?
鑸婄枏鏁?/ DBAct 绋嬪紡涓嶅湪 `main`锛屽畬鏁翠繚瀛樺湪 [`local-main-backup`](https://github.com/Wu-kaixin/Crowd-Management/tree/local-main-backup)銆?
杩疯矾鏅傚厛鐪嬶細**[docs/CODEMAP.zh.md](docs/CODEMAP.zh.md)**锛堟牳蹇冪畻娉?/ 杈撳叆閰嶇疆 / 杩愯杈撳嚭 瀵圭収锛夈€?
## 瑕栬绺借

绱犳潗鍙敤 `python scripts/build_readme_media.py` 閲嶆柊鐢熸垚銆傝┏瑕嬭嫳鏂?[README.md](README.md) 鍦栫墖鍗€銆?
![ABCG static containment grid](reports/media/abcg_static_containment_grid.png)

![ABCG containment animation](reports/media/abcg_static_containment.gif)

![Step 1 G6 scenarios](reports/media/step1_g6_scenarios.png)

![Step 1 closed-loop tracking](reports/media/step1_closed_loop.gif)

姝ｅ紡 G6 鍫卞憡锛歔G6_COMPLIANCE_REPORT.md](reports/step1_g6_compliance/G6_COMPLIANCE_REPORT.md)銆?
## 浣跨敤鏂瑰紡

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

CI銆佹脯瑭︽暩閲忚垏闁嬬櫦鐙€鎱嬩互鑻辨枃 [README.md](README.md) 鐨?Development Status 鑸?GitHub Actions badge 鐐烘簴锛堝嬁鍐嶆墜瀵簰鐩歌绐佺殑 passed 鏁稿瓧锛夈€?
## 鑸婄増灏佸瓨

```text
local-main-backup:legacy/evacuation_guidance/
local-main-backup:src/crowd_management/legacy/
```

`git switch local-main-backup` 鍙瑕栥€傛柊宸ヤ綔璜嬪緸 `main` 鐨?`scripts/run_static_containment.py` 闁嬪銆?
