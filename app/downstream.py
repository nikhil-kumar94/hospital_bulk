"""Async client for the downstream Hospital Directory API.

The client wraps the three directory operations the bulk processor needs:
creating a hospital, activating a creation batch, and deleting a creation
batch. Retry behaviour differs by idempotency:

* ``create_hospital`` uses a non-idempotent POST, so it retries ONLY when the
  connection was provably never established (ConnectError / ConnectTimeout).
  A read timeout must never be retried: the request may already have created
  the record, and a retry would duplicate the hospital.
* ``activate_batch`` and ``delete_batch`` are idempotent, so they also retry
  on read timeouts and 5xx responses.
"""
import asyncio
from typing import Optional

import httpx

from app.models import HospitalRow

BACKOFF_BASE = 0.05


async def _backoff_sleep(attempt: int) -> None:
    """Sleep for a short exponential backoff before the next retry."""
    delay = BACKOFF_BASE * (2 ** attempt)
    if delay > 0:
        await asyncio.sleep(delay)


class DownstreamError(Exception):
    """Raised when a downstream directory call ultimately fails.

    Carries the HTTP status code when the failure was an HTTP response, so
    callers can distinguish transport failures from server errors.
    """

    def __init__(self, message: str, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class DirectoryClient:
    """Thin async wrapper over the downstream Hospital Directory API."""

    def __init__(self, client: httpx.AsyncClient, base_url: str, max_retries: int) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._max_retries = max_retries

    async def create_hospital(self, row: HospitalRow, batch_id: str) -> int:
        """Create one hospital; return its new integer id.

        Retries ONLY on ConnectError / ConnectTimeout (connection provably
        never established). Any other failure — non-2xx status, ReadTimeout,
        or any other exception — raises DownstreamError WITHOUT retrying,
        because POST is not idempotent.
        """
        url = f"{self._base_url}/hospitals/"
        body = {
            "name": row.name,
            "address": row.address,
            "phone": row.phone,
            "creation_batch_id": batch_id,
        }

        attempt = 0
        while True:
            try:
                response = await self._client.post(url, json=body)
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                if attempt < self._max_retries:
                    await _backoff_sleep(attempt)
                    attempt += 1
                    continue
                raise DownstreamError(
                    f"create_hospital failed to connect after "
                    f"{self._max_retries} retries: {exc!r}"
                ) from exc
            except Exception as exc:
                raise DownstreamError(
                    f"create_hospital request error (not retried): {exc!r}"
                ) from exc

            if 200 <= response.status_code < 300:
                return response.json()["id"]

            raise DownstreamError(
                f"create_hospital returned HTTP {response.status_code}",
                status_code=response.status_code,
            )

    async def activate_batch(self, batch_id: str) -> None:
        """Activate a creation batch (idempotent)."""
        url = f"{self._base_url}/hospitals/batch/{batch_id}/activate"
        await self._request_idempotent("PATCH", url, "activate_batch")

    async def delete_batch(self, batch_id: str) -> None:
        """Delete a creation batch (idempotent)."""
        url = f"{self._base_url}/hospitals/batch/{batch_id}"
        await self._request_idempotent("DELETE", url, "delete_batch")

    async def _request_idempotent(self, method: str, url: str, op: str) -> None:
        """Run an idempotent request, retrying on connect/read timeouts and 5xx."""
        attempt = 0
        while True:
            try:
                response = await self._client.request(method, url)
            except (
                httpx.ConnectError,
                httpx.ConnectTimeout,
                httpx.ReadTimeout,
            ) as exc:
                if attempt < self._max_retries:
                    await _backoff_sleep(attempt)
                    attempt += 1
                    continue
                raise DownstreamError(
                    f"{op} transport error after {self._max_retries} retries: {exc!r}"
                ) from exc
            except Exception as exc:
                raise DownstreamError(f"{op} request error: {exc!r}") from exc

            if 200 <= response.status_code < 300:
                return

            if 500 <= response.status_code < 600 and attempt < self._max_retries:
                await _backoff_sleep(attempt)
                attempt += 1
                continue

            raise DownstreamError(
                f"{op} returned HTTP {response.status_code}",
                status_code=response.status_code,
            )
