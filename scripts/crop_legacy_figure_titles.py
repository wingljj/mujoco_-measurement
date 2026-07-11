"""Create manuscript derivatives with only legacy top titles removed.

The source PNG/PDF files remain untouched. PNG crops use explicit pixel rows;
matching raster-backed PDF derivatives retain the source figures' 360 dpi scale.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
FIGURES = (
    (
        ROOT / "outputs/paper_figures/rendered_transport_snapshots",
        ROOT / "outputs/paper_figures/rendered_transport_snapshots_title_cropped",
        90,
        360,
    ),
    (
        ROOT / "outputs/figures/trajectory_3d_render",
        ROOT / "outputs/figures/trajectory_3d_render_title_cropped",
        100,
        360,
    ),
)


def crop_figure(source: Path, destination: Path, top_pixels: int, dpi: int) -> None:
    with Image.open(source.with_suffix(".png")) as image:
        cropped = image.crop((0, top_pixels, image.width, image.height))
        cropped.save(destination.with_suffix(".png"))
        # Keep a PDF counterpart at the source figure's 360 dpi physical scale.
        # The derivative is intentionally raster-backed so the crop is portable
        # on Windows systems where pdfcrop cannot link files reliably.
        cropped.convert("RGB").save(destination.with_suffix(".pdf"), resolution=dpi)


def main() -> None:
    for figure in FIGURES:
        crop_figure(*figure)


if __name__ == "__main__":
    main()
