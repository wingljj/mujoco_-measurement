# Word 插图指南

本文统一管理 8 张图。所有图均由独立的 XeLaTeX/PGFPlots/TikZ 源文件构建：矢量主文件位于 `figures/pgfplots/build/`，供 Word 使用的 600 DPI PNG 位于 `outputs/word_figures/`。600 DPI PNG 是 Word 插入的可靠主资产。图内不嵌入图号或图题；中文图题应在 Word 中通过“插入题注”另行添加，以便自动编号和交叉引用。

`figures/pgfplots/build/` 中的 PDF 是矢量归档主文件，适合投稿系统、外部矢量转换和质量核对。Word 正文统一插入 PNG，不在同一文稿中交替混用 PNG 与 PDF。确需在 Word 中保留 PDF 对象时，只使用“插入 → 对象 → 由文件创建”；该方式插入的是对象而不是常规图片，不作为正文排版的默认方案。

## 图件清单与排版位置

| 图号 | 文件基名 | 成品尺寸 | 建议位置 | Word 中文图题 |
|---|---|---:|---|---|
| 图1 | `fig01_method_pipeline` | 15 cm × 6 cm | 引言的研究目标与完整工作流之后 | 图1 机械臂持经纬仪测站转移的规划、执行与到位测量流程 |
| 图2 | `fig02_workspace_multiview` | 15 cm × 6 cm | 第6节工作空间目标分布 | 图2 五类目标测站在XY、XZ和YZ平面的空间分布 |
| 图3 | `fig03_transport_sequence` | 15 cm × 5.5 cm | 第7节轨迹生成与运输阶段说明 | 图3 机械臂持经纬仪转移过程的五阶段姿态示意 |
| 图4 | `fig04_case_study` | 15 cm × 9 cm | 第7节代表性任务分析 | 图4 代表性测站任务的轨迹、关节角、经纬仪倾角与逐路径点IK位置残差 |
| 图5 | `fig05_ablation_comparison` | 8 cm × 6 cm，单栏 | 第8节消融结果 | 图5 四种残差配置的IK可达率与仿真成功率 |
| 图6 | `fig06_error_tilt_margin` | 15 cm × 6 cm | 第8节误差、倾角与姿态裕度经验累积分布 | 图6 完整方法的位置误差、经纬仪最大倾角及相对10°阈值的姿态裕度 |
| 图7 | `fig07_dynamic_metrics` | 15 cm × 8 cm | 第10节规划轨迹动态代理结果 | 图7 成功测站转移任务的运输动态扰动代理指标分布 |
| 图8 | `fig08_baseline_comparison` | 8 cm × 6 cm，单栏 | 第11节外部基线比较 | 图8 本文方法与优先级IK在匹配测站目标上的位置误差—倾角对比 |

图3是五阶段轨迹姿态示意，不是真实仪器动力学渲染。图7展示规划轨迹的动态代理量，并采用统一的合成 0–2 s 时间参数化；它不是 MuJoCo 跟踪动力学或真实仪器时序测量结果，排版时不得删去正文中的这一限制说明。

## 文件命名对照

| 图号 | Word PNG（600 DPI） | 矢量 PDF 主文件 |
|---|---|---|
| 图1 | `outputs/word_figures/fig01_method_pipeline.png` | `figures/pgfplots/build/fig01_method_pipeline.pdf` |
| 图2 | `outputs/word_figures/fig02_workspace_multiview.png` | `figures/pgfplots/build/fig02_workspace_multiview.pdf` |
| 图3 | `outputs/word_figures/fig03_transport_sequence.png` | `figures/pgfplots/build/fig03_transport_sequence.pdf` |
| 图4 | `outputs/word_figures/fig04_case_study.png` | `figures/pgfplots/build/fig04_case_study.pdf` |
| 图5 | `outputs/word_figures/fig05_ablation_comparison.png` | `figures/pgfplots/build/fig05_ablation_comparison.pdf` |
| 图6 | `outputs/word_figures/fig06_error_tilt_margin.png` | `figures/pgfplots/build/fig06_error_tilt_margin.pdf` |
| 图7 | `outputs/word_figures/fig07_dynamic_metrics.png` | `figures/pgfplots/build/fig07_dynamic_metrics.pdf` |
| 图8 | `outputs/word_figures/fig08_baseline_comparison.png` | `figures/pgfplots/build/fig08_baseline_comparison.pdf` |

## Word 插入步骤

1. 在正文指定位置选择“插入 → 图片 → 此设备”，选择对应 PNG；不要在此图片选择器中以 PDF 替代 PNG。
2. 将版式设为“上下型环绕”或期刊模板要求的嵌入方式，锁定纵横比，并按清单设置物理宽度和高度。
3. 图片段落居中，段前、段后间距服从投稿模板；不要在 Word 中拉伸、压缩或二次裁切图内数据区域。
4. 在图片下方选择“引用 → 插入题注”，类别设为“图”，粘贴清单中的中文图题；图号和图题不要烘焙进图片。
5. 正文通过“引用 → 交叉引用 → 图”插入引用，避免手工维护图号。
6. 导出 PDF 后在 100% 和 200% 缩放下检查轴标签、图例、线型和中文字符，并确认图题未与图片分离到下一页。

## 600 DPI 尺寸核查

600 DPI 下，像素尺寸按 `物理尺寸（cm）÷ 2.54 × 600` 换算。名义宽度 8 cm 的单栏图约为 1890 px，名义宽度 15 cm 的图约为 3543 px；这是加入约 1 pt 边框及独立文档裁边前的画布换算值，最终像素边界可有少量差异。

| 成品尺寸 | 600 DPI 名义像素尺寸（约） |
|---|---:|
| 15 cm × 6 cm | 3543 × 1417 px |
| 15 cm × 5.5 cm | 3543 × 1299 px |
| 15 cm × 9 cm | 3543 × 2126 px |
| 8 cm × 6 cm | 1890 × 1417 px |
| 15 cm × 8 cm | 3543 × 1890 px |

若 PNG 像素数量明显低于表中名义值，应回到统一 XeLaTeX/PGFPlots/TikZ 构建流程重新生成，不要在 Word 中放大低分辨率位图。交付前必须保证每个文件基名同时存在非空 PNG 与非空 PDF。
