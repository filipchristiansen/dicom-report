"""Generate a report from the test US image (N copies) and save to results dir."""

from PIL import Image

from dicom_report import generate_report
from dicom_report.utils.enums import Diagnosis
from dicom_report.utils.paths import RESULTS_DIR, TESTS_DIR

N_IMAGES = 6


def main() -> None:
    image_path = TESTS_DIR / "test_us_image.tif"

    with Image.open(image_path) as base_img:
        images = [base_img.copy() for _ in range(N_IMAGES)]

    diagnosis = Diagnosis.BENIGN
    report = generate_report(images, diagnosis=diagnosis)
    report.save(RESULTS_DIR / f"report_{N_IMAGES}_images.png")


if __name__ == "__main__":
    main()
