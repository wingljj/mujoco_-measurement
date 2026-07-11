# Round 3 修订最终自检清单

## 数据完整性

- [x] `check_data_integrity.py --strict` PASS
- [x] 无“实验运行中”、`TBD`、`TODO`、`XXX`、`??`、`± σ`、“标准差 -”或“首次”残留
- [x] 表 3 的四个消融变体与 `outputs/ablation_study/ablation_summary.csv` 完全一致
- [x] 误差与倾角安全统计包含所有实际执行的仿真，未排除仿真失败轨迹
- [x] 外部 baseline 的 150 个目标已逐行匹配，精确双侧 McNemar 二项检验为 p = 0.03125
- [x] 13 个正文引用键与 13 条参考文献一一对应

## 图片

- [x] Fig. 1–Fig. 6 存在，PNG 为 360 DPI
- [x] Fig. 7 dynamic metrics 存在，PNG/PDF 已导出
- [x] Fig. 8 baseline comparison 存在，PNG/PDF 已导出
- [x] `outputs/word_figures/` 共有 8 张 `fig*.png`，像素尺寸和 DPI 已用 Pillow 核验
- [x] `docs/theory_and_simulation.md` 中的 Markdown 图片引用均指向存在文件
- [x] Fig. 5 的 `no_tilt_barrier` 仿真成功率显示为 98.0%

## 章节

- [x] §1 Introduction 已重写贡献声明
- [x] §1.5 Related Work 已新增，覆盖 IK、DLS/SNS、容器运输、sloshing 和 TOPP
- [x] §4.2 数据一致性已修复
- [x] §4.3 Findings 已按真实 CSV 重写
- [x] §4.4 收紧倾角阈值对照已新增
- [x] §4.5 外部优先级 IK baseline 已新增
- [x] §5.2 sim 层权重敏感度已补齐
- [x] §6.2 工作空间分区结果已填入
- [x] §7.3 动态代理指标结果已填入
- [x] §9.2.1 跨机器人迁移讨论已新增
- [x] §11 参考文献已新增，共13 条可核验条目

## 语言与格式

- [x] 无“首次”等无证据强断言
- [x] 核心 claim 已按“本实验条件下”、“数据表明”和限制条件校准
- [x] 10 张 Markdown 表均有表号、表题和数据/实现来源
- [x] 图 1 有图号、图题和正文显式引用
- [x] 数学公式中的主要变量已在首次出现附近给出语义
- [x] 参考文献格式统一为 IEEE 简式

## 待办

- [ ] 10° 收紧阈值实验仍未实际分离 `full_tight10` 与 `no_barrier_tight10`。两种变体的规划倾角峰值均为 5.14°，但仿真倾角峰值达 10.15°。若投稿时仍希望主张 tilt barrier 的独立贡献，需使用低于 5.14° 的规划阈值，或构造更具挑战性的目标集；当前稿件已将该点如实写为阴性结果与限制。
- [ ] 目标期刊尚未指定。正式投稿前需再核对期刊的章节顺序、字数、引用格式、图尺寸与 AI 使用披露要求。
