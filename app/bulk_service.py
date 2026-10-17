"""Bulk hospital-creation orchestrator.

``process_bulk`` is the heart of POST /hospitals/bulk. It:

1. Creates a batch id and records the batch in the store.
2. Fans out one create per row, bounded by a concurrency semaphore.
3. Resolves the whole batch:
   * on full success -> activate the batch directly;
   * on a partial failure -> delegate to the configured failure policy.
4. ALWAYS returns a :class:`BulkResult`. A failing batch-level activate/delete
   (a downstream error) never propagates out of this function -- it degrades
   the result (batch_activated False, succeeded rows labelled "created").
"""
import asyncio
import time
import uuid
from typing import List, Optional

from app.config import Settings
from app.downstream import DirectoryClient, DownstreamError
from app.failure_policy import get_failure_policy
from app.models import BulkResult, HospitalRow, RowResult
from app.store import BatchStore


async def process_bulk(
    rows: List[HospitalRow],
    client: DirectoryClient,
    store: BatchStore,
    settings: Settings,
) -> BulkResult:
    """Create all ``rows`` as one batch and resolve its fate.

    Returns a BulkResult describing per-row outcomes and whether the batch was
    activated. Never raises on downstream failure.
    """
    batch_id = str(uuid.uuid4())
    store.create(batch_id, len(rows))
    start = time.perf_counter()

    semaphore = asyncio.Semaphore(settings.max_concurrency)

    async def _create_one(i: int, row: HospitalRow) -> RowResult:
        async with semaphore:
            try:
                hid: Optional[int] = await client.create_hospital(row, batch_id)
            except DownstreamError:
                await store.increment(batch_id, failed=1)
                return RowResult(row=i, hospital_id=None, name=row.name, status="failed")
            await store.increment(batch_id, completed=1)
            return RowResult(row=i, hospital_id=hid, name=row.name, status="")

    results: List[RowResult] = await asyncio.gather(
        *(_create_one(i, row) for i, row in enumerate(rows, start=1))
    )
    results.sort(key=lambda r: r.row)

    failed_count = sum(1 for r in results if r.hospital_id is None)
    succeeded_count = len(results) - failed_count

    if failed_count == 0:
        try:
            await client.activate_batch(batch_id)
            batch_activated = True
            for r in results:
                r.status = "created_and_activated"
        except DownstreamError:
            batch_activated = False
            for r in results:
                r.status = "created"
    else:
        policy = get_failure_policy(settings.failure_policy)
        try:
            outcome = await policy.resolve(batch_id, client)
            batch_activated = outcome.batch_activated
            succ_status = outcome.succeeded_status
        except DownstreamError:
            batch_activated = False
            succ_status = "created"
        for r in results:
            if r.hospital_id is not None:
                r.status = succ_status
            else:
                r.status = "failed"

    state = "completed" if (failed_count == 0 and batch_activated) else "failed"
    await store.finalize(batch_id, state=state, batch_activated=batch_activated)

    processing_time_seconds = round(time.perf_counter() - start, 2)

    return BulkResult(
        batch_id=batch_id,
        total_hospitals=len(rows),
        processed_hospitals=succeeded_count,
        failed_hospitals=failed_count,
        processing_time_seconds=processing_time_seconds,
        batch_activated=batch_activated,
        hospitals=results,
    )
