"""Report layout and scaling constants."""

from typing import NamedTuple


REPORT_WIDTH: int = 3840
REPORT_HEIGHT: int = 2160
THUMBNAIL_SPACING: int = 25
THUMBNAIL_BORDER: int = 1

SCALE_MIN: float = 0.01
SCALE_MAX: float = 1000.0
BINARY_SEARCH_ITERATIONS: int = 40


class ThumbnailArea(NamedTuple):
    """Bounding box (x_start, x_end, y_start, y_end) for the thumbnail area in the report."""

    x_start: int
    x_end: int
    y_start: int
    y_end: int


THUMBNAIL_AREA = ThumbnailArea(
    x_start=100,
    x_end=2530,
    y_start=1372,
    y_end=2060,
)
