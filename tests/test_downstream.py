"""Tests for the Downstream Directory client (app/downstream.py).

All HTTP is mocked with respx; no real network calls are ever made and no
real hospitals are created.
"""
import json

import httpx
import pytest
import respx

from app.downstream import DirectoryClient, DownstreamError
from app.models import HospitalRow

BASE_URL = "https://api.test"


async def test_create_hospital_returns_id_and_sends_batch_id():
    row = HospitalRow(name="Gen Hospital", address="1 Main St", phone="555-1234")
    batch_id = "batch-abc-123"

    with respx.mock(assert_all_called=False) as respx_mock:
        route = respx_mock.post(f"{BASE_URL}/hospitals/").mock(
            return_value=httpx.Response(200, json={"id": 101})
        )
        async with httpx.AsyncClient() as c:
            client = DirectoryClient(c, base_url=BASE_URL, max_retries=2)
            result = await client.create_hospital(row, batch_id)

    assert result == 101
    assert route.call_count == 1
    sent_body = json.loads(route.calls.last.request.content)
    assert sent_body["creation_batch_id"] == batch_id
    assert sent_body["name"] == "Gen Hospital"
    assert sent_body["address"] == "1 Main St"
    assert sent_body["phone"] == "555-1234"


async def test_create_retries_on_connect_error_then_succeeds(monkeypatch):
    # Keep the backoff at zero so the retry does not actually sleep.
    import app.downstream as downstream

    monkeypatch.setattr(downstream, "BACKOFF_BASE", 0.0)

    row = HospitalRow(name="Gen", address="1 Main St")
    batch_id = "batch-xyz"

    with respx.mock(assert_all_called=False) as respx_mock:
        route = respx_mock.post(f"{BASE_URL}/hospitals/").mock(
            side_effect=[
                httpx.ConnectError("boom"),
                httpx.Response(200, json={"id": 5}),
            ]
        )
        async with httpx.AsyncClient() as c:
            client = DirectoryClient(c, base_url=BASE_URL, max_retries=2)
            result = await client.create_hospital(row, batch_id)

    assert result == 5
    assert route.call_count == 2


async def test_create_does_not_retry_on_read_timeout():
    # KEY TEST: POST is not idempotent, so a read timeout must NOT be retried.
    row = HospitalRow(name="Gen", address="1 Main St")
    batch_id = "batch-timeout"

    with respx.mock(assert_all_called=False) as respx_mock:
        route = respx_mock.post(f"{BASE_URL}/hospitals/").mock(
            side_effect=httpx.ReadTimeout("read timed out")
        )
        async with httpx.AsyncClient() as c:
            client = DirectoryClient(c, base_url=BASE_URL, max_retries=3)
            with pytest.raises(DownstreamError):
                await client.create_hospital(row, batch_id)

    assert route.call_count == 1


async def test_create_raises_on_http_500_and_does_not_retry():
    row = HospitalRow(name="Gen", address="1 Main St")
    batch_id = "batch-500"

    with respx.mock(assert_all_called=False) as respx_mock:
        route = respx_mock.post(f"{BASE_URL}/hospitals/").mock(
            return_value=httpx.Response(500, json={"detail": "nope"})
        )
        async with httpx.AsyncClient() as c:
            client = DirectoryClient(c, base_url=BASE_URL, max_retries=3)
            with pytest.raises(DownstreamError):
                await client.create_hospital(row, batch_id)

    assert route.call_count == 1


async def test_activate_batch_hits_patch_endpoint():
    batch_id = "batch-act"

    with respx.mock(assert_all_called=False) as respx_mock:
        route = respx_mock.patch(
            f"{BASE_URL}/hospitals/batch/{batch_id}/activate"
        ).mock(return_value=httpx.Response(200))
        async with httpx.AsyncClient() as c:
            client = DirectoryClient(c, base_url=BASE_URL, max_retries=2)
            await client.activate_batch(batch_id)

    assert route.call_count == 1
    request = route.calls.last.request
    assert request.method == "PATCH"
    assert request.url.path == f"/hospitals/batch/{batch_id}/activate"


async def test_delete_batch_hits_delete_endpoint():
    batch_id = "batch-del"

    with respx.mock(assert_all_called=False) as respx_mock:
        route = respx_mock.delete(f"{BASE_URL}/hospitals/batch/{batch_id}").mock(
            return_value=httpx.Response(200)
        )
        async with httpx.AsyncClient() as c:
            client = DirectoryClient(c, base_url=BASE_URL, max_retries=2)
            await client.delete_batch(batch_id)

    assert route.call_count == 1
    request = route.calls.last.request
    assert request.method == "DELETE"
    assert request.url.path == f"/hospitals/batch/{batch_id}"
