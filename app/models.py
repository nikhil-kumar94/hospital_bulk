"""Pydantic data models shared across the bulk-processing service."""
from typing import List, Optional

from pydantic import BaseModel, field_validator


class HospitalRow(BaseModel):
    """One validated hospital parsed from the uploaded CSV."""

    name: str
    address: str
    phone: Optional[str] = None

    @field_validator("name", "address")
    @classmethod
    def _required_non_empty(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError("must be a non-empty value")
        return value

    @field_validator("phone")
    @classmethod
    def _blank_phone_is_none(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        return value or None


class RowResult(BaseModel):
    """Per-row outcome included in the bulk response."""

    row: int
    hospital_id: Optional[int] = None
    name: str
    status: str


class BulkResult(BaseModel):
    """The response returned by POST /hospitals/bulk (exact spec schema)."""

    batch_id: str
    total_hospitals: int
    processed_hospitals: int
    failed_hospitals: int
    processing_time_seconds: float
    batch_activated: bool
    hospitals: List[RowResult]


class BatchStatus(BaseModel):
    """Live progress for a batch, surfaced by the polling endpoint."""

    batch_id: str
    state: str
    total: int
    completed: int
    failed: int
    batch_activated: bool
