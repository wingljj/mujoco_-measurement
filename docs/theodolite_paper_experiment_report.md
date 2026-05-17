# 面向卫星测量任务的机械臂末端经纬仪姿态约束规划实验说明

## 1. 论文任务表述

本项目面向卫星测量任务中机械臂携带经纬仪载荷的末端位姿规划问题。经纬仪作为姿态敏感测量载荷，在机械臂运动过程中不仅需要到达给定目标点，还需要满足工作姿态、机械安装安全边界和观测精度共同决定的倾角安全约束。

现有 MuJoCo 模型中的水杯仅作为经纬仪载荷姿态可视化的等效刚性模型。论文中建议统一表述为“经纬仪末端载荷”或“经纬仪等效刚性载荷”，水杯外观不作为研究对象。

## 2. 研究问题

在给定机械臂可达空间内，如何规划机械臂末端轨迹，使末端经纬仪载荷在运动全过程中不超过给定倾角约束，同时保证最终目标点定位精度和关节轨迹平滑性？

## 3. 本文方法

本文方法采用带姿态安全项的约束逆运动学规划。优化残差由以下部分组成：

- 末端位置误差：保证经纬仪载荷安装点到达目标坐标。
- 载荷竖直轴倾角误差：使经纬仪局部竖直轴尽量与世界竖直方向一致。
- 关节连续性项：抑制相邻路径点之间的关节突变，提高轨迹平滑性。
- 关节限位项：降低关节接近极限位置的风险。
- 倾角越界惩罚项：当载荷倾角超过设定阈值时施加额外惩罚。

轨迹生成采用任务空间直线插值与 cubic smoothstep 时间参数化。每个路径点以上一路径点关节角作为初值进行非线性最小二乘求解，从而提高关节序列连续性。

核心实现位置：

- `src/planner.py`：约束 IK 与轨迹规划。
- `src/simulate_transport.py`：MuJoCo 伺服跟踪仿真与指标记录。
- `src/paper_experiment_figures.py`：方法对比、采样点分布、顺滑性图表。
- `src/tilt_scan_figures.py`：倾角阈值扫描图表。

## 4. 对比方法

为突出本文方法同时满足安全、精度和顺滑性的优势，设置两种传统基线：

1. Position-only IK：仅优化末端位置，不显式约束经纬仪倾角，也不强调关节连续性。
2. Joint interpolation：先求解目标点 IK，再在初始关节角与目标关节角之间进行关节空间平滑插值。

这两种方法分别代表“只关心末端到点”和“关节空间平滑但不显式保证载荷姿态”的常见规划思路。

## 5. 评价指标

实验同时统计以下指标：

- 规划可达数：IK 或轨迹规划成功的目标点数量。
- 完整成功数：最终误差不超过 0.02 m，且全过程最大倾角不超过阈值的目标点数量。
- 最终误差：末端最终位置与目标点之间的欧氏距离。
- 最大观测倾角：运动全过程中经纬仪载荷竖直轴相对世界竖直方向的最大夹角。
- 关节路径长度：关节空间相邻路径点变化量的累计和。
- 最大关节步长：相邻路径点最大关节变化量。
- RMS 关节速度：离散关节速度范数的均方根。
- RMS 关节加速度：离散关节加速度范数的均方根，用于评价轨迹顺滑性。

## 6. 正式 100 点对比实验结果

实验使用相同随机种子 `42`，在机械臂前方工作空间采样 100 个目标点。倾角安全阈值为 45 deg，最终位置误差阈值为 0.02 m。

| 方法 | 规划成功数 | 完整成功数 | 完整成功率 | 有效仿真平均误差/mm | 最大观测倾角/deg | 倾角越界样本数 | RMS 加速度中位数/(rad/s^2) |
|---|---:|---:|---:|---:|---:|---:|---:|
| 本文方法 | 99/100 | 98/100 | 98.0% | 5.01 | 14.36 | 0 | 2.52 |
| Position-only IK | 52/100 | 20/100 | 20.0% | 5.07 | 83.47 | 32 | 68.60 |
| Joint interpolation | 60/100 | 31/100 | 31.0% | 5.11 | 110.45 | 29 | 1.98 |

结果说明：传统方法在有限样本上也能获得毫米级到厘米级末端误差，但由于缺少经纬仪姿态约束，运动过程中容易出现大幅倾角越界。关节空间插值虽然 RMS 加速度较低，但最大倾角达到 110.45 deg，不能满足经纬仪载荷安全要求。本文方法在 100 个采样点中实现 98% 完整成功率，最大观测倾角为 14.36 deg，显著低于 45 deg 阈值。

正式图表输出位置：

- `outputs/paper_runs/figures_100/sampling_constraint_3d.png`
- `outputs/paper_runs/figures_100/method_comparison_metrics.png`
- `outputs/paper_runs/figures_100/smoothness_profile.png`
- `outputs/paper_runs/figures_100/experiment_summary.csv`

## 7. 倾角约束极限扫描

为分析经纬仪倾角约束的可行下限，本文方法在 5 deg、10 deg、12 deg、14 deg、15 deg、20 deg、30 deg、45 deg 八组阈值下进行 100 点仿真。

| 倾角阈值/deg | 规划成功数 | 完整成功数 | 完整成功率 | 最大成功倾角/deg | 平均成功误差/mm |
|---:|---:|---:|---:|---:|---:|
| 5 | 96/100 | 95/100 | 95.0% | 4.03 | 4.56 |
| 10 | 99/100 | 95/100 | 95.0% | 4.03 | 4.56 |
| 12 | 99/100 | 97/100 | 97.0% | 11.29 | 4.68 |
| 14 | 99/100 | 97/100 | 97.0% | 11.29 | 4.68 |
| 15 | 99/100 | 98/100 | 98.0% | 14.36 | 4.73 |
| 20 | 99/100 | 98/100 | 98.0% | 14.36 | 4.73 |
| 30 | 99/100 | 98/100 | 98.0% | 14.36 | 4.73 |
| 45 | 99/100 | 98/100 | 98.0% | 14.36 | 4.73 |

在当前采样空间与控制参数下，如果要求达到 45 deg 基准实验相同的 98/100 完整成功数，最小测试阈值为 15 deg；如果允许成功率降低到 95%，则 5 deg 约束仍可完成 95/100 个目标点。论文中建议采用“15 deg 为本实验条件下达到基准成功率的最小测试阈值”这一更稳妥表述。

倾角扫描图表输出位置：

- `outputs/paper_runs/tilt_scan_summary/tilt_limit_sweep.png`
- `outputs/paper_runs/tilt_scan_summary/tilt_scan_summary.csv`

## 8. 可复现实验命令

```powershell
conda run -n mujoco python src\simulate_transport.py --model kuka_kr20\kuka_kr20_cup_transport.xml --targets 100 --seed 42 --method proposed --out outputs\paper_runs\proposed_100
conda run -n mujoco python src\simulate_transport.py --model kuka_kr20\kuka_kr20_cup_transport.xml --targets 100 --seed 42 --method position_only --out outputs\paper_runs\position_only_100
conda run -n mujoco python src\simulate_transport.py --model kuka_kr20\kuka_kr20_cup_transport.xml --targets 100 --seed 42 --method joint_linear --out outputs\paper_runs\joint_linear_100

python src\paper_experiment_figures.py --results outputs\paper_runs\proposed_100\results.csv outputs\paper_runs\position_only_100\results.csv outputs\paper_runs\joint_linear_100\results.csv --out outputs\paper_runs\figures_100
python src\tilt_scan_figures.py --runs outputs\paper_runs\tilt_scan_5 outputs\paper_runs\tilt_scan_10 outputs\paper_runs\tilt_scan_12 outputs\paper_runs\tilt_scan_14 outputs\paper_runs\tilt_scan_15 outputs\paper_runs\tilt_scan_20 outputs\paper_runs\tilt_scan_30 outputs\paper_runs\proposed_100 --out outputs\paper_runs\tilt_scan_summary
```

## 9. 写入论文时的建议表述

建议不要将研究对象写成“水杯防洒”，而写成：

> 为便于可视化观察末端载荷姿态变化，仿真模型采用透明圆柱体表示经纬仪等效刚性载荷的姿态轴线。该可视化几何仅用于显示载荷倾角，不参与液体动力学或抓取接触分析。

讨论局限性时可写：

> 本文主要验证经纬仪载荷姿态约束下的机械臂位姿规划可行性，暂未考虑经纬仪内部光机结构、安装柔性、标定误差和真实测量闭环反馈。后续可进一步引入测量误差传播模型和实物平台实验。
