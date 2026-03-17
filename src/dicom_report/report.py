"""Core report generation logic for adnexal mass ultrasound reports."""

from collections.abc import Sequence

from PIL import Image

from dicom_report.utils.constants import (
    BINARY_SEARCH_ITERATIONS,
    REPORT_HEIGHT,
    REPORT_WIDTH,
    SCALE_MAX,
    SCALE_MIN,
    THUMBNAIL_AREA,
    THUMBNAIL_BORDER,
    THUMBNAIL_SPACING,
    ThumbnailArea,
)
from dicom_report.utils.enums import Diagnosis
from dicom_report.utils.paths import TEMPLATE_DIR


def generate_report(images: Sequence[Image.Image], diagnosis: Diagnosis) -> Image.Image:
    """Generate a PNG report image from template and images.

    Renders thumbnails onto a diagnosis-specific template image.

    Parameters
    ----------
    images : Sequence[Image.Image]
        The sequence of PIL images to include as thumbnails.
    diagnosis : Diagnosis
        The diagnosis to use for the report.

    Returns
    -------
    Image.Image
        The generated report image.

    Raises
    ------
    ValueError
        If the report size is not as expected, or if the number of images is 0.
    """
    with Image.open(TEMPLATE_DIR / f"{diagnosis.value}.png") as img:
        report = img.convert("RGB")

    if report.size != (REPORT_WIDTH, REPORT_HEIGHT):
        width, height = report.size
        msg = f"Expected report size to be {REPORT_WIDTH}x{REPORT_HEIGHT}, but got {width}x{height}"
        raise ValueError(msg)

    if not images:
        msg = "Expected at least one image, but got 0"
        raise ValueError(msg)

    _layout_flow(report, images=images, area=THUMBNAIL_AREA)
    return report


def _layout_flow(report: Image.Image, images: Sequence[Image.Image], area: ThumbnailArea) -> None:
    """Flow layout: 25px between each thumbnail, variable sizes by aspect ratio."""
    max_h = max(img.height for img in images)
    sizes = [(int(img.width * max_h / img.height), max_h) for img in images]
    scale = _find_max_scale(sizes, area)
    positions, _ = _compute_layout(sizes, scale, area)

    for img, pos, size in zip(images, positions, sizes, strict=True):
        _paste_thumbnail(report, img, pos, size, scale)


def _compute_layout(
    sizes: Sequence[tuple[int, int]],
    scale: float,
    area: ThumbnailArea,
) -> tuple[list[tuple[int, int]], bool]:
    """Compute (x, y) positions for each item at given scale.

    Parameters
    ----------
    sizes : Sequence[tuple[int, int]]
        The sequence of sizes of the images.
    scale : float
        The scale to use for the layout.
    area : ThumbnailArea
        The area to layout the images in.

    Returns
    -------
    tuple[list[tuple[int, int]], bool]
        The positions of the images and whether the layout fits.
    """
    positions: list[tuple[int, int]] = []
    x: float = float(area.x_start)
    y: float = float(area.y_start)
    row_h: float = 0
    for tw, th in sizes:
        w, h = tw * scale, th * scale
        if x + w > area.x_end and x > area.x_start:
            x = float(area.x_start)
            y += row_h + THUMBNAIL_SPACING
            row_h = 0
        if x > area.x_start:
            x += THUMBNAIL_SPACING
        positions.append((int(x), int(y)))
        x += w
        row_h = max(row_h, h)
    fits = y + row_h <= area.y_end
    return positions, fits


def _find_max_scale(sizes: list[tuple[int, int]], area: ThumbnailArea) -> float:
    """Binary search for the largest scale that fits the layout."""
    lo, hi = SCALE_MIN, SCALE_MAX
    for _ in range(BINARY_SEARCH_ITERATIONS):
        mid = (lo + hi) / 2
        _, fits = _compute_layout(sizes, mid, area)
        if fits:
            lo = mid
        else:
            hi = mid
    return lo


def _paste_thumbnail(
    report: Image.Image, img: Image.Image, position: tuple[int, int], size: tuple[int, int], scale: float
) -> None:
    """Resize, border, and paste one thumbnail onto the report."""
    x, y = position
    tw, th = size
    nw = max(1, int(tw * scale))
    nh = max(1, int(th * scale))
    if min(nw, nh) < 2 * THUMBNAIL_BORDER:
        min_side = 2 * THUMBNAIL_BORDER
        msg = f"Thumbnail too small for border: {nw}x{nh} (minimum {min_side}x{min_side} required)"
        raise ValueError(msg)
    inner = (nw - 2 * THUMBNAIL_BORDER, nh - 2 * THUMBNAIL_BORDER)
    bordered = Image.new("RGB", (nw, nh), color="white")
    bordered.paste(img.resize(inner, Image.Resampling.LANCZOS), (THUMBNAIL_BORDER, THUMBNAIL_BORDER))
    report.paste(bordered, (x, y))
