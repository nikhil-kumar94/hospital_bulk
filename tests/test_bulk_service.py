"""Tests for the bulk orchestrator (app/bulk_service.py).

``process_bulk`` fans out one create per row (bounded by a semaphore),
then resolves the whole batch: on full success it activates directly; on a
partial failure it delegates to the configured failure policy. It must ALWAYS
return a BulkResult -- even when the batch-level activate/delete call itself
fails -- never raising.

No real network is used: a configurable duck-typed FakeClient records
activate/delete calls and fails specific rows. A real BatchStore and real
Settings are used. Row failures are keyed off row IDENTITY (name == "FAIL")
rather than call order, because creates run concurrently and call-order is
nondeterministic.
"""
from typing import List

from app.bulk_service import process_bulk
from app.config import Settings
from app.downstream import DownstreamError
from app.models import BulkResult, HospitalRow
from app.store import BatchStore


class FakeClient:
    """Duck-typed stand-in for DirectoryClient.

    A row fails to create iff its name is ``"FAIL"`` (identity-keyed, so the
    outcome is deterministic regardless of concurrent scheduling order).
    activate_batch / delete_batch can be made to raise DownstreamError.
    """

    def __init__(self, activate_raises=False, delete_raises=False):
        self.activate_raises = activate_raises
        self.delete_raises = delete_raises
        self.activated: List[str] = []
        self.deleted: List[str] = []
        self._next_id = 100

    async def create_hospital(self, row, batch_id):
        if row.name == "FAIL":
            raise DownstreamError("boom")
        self._next_id += 1
        return self._next_id

    async def activate_batch(self, batch_id):
        if self.activate_raises:
            raise DownstreamError("activate boom")
        self.activated.append(batch_id)

    async def delete_batch(self, batch_id):
        if self.delete_raises:
            raise DownstreamError("delete boom")
        self.deleted.append(batch_id)


def _good(name="Good"):
    return HospitalRow(name=name, address="1 Main St")


def _bad():
    return HospitalRow(name="FAIL", address="1 Main St")


async def test_all_success_activates():
    rows = [_good("A"), _good("B"), _good("C")]
    fake = FakeClient()
    store = BatchStore()
    settings = Settings(failure_policy="rollback")

    result = await process_bulk(rows, fake, store, settings)

    assert isinstance(result, BulkResult)
    assert result.total_hospitals == 3
    assert result.processed_hospitals == 3
    assert result.failed_hospitals == 0
    assert result.batch_activated is True
    assert [h.status for h in result.hospitals] == ["created_and_activated"] * 3
    assert fake.activated == [result.batch_id]
    assert fake.deleted == []
    assert store.get(result.batch_id).state == "completed"


async def test_rollback_on_failure():
    rows = [_good("A"), _bad(), _good("C")]
    fake = FakeClient()
    store = BatchStore()
    settings = Settings(failure_policy="rollback")

    result = await process_bulk(rows, fake, store, settings)

    assert len(fake.deleted) == 1
    assert fake.deleted == [result.batch_id]
    assert fake.activated == []
    assert result.batch_activated is False
    assert result.failed_hospitals == 1
    assert result.processed_hospitals == 2
    statuses = sorted(h.status for h in result.hospitals)
    assert statuses == ["failed", "rolled_back", "rolled_back"]
    assert store.get(result.batch_id).state == "failed"


async def test_leave_policy_keeps_created():
    rows = [_good("A"), _bad(), _good("C")]
    fake = FakeClient()
    store = BatchStore()
    settings = Settings(failure_policy="leave")

    result = await process_bulk(rows, fake, store, settings)

    assert fake.deleted == []
    assert fake.activated == []
    assert result.batch_activated is False
    statuses = sorted(h.status for h in result.hospitals)
    assert statuses == ["created", "created", "failed"]


async def test_partial_policy_activates():
    rows = [_good("A"), _bad(), _good("C")]
    fake = FakeClient()
    store = BatchStore()
    settings = Settings(failure_policy="partial")

    result = await process_bulk(rows, fake, store, settings)

    assert len(fake.activated) == 1
    assert fake.activated == [result.batch_id]
    assert fake.deleted == []
    assert result.batch_activated is True
    statuses = sorted(h.status for h in result.hospitals)
    assert statuses == ["created_and_activated", "created_and_activated", "failed"]


async def test_policy_action_failure_is_swallowed():
    # Review Focus #4: rollback's delete itself raises -> still get a report.
    rows = [_good("A"), _bad(), _good("C")]
    fake = FakeClient(delete_raises=True)
    store = BatchStore()
    settings = Settings(failure_policy="rollback")

    result = await process_bulk(rows, fake, store, settings)

    assert isinstance(result, BulkResult)
    assert result.batch_activated is False
    assert result.failed_hospitals == 1
    assert result.processed_hospitals == 2
    succeeded = [h for h in result.hospitals if h.hospital_id is not None]
    assert all(h.status == "created" for h in succeeded)
    assert fake.deleted == []  # delete raised, nothing recorded


async def test_activation_failure_on_full_success_is_swallowed():
    # Review Focus #4 variant: all rows good but activate raises.
    rows = [_good("A"), _good("B"), _good("C")]
    fake = FakeClient(activate_raises=True)
    store = BatchStore()
    settings = Settings(failure_policy="rollback")

    result = await process_bulk(rows, fake, store, settings)

    assert isinstance(result, BulkResult)
    assert result.batch_activated is False
    assert [h.status for h in result.hospitals] == ["created"] * 3
    assert fake.activated == []  # activate raised, nothing recorded
    assert store.get(result.batch_id).state == "failed"


async def test_processing_time_and_ordering():
    rows = [_good("A"), _good("B"), _good("C")]
    fake = FakeClient()
    store = BatchStore()
    settings = Settings(failure_policy="rollback")

    result = await process_bulk(rows, fake, store, settings)

    assert isinstance(result.processing_time_seconds, float)
    assert result.processing_time_seconds >= 0
    assert [h.row for h in result.hospitals] == [1, 2, 3]


async def test_store_progress_recorded():
    rows = [_good("A"), _bad(), _good("C")]
    fake = FakeClient()
    store = BatchStore()
    settings = Settings(failure_policy="leave")

    result = await process_bulk(rows, fake, store, settings)

    status = store.get(result.batch_id)
    assert status is not None
    assert status.total == 3
    assert status.completed + status.failed == status.total
    assert status.completed == 2
    assert status.failed == 1
