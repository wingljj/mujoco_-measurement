"""Prepare title-free manuscript derivatives of the restored MuJoCo figures.

The Word PNGs are cropped in pixel space.  The PDF derivatives are produced by
pdfcrop from the original PDFs with an explicit page box, so their existing PDF
content (including vector paths and separately embedded panel images) is not
rasterized.  Source assets are never modified.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class RestoredFigure:
    source: Path
    destination: Path
    top_pixels: int
    dpi: int = 360


FIGURES = (
    RestoredFigure(
        ROOT / "outputs/paper_figures/rendered_transport_snapshots",
        ROOT / "outputs/paper_figures/rendered_transport_snapshots_title_cropped",
        90,
    ),
    RestoredFigure(
        ROOT / "outputs/figures/trajectory_3d_render",
        ROOT / "outputs/figures/trajectory_3d_render_title_cropped",
        100,
    ),
)


def prepare_figure(figure: RestoredFigure) -> None:
    source_png = figure.source.with_suffix(".png")
    destination_png = figure.destination.with_suffix(".png")
    with Image.open(source_png) as image:
        image.crop((0, figure.top_pixels, image.width, image.height)).save(destination_png)

    source_pdf = figure.source.with_suffix(".pdf")
    destination_pdf = figure.destination.with_suffix(".pdf")
    # PDF coordinates use 72 points/inch and start at the lower-left. Cropping
    # the top N pixels therefore reduces the upper page coordinate by N*72/dpi.
    trim_points = figure.top_pixels * 72 / figure.dpi
    build_dir = ROOT / "tmp/pdfs/restored-assets" / figure.destination.name
    build_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_pdf, build_dir / "source.pdf")
    (build_dir / "crop.tex").write_text(
        "\\documentclass[border=0pt]{standalone}\n"
        "\\usepackage{graphicx}\n"
        "\\begin{document}\n"
        f"\\includegraphics[trim=0 0 0 {trim_points:.6f}bp,clip]{{source.pdf}}\n"
        "\\end{document}\n",
        encoding="ascii",
    )
    subprocess.run(
        ["pdflatex", "-interaction=batchmode", "-halt-on-error", "crop.tex"],
        cwd=build_dir,
        check=True,
    )
    shutil.copy2(build_dir / "crop.pdf", destination_pdf)


def main() -> None:
    for figure in FIGURES:
        prepare_figure(figure)


if __name__ == "__main__":
    main()
