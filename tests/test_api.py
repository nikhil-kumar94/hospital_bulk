"""API-level tests for the bulk-processing FastAPI app.

These exercise the HTTP surface via FastAPI's in-process TestClient while
mocking only the OUTBOUND downstream directory calls with respx. The
TestClient's ASGI transport is NOT intercepted by respx (that is the
app itself); only the app's httpx calls to ``base_url`` are mocked.
"""
import httpx
import respx
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

BASE_URL = "https://api.test"

VALID_CSV = b"name,address,phone\nA,1 St,5\nB,2 St,\n"


def _build_app():
    return create_app(Settings(base_url=BASE_URL, max_concurrency=5))


def test_bulk_happy_path_activates_batch():
    with respx.mock(assert_all_called=False) as router:
        create_route = router.post(f"{BASE_URL}/hospitals/").mock(
            return_value=httpx.Response(200, json={"id": 101})
        )
        activate_route = router.patch(
            url__regex=r"https://api\.test/hospitals/batch/[^/]+/activate"
        ).mock(return_value=httpx.Response(200))

        app = _build_app()
        with TestClient(app) as client:
            resp = client.post(
                "/hospitals/bulk",
                files={"file": ("h.csv", VALID_CSV, "text/csv")},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["batch_activated"] is True
        assert body["total_hospitals"] == 2
        assert body["processed_hospitals"] == 2
        assert create_route.called
        assert activate_route.called


def test_bulk_oversized_csv_returns_400():
    # Header + 21 data rows (limit is max_rows=20).
    rows = b"".join(b"A,%d St,5\n" % i for i in range(1, 22))
    oversized = b"name,address,phone\n" + rows

    with respx.mock(assert_all_called=False) as router:
        create_route = router.post(f"{BASE_URL}/hospitals/").mock(
            return_value=httpx.Response(200, json={"id": 101})
        )

        app = _build_app()
        with TestClient(app) as client:
            resp = client.post(
                "/hospitals/bulk",
                files={"file": ("big.csv", oversized, "text/csv")},
            )

        assert resp.status_code == 400
        # A validation failure must never hit the downstream.
        assert not create_route.called


def test_validate_endpoint_makes_no_downstream_call():
    malformed = b"name,phone\nA,1"  # missing required 'address' column

    with respx.mock(assert_all_called=False) as router:
        create_route = router.post(f"{BASE_URL}/hospitals/").mock(
            return_value=httpx.Response(200, json={"id": 101})
        )
        activate_route = router.patch(
            url__regex=r"https://api\.test/hospitals/batch/[^/]+/activate"
        ).mock(return_value=httpx.Response(200))

        app = _build_app()
        with TestClient(app) as client:
            bad = client.post(
                "/hospitals/bulk/validate",
                files={"file": ("bad.csv", malformed, "text/csv")},
            )
            good = client.post(
                "/hospitals/bulk/validate",
                files={"file": ("ok.csv", VALID_CSV, "text/csv")},
            )

        assert bad.status_code == 200
        bad_body = bad.json()
        assert bad_body["valid"] is False
        assert bad_body["errors"]  # non-empty

        assert good.status_code == 200
        good_body = good.json()
        assert good_body["valid"] is True
        assert good_body["row_count"] == 2

        # The validate endpoint must not touch the downstream at all.
        assert not create_route.called
        assert not activate_route.called


def test_status_unknown_batch_returns_404():
    app = _build_app()
    with TestClient(app) as client:
        resp = client.get("/hospitals/bulk/does-not-exist/status")
    assert resp.status_code == 404
