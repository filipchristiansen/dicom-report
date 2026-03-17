"""Path configuration for the dicom-report package."""

from pathlib import Path

_PACKAGE_DIR = Path(__file__).resolve().parents[1]

TEMPLATE_DIR = _PACKAGE_DIR / "templates"

ROOT_DIR = _PACKAGE_DIR.parents[1]

TESTS_DIR = ROOT_DIR / "tests"
RESULTS_DIR = ROOT_DIR / "results"
TEST_REPORTS_DIR = ROOT_DIR / "test_reports"
