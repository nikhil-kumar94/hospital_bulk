import asyncio

from app.store import BatchStore


def test_create_then_get_returns_processing_status():
    store = BatchStore()
    store.create("b", 3)
    status = store.get("b")
    assert status is not None
    assert status.state == "processing"
    assert status.total == 3
    assert status.completed == 0
    assert status.failed == 0
    assert status.batch_activated is False


async def test_concurrent_increments_are_consistent():
    store = BatchStore()
    store.create("b", 100)
    await asyncio.gather(*[store.increment("b", completed=1) for _ in range(100)])
    assert store.get("b").completed == 100


def test_get_unknown_batch_returns_none():
    store = BatchStore()
    assert store.get("missing") is None


async def test_finalize_sets_state_and_batch_activated():
    store = BatchStore()
    store.create("b", 1)
    await store.finalize("b", state="completed", batch_activated=True)
    status = store.get("b")
    assert status.state == "completed"
    assert status.batch_activated is True
