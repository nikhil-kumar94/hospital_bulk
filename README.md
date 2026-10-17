# Hospital Bulk Processing System

A FastAPI service that bulk-creates hospitals from a CSV upload by orchestrating calls to the
existing **Hospital Directory API**. It creates every row under one batch ID, then activates the
batch so the hospitals go live together — or, if any row fails, applies a configurable
**failure policy** (default: roll the whole batch back).

> Design rationale and the full decision log live in [`../docs/specs.md`](../docs/specs.md);
> the task-by-task build plan is in [`../docs/plan.md`](../docs/plan.md).

## How it works

1. `POST /hospitals/bulk` accepts a CSV (`name,address,phone`; phone optional; **max 20 rows**).
2. The service generates a UUID `batch_id` and creates each hospital via `POST /hospitals/`
   with that `creation_batch_id` (the downstream marks batch-created hospitals **inactive**).
3. Creates are run **concurrently** with a bounded semaphore (the downstream is slow).
4. **On full success** → `PATCH /hospitals/batch/{id}/activate` → all go live.
   **On any failure** → the selected `FAILURE_POLICY` decides (see below).
5. Returns a per-row report (batch id, counts, timing, per-row status).

### Failure policy (Strategy pattern)

Selected via `FAILURE_POLICY`:

| Value | On a partial failure | `batch_activated` |
|-------|----------------------|-------------------|
| `rollback` *(default)* | `DELETE` the batch — nothing persists (clean all-or-nothing) | `false` |
| `leave` | Leave succeeded hospitals created-but-inactive | `false` |
| `partial` | Activate the succeeded ones; failed rows reported | `true` |

**Retries are connection-error-only on create** (never on read-timeouts/5xx), because
`POST /hospitals/` is not idempotent — retrying an ambiguous timeout could duplicate a record.

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/hospitals/bulk` | Upload a CSV; create + activate the batch; returns the processing report. `400` on invalid CSV. |
| POST | `/hospitals/bulk/validate` | Validate a CSV without any downstream calls → `{valid, row_count, errors}`. |
| GET | `/hospitals/bulk/{batch_id}/status` | Poll a batch's progress (`404` if unknown). |

Interactive API docs (Swagger) are served at `/docs`.

## Configuration (environment variables)

| Var | Default | Meaning |
|-----|---------|---------|
| `BASE_URL` | `https://hospital-directory.onrender.com` | Downstream Hospital Directory API base URL |
| `FAILURE_POLICY` | `rollback` | `rollback` \| `leave` \| `partial` |
| `MAX_CONCURRENCY` | `10` | Max concurrent downstream create calls |
| `REQUEST_TIMEOUT` | `30` | Per-request timeout (seconds) |
| `MAX_RETRIES` | `2` | Retry attempts (see retry rules above) |
| `MAX_ROWS` | `20` | Max hospitals per CSV |

## Run with Docker (recommended)

```bash
# from this directory (apps/)
docker compose up --build
# API now on http://localhost:8000  (docs at /docs)

# override a setting, e.g. the failure policy:
FAILURE_POLICY=partial docker compose up --build
```

Stop with `docker compose down`.

## Run locally (without Docker)

```bash
# from this directory (apps/)
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/uvicorn app.main:create_app --factory --reload --port 8000
```

## Run the tests

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -v
```

## Example usage

```bash
# Create a sample CSV
printf 'name,address,phone\nGeneral Hospital,1 Main St,555-1234\nCity Clinic,2 Oak Ave,\n' > hospitals.csv

# Validate it first (no downstream calls)
curl -s -F "file=@hospitals.csv" http://localhost:8000/hospitals/bulk/validate

# Bulk create + activate
curl -s -F "file=@hospitals.csv" http://localhost:8000/hospitals/bulk

# Poll a batch's status
curl -s http://localhost:8000/hospitals/bulk/<batch_id>/status
```

Example bulk response:

```json
{
  "batch_id": "550e8400-e29b-41d4-a716-446655440000",
  "total_hospitals": 2,
  "processed_hospitals": 2,
  "failed_hospitals": 0,
  "processing_time_seconds": 1.73,
  "batch_activated": true,
  "hospitals": [
    { "row": 1, "hospital_id": 101, "name": "General Hospital", "status": "created_and_activated" }
  ]
}
```

## Project layout

```
apps/
  app/
    main.py            # create_app() factory + lifespan (httpx client, store)
    config.py          # Settings (env-driven)
    models.py          # Pydantic models
    csv_parser.py      # CSV parsing + validation
    downstream.py      # DirectoryClient (httpx wrapper, safe retries)
    store.py           # in-memory batch status store
    failure_policy.py  # FailurePolicy strategies (rollback/leave/partial)
    bulk_service.py    # orchestrator (fan-out + activate/rollback)
    routers/bulk.py    # API endpoints
  tests/               # unit + integration tests
  Dockerfile, docker-compose.yml, requirements*.txt
```
# hospital_bulk
