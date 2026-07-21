# 性能与重构实施计划（perf-hardware-aware-refactor）

状态：**待确认**。本文档是审计结论 + Phase 0/1 设计 + 全阶段实施计划。
在计划被确认之前，不进行任何算法代码或结构性修改。

约束（全程有效）：不改变 ABCG 算法数学定义、成功/失败判定、随机种子语义、
paired comparison、超时定义、正式结果 schema 与统计口径；不减少 case /
episode / step；不降精度；所有优化以基准数据为准，无提升则回滚。

---

## 0. 审计结论（当前代码实际情况）

### 0.1 并行现状（与预期不同，关键）

仓库**没有 multiprocessing 进程池**。全部并行为 `ThreadPoolExecutor`
（线程池），共 4 处，worker 默认 4：

| 位置 | 用途 | 调度 |
| --- | --- | --- |
| `src/crowd_management/evaluation/step1_g6.py:1415` | G6 主评测 case 级并行 | `executor.map`，有序收集后显式 `sort` |
| `src/crowd_management/evaluation/step1_g6.py:932` | ablation case | 同上 |
| `src/crowd_management/evaluation/step1_g6.py:1030` | robustness case | 同上 |
| `src/crowd_management/evaluation/step1_pr6.py:495` | PR6 paired 评测 | 同上 |

- worker 数来自 `--workers`（默认 4），已做 `min(workers, len(cases))` 截断。
- 结果在收集后按 `(scenario, seed, ...)` 显式排序，**输出顺序确定性已由代码保证**，
  与调度顺序解耦——这为改用无序动态调度提供了安全基础。
- `scripts/run_static_containment.py` / `experiments/static_containment.py` 为**纯串行**。
- 无任何 BLAS/OMP 线程控制代码；无 psutil / threadpoolctl / numba 依赖。

含义：
1. "24 worker × 多线程 MKL" 的进程级过度订阅目前不存在；实际风险是
   **单进程内 4 个 Python 线程共享 GIL + OpenBLAS 内部线程池**的混合竞争。
2. 提速空间的第一问题是：热点在 Python 字节码（GIL 限制线程扩展）还是在
   NumPy/OpenBLAS 原生代码（线程可扩展）。这必须由 Phase 1 profiling 回答，
   决定"继续线程池 + 治理 BLAS 线程"还是"改进程池（spawn）"。

### 0.2 实际硬件（与提示词假设不同，关键）

本机不是 14900KF（24C/32T），实际为：

- CPU：**Intel Core Ultra 9 285H**，16 物理核 / 16 逻辑线程（混合架构
  6P + 8E + 2LPE，无超线程），affinity 全部 16 可用
- 内存：31.5 GB
- OS：Windows 11 (10.0.26200)；multiprocessing start method = `spawn`
- 环境：conda `abcg`，Python 3.12.13，NumPy 2.5.1（BLAS/LAPACK =
  **scipy-openblas**，非 MKL），SciPy 1.18.0，matplotlib 3.11.1
- `OMP/MKL/OPENBLAS/NUMEXPR/VECLIB` 环境变量均未设置 →
  OpenBLAS 默认按全部核数开内部线程
- psutil、threadpoolctl、numba：**未安装**（硬件感知模块需新增依赖并优雅降级）

### 0.3 大文件清单（>500 行，重构候选）

| 文件 | 行数 |
| --- | --- |
| `src/crowd_management/evaluation/step1_g6.py` | 1452 |
| `src/crowd_management/estimation/boundary_v2.py` | 774 |
| `src/crowd_management/experiments/static_containment.py` | 751 |
| `src/crowd_management/controllers/abcg_v2.py` | 737 |
| `src/crowd_management/evaluation/step1_pr6.py` | 501 |

`step1_g6.py` 同时承担：配置、case 编排、ablation、robustness、stress、
统计汇总、序列化、报告生成——是首要拆分对象。

### 0.4 热点候选（待 Phase 1 用数据确认）

1. boundary 估计：bootstrap 重采样 × alpha-shape 重复估计（`boundary_v2.py`）
2. 逐 step safety filter 的半空间投影（`controllers/safety.py`）
3. 边界曲线 O(K²) 自交检测
4. 广播式 pairwise 距离矩阵（chamfer / hausdorff、metrics）
5. 每个 case 独立重建 observation / truth（可能重复构造静态几何）

序列化为 episode 结束后一次性写盘（G6 约 600 run × 8 文件），**不存在逐 step
写盘问题**；仿真过程中无绘图（绘图在评测收尾/独立脚本）。

### 0.5 测试与确定性现状

- 77 个测试；`tests/step1/` 覆盖边界估计、safety、assignment、episode、
  G6 合规（`test_g6_compliance.py` 用 workers=2 跑小规模闭环）。
- seed 显式传播（`np.random.default_rng(固定偏移 + seed)`），有 paired
  comparison 逻辑与结果 SHA/manifest。
- 缺少：跨 worker 数的一致性测试、golden-summary characterization tests。

---

## 1. Phase 0：基准设计

新增基准脚本（只读测量，不改被测代码）：

```
scripts/benchmark_baseline.py
docs/performance/baseline_report.md      （输出）
artifacts/performance/baseline.json      （输出）
```

三档代表性工作负载（均使用现有正式入口，不改任何口径）：

| 档位 | 命令 | 说明 |
| --- | --- | --- |
| small | `run_static_containment.py --config configs/static_crowd_circle.yaml`（全方法） | 串行路径 |
| standard | `run_step1_pr6_evaluation.py --seed-count 30`（默认 workers=4） | 文档标准命令 |
| formal | `run_step1_g6_compliance.py`（默认参数，workers=4） | 正式 G6 口径 |

每档记录进 `baseline.json`：

- 元数据：Git SHA、Python/NumPy/SciPy 版本、BLAS 后端、OS、CPU 型号、
  物理/逻辑核数、affinity、总/可用内存、五个 `*_NUM_THREADS` 环境变量、
  start method、workers 数（隐私字段——用户名/主机名/路径/MAC——一律不写入）
- 测量：wall time、CPU time（`os.times`/`psutil`）、peak RSS、平均 CPU 利用率、
  每 case 耗时（从 events/记录时间戳提取或注入轻量计时）、最慢 case、
  p50/p90/p95 case latency、record_count、exit code
- 一致性锚点：全部正式结果文件的 **SHA256 清单**（`aggregate.json`、
  `records.json/csv`、`paired_comparisons.json`、`gate_evidence.json` 等），
  作为后续所有优化的比对基线

formal 档预计耗时最长（用户报告约半小时量级），基准阶段跑 **1 次完整 +
small/standard 各 2 次**取稳定值；若 wall time 抖动 >5% 再补测。

## 2. Phase 1：Profiling 设计

工具：`cProfile`（函数级累计/自身时间）+ 自定义阶段计时器（模块级归因）；
如需行级证据再加 `line_profiler`（仅 dev 依赖，不进运行时代码）。
py-spy 在 Windows 上可用则补一份采样火焰图（区分 GIL 持有 / native 时间，
这直接回答"线程池 vs 进程池"问题）。

测量对象与归因维度（对应 16 项清单）：

- **workers=1 串行 cProfile**：standard 档 + formal 档缩样（相同口径、仅
  profiling 用，不产出正式结果），得到 top-20 cumulative / top-20 self
- **阶段计时**：boundary estimation（含 bootstrap 循环拆分）、alpha shape、
  arc-length 参数化、resampling、guide 数计算、assignment
  （`linear_sum_assignment` 与 cost matrix 构造分开计）、velocity 控制器、
  safety filter、距离计算、metrics、轨迹记录、npz/json 序列化、SHA、
  线程池提交/收集开销
- **并发行为**：workers ∈ {1, 4} 下 wall/CPU time 比值、CPU 利用率曲线、
  OpenBLAS 线程数（`threadpoolctl.threadpool_info()`）、case 完成时间线
  （检测长尾/worker 空闲）

产出 `docs/performance/profile_report.md`，必须回答：

1. Python 时间 vs native 时间比例（决定并行策略走向）
2. 是否存在重复计算（bootstrap 内可缓存量、每 case 重建的静态几何）
3. 是否存在多层 Python 循环、频繁小对象/临时数组、过量复制
4. 是否存在 nested parallelism（Python 线程 × OpenBLAS 线程）
5. 长尾 case 与负载不均衡程度

**完成本报告并经确认前，不进入任何代码优化。**

## 3. Phase 2+：实施阶段（在 Phase 0/1 数据确认后执行）

### Phase 2：硬件感知运行时（新模块，遵循现有包结构）

```
src/crowd_management/runtime/
    __init__.py
    hardware.py        # 只读检测：CPU/核数/affinity/内存/OS/BLAS/GPU 有无
    thread_limits.py   # BLAS 线程治理（threadpoolctl + 子进程 env 注入）
    parallel_config.py # conservative/balanced/maximum/manual 决策
    diagnostics.py     # 启动时打印最终配置与选择理由
```

- psutil / threadpoolctl 加入 `[dev]` 之外的可选依赖组；缺失时降级到
  `os.cpu_count()` / `platform`，绝不让仿真失败
- 硬件元数据写入运行 manifest（剔除用户名/主机名/IP/MAC/个人路径）

### Phase 3：线程治理与并行配置

- 若 Phase 1 证明热点为 native 计算 → 保留线程池，用 threadpoolctl 在
  worker 区域内限 BLAS 线程，扫描 (python_workers × blas_threads) 组合
- 若热点为 Python 字节码（GIL 受限）→ 改 `ProcessPoolExecutor`（spawn），
  子进程创建前注入 `OMP/MKL/OPENBLAS/NUMEXPR/VECLIB_NUM_THREADS=1`
  （必须在 NumPy import 前生效，用 initializer + env 双保险），
  worker 只回传轻量 record dict（现有代码已如此）
- worker 决策：`workers = min(case_count, affinity_cpus, 模式上限)`；
  balanced 候选 = {physical−1, physical, 0.75×logical} 中基准最快者；
  285H 无超线程，logical==physical==16，重点是 P/E 核混合下的实测
- CLI：`--workers auto|N`、`--performance-mode conservative|balanced|maximum`，
  默认保持现状（workers=4）直至基准证明 auto 更快，保证向后兼容
- 启动时输出：Detected CPU / cores / affinity / selected workers /
  BLAS threads per worker / est. memory per worker / mode / reason

### Phase 4：调度优化

- `executor.map` → `as_completed` / `imap_unordered` 等动态领取，
  chunksize=1；收集后沿用现有显式 sort（正式输出顺序不变）
- episode 级下沉仅在证明不影响 paired seed 对齐与统计单位时作为
  **单独实验性提案**，默认不实施

### Phase 5：热点优化（逐项以 profiling 证据驱动）

允许：缓存不变几何/arc-length 参数化、bootstrap 内向量化、预分配、
`scipy.spatial` 替代广播全矩阵（若内存/时间证明）、减少每 case 重复构造。
禁止：改数学定义、float32、近似替代、砍安全检查、无基准引入 numba。

### Phase 6：characterization tests + 大文件重构

1. 先加 characterization tests：小规模固定 seed 下锁定 record_count、
   success/failure 分类、failure reason、关键 metric 数值（现有容差）、
   workers ∈ {1,2} 结果一致、重复运行确定性
2. 再拆 `step1_g6.py`（1452 行）→ 配置 / case 执行 / ablation / robustness /
   统计 / 序列化 / 报告 各归一模块；`static_containment.py`、`abcg_v2.py`、
   `boundary_v2.py` 逐个评估，产出 `docs/architecture/refactor_plan.md`
3. 每拆一个模块跑全量测试 + SHA 比对

### Phase 7：验收

比较 workers=1 / 原默认(4) / auto balanced / auto maximum 四配置，产出
`docs/performance/final_report.md` + `artifacts/performance/comparison.json`
（wall/CPU time、speedup、并行效率、peak RSS、p50/p90/p95、最慢 case、
worker 空闲尾、正式结果一致性证明）。最低验收：77 测试全过、正式结果口径
不变、单进程与并行结果一致（容差内并解释来源）、auto 不慢于原配置、
无提升的复杂化全部回滚。

## 4. 提交序列（小步、可审查）

1. `docs: add performance audit and implementation plan`（本文档）
2. `perf: add baseline benchmark infrastructure`
3. `perf: add profiling harness and profile report`
4. `perf: add hardware diagnostics runtime module`
5. `perf: prevent numerical thread oversubscription`
6. `perf: add adaptive worker selection with CLI override`
7. `perf: improve dynamic task scheduling`
8. `test: add deterministic characterization coverage`
9. `refactor: split step1_g6 evaluation orchestration`（后续各重构一条）
10. `docs: add final benchmark and architecture reports`

## 5. 风险与开放问题

1. **机器差异**：本项目在两台机器上运行——笔记本（Ultra 9 285H，16C/16T，
   31.5 GiB）与台式机（Raptor Lake 24C/32T，64 GiB，含 CUDA GPU）。
   Phase 0/1 已在两台机器分别测量（`baseline.json` / `baseline_desktop.json`，
   `profile.json` / `profile_desktop.json`），结论定性一致：热点在 Python
   字节码，线程池无效，需进程池 + BLAS 线程治理。worker 数一律运行时检测，
   不硬编码。
2. **formal 档基准耗时约 30 分钟/次**，四配置对比一轮 ≈ 2 小时，需要预留。
3. 线程池→进程池切换在 Windows spawn 下每 worker 有 import 开销
   （NumPy/SciPy 冷启动数秒），case 数少时可能不划算——由基准裁决。
4. G6 的 ablation 复用 primary 结果（`primary_by_key`），调度改动必须保持
   primary → ablation 的阶段顺序，不能跨阶段乱序。
