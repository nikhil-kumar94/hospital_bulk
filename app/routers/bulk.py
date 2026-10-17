"""HTTP routes for hospital bulk processing."""
from fastapi import APIRouter, HTTPException, Request, UploadFile

from app.bulk_service import process_bulk
from app.csv_parser import CSVValidationError, parse_csv
from app.models import BatchStatus, BulkResult

router = APIRouter()


@router.post("/hospitals/bulk", response_model=BulkResult)
async def bulk_create(request: Request, file: UploadFile) -> BulkResult:
    """Parse the uploaded CSV and process the whole batch downstream."""
    settings = request.app.state.settings
    content = await file.read()
    try:
        rows = parse_csv(content, settings.max_rows)
    except CSVValidationError as exc:
        raise HTTPException(status_code=400, detail=exc.message)

    return await process_bulk(
        rows,
        request.app.state.directory,
        request.app.state.store,
        settings,
    )


@router.post("/hospitals/bulk/validate")
async def bulk_validate(request: Request, file: UploadFile) -> dict:
    """Validate the uploaded CSV without making any downstream call."""
    settings = request.app.state.settings
    content = await file.read()
    try:
        rows = parse_csv(content, settings.max_rows)
    except CSVValidationError as exc:
        return {"valid": False, "row_count": 0, "errors": [exc.message]}
    return {"valid": True, "row_count": len(rows), "errors": []}


@router.get("/hospitals/bulk/{batch_id}/status", response_model=BatchStatus)
async def bulk_status(request: Request, batch_id: str) -> BatchStatus:
    """Return live progress for a batch, or 404 if it is unknown."""
    status = request.app.state.store.get(batch_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Batch not found.")
    return status
