"""Generate sample reports with varying image counts and aspect ratios."""
from __future__ import annotations

import random

from PIL import Image

from dicom_report.utils.enums import Diagnosis
from dicom_report.utils.paths import TEST_REPORTS_DIR
from dicom_report.report import generate_report


def _gray(width: int, height: int) -> Image.Image:
    return Image.new("RGB", (width, height), color=(128, 128, 128))


def random_images(
    n: int,
    seed: int | None = None,
    *,
    aspect_range: tuple[float, float] = (0.4, 2.8),
) -> list[Image.Image]:
    """Generate n gray images with aspect ratios in aspect_range (w/h)."""
    rng = random.Random(seed)
    base = 400
    images = []
    for _ in range(n):
        aspect = rng.uniform(*aspect_range)
        w = max(1, int(base * aspect))
        h = base
        images.append(_gray(w, h))
    return images


def main() -> None:
    TEST_REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    rng = random.Random(42)

    # Different image counts
    for n in [1, 2, 5, 8, 12, 18, 25, 35]:
        imgs = random_images(n, seed=rng.randint(0, 99999), aspect_range=(0.5, 2.2))
        report = generate_report(imgs, Diagnosis.BENIGN)
        report.save(TEST_REPORTS_DIR / f"report_{n}img_extreme.png")
        print(f"Saved report_{n}img_extreme.png")

    # Semi-extreme aspect ratios: wide (2.5:1) and tall (1:2)
    wide = [_gray(500, 200) for _ in range(6)]
    tall = [_gray(200, 500) for _ in range(6)]
    report = generate_report(wide, Diagnosis.BENIGN)

    report.save(TEST_REPORTS_DIR / "report_wide_6img.png")
    print("Saved report_wide_6img.png")
    report = generate_report(tall, Diagnosis.BENIGN)

    report.save(TEST_REPORTS_DIR / "report_tall_6img.png")
    print("Saved report_tall_6img.png")

    # Mixed extreme aspects in one report
    mixed = (
        [_gray(600, 200)] * 2
        + [_gray(200, 600)] * 2
        + [_gray(400, 400)] * 2
        + [_gray(150, 400)] * 2
        + [_gray(400, 150)] * 2
    )
    report = generate_report(mixed, Diagnosis.BENIGN)
    report.save(TEST_REPORTS_DIR / "report_mixed_extreme.png")
    print("Saved report_mixed_extreme.png")


if __name__ == "__main__":
    main()