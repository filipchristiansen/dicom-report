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
        images: Sequence[Image.Image]
            The sequence of PIL images to include as thumbnails.
        diagnosis: Diagnosis
            The diagnosis to use for the report.

    Returns
    -------
        Image.Image
            The generated report image.

    Raises
    ------
        ValueError: If the report size is not as expected.
        ValueError: If the number of images is 0.
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


def _compute_layout(
    sizes: Sequence[tuple[int, int]],
    scale: float,
    area: ThumbnailArea,
) -> tuple[list[tuple[int, int]], bool]:
    """Compute (x, y) positions for each item at given scale.

    Parameters
    ----------
        sizes: Sequence[tuple[int, int]]
            The sequence of sizes of the images.
        scale: float
            The scale to use for the layout.
        area: ThumbnailArea
            The area to layout the images in.

    Returns
    -------
        tuple[list[tuple[int, int]], bool]
            The positions of the images and whether the layout fits.
    """
    positions: list[tuple[int, int]] = []
    x, y = area.x_start, area.y_start
    row_h = 0
    for tw, th in sizes:
        w, h = tw * scale, th * scale
        if x + w > area.x_end and x > area.x_start:
            x = area.x_start
            y += row_h + THUMBNAIL_SPACING
            row_h = 0
        if x > area.x_start:
            x += THUMBNAIL_SPACING
        positions.append((int(x), int(y)))
        x += w
        row_h = max(row_h, h)
    fits = y + row_h <= area.y_end
    return positions, fits


def _layout_flow(report: Image.Image, images: Sequence[Image.Image], area: ThumbnailArea) -> None:
    """Flow layout: 25px between each thumbnail, variable sizes by aspect ratio."""
    max_h = max(img.height for img in images)
    sizes = [(int(img.width * max_h / img.height), max_h) for img in images]

    # Binary search for max scale
    lo, hi = SCALE_MIN, SCALE_MAX
    for _ in range(BINARY_SEARCH_ITERATIONS):
        mid = (lo + hi) / 2
        _, fits = _compute_layout(sizes, mid, area)
        if fits:
            lo = mid
        else:
            hi = mid
    scale = lo

    positions, _ = _compute_layout(sizes, scale, area)

    for img, (x, y), (tw, th) in zip(images, positions, sizes):
        nw = max(1, int(tw * scale))
        nh = max(1, int(th * scale))
        min_size = 2 * THUMBNAIL_BORDER
        if min(nw, nh) < min_size:
            msg = f"Thumbnail too small for border: {nw}x{nh} (minimum {min_size}x{min_size} required)"
            raise ValueError(msg)
        inner_w = nw - 2 * THUMBNAIL_BORDER
        inner_h = nh - 2 * THUMBNAIL_BORDER
        thumb = img.resize((inner_w, inner_h), Image.Resampling.LANCZOS)
        bordered = Image.new("RGB", (nw, nh), color="white")
        bordered.paste(thumb, (THUMBNAIL_BORDER, THUMBNAIL_BORDER))
        report.paste(bordered, (x, y))
