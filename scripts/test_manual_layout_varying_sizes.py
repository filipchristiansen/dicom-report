"""Manual visual test: generate report with varying image sizes.

Uses gray placeholder images with hardcoded dimensions (width x height)
to verify thumbnail layout without relying on external data.
"""

from PIL import Image

from dicom_report import generate_report
from dicom_report.utils.enums import Diagnosis
from dicom_report.utils.paths import TEST_REPORTS_DIR

# Image dimensions (width, height)
IMAGE_SIZES = [
    (725, 464),
    (619, 427),
    (709, 522),
    (750, 519),
    (700, 506),
    (750, 473),
    (732, 505),
]


def _gray(width: int, height: int) -> Image.Image:
    return Image.new("RGB", (width, height), color=(128, 128, 128))


def main() -> None:
    images = [_gray(w, h) for w, h in IMAGE_SIZES]
    report = generate_report(images, diagnosis=Diagnosis.INCONCLUSIVE)
    TEST_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = TEST_REPORTS_DIR / "layout_varying_sizes.png"
    report.save(out_path)
    print(f"Saved {out_path} - visually verify thumbnail uniformity")


if __name__ == "__main__":
    main()
