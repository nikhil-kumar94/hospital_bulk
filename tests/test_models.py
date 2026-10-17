import pytest
from pydantic import ValidationError

from app.models import HospitalRow, RowResult, BulkResult, BatchStatus


def test_hospitalrow_requires_name_and_address():
    with pytest.raises(ValidationError):
        HospitalRow(name="", address="123 St")
    with pytest.raises(ValidationError):
        HospitalRow(name="Gen", address="   ")


def test_hospitalrow_phone_optional_and_empty_becomes_none():
    assert HospitalRow(name="A", address="B").phone is None
    assert HospitalRow(name="A", address="B", phone="").phone is None
    assert HospitalRow(name="A", address="B", phone="555-1234").phone == "555-1234"


def test_hospitalrow_strips_name_and_address():
    row = HospitalRow(name="  Gen Hospital ", address=" 1 Main St ")
    assert row.name == "Gen Hospital"
    assert row.address == "1 Main St"


def test_bulkresult_round_trips_to_spec_fields():
    r = BulkResult(
        batch_id="x",
        total_hospitals=1,
        processed_hospitals=1,
        failed_hospitals=0,
        processing_time_seconds=1.0,
        batch_activated=True,
        hospitals=[RowResult(row=1, hospital_id=101, name="A", status="created_and_activated")],
    )
    assert set(r.model_dump().keys()) == {
        "batch_id",
        "total_hospitals",
        "processed_hospitals",
        "failed_hospitals",
        "processing_time_seconds",
        "batch_activated",
        "hospitals",
    }
    assert r.model_dump()["hospitals"][0] == {
        "row": 1,
        "hospital_id": 101,
        "name": "A",
        "status": "created_and_activated",
    }


def test_batchstatus_holds_progress_fields():
    s = BatchStatus(batch_id="b", state="processing", total=3, completed=1, failed=0, batch_activated=False)
    assert s.state == "processing" and s.total == 3
