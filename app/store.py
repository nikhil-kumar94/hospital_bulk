"""In-memory batch store tracking live progress for bulk-processing batches."""
import asyncio
from typing import Dict, Optional

from app.models import BatchStatus


class BatchStore:
    """Thread-safe-ish async store of BatchStatus keyed by batch_id.

    Concurrent writers are serialized through an asyncio.Lock so that
    increment/finalize mutations never race.
    """

    def __init__(self) -> None:
        self._batches: Dict[str, BatchStatus] = {}
        self._lock = asyncio.Lock()

    def create(self, batch_id: str, total: int) -> None:
        self._batches[batch_id] = BatchStatus(
            batch_id=batch_id,
            state="processing",
            total=total,
            completed=0,
            failed=0,
            batch_activated=False,
        )

    async def increment(self, batch_id: str, *, completed: int = 0, failed: int = 0) -> None:
        async with self._lock:
            status = self._batches[batch_id]
            status.completed += completed
            status.failed += failed

    async def finalize(self, batch_id: str, *, state: str, batch_activated: bool) -> None:
        async with self._lock:
            status = self._batches[batch_id]
            status.state = state
            status.batch_activated = batch_activated

    def get(self, batch_id: str) -> Optional[BatchStatus]:
        return self._batches.get(batch_id)
