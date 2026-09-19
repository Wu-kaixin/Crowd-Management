# Step 1 已知边界结果

正式闭合报告（开发集 + holdout、范围冻结、失败审计）：[`STEP1_CLOSURE_REPORT.md`](STEP1_CLOSURE_REPORT.md)。

环境边界已知。人群边界未知。
JuPedSim 生成几何仅供评估器/仿真器使用，不暴露给 ABCG。

本报告区分**执行成功**（流水线无崩溃完成）、**科学成功**（有效边界、部署、资源、规划、指派、收敛与采样安全）以及**失败**（全部计入每一个分母）。

## 全部记录

- n: 40
- 执行成功: 0.850
- 科学成功: 0.800
- 边界有效: 0.850
- 部署有效: 0.850
- 收敛: 0.800
- 失败（计入分母）: BOUNDARY_INVALID=6, TIMEOUT=2

## 环境：rectangle

- n: 20
- 执行成功: 0.850
- 科学成功: 0.800
- 边界有效: 0.850
- 部署有效: 0.850
- 收敛: 0.800
- 失败（计入分母）: BOUNDARY_INVALID=3, TIMEOUT=1

## 环境：square

- n: 20
- 执行成功: 0.850
- 科学成功: 0.800
- 边界有效: 0.850
- 部署有效: 0.850
- 收敛: 0.800
- 失败（计入分母）: BOUNDARY_INVALID=3, TIMEOUT=1

## 人群形状：circle

- n: 10
- 执行成功: 0.600
- 科学成功: 0.600
- 边界有效: 0.600
- 部署有效: 0.600
- 收敛: 0.600
- 失败（计入分母）: BOUNDARY_INVALID=4

## 人群形状：concave

- n: 10
- 执行成功: 1.000
- 科学成功: 1.000
- 边界有效: 1.000
- 部署有效: 1.000
- 收敛: 1.000
- 失败（计入分母）: 无

## 人群形状：ellipse

- n: 10
- 执行成功: 0.800
- 科学成功: 0.800
- 边界有效: 0.800
- 部署有效: 0.800
- 收敛: 0.800
- 失败（计入分母）: BOUNDARY_INVALID=2

## 人群形状：irregular

- n: 10
- 执行成功: 1.000
- 科学成功: 0.800
- 边界有效: 1.000
- 部署有效: 1.000
- 收敛: 0.800
- 失败（计入分母）: TIMEOUT=2

## 异构

- n: 40
- 执行成功: 0.850
- 科学成功: 0.800
- 边界有效: 0.850
- 部署有效: 0.850
- 收敛: 0.800
- 失败（计入分母）: BOUNDARY_INVALID=6, TIMEOUT=2

## 划分：development

- n: 40
- 执行成功: 0.850
- 科学成功: 0.800
- 边界有效: 0.850
- 部署有效: 0.850
- 收敛: 0.800
- 失败（计入分母）: BOUNDARY_INVALID=6, TIMEOUT=2

## 同构 vs 异构消融

成对比较 `square_circle` 与 `homogeneous_square_circle`，种子 0-4，控制器参数相同。

- 种子 0、2、3：两侧均为 CONVERGED，跟踪 RMSE 一致到 1e-15
- 种子 1、4：两侧均为 BOUNDARY_INVALID（`alpha_resampled_observation_coverage_below_threshold` 类）
- 该静态 Step 1 控制器上未测到可度量的异构效应。`desired_speed` 与 `time_gap` 仍为元数据；需求/半径被观测到，但此处未改变 ABCG 输出。

Holdout 种子 100-119 未用于调参。独立 160-run 结果见 [`STEP1_CLOSURE_REPORT.md`](STEP1_CLOSURE_REPORT.md)（科学成功 110/160）。
