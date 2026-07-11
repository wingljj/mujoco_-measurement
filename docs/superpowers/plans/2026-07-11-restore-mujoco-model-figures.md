# Restore MuJoCo Model Figures Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore the MuJoCo transport snapshots and three-dimensional trajectory figure to the Chinese manuscript without removing the existing eight unified figures, then publish a verified 10-figure manuscript PDF.

**Architecture:** Keep `docs/theory_and_simulation.md` as the single manuscript content source. Extend the Pandoc Lua filter so all manuscript images resolve to vector PDFs at journal-appropriate widths, and extend the integrity checker with explicit assertions for the restored assets and new figure order. Build with Pandoc/XeLaTeX and visually verify Poppler-rendered pages.

**Tech Stack:** Markdown, Pandoc 3, Lua filter, XeLaTeX/ctex, PDF/Poppler, Python/pytest.

---

## File Structure

- Modify `docs/theory_and_simulation.md`: insert two figures, boundary text, and renumber all affected figure references.
- Modify `docs/manuscript-filter.lua`: map restored PNG references to their vector PDF counterparts and apply 15 cm widths.
- Modify `review-stage/round2_review/check_data_integrity.py`: validate 10-image order, restored-figure presence, and required proxy-model disclaimers.
- Modify `scripts/build_manuscript_pdf.ps1`: keep the existing reproducible PDF build entry point; no new build system.
- Regenerate `output/pdf/theodolite_station_transfer_manuscript.pdf`: final 10-figure manuscript.

### Task 1: Add failing manuscript-integrity checks

**Files:**
- Modify: `review-stage/round2_review/check_data_integrity.py`
- Test: `review-stage/round2_review/check_data_integrity.py`

- [ ] **Step 1: Add assertions for the restored images and 10-figure order**

Extend the checker’s expected manuscript image list to the following exact order:

```python
EXPECTED_MANUSCRIPT_IMAGES = [
    "fig01_method_pipeline.png",
    "rendered_transport_snapshots.png",
    "fig02_workspace_multiview.png",
    "trajectory_3d_render.png",
    "fig03_transport_sequence.png",
    "fig04_case_study.png",
    "fig05_ablation_comparison.png",
    "fig06_error_tilt_margin.png",
    "fig07_dynamic_metrics.png",
    "fig08_baseline_comparison.png",
]
```

Require adjacent manuscript text to contain “简化刚性负载代理” and “不代表真实经纬仪” for the restored snapshots and trajectory.

- [ ] **Step 2: Run the strict checker and verify it fails**

Run:

```powershell
conda run --no-capture-output -n mujoco python review-stage/round2_review/check_data_integrity.py --strict
```

Expected: failure because the two restored image references are not yet present in the manuscript.

- [ ] **Step 3: Commit the failing checks**

```powershell
git add review-stage/round2_review/check_data_integrity.py
git commit -m "test: require restored MuJoCo manuscript figures"
```

### Task 2: Restore both MuJoCo figures and update numbering

**Files:**
- Modify: `docs/theory_and_simulation.md`

- [ ] **Step 1: Insert the MuJoCo transport snapshots in Section 3**

After the simulation-system description, add the figure reference:

```markdown
图2展示当前 MuJoCo 模型中的机械臂、末端简化刚性负载代理及运输过程。图中末端外观仅用于显示代理竖轴姿态与场景关系，不代表真实经纬仪的结构、质量、惯量、夹持柔顺性或测量标定模型。

![图2 MuJoCo机械臂持经纬仪简化刚性代理的运输过程快照](../outputs/paper_figures/rendered_transport_snapshots.png)
```

- [ ] **Step 2: Insert the original three-dimensional trajectory in Section 7**

Before the five-stage schematic, add:

```markdown
图4给出原始 MuJoCo 任务的三维末端运输轨迹。该轨迹对应简化刚性负载代理的仿真运动，不代表真实经纬仪动力学或测量过程；经纬仪仍只在到达目标位姿并稳定后进行测量。

![图4 原始MuJoCo任务中的机械臂末端三维运输轨迹](../outputs/figures/trajectory_3d_render.png)
```

- [ ] **Step 3: Renumber all later figure captions and prose references**

Use the exact final order specified in the design: existing figures 2–8 become figures 3, 5, 6, 7, 8, 9, and 10 as appropriate. Search for every `图[1-9]` occurrence and verify no stale number remains.

- [ ] **Step 4: Run the strict checker and verify it passes**

Run:

```powershell
conda run --no-capture-output -n mujoco python review-stage/round2_review/check_data_integrity.py --strict
```

Expected: strict integrity check passes with 10 manuscript images in the required order.

- [ ] **Step 5: Commit manuscript restoration**

```powershell
git add docs/theory_and_simulation.md review-stage/round2_review/check_data_integrity.py
git commit -m "feat: restore MuJoCo model figures to manuscript"
```

### Task 3: Extend vector-PDF image mapping

**Files:**
- Modify: `docs/manuscript-filter.lua`
- Test: `output/pdf/theodolite_station_transfer_manuscript.pdf`

- [ ] **Step 1: Add exact restored-asset mappings**

Add a lookup before the existing pgfplots mapping:

```lua
local restored_figures = {
  ['rendered_transport_snapshots.png'] = '../outputs/paper_figures/rendered_transport_snapshots.pdf',
  ['trajectory_3d_render.png'] = '../outputs/figures/trajectory_3d_render.pdf',
}
```

When an image basename exists in this lookup, replace `el.src` with the mapped PDF and set `el.attributes.width = '15cm'`. Preserve the existing 15 cm/8 cm sizing for the eight pgfplots figures.

- [ ] **Step 2: Build the manuscript PDF**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_manuscript_pdf.ps1
```

Expected: exit code 0 and a newly generated `output/pdf/theodolite_station_transfer_manuscript.pdf`.

- [ ] **Step 3: Check structural PDF properties**

Run:

```powershell
pdfinfo output/pdf/theodolite_station_transfer_manuscript.pdf
pdffonts output/pdf/theodolite_station_transfer_manuscript.pdf
pdftotext output/pdf/theodolite_station_transfer_manuscript.pdf tmp/manuscript.txt
```

Expected: A4 PDF, all `emb` columns are `yes`, 10 captions are extractable, and no caption matches `图\s*\d+\s+图\s*\d+`.

- [ ] **Step 4: Commit vector mapping and generated PDF**

```powershell
git add docs/manuscript-filter.lua scripts/build_manuscript_pdf.ps1 output/pdf/theodolite_station_transfer_manuscript.pdf
git commit -m "build: publish manuscript with restored MuJoCo figures"
```

### Task 4: Visual and regression verification

**Files:**
- Test: `output/pdf/theodolite_station_transfer_manuscript.pdf`
- Test: `tests/`

- [ ] **Step 1: Render every PDF page**

```powershell
New-Item -ItemType Directory -Force tmp/pdfs/restored | Out-Null
pdftoppm -png -r 120 output/pdf/theodolite_station_transfer_manuscript.pdf tmp/pdfs/restored/page
```

Expected: one non-empty PNG per PDF page.

- [ ] **Step 2: Visually inspect all rendered pages**

Check both restored figures for correct aspect ratio, legible labels, complete cropping, and nearby proxy-model disclaimers. Check the eight existing figures, tables, equations, captions, headers, footers, and page breaks for regressions.

- [ ] **Step 3: Run repository regression tests**

```powershell
conda run --no-capture-output -n mujoco python -m pytest -q
conda run --no-capture-output -n mujoco python review-stage/round2_review/check_data_integrity.py --strict
```

Expected: all tests and the strict checker pass.

- [ ] **Step 4: Remove temporary renders and verify Git scope**

```powershell
Remove-Item -LiteralPath tmp/pdfs/restored -Recurse -Force
git status --short
```

Expected: only intentional manuscript, checker, filter, plan, and PDF changes are tracked; pre-existing unrelated untracked review files remain untouched.
