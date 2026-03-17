"""Tests for report generation with varying aspect ratios."""

import random

import pytest
from PIL import Image

from dicom_report.utils.enums import Diagnosis
from dicom_report.report import generate_report


def _gray_image(width: int, height: int) -> Image.Image:
    """Create a gray placeholder image."""
    return Image.new("RGB", (width, height), color=(128, 128, 128))


def _random_images_4_3(n: int, seed: int = 42) -> list[Image.Image]:
    """Generate n gray images with aspect ratio ~4/3 (with variation)."""
    rng = random.Random(seed)
    images = []
    base_size = 400
    for _ in range(n):
        # Aspect ratio: 4/3 ± ~25% variation (roughly 1.0 to 1.8)
        aspect = (4 / 3) * rng.uniform(0.75, 1.25)
        w = int(base_size * aspect)
        h = base_size
        images.append(_gray_image(w, h))
    return images


@pytest.mark.parametrize("n_images", [1, 3, 6, 10, 15, 30, 50])
def test_report_generates_with_random_aspect_ratios(n_images: int) -> None:
    """Report generation works with images of varying aspect ratios (~4/3)."""
    images = _random_images_4_3(n_images)
    report = generate_report(images, Diagnosis.BENIGN)
    assert report.size == (3840, 2160)
    assert report.mode == "RGB"


def test_report_zero_images() -> None:
    """Report with no images raises ValueError."""
    with pytest.raises(ValueError, match="Expected at least one image, but got 0"):
        generate_report([], Diagnosis.BENIGN)
