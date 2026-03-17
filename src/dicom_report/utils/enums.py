"""Enums for the dicom-report package."""

from enum import Enum


class Diagnosis(Enum):
    """Adnexal mass diagnosis from deep learning model prediction."""

    def __str__(self) -> str:
        return str(self.value)

    BENIGN = "benign"
    INCONCLUSIVE = "inconclusive"
    MALIGNANT = "malignant"
