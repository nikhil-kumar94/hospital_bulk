"""Tests for the CSV parser & validation layer."""
import pytest

from app.csv_parser import CSVValidationError, parse_csv
from app.models import HospitalRow


def test_parses_rows_phone_optional():
    content = b"name,address,phone\nAlpha Hospital,1 Alpha St,111\nBeta Hospital,2 Beta Ave,\n"
    rows = parse_csv(content, 20)
    assert len(rows) == 2
    assert all(isinstance(row, HospitalRow) for row in rows)
    assert rows[0].name == "Alpha Hospital"
    assert rows[0].address == "1 Alpha St"
    assert rows[0].phone == "111"
    assert rows[1].name == "Beta Hospital"
    assert rows[1].phone is None


def test_rejects_missing_required_column():
    with pytest.raises(CSVValidationError):
        parse_csv(b"name,phone\nA,1", 20)


def test_rejects_empty_content():
    with pytest.raises(CSVValidationError):
        parse_csv(b"", 20)


def test_rejects_header_only():
    with pytest.raises(CSVValidationError):
        parse_csv(b"name,address,phone\n", 20)


def test_rejects_over_max_rows():
    lines = ["name,address,phone"]
    for i in range(21):
        lines.append("Hosp {0},Addr {0},{0}".format(i))
    content = ("\n".join(lines) + "\n").encode()
    with pytest.raises(CSVValidationError):
        parse_csv(content, 20)


def test_handles_bom_quoted_comma_and_trailing_blank_line():
    content = ('﻿name,address,phone\n"Gen, Hosp","1, Main St",5\n\n').encode()
    rows = parse_csv(content, 20)
    assert len(rows) == 1
    assert rows[0].name == "Gen, Hosp"
    assert rows[0].address == "1, Main St"
    assert rows[0].phone == "5"


def test_rejects_empty_name_and_names_row_number():
    content = b"name,address,phone\nGood Hospital,1 Good St,1\n   ,2 Bad St,2\n"
    with pytest.raises(CSVValidationError) as excinfo:
        parse_csv(content, 20)
    # The offending data row is the 2nd data row (1-based).
    assert "2" in str(excinfo.value)


def test_csv_validation_error_message_attribute():
    err = CSVValidationError("boom")
    assert err.message == "boom"
    assert str(err) == "boom"
