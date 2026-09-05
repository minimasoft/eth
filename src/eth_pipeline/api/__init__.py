from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from eth_pipeline.api.lifespan import lifespan

# Re-export all models for backward compatibility
from eth_pipeline.api.models import (  # noqa: F401 — intentional re-export
    APIInfo,
    ChunkTextResponse,
    ComparisonDocument,
    ComparisonEvent,
    ComparisonResponse,
    DocumentCreated,
    DocumentDeleted,
    DocumentInput,
    DocumentListItem,
    DocumentListResponse,
    DocumentStatus,
    DocumentUploadCreated,
    EventListV2Response,
    EventLocationDetail,
    EventParticipantDetail,
    EventRefDetail,
    EventV2DetailResponse,
    EventV2ListItem,
    HealthResponse,
    ProcessingLogListItem,
    ProcessingLogListResponse,
)

logger = logging.getLogger(__name__)

# =======================================================================
# Application
# =======================================================================

app = FastAPI(
    title="eth-pipeline",
    description="Document processing pipeline with Temporal and PostgreSQL",
    version="0.1.0",
    lifespan=lifespan,
)

# Serve the web UI from /ui (single-page static application)
# The static directory lives at eth_pipeline/static/ — one level above the api/ package.
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

# Explicit route for the providers page must come BEFORE the StaticFiles mount,
# because Starlette matches routes in order and the mount would catch all /ui/* paths.
@app.get("/ui/providers")
async def get_providers_page(request: Request) -> FileResponse:  # noqa: ARG001
    return FileResponse(str(STATIC_DIR / "providers.html"))

if STATIC_DIR.is_dir():
    app.mount(
        "/ui",
        StaticFiles(directory=str(STATIC_DIR), html=True),
        name="ui",
    )
else:
    logger.warning("Static directory %s not found — UI will not be served at /ui", STATIC_DIR)

# =======================================================================
# Include route modules via their routers
# =======================================================================

# Import routers AFTER app is created to avoid circular imports.
# Each route module imports `app` from this package, which is now available.

from eth_pipeline.api.routes.comparisons import router as comparisons_router  # noqa: E402
from eth_pipeline.api.routes.documents import router as documents_router  # noqa: E402
from eth_pipeline.api.routes.events_v2 import router as events_v2_router  # noqa: E402
from eth_pipeline.api.routes.providers import router as providers_router  # noqa: E402

app.include_router(documents_router)
app.include_router(events_v2_router)
app.include_router(comparisons_router)
app.include_router(providers_router)
