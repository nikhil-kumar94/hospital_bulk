"""CSV parsing and validation for hospital bulk uploads."""
import csv
import io
from typing import List

from pydantic import ValidationError

from app.models import HospitalRow

REQUIRED_COLUMNS = ("name", "address")


class CSVValidationError(Exception):
    """Raised when uploaded CSV content fails parsing or validation."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


def _is_blank_row(row: dict) -> bool:
    """A row is blank when every value is None or empty/whitespace."""
    for value in row.values():
        if value is not None and str(value).strip():
            return False
    return True


def parse_csv(content: bytes, max_rows: int) -> List[HospitalRow]:
    """Parse and validate hospital CSV bytes into a list of HospitalRow.

    Decodes with 'utf-8-sig' (tolerating a UTF-8 BOM), parses with
    csv.DictReader, skips fully blank lines, and enforces the required
    header, row-count, and per-row validation rules. Raises
    CSVValidationError with a specific message on any violation.
    """
    text = content.decode("utf-8-sig")
    if not text.strip():
        raise CSVValidationError("CSV content is empty.")

    reader = csv.DictReader(io.StringIO(text))
    header = reader.fieldnames
    if not header:
        raise CSVValidationError("CSV content is empty.")

    missing = [column for column in REQUIRED_COLUMNS if column not in header]
    if missing:
        raise CSVValidationError(
            "Missing required column(s): {0}.".format(", ".join(missing))
        )

    hospitals = []
    data_row_number = 0
    for raw_row in reader:
        if _is_blank_row(raw_row):
            continue
        data_row_number += 1

        if data_row_number > max_rows:
            raise CSVValidationError(
                "Too many data rows: limit is {0}.".format(max_rows)
            )

        name = (raw_row.get("name") or "").strip()
        address = (raw_row.get("address") or "").strip()
        if not name:
            raise CSVValidationError(
                "Row {0}: 'name' is required and must not be empty.".format(
                    data_row_number
                )
            )
        if not address:
            raise CSVValidationError(
                "Row {0}: 'address' is required and must not be empty.".format(
                    data_row_number
                )
            )

        try:
            hospital = HospitalRow(
                name=raw_row.get("name"),
                address=raw_row.get("address"),
                phone=raw_row.get("phone"),
            )
        except ValidationError as exc:
            raise CSVValidationError(
                "Row {0}: invalid data ({1}).".format(data_row_number, exc)
            )
        hospitals.append(hospital)

    if data_row_number == 0:
        raise CSVValidationError("CSV has no data rows.")

    return hospitals
