"""FastAPI application factory for the Hospital Bulk Processing System."""
from contextlib import asynccontextmanager
from typing import Optional

import httpx
from fastapi import FastAPI

from app.config import Settings, get_settings
from app.downstream import DirectoryClient
from app.routers.bulk import router as bulk_router
from app.store import BatchStore


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    """Build and return a configured FastAPI application.

    Accepts an optional ``settings`` so tests can inject a test base_url.
    A single shared ``httpx.AsyncClient`` is created on startup and closed
    on shutdown via the lifespan.
    """
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        http_client = httpx.AsyncClient(timeout=settings.request_timeout)
        app.state.http_client = http_client
        app.state.directory = DirectoryClient(
            http_client, settings.base_url, settings.max_retries
        )
        app.state.store = BatchStore()
        app.state.settings = settings
        try:
            yield
        finally:
            await app.state.http_client.aclose()

    app = FastAPI(lifespan=lifespan)
    app.include_router(bulk_router)
    return app


app = create_app()
