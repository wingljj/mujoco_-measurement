# Response to Reviewers — Round 3 Revision

Dear Editor,

我们感谢编辑与所有审稿人的建设性意见。我们已按 Major Revision 决定信的优先级完成数据核对、补充实验、文献定位、外部基线、统计报告和语言边界修订。以下按 Revision Roadmap 的 ID 逐条回应。

---

## Concern P0-1: 修正 §4.2 Table 数据

> 用 `outputs/ablation_study/ablation_summary.csv` 的真实数据重写表格。

**Author's Response**：我们同意原表格与汇总 CSV 不一致是阻断性问题。修订后的表 3 直接采用汇总 CSV，其中 `no_tilt_barrier` 为 147/150（98.0%），`position_only` 为 45/150（30.0%），`position_orientation` 为 144/150（96.0%）。我们同时新增数据来源脚注和提交前自动一致性检查器。

**Location in Revised Manuscript**：§4.2，表 3。

**Related Commit**：`b86b6f4 review0604_round3_p0_1_fix_table_4_2_data_integrity`；`59d244f review0604_round3_p3_integrity_checker`；`60ec7c8 review0604_round3_p3_fix_integrity_checker_encoding`。

**Verified?**：[x]

---

## Concern P0-2: 重写 §4.3 Findings

> Finding 1/2/3 全部按修正后数据重写；诚实说明“tilt_barrier 在默认权重下从未激活”。

**Author's Response**：我们已删除“倾角屏障至关重要”和“纯位置 IK 导致仿真失败”等不受数据支持的表述。新 Findings 区分了 IK 可达性与仿真跟踪，并明确默认条件下 orientation 项已将倾角压到屏障触发阈值以下。

**Location in Revised Manuscript**：§4.3，发现 1–3。

**Related Commit**：`da9d96b review0604_round3_p0_2_rewrite_findings`；`4e0f38f review0604_round3_p2_language_polish`。

**Verified?**：[x]

---

## Concern P0-3: 补充 tilt_barrier 激活条件实验

> 收紧 `tilt-limit-deg` 到 5° 或 10° 重跑 ablation，观察此时 tilt_barrier 与 no_tilt_barrier 的差别。

**Author's Response**：我们将 `tilt_limit_deg` 收紧到 10°，对两种变体各运行 3 个随机种子 × 50 个目标。两者均取得 147/150（98.0%）仿真成功，平均/全局最大倾角均为 1.17°/5.11°。该阴性结果表明 10° 仍未分离两种配置，因此我们将其表述为“收紧阈值对照”，并明确说明若要量化屏障激活后的效果，仍需更低阈值或更具挑战性的目标集。

**Location in Revised Manuscript**：§4.4，表 4。

**Related Commit**：`6adb1fb review0604_round3_p0_3a_add_tight_tilt_variants`；`61586ab review0604_round3_p0_3b_activation_experiment`。

**Verified?**：[x]

---

## Concern P0-4: 删除 §6.2、§7.3 的 TBD 或跑完实验

> 用 `enhanced_experiments.py --mode dynamic` 跑动态指标并填入完整结果表。

**Author's Response**：我们已完成 30 个目标的动态指标实验，报告最大加速度、Jerk、最大与平均角速度的均值、P50 和 P95。我们也用已有分区 CSV 填充五个工作空间区域的规划与仿真结果，并删除所有“实验运行中”占位符。

**Location in Revised Manuscript**：§6.2，表 8；§7.3，表 9。

**Related Commit**：`6878a7f review0604_round3_p0_4_fill_tbd_sections`。

**Verified?**：[x]

---

## Concern P1-1: 新增 Related Work

> 在 §1 与 §2 之间新增相关工作，覆盖约束 IK、优先级 IK、DLS/SNS、pouring、sloshing 和 TOPP。

**Author's Response**：我们新增六个相关工作子节和 13 条参考文献，并将本文定位为对已有容器运输、sloshing 抑制和时间参数化工作的增量实证补充。所有引用均有对应的文末条目；无法核验的提示词文献未被写入。

**Location in Revised Manuscript**：§1.5.1–§1.5.6；§11 参考文献。

**Related Commit**：`5b51673 review0604_round3_p1_1_related_work`。

**Verified?**：[x]

---

## Concern P1-2: 新增 §4.5 外部 baseline 对比

> 至少选择 1 个外部对手（例如优先级 IK）运行相同 150 个目标。

**Author's Response**：我们实现了位置主任务和竖直姿态零空间次任务的优先级 IK，并在相同随机种子与 150 个目标上比较。优先级 IK 的仿真成功率为 94.0%，完整方法为 98.0%；两者差异为 4 个百分点，未达预设 5% 触发阈值。修订稿同时报告误差、倾角和规划时间。

**Location in Revised Manuscript**：§4.5，表 5。对应的散点图已作为修订包图形产物 `fig08_baseline_comparison.png` 导出。

**Related Commit**：`4866e9f review0604_round3_p1_2a_external_baseline_code`；`490e138 review0604_round3_p1_2_external_baseline`；`9c1ec3f review0604_round3_p2_regenerate_figures`。

**Verified?**：[x]

---

## Concern P1-3: 补充权重敏感度的 sim 层

> 对每个参数的权重水平运行 MuJoCo 仿真，更新 §5.2。

**Author's Response**：我们新增 `--with-sim` 开关，对 24 个权重水平各运行 30 个目标，共得到 720 行规划与仿真明细。表 6 同时报告 IK 与仿真成功率，新增的发现 6 明确区分了两层敏感性。

**Location in Revised Manuscript**：§5.1–§5.3，表 6 和发现 6。

**Related Commit**：`b1c84e9 review0604_round3_p1_3a_sim_layer_sensitivity_code`；`45b965e review0604_round3_p1_3_sim_layer_sensitivity`。

**Verified?**：[x]

---

## Concern P1-4: 修正贡献声明

> 去掉所有“首次”；改为在已有 upright-transport 工作基础上补充系统化消融。

**Author's Response**：我们已重写 §1 和 §9.1 的五项贡献，将每项贡献映射到已核验的相关工作，并删除“首次”“唯一”“严格证明”以及“不可或缺”等超出证据的表述。结论现在明确限定于 KUKA KR20、当前目标分布与位置伺服仿真。

**Location in Revised Manuscript**：§1 贡献列表；§9.1；§9.3。

**Related Commit**：`9504a79 review0604_round3_p1_4_contribution_claim`；`4e0f38f review0604_round3_p2_language_polish`。

**Verified?**：[x]

---

## Concern P2-1: 修正 `98.0% ± σ` 占位符

> 按 seed 计算成功率均值与标准差，替换占位符。

**Author's Response**：3 个随机种子的成功率为 98.0%、96.0% 和 100.0%。修订稿报告为 98.0% ± 1.63%（均值 ± 总体标准差），并标明数据来源。

**Location in Revised Manuscript**：§9.1。

**Related Commit**：`a2a952c review0604_round3_p2_polish_and_placeholders`。

**Verified?**：[x]

---

## Concern P2-2: 补齐 §8.1 标准差

> 从 `full_method_results.csv` 计算 nfev 与规划时间统计，删除空缺单元格。

**Author's Response**：我们已将每条轨迹总 nfev 的标准差报告为 12.41，总规划时间的标准差报告为 0.021 s。同时修正了原稿将“每轨迹 nfev”误写为“每路径点 nfev”的口径问题。

**Location in Revised Manuscript**：§8.1，表 10。

**Related Commit**：`a2a952c review0604_round3_p2_polish_and_placeholders`；`4e0f38f review0604_round3_p2_language_polish`。

**Verified?**：[x]

---

## Concern P2-3: 说明 45° 阈值来源

> 在建模部分说明 45° 倾角阈值的来源与边界。

**Author's Response**：我们未找到足以将 45° 定义为通用工业标准或物理倾洒界限的可核验依据。因此修订稿明确将其定义为本文的粗粒度运动学安全阈值，并结合 sloshing 文献说明真实风险与液位、粘度、容器几何和加速度耦合。

**Location in Revised Manuscript**：§2“倾洒风险判据”及其脚注。

**Related Commit**：`a2a952c review0604_round3_p2_polish_and_placeholders`。

**Verified?**：[x]

---

## Concern P2-4: SO(3) 参数化讨论

> 在 §3.2 讨论交叉积 orientation 残差相对 axis–angle 的选择。

**Author's Response**：新增子节说明交叉积在小倾角下的平滑性、数值梯度和无四元数双覆盖优势，同时明确其在 θ → π 时梯度消失的局限。我们将结论边界限定为本任务中不超过 π/2 的姿态范围。

**Location in Revised Manuscript**：§3.2.1。

**Related Commit**：`a2a952c review0604_round3_p2_polish_and_placeholders`。

**Verified?**：[x]

---

## Concern P2-5: 跨机器人迁移讨论

> 在 §9.2 讨论 7-DOF、力矩控制和移动机械臂的迁移边界。

**Author's Response**：我们新增跨机器人迁移子节。对 7-DOF 机械臂，建议将限位项改写为零空间正则化；对力矩控制，需重做消融；对移动机械臂，需将 base pose 纳入 IK 变量并增加底盘稳定性残差。

**Location in Revised Manuscript**：§9.2.1。

**Related Commit**：`a2a952c review0604_round3_p2_polish_and_placeholders`。

**Verified?**：[x]

---

## Concern P2-6: position_tolerance = 20 mm 的任务规范

> 在 §3.3 说明 20 mm 容差的性质与精密倾倒场景的适用边界。

**Author's Response**：我们明确将 20 mm 定义为本基准任务的成功判定规格，而非通用工业装配公差。修订稿还说明，精密倾倒场景应收紧至 5 mm，并重新评估 IK 可达率和仿真跟踪率。

**Location in Revised Manuscript**：§3.3 脚注。

**Related Commit**：`a2a952c review0604_round3_p2_polish_and_placeholders`。

**Verified?**：[x]

---

## Concern P2-7: 补 §8.1 的 P50 / P95 / max

> 对 nfev 和 plan_time 补充分位数与边界统计。

**Author's Response**：表 10 现在报告每条轨迹总 nfev 的最小值 140、P50 = 180、P95 = 191 和最大值 213；规划时间报告均值 0.182 s、P50 = 0.182 s、P95 = 0.217 s 和最大值 0.266 s。新增运行时讨论还明确当前实现适用于 planner level，而非 500 Hz controller level。

**Location in Revised Manuscript**：§8.1，表 10 及运行时讨论。

**Related Commit**：`a2a952c review0604_round3_p2_polish_and_placeholders`；`4e0f38f review0604_round3_p2_language_polish`。

**Verified?**：[x]

---

我们再次感谢编辑与审稿人的严谨评论，尤其感谢 Devil's Advocate 对数据完整性的质疑。该意见帮助我们定位了表 4.2 未随 CSV 数据源同步更新的问题。本次修订已以原始 CSV 重建表格与 Findings，补充收紧倾角阈值对照、外部优先级 IK、动态代理指标和 sim 层灵敏度，并新增自动完整性检查器以防止类似不一致再次发生。
