# 经纬仪测量主题论文与 pgfplots 图组重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将论文正文、图题和8张插图统一重构为“机械臂持经纬仪测站转移与到位稳定测量”主题，并交付可追溯的 pgfplots/TikZ 源码、裁剪 PDF 和600 DPI PNG。

**Architecture:** 使用一个纯数据准备脚本把现有 CSV/NPZ 转换为只含绘图字段的稳定 CSV，再由8个独立 `standalone` 文档通过公共样式包读取。PowerShell 构建脚本负责 XeLaTeX 编译、PDF检查和 Poppler PNG转换；正文和 Word 插图指南只引用新输出，不改变原始实验数据。

**Tech Stack:** Python 3、NumPy、标准库 `csv`/`unittest`、XeLaTeX、TikZ、pgfplots 1.18、latexmk、Poppler (`pdfinfo`/`pdffonts`/`pdftoppm`)、PowerShell、Markdown。

---

## 文件结构

**新建**

- `scripts/prepare_pgfplots_data.py`：读取原始实验文件，验证字段并生成图2、4–8使用的绘图 CSV。
- `tests/test_prepare_pgfplots_data.py`：验证代表任务选择、ECDF、直方分箱、单位转换和配对数据规则。
- `figures/pgfplots/jmechplots.sty`：全局《机械工程学报》风格、尺寸接口、中文字体、颜色和系列样式。
- `figures/pgfplots/fig01_method_pipeline.tex`：方法流程图。
- `figures/pgfplots/fig02_workspace_multiview.tex`：工作空间三视图。
- `figures/pgfplots/fig03_transport_sequence.tex`：经纬仪转移五阶段示意。
- `figures/pgfplots/fig04_case_study.tex`：代表任务四联图。
- `figures/pgfplots/fig05_ablation_comparison.tex`：消融分组柱图。
- `figures/pgfplots/fig06_error_tilt_margin.tex`：误差、倾角与10°裕度三联 ECDF。
- `figures/pgfplots/fig07_dynamic_metrics.tex`：动态代理四联直方图。
- `figures/pgfplots/fig08_baseline_comparison.tex`：基线散点图。
- `figures/pgfplots/build_figures.ps1`：数据准备、编译、检查和600 DPI转换入口。
- `figures/pgfplots/data/*.csv`：可追溯绘图数据。
- `figures/pgfplots/build/*.pdf`：紧裁剪矢量输出。

**修改**

- `docs/theory_and_simulation.md`：统一论文主题、证据边界、8张图题与引用。
- `review-stage/round2_review/WORD_FIGURE_GUIDE.md`：更新图名、尺寸、图题、DPI和 Word 插入说明。
- `review-stage/round2_review/check_data_integrity.py`：增加经纬仪主题残留词和新图输出检查。
- `tests/test_data_integrity.py`：覆盖新增完整性规则。

**保留不动**

- `outputs/**/*.csv`、`outputs/**/*.npz`：原始实验数据。
- `src/paper_figures.py`：旧 Matplotlib 生成器作为历史复现脚本保留，但正文和指南不再调用它生成投稿图。

---

### Task 1: 数据准备模块与单元测试

**Files:**
- Create: `scripts/prepare_pgfplots_data.py`
- Create: `tests/test_prepare_pgfplots_data.py`
- Create: `figures/pgfplots/data/.gitkeep`

- [ ] **Step 1: 编写代表任务、ECDF和直方分箱的失败测试**

测试应使用临时 CSV/NPZ，不读取工作区大文件。核心断言如下：

```python
import csv
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from prepare_pgfplots_data import (
    empirical_cdf,
    histogram_rows,
    select_representative_target,
)


class PreparePgfplotsDataTests(unittest.TestCase):
    def test_selects_successful_case_nearest_median_error(self):
        rows = [
            {"target_id": "0", "sim_success": "True", "final_error_m": "0.002"},
            {"target_id": "1", "sim_success": "False", "final_error_m": "0.004"},
            {"target_id": "2", "sim_success": "True", "final_error_m": "0.006"},
            {"target_id": "3", "sim_success": "True", "final_error_m": "0.010"},
        ]
        self.assertEqual(select_representative_target(rows), 2)

    def test_empirical_cdf_is_sorted_and_inclusive(self):
        self.assertEqual(empirical_cdf([3.0, 1.0, 2.0]), [(1.0, 1/3), (2.0, 2/3), (3.0, 1.0)])

    def test_histogram_rows_preserve_count(self):
        rows = histogram_rows([1.0, 1.2, 1.8, 2.1], bins=2, log_scale=False)
        self.assertEqual(sum(row["count"] for row in rows), 4)
        self.assertTrue(all(row["left"] < row["right"] for row in rows))

    def test_log_histogram_rejects_nonpositive_values(self):
        with self.assertRaisesRegex(ValueError, "positive"):
            histogram_rows([0.0, 1.0], bins=3, log_scale=True)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试并确认失败**

Run:

```powershell
conda run -n mujoco python -m unittest tests.test_prepare_pgfplots_data -v
```

Expected: `ModuleNotFoundError: No module named 'prepare_pgfplots_data'`。

- [ ] **Step 3: 实现纯函数和数据导出入口**

`scripts/prepare_pgfplots_data.py` 必须包含以下公开接口和固定源文件映射：

```python
from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Iterable

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "figures" / "pgfplots" / "data"


def as_bool(value: str) -> bool:
    return value.strip().lower() in {"true", "1", "yes"}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def select_representative_target(rows: list[dict[str, str]]) -> int:
    successful = [row for row in rows if as_bool(row["sim_success"]) and row["final_error_m"]]
    if not successful:
        raise ValueError("no successful simulation rows")
    errors = np.asarray([float(row["final_error_m"]) for row in successful])
    median = float(np.median(errors))
    selected = min(successful, key=lambda row: (abs(float(row["final_error_m"]) - median), int(row["target_id"])))
    return int(selected["target_id"])


def empirical_cdf(values: Iterable[float]) -> list[tuple[float, float]]:
    ordered = sorted(float(value) for value in values if np.isfinite(value))
    if not ordered:
        raise ValueError("ECDF requires finite values")
    count = len(ordered)
    return [(value, (index + 1) / count) for index, value in enumerate(ordered)]


def histogram_rows(values: Iterable[float], bins: int, log_scale: bool) -> list[dict[str, float | int]]:
    array = np.asarray([float(value) for value in values if np.isfinite(value)], dtype=float)
    if array.size == 0:
        raise ValueError("histogram requires finite values")
    if log_scale and np.any(array <= 0):
        raise ValueError("log histogram values must be positive")
    edges = np.geomspace(array.min() * 0.9, array.max() * 1.1, bins + 1) if log_scale else np.linspace(array.min(), array.max(), bins + 1)
    counts, edges = np.histogram(array, bins=edges)
    return [
        {"left": float(edges[i]), "right": float(edges[i + 1]), "center": float((edges[i] + edges[i + 1]) / 2), "count": int(counts[i])}
        for i in range(len(counts))
    ]
```

入口 `main()` 依次输出：

- `fig02_workspace.csv`：`target_id,region_cn,x,y,z,sim_success,max_tilt_deg`，区域映射为标准区、宽方位角区、低伸区、高伸区、远距离区。
- `fig04_meta.csv`：唯一一行 `target_id,target_x,target_y,target_z,final_error_mm,max_tilt_deg`。
- `fig04_trajectory.csv`：`sample,x,y,z,desired_x,desired_y,desired_z,ik_error_mm`；期望路径用首个规划末端点至目标点的 cubic smoothstep 重建。
- `fig04_joints.csv`：`sample,q1,q2,q3,q4,q5,q6`。
- `fig04_tilt.csv`：`time_s,tilt_deg`。
- `fig05_ablation.csv`：中文方法名、`ik_rate_pct,sim_rate_pct`。
- `fig06_error_ecdf.csv`、`fig06_tilt_ecdf.csv`、`fig06_margin_ecdf.csv`；使用所有实际执行且数值有限的 full-method 仿真，误差转 mm，裕度为 `10-max_tilt_deg`。
- `fig07_histograms.csv`：`metric,left,right,center,count,median,log_scale`；加速度线性10箱，其余三项对数9箱。
- `fig08_baselines.csv`：`target_id,method_cn,error_mm,tilt_deg,sim_success`；两个文件按 `target_id` 内连接并各输出一行，确保相同目标配对。

命令行接口固定为：

```python
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    return parser
```

- [ ] **Step 4: 添加工作区数据的集成断言**

在测试文件加入：

```python
    def test_workspace_sources_have_expected_cardinality(self):
        root = Path(__file__).resolve().parents[1]
        expanded = read_csv(root / "outputs/round2_experiments/expanded_workspace_results.csv")
        full = read_csv(root / "outputs/ablation_study/full_method_results.csv")
        priority = read_csv(root / "outputs/external_baselines/priority_ik_results.csv")
        self.assertEqual(len(expanded), 80)
        self.assertEqual(len(full), 150)
        self.assertEqual({row["target_id"] for row in full}, {row["target_id"] for row in priority})
```

并把 `read_csv` 加入 import 列表。

- [ ] **Step 5: 运行测试与数据生成**

Run:

```powershell
conda run -n mujoco python -m unittest tests.test_prepare_pgfplots_data -v
conda run -n mujoco python scripts/prepare_pgfplots_data.py
```

Expected: 5 tests PASS；`figures/pgfplots/data/` 生成11个非空 CSV，代表任务元数据恰好1行。

- [ ] **Step 6: 提交数据准备模块**

```powershell
git add scripts/prepare_pgfplots_data.py tests/test_prepare_pgfplots_data.py figures/pgfplots/data
git commit -m "feat: prepare traceable pgfplots source data"
```

---

### Task 2: 公共 pgfplots 样式与构建冒烟测试

**Files:**
- Create: `figures/pgfplots/jmechplots.sty`
- Create: `figures/pgfplots/build_figures.ps1`
- Create temporarily then remove: `figures/pgfplots/style_smoke.tex`

- [ ] **Step 1: 创建会因样式缺失而失败的最小文档**

```tex
\documentclass[tikz,border=1pt]{standalone}
\usepackage{jmechplots}
\begin{document}
\begin{tikzpicture}
\begin{axis}[jmech/single,xlabel={时间 / s},ylabel={倾角 /(°)}]
\addplot[jmech/series blue] coordinates {(0,0) (1,1)};
\end{axis}
\end{tikzpicture}
\end{document}
```

- [ ] **Step 2: 编译并确认失败**

Run:

```powershell
Push-Location figures/pgfplots
xelatex -halt-on-error style_smoke.tex
Pop-Location
```

Expected: FAIL，提示 `jmechplots.sty not found`。

- [ ] **Step 3: 实现公共样式**

`jmechplots.sty` 至少定义以下完整公共接口：

```tex
\NeedsTeXFormat{LaTeX2e}
\ProvidesPackage{jmechplots}[2026/07/11 Unified Chinese journal plots]
\RequirePackage[UTF8,fontset=windows]{ctex}
\RequirePackage{pgfplots}
\RequirePackage{pgfplotstable}
\RequirePackage{siunitx}
\RequirePackage{xcolor}
\pgfplotsset{compat=1.18}
\usepgfplotslibrary{groupplots,statistics,fillbetween}
\usetikzlibrary{arrows.meta,calc,positioning,shapes.geometric,patterns.meta}
\definecolor{JBlue}{HTML}{244A73}
\definecolor{JRed}{HTML}{8C3B3B}
\definecolor{JGreen}{HTML}{426B57}
\definecolor{JGold}{HTML}{9A7432}
\definecolor{JGray}{HTML}{666666}
\definecolor{JLightGray}{HTML}{D8D8D8}
\sisetup{detect-all,per-mode=symbol}
\newcommand{\SingleWidth}{8cm}
\newcommand{\DoubleWidth}{15cm}
\pgfplotsset{
  jmech/base/.style={
    axis lines=box,
    axis line style={line width=0.7pt,black},
    tick align=inside,
    major tick length=3pt,
    minor tick length=1.5pt,
    tick label style={font=\fontsize{8}{9.6}\selectfont},
    label style={font=\fontsize{8}{9.6}\selectfont},
    title style={font=\fontsize{8}{9.6}\selectfont},
    legend style={font=\fontsize{8}{9.6}\selectfont,draw=none,fill=none,cells={anchor=west}},
    line width=0.8pt,
    grid=none,
    scaled ticks=false,
    every axis plot/.append style={line width=0.9pt},
  },
  jmech/single/.style={jmech/base,width=\FigWidth,height=\FigHeight},
  jmech/series blue/.style={JBlue,solid,mark=o,mark options={fill=white,solid},mark size=1.6pt},
  jmech/series red/.style={JRed,dashed,mark=square,mark options={fill=white,solid},mark size=1.5pt},
  jmech/series green/.style={JGreen,dash dot,mark=triangle,mark options={fill=white,solid},mark size=1.7pt},
  jmech/series black/.style={black,densely dotted,mark=diamond,mark options={fill=white,solid},mark size=1.5pt},
  jmech/threshold/.style={JRed,dashed,line width=0.8pt,no marks},
  jmech/light grid/.style={grid=major,major grid style={JLightGray,densely dashed,line width=0.25pt}},
}
```

- [ ] **Step 4: 编译样式冒烟文档并检查字体**

Run:

```powershell
Push-Location figures/pgfplots
xelatex -halt-on-error -interaction=nonstopmode style_smoke.tex
pdffonts style_smoke.pdf
Pop-Location
```

Expected: 编译成功；`pdffonts` 显示中文字体 `emb=yes`。

- [ ] **Step 5: 实现统一构建脚本**

`build_figures.ps1` 接受 `-SkipData`，默认执行数据准备；对8个固定 basename 运行 `latexmk -xelatex`，再运行：

```powershell
pdfinfo $pdf | Select-String 'Page size'
pdffonts $pdf
pdftoppm -png -r 600 -singlefile $pdf $pngStem
Copy-Item -Force $png "$Root\outputs\word_figures\$name.png"
```

脚本启用 `$ErrorActionPreference = 'Stop'`，任何 TeX、字体或转换命令退出码非零时抛错；输出 PDF 复制至 `figures/pgfplots/build/`。8个名称固定为：

```powershell
$Figures = @(
  'fig01_method_pipeline','fig02_workspace_multiview','fig03_transport_sequence',
  'fig04_case_study','fig05_ablation_comparison','fig06_error_tilt_margin',
  'fig07_dynamic_metrics','fig08_baseline_comparison'
)
```

- [ ] **Step 6: 删除冒烟产物并提交**

```powershell
Remove-Item figures/pgfplots/style_smoke.aux,figures/pgfplots/style_smoke.log,figures/pgfplots/style_smoke.pdf,figures/pgfplots/style_smoke.tex -ErrorAction SilentlyContinue
git add figures/pgfplots/jmechplots.sty figures/pgfplots/build_figures.ps1
git commit -m "feat: add unified pgfplots journal style"
```

---

### Task 3: 图1方法流程与图3运输姿态示意

**Files:**
- Create: `figures/pgfplots/fig01_method_pipeline.tex`
- Create: `figures/pgfplots/fig03_transport_sequence.tex`

- [ ] **Step 1: 编写两个 standalone 文档**

图1固定为 `\FigWidth=15cm`、`\FigHeight=6cm`，使用5个圆角矩形：目标测站采样、五项残差约束、顺序热启动 IK、轨迹执行评估、到位稳定测量。下方绘制经纬仪竖轴、世界竖直方向和倾角 `\theta`，并写明“45°粗粒度安全上限；10°保守运输阈值”。流程框只用 JBlue/JGreen/JGold 的低饱和浅色填充，文字为黑色。

图3固定为 `15cm × 5.5cm`，用一条 cubic smoothstep 示意轨迹和5个等间隔阶段。每个阶段用相同的简化经纬仪图标（底座、水平度盘、望远镜、竖轴）表示，竖轴与世界竖直方向夹角保持小量；右下角必须写“轨迹姿态示意，非仪器动力学渲染”。

两个文件统一采用：

```tex
\documentclass[tikz,border=1pt]{standalone}
\newcommand{\FigWidth}{15cm}
\newcommand{\FigHeight}{6cm} % 图3改为5.5cm
\usepackage{jmechplots}
\begin{document}
\begin{tikzpicture}[font=\fontsize{8}{9.6}\selectfont,>=Latex]
% 所有节点使用明确坐标或 positioning；不使用外部位图
\end{tikzpicture}
\end{document}
```

- [ ] **Step 2: 单独编译并检查页面尺寸**

Run:

```powershell
Push-Location figures/pgfplots
latexmk -xelatex -halt-on-error fig01_method_pipeline.tex
latexmk -xelatex -halt-on-error fig03_transport_sequence.tex
pdfinfo fig01_method_pipeline.pdf | Select-String 'Page size'
pdfinfo fig03_transport_sequence.pdf | Select-String 'Page size'
Pop-Location
```

Expected: 两份 PDF 编译成功；裁剪边界无异常空白，图1约15 cm宽、图3约15 cm宽。

- [ ] **Step 3: 提交两张示意图**

```powershell
git add figures/pgfplots/fig01_method_pipeline.tex figures/pgfplots/fig03_transport_sequence.tex
git commit -m "feat: redraw theodolite method and transport schematics"
```

---

### Task 4: 图2工作空间与图4代表任务

**Files:**
- Create: `figures/pgfplots/fig02_workspace_multiview.tex`
- Create: `figures/pgfplots/fig04_case_study.tex`

- [ ] **Step 1: 实现图2三联投影**

使用 `groupplot` 的 `group size=3 by 1`，分别读取同一 `data/fig02_workspace.csv` 的 `(x,y)`、`(x,z)`、`(y,z)`。五个区域固定映射为不同线型/空心标记，区域颜色跨三个子图保持一致；机械臂基座以黑色实心三角标记。轴标签为“X / m”“Y / m”“Z / m”，子图标题为“俯视投影”“正视投影”“侧视投影”。图例置于整图下方一行，不使用彩虹色或连续色条。

文件头：

```tex
\documentclass[tikz,border=1pt]{standalone}
\newcommand{\FigWidth}{15cm}
\newcommand{\FigHeight}{6cm}
\usepackage{jmechplots}
\begin{document}
\begin{tikzpicture}
\begin{groupplot}[group style={group size=3 by 1,horizontal sep=1.0cm},jmech/base,width=4.45cm,height=4.8cm]
% 每个区域通过 restrict expr to domain 或 row predicate 从 region_cn 过滤
\end{groupplot}
\end{tikzpicture}
\end{document}
```

- [ ] **Step 2: 实现图4四联过程证据**

采用 `group size=2 by 2`：

1. `(a)` XZ 平面上的期望轨迹与实际末端轨迹，起点为空心圆、目标点为空心星形；
2. `(b)` 六个关节角随路径点变化，使用6种颜色/线型组合；
3. `(c)` 仿真经纬仪最大倾角时序，绘制10°保守运输阈值；
4. `(d)` 逐路径点 IK 位置残差，绘制20 mm任务判定线。

读取 `fig04_trajectory.csv`、`fig04_joints.csv`、`fig04_tilt.csv`，不得把 `plan_nfev` 当作逐迭代收敛曲线。整图15 cm × 9 cm，子图字母置于各轴左上角。

- [ ] **Step 3: 编译并目视检查图例与轴标签**

Run:

```powershell
Push-Location figures/pgfplots
latexmk -xelatex -halt-on-error fig02_workspace_multiview.tex
latexmk -xelatex -halt-on-error fig04_case_study.tex
pdftoppm -png -r 180 -singlefile fig02_workspace_multiview.pdf build/preview_fig02
pdftoppm -png -r 180 -singlefile fig04_case_study.pdf build/preview_fig04
Pop-Location
```

Expected: 三视图比例一致；图4无曲线跨出轴框、无图例覆盖数据、10°和20 mm阈值标签清晰。

- [ ] **Step 4: 提交图2与图4**

```powershell
git add figures/pgfplots/fig02_workspace_multiview.tex figures/pgfplots/fig04_case_study.tex
git commit -m "feat: redraw workspace and representative trajectory figures"
```

---

### Task 5: 图5消融与图6姿态裕度

**Files:**
- Create: `figures/pgfplots/fig05_ablation_comparison.tex`
- Create: `figures/pgfplots/fig06_error_tilt_margin.tex`

- [ ] **Step 1: 实现图5分组柱状图**

读取 `fig05_ablation.csv`，每个方法并排绘制 IK 可达率与仿真成功率。使用 JBlue 实色斜线填充与 JRed 空心交叉填充，柱顶标注一位小数；Y轴0–105%，X轴四类中文方法名允许两行换行。图例置于右下数据空白处，尺寸8 cm × 6 cm。

关键轴配置：

```tex
ybar,
bar width=5pt,
ymin=0,ymax=105,
ylabel={成功率 / \%},
symbolic x coords={完整方法,无倾角屏障,纯位置,位置+姿态},
xtick=data,
nodes near coords={\pgfmathprintnumber[fixed,precision=1]{\pgfplotspointmeta}},
```

- [ ] **Step 2: 实现图6三联 ECDF**

整图15 cm × 6 cm，三个轴分别读取误差、倾角和姿态裕度 ECDF。误差图标注20 mm判定线；倾角图标注10°保守运输阈值；裕度图标注0°边界，负值代表超过保守阈值。Y轴统一为“累计比例”，范围0–1；仅第一个子图显示Y标签。

- [ ] **Step 3: 编译并核对柱高与ECDF终点**

Run:

```powershell
Push-Location figures/pgfplots
latexmk -xelatex -halt-on-error fig05_ablation_comparison.tex
latexmk -xelatex -halt-on-error fig06_error_tilt_margin.tex
Pop-Location
conda run -n mujoco python -c "import csv; r=list(csv.DictReader(open('figures/pgfplots/data/fig05_ablation.csv',encoding='utf-8'))); print([(x['method_cn'],x['ik_rate_pct'],x['sim_rate_pct']) for x in r])"
```

Expected: 输出依次包含完整方法98.6667/98.0、无倾角屏障98.6667/98.0、纯位置30.0/30.0、位置+姿态100.0/96.0；三条 ECDF 的最后一点均为1.0。

- [ ] **Step 4: 提交图5与图6**

```powershell
git add figures/pgfplots/fig05_ablation_comparison.tex figures/pgfplots/fig06_error_tilt_margin.tex
git commit -m "feat: redraw ablation and posture margin figures"
```

---

### Task 6: 图7动态代理与图8外部基线

**Files:**
- Create: `figures/pgfplots/fig07_dynamic_metrics.tex`
- Create: `figures/pgfplots/fig08_baseline_comparison.tex`

- [ ] **Step 1: 实现图7四联直方图**

按 `metric` 过滤 `fig07_histograms.csv`。最大加速度使用线性X轴；最大 Jerk、最大角速度和平均角速度使用 `xmode=log`。每个子图绘制柱形计数与黑色虚线中位数，不使用均值线以避免单个异常样本误导。标题分别为“最大加速度”“最大 Jerk”“最大角速度”“平均角速度”，单位写在X轴，Y轴为“样本数”。整图15 cm × 8 cm。

- [ ] **Step 2: 实现图8配对目标散点图**

读取 `fig08_baselines.csv`：本文方法使用深蓝空心圆，优先级 IK 使用深红空心三角。X轴最终位置误差/mm，Y轴最大经纬仪倾角/(°)；绘制20 mm任务判定线和10°保守运输阈值。只绘制数值有限的实际仿真记录，失败点仍保留并以相同标记加黑色叉号叠加。尺寸8 cm × 6 cm。

- [ ] **Step 3: 编译并核对样本数**

Run:

```powershell
Push-Location figures/pgfplots
latexmk -xelatex -halt-on-error fig07_dynamic_metrics.tex
latexmk -xelatex -halt-on-error fig08_baseline_comparison.tex
Pop-Location
conda run -n mujoco python -c "import csv,collections; r=list(csv.DictReader(open('figures/pgfplots/data/fig08_baselines.csv',encoding='utf-8'))); print(collections.Counter(x['method_cn'] for x in r))"
```

Expected: 两种方法各150行；图7四个面板的直方计数各合计30。

- [ ] **Step 4: 提交图7与图8**

```powershell
git add figures/pgfplots/fig07_dynamic_metrics.tex figures/pgfplots/fig08_baseline_comparison.tex
git commit -m "feat: redraw dynamic proxy and baseline figures"
```

---

### Task 7: 论文主题重写与插图引用

**Files:**
- Modify: `docs/theory_and_simulation.md`

- [ ] **Step 1: 先写主题残留扫描并确认当前失败**

Run:

```powershell
rg -n "持杯|杯体|防洒|倾洒|液体|晃动|容器运输|sloshing" docs/theory_and_simulation.md
```

Expected: 找到标题、相关工作、建模、倾角判据、动态图指标、讨论和结论中的多处旧主题词。

- [ ] **Step 2: 重写标题、摘要式研究目标和系统建模**

采用标题“面向经纬仪测站转移的机械臂约束逆运动学与姿态保持研究”。在开头明确：经纬仪刚性安装在末端；运动阶段不测量；到达并稳定后才测量；倾角是测量准备风险代理。第2节改名“机械臂与经纬仪建模”，将 `z_cup` 的展示符号改为 `z_inst`，但注明实现代码中的历史变量名不影响数学含义。

- [ ] **Step 3: 重写相关工作与方法解释**

保留约束 IK、优先级 IK、阻尼最小二乘和时间参数化文献；删除把液体容器运输与 sloshing 当作本文直接相关证据的段落。新增“机器人化测量与仪器姿态保持”的谨慎定位，不添加未经核验的经纬仪精度数值或标准。残差表中将姿态约束、倾角软屏障的作用改为保持经纬仪竖轴和限制运输倾斜。

- [ ] **Step 4: 重写实验结果、讨论和结论**

保持所有表格数值不变；将动态指标解释为仪器结构激励与到位稳定恢复负担的代理。45°始终写作“粗粒度机械安全上限”，10°写作“本文保守运输阈值”。在限制中新增“缺少具体经纬仪型号、真实标定与角秒精度实验”，并删除任何“倾角直接导致已测得精度损失”的强因果表述。

- [ ] **Step 5: 在对应章节插入8张图及中文图题**

链接固定为：

```markdown
![图1 机械臂持经纬仪测站转移的规划、执行与到位测量流程](../outputs/word_figures/fig01_method_pipeline.png)
![图2 五类目标测站在XY、XZ和YZ平面的空间分布](../outputs/word_figures/fig02_workspace_multiview.png)
![图3 机械臂持经纬仪转移过程的五阶段姿态示意](../outputs/word_figures/fig03_transport_sequence.png)
![图4 代表性测站任务的轨迹、关节角、经纬仪倾角与逐路径点IK位置残差](../outputs/word_figures/fig04_case_study.png)
![图5 四种残差配置的IK可达率与仿真成功率](../outputs/word_figures/fig05_ablation_comparison.png)
![图6 完整方法的位置误差、经纬仪最大倾角及相对10°阈值的姿态裕度](../outputs/word_figures/fig06_error_tilt_margin.png)
![图7 成功测站转移任务的运输动态扰动代理指标分布](../outputs/word_figures/fig07_dynamic_metrics.png)
![图8 本文方法与优先级IK在匹配测站目标上的位置误差—倾角对比](../outputs/word_figures/fig08_baseline_comparison.png)
```

图1放研究目标末尾，图2放第6.1节，图3放第3.4节，图4放第3.4节之后，图5放第4.2节，图6放第4.3节，图7放第7.3节，图8放第4.5节。

- [ ] **Step 6: 扫描主题与证据边界**

Run:

```powershell
rg -n "持杯|杯体|防洒|倾洒|液体|晃动|容器运输|sloshing" docs/theory_and_simulation.md
rg -n "测量精度提高了|精度提升[0-9]|角秒|行业标准|允许倾角" docs/theory_and_simulation.md
rg -n "!\[图[1-8]" docs/theory_and_simulation.md
```

Expected: 第一条无结果，或只出现明确标记为历史实现/被排除研究范围的说明；第二条无未经支持的定量因果主张；第三条恰好8行。

- [ ] **Step 7: 提交论文重写**

```powershell
git add docs/theory_and_simulation.md
git commit -m "docs: reframe manuscript around theodolite station transfer"
```

---

### Task 8: Word 插图指南与完整性检查

**Files:**
- Modify: `review-stage/round2_review/WORD_FIGURE_GUIDE.md`
- Modify: `review-stage/round2_review/check_data_integrity.py`
- Modify: `tests/test_data_integrity.py`

- [ ] **Step 1: 添加失败的完整性测试**

在 `tests/test_data_integrity.py` 增加临时正文测试，要求 `check_manuscript_theme(path)` 对“持杯运输”返回错误，对包含“到位稳定后测量”“10°保守运输阈值”的正文通过。增加 `check_figure_outputs(root)` 测试，缺少任一 `fig01`–`fig08` PNG/PDF 时返回错误列表。

- [ ] **Step 2: 运行新增测试确认失败**

Run:

```powershell
conda run -n mujoco python -m unittest tests.test_data_integrity -v
```

Expected: FAIL，提示新增检查函数尚不存在。

- [ ] **Step 3: 实现主题与输出检查**

在 `check_data_integrity.py` 中定义：

```python
LEGACY_THEME_TERMS = ("持杯", "杯体", "防洒", "倾洒", "液体晃动", "容器运输")
REQUIRED_THEME_PHRASES = ("到达目标位姿并稳定后", "10°", "保守运输")
FIGURE_BASENAMES = (
    "fig01_method_pipeline", "fig02_workspace_multiview", "fig03_transport_sequence",
    "fig04_case_study", "fig05_ablation_comparison", "fig06_error_tilt_margin",
    "fig07_dynamic_metrics", "fig08_baseline_comparison",
)
```

`check_manuscript_theme` 返回每个旧词的行号，并验证三个必需主题短语；`check_figure_outputs` 验证 `outputs/word_figures/*.png` 与 `figures/pgfplots/build/*.pdf` 均存在且非空。将两项加入严格检查主流程。

- [ ] **Step 4: 重写 Word 插图指南**

删除旧的持杯/防倾洒图题和360 DPI说明，写入8张新图的尺寸、中文图题、章节位置、600 DPI状态及“图题在 Word 中添加、不要烘焙进图片”的说明。图5和图8为8 cm单栏，其余为15 cm双栏；图3注明矢量示意而非真实仪器动力学渲染。

- [ ] **Step 5: 运行完整性测试**

Run:

```powershell
conda run -n mujoco python -m unittest tests.test_data_integrity -v
```

Expected: 单元测试通过；若此时图尚未统一构建，输出检查允许在测试临时目录中构造文件，不要求工作区产物提前存在。

- [ ] **Step 6: 提交指南与检查器**

```powershell
git add review-stage/round2_review/WORD_FIGURE_GUIDE.md review-stage/round2_review/check_data_integrity.py tests/test_data_integrity.py
git commit -m "test: enforce theodolite manuscript and figure integrity"
```

---

### Task 9: 全量构建、视觉QA与最终验证

**Files:**
- Generate: `figures/pgfplots/build/*.pdf`
- Generate/replace: `outputs/word_figures/fig01_method_pipeline.png`
- Generate/replace: `outputs/word_figures/fig02_workspace_multiview.png`
- Generate/replace: `outputs/word_figures/fig03_transport_sequence.png`
- Generate/replace: `outputs/word_figures/fig04_case_study.png`
- Generate/replace: `outputs/word_figures/fig05_ablation_comparison.png`
- Generate/replace: `outputs/word_figures/fig06_error_tilt_margin.png`
- Generate/replace: `outputs/word_figures/fig07_dynamic_metrics.png`
- Generate/replace: `outputs/word_figures/fig08_baseline_comparison.png`
- Remove after replacement: `outputs/word_figures/fig03_transport_snapshots.png`
- Remove after replacement: `outputs/word_figures/fig05_success_dashboard.png`
- Remove after replacement: `outputs/word_figures/fig06_error_tilt_safety.png`

- [ ] **Step 1: 执行全量构建**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File figures/pgfplots/build_figures.ps1
```

Expected: 8份 XeLaTeX 编译成功、8份 PDF 字体检查成功、8张600 DPI PNG 写入 Word 插图目录。

随后删除已被新命名取代的3张旧主题 Word 图片，避免人工排版时误选：

```powershell
Remove-Item outputs/word_figures/fig03_transport_snapshots.png,
            outputs/word_figures/fig05_success_dashboard.png,
            outputs/word_figures/fig06_error_tilt_safety.png
```

- [ ] **Step 2: 检查PDF尺寸、字体和PNG像素**

Run:

```powershell
Get-ChildItem figures/pgfplots/build/*.pdf | ForEach-Object { pdfinfo $_.FullName | Select-String 'Page size'; pdffonts $_.FullName }
conda run -n mujoco python -c "from PIL import Image; from pathlib import Path; files=sorted(Path('outputs/word_figures').glob('fig0[1-8]_*.png')); print([(p.name,Image.open(p).size,Image.open(p).info.get('dpi')) for p in files])"
```

Expected: 单栏图约1890 px宽，双栏图约3543 px宽（600 DPI，允许紧裁剪边框造成小幅差异）；所有PDF中文字体 `emb=yes`。

- [ ] **Step 3: 逐张视觉检查**

使用本地图片查看工具依次检查8张 PNG：无截断、无错位、字体与轴线一致、图例不盖住数据、阈值线说明清楚、中文无乱码、灰度下仍能依靠线型/标记区分。若任一项失败，只修改对应 `.tex` 或公共样式后重新运行构建脚本。

- [ ] **Step 4: 运行全部自动验证**

Run:

```powershell
conda run -n mujoco python -m unittest discover -s tests -v
conda run -n mujoco python review-stage/round2_review/check_data_integrity.py --strict
git diff --check
```

Expected: 全部单元测试 PASS；严格数据完整性检查 PASS；`git diff --check` 无输出。

- [ ] **Step 5: 核对数据追溯与主题残留**

Run:

```powershell
rg -n "持杯|杯体|防洒|倾洒|液体|晃动|容器运输|sloshing" docs/theory_and_simulation.md review-stage/round2_review/WORD_FIGURE_GUIDE.md figures/pgfplots
rg -n "45°|10°|到达目标位姿并稳定后" docs/theory_and_simulation.md
git status --short
```

Expected: 无非历史说明的旧主题残留；45°和10°的证据边界一致；只有本计划授权的新文件、论文、指南、检查器和图输出发生变化，五个既有未跟踪审稿输入文件保持未跟踪且未修改。

- [ ] **Step 6: 提交最终构建产物**

```powershell
git add figures/pgfplots/build outputs/word_figures docs/theory_and_simulation.md review-stage/round2_review/WORD_FIGURE_GUIDE.md
git commit -m "feat: deliver unified theodolite pgfplots figure set"
```

---

## 最终验收标准

- 论文从标题到结论均围绕经纬仪测站转移与到位稳定测量，不再以杯体或液体倾洒为研究对象。
- 明确说明运动过程中不测量，且无倾角—角秒误差标定；不夸大“精度提升”。
- 45°与10°分别被一致解释为粗粒度机械安全上限和本文保守运输阈值。
- 8张图均有独立 `standalone` TeX 源码、嵌入中文字体的裁剪 PDF、600 DPI PNG和可追溯数据。
- 单栏图8 cm、双栏图15 cm；全局8 pt、封闭坐标轴、向内刻度、0.7 pt轴线、0.8–1.0 pt数据线、低饱和配色及灰度可区分样式。
- 原始 CSV/NPZ 未修改；图中统计与提交数据一致；全部测试和严格完整性检查通过。
