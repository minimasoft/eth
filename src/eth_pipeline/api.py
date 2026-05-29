"""
eth-pipeline: FastAPI application for document ingestion.

Provides HTTP endpoints for submitting documents to the pipeline,
checking service health, retrieving document status, and triggering
reprocessing via event deletion.

Endpoints
---------
- ``GET  /``                         — Basic API information
- ``GET  /health``                   — Liveness check (no DB required)
- ``POST /documents``                — Submit a document for processing (stored in SurrealDB)
- ``GET  /documents/{document_id}``  — Get document status and metadata
- ``DELETE /documents/{document_id}/events`` — Clear extraction results and reset status

Lifespan
--------
On startup the application connects to SurrealDB using credentials from
environment variables (or defaults from :mod:`eth_pipeline.db`).  The
connection is held in ``app.state.db`` and closed gracefully on shutdown.

When Temporal is available, a client connection is also established and
stored in ``app.state.temporal``.  If Temporal is unreachable the API
continues in degraded mode (documents are ingested but not processed).
"""

from __future__ import annotations

import base64
import logging
import os
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from urllib.parse import urlparse

import httpx

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response as FastAPIResponse
from pydantic import BaseModel
from surrealdb import AsyncWsSurrealConnection

from eth_pipeline.db import (
    DEFAULT_DB,
    DEFAULT_NS,
    DEFAULT_PASS,
    DEFAULT_URL,
    DEFAULT_USER,
    _connect,
)

logger = logging.getLogger(__name__)

# =======================================================================
# Pydantic models
# =======================================================================


class DocumentInput(BaseModel):
    """Request body for ``POST /documents``."""

    text: str
    """Plain-text content of the document to be processed."""

    filename: str
    """Original filename (used for display and debugging)."""

    mime_type: str | None = None
    """MIME type of the source (defaults to ``text/plain`` at creation)."""


class DocumentCreated(BaseModel):
    """Response body for a successful ``POST /documents`` (HTTP 201)."""

    document_id: str
    """Unique identifier for the created document."""

    status: str = "pending"
    """Initial lifecycle status of the document."""


class DocumentStatus(BaseModel):
    """Response body for ``GET /documents/{document_id}``."""

    document_id: str
    """Unique identifier of the document."""

    status: str
    """Current processing status (pending/processing/processed/failed)."""

    filename: str
    """Original filename submitted at creation time."""

    error_message: str | None = None
    """Human-readable error description when status is ``failed``."""

    created_at: str | None = None
    """ISO-8601 timestamp of document creation (if available)."""


class EventsCleared(BaseModel):
    """Response body for ``DELETE /documents/{document_id}/events``."""

    document_id: str
    """Unique identifier of the document whose events were cleared."""

    status: str = "pending"
    """The document status after clearing events."""

    events_cleared: bool = True
    """Whether any events were actually cleared."""


class HealthResponse(BaseModel):
    """Response body for ``GET /health``."""

    status: str = "ok"


class GraphQLRequest(BaseModel):
    """Request body for ``POST /graphql``.

    SurrealDB's auto-GraphQL endpoint accepts standard GraphQL POST bodies
    (``query`` + optional ``variables``).  We forward the body as-is.
    """

    query: str
    """The GraphQL query string."""

    variables: dict | None = None
    """Optional variables for the GraphQL query."""

    operationName: str | None = None
    """Optional operation name for the GraphQL request."""


class APIInfo(BaseModel):
    """Response body for ``GET /``."""

    name: str
    version: str
    description: str
    endpoints: dict[str, str]


# =======================================================================
# Lifespan
# =======================================================================


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Connect to SurrealDB and Temporal on startup; close on shutdown.

    Credentials are read from environment variables with fallback to the
    local-development defaults defined in :mod:`eth_pipeline.db`.

    Temporal connection uses ``TEMPORAL_URL`` (default ``localhost:7233``)
    and is best-effort — the API works in degraded mode when Temporal is
    not available.
    """
    # ---- SurrealDB ----
    url = os.environ.get("SURREAL_URL", DEFAULT_URL)
    user = os.environ.get("SURREAL_USER", DEFAULT_USER)
    password = os.environ.get("SURREAL_PASS", DEFAULT_PASS)
    ns = os.environ.get("SURREAL_NS", DEFAULT_NS)
    database = os.environ.get("SURREAL_DB", DEFAULT_DB)

    logger.info(
        "Connecting to SurrealDB at %s (ns=%s, db=%s)",
        url, ns, database,
    )

    try:
        conn = await _connect(url, user, password, ns, database)
    except ConnectionError:
        logger.warning(
            "SurrealDB unreachable at %s — running in degraded mode",
            url,
        )
        app.state.db = None
    else:
        app.state.db = conn

    # ---- Temporal ----
    temporal_url = os.environ.get("TEMPORAL_URL", "localhost:7233")
    temporal_namespace = os.environ.get("TEMPORAL_NAMESPACE", "default")

    logger.info(
        "Connecting to Temporal at %s (namespace=%s)",
        temporal_url,
        temporal_namespace,
    )

    try:
        from temporalio.client import Client as TemporalClient

        temporal_client = await TemporalClient.connect(
            temporal_url,
            namespace=temporal_namespace,
        )
        app.state.temporal = temporal_client
        logger.info("Temporal client connected at %s", temporal_url)
    except Exception:
        logger.warning(
            "Temporal unreachable at %s — running in degraded mode",
            temporal_url,
        )
        app.state.temporal = None

    yield

    # ---- Cleanup ----
    if app.state.db is not None:
        logger.info("Closing SurrealDB connection")
        await app.state.db.close()

    if app.state.temporal is not None:
        logger.info("Closing Temporal client")
        app.state.temporal.close()


# =======================================================================
# Application
# =======================================================================

app = FastAPI(
    title="eth-pipeline",
    description="Ethereum document processing pipeline with Temporal and SurrealDB",
    version="0.1.0",
    lifespan=lifespan,
)


# =======================================================================
# Endpoints
# =======================================================================


@app.get("/", response_model=APIInfo)
async def root() -> APIInfo:
    """Return basic API information and available endpoints."""
    return APIInfo(
        name="eth-pipeline",
        version="0.1.0",
        description="Ethereum document processing pipeline with Temporal and SurrealDB",
        endpoints={
            "/": "This information",
            "/health": "Liveness check",
            "/graphql": "Proxy to SurrealDB auto-GraphQL (POST)",
            "/documents": "Submit a document for processing (POST)",
            "/documents/{document_id}": "Get document status (GET)",
            "/documents/{document_id}/events": "Clear extraction results (DELETE)",
        },
    )


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness check endpoint.

    Returns ``{"status": "ok"}`` regardless of database state so that
    orchestrators (Docker, Kubernetes) can monitor the process itself.
    """
    return HealthResponse(status="ok")


@app.post("/documents", response_model=DocumentCreated, status_code=201)
async def create_document(input: DocumentInput) -> DocumentCreated:
    """Ingest a new document into the pipeline.

    The document is stored in SurrealDB with status ``"pending"`` for
    later extraction by the Temporal workflow.  If SurrealDB is not
    available the endpoint returns HTTP 503.

    When Temporal is connected, a workflow is started automatically to
    process the document.  If Temporal is unavailable the document is
    still stored and can be processed later.
    """
    db: AsyncWsSurrealConnection | None = app.state.db

    if db is None:
        logger.error("POST /documents rejected — SurrealDB unavailable")
        raise HTTPException(
            status_code=503,
            detail="SurrealDB is not available. Please try again later.",
        )

    doc_id = str(uuid.uuid4().hex)  # hex = no dashes (SurrealDB SQL parser limitation)

    # For plain-text documents the original blob is a base64-encoded
    # version of the text content (the schema requires a string value).
    original_blob = base64.b64encode(input.text.encode("utf-8")).decode("ascii")

    try:
        await db.create(
            f"document:{doc_id}",
            {
                "text_content": input.text,
                "original_blob": original_blob,
                "filename": input.filename,
                "mime_type": input.mime_type or "text/plain",
                "status": "pending",
                "error_message": None,
            },
        )
    except Exception as exc:
        logger.error("Failed to create document in SurrealDB: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Failed to store document in database.",
        ) from exc

    logger.info(
        "Created document %s (filename=%s, status=pending)",
        doc_id,
        input.filename,
    )

    # ---- Trigger Temporal workflow (best-effort) ----
    temporal = getattr(app.state, "temporal", None)
    if temporal is not None:
        try:
            from eth_pipeline.workflows import DocumentProcessingWorkflow

            await temporal.start_workflow(
                DocumentProcessingWorkflow.run,
                id=f"doc-{doc_id}",
                task_queue="event-extraction",
                args=[doc_id, input.text],
                id_conflict_policy=1,  # USE_EXISTING
            )
            logger.info("Temporal workflow started for document %s", doc_id)
        except Exception as exc:
            logger.warning(
                "Failed to start Temporal workflow for document %s: %s",
                doc_id,
                exc,
            )
    else:
        logger.warning(
            "Temporal not available — document %s stored but workflow not started",
            doc_id,
        )

    return DocumentCreated(document_id=doc_id, status="pending")


@app.get("/documents/{document_id}", response_model=DocumentStatus)
async def get_document(document_id: str) -> DocumentStatus:
    """Retrieve document status and metadata.

    Queries SurrealDB for the document record identified by ``document_id``
    and returns its current status, filename, error message, and creation
    timestamp.

    Returns HTTP 404 if the document does not exist and HTTP 503 if the
    database is unavailable.
    """
    db: AsyncWsSurrealConnection | None = app.state.db

    if db is None:
        logger.error("GET /documents/%s rejected — SurrealDB unavailable", document_id)
        raise HTTPException(
            status_code=503,
            detail="SurrealDB is not available. Please try again later.",
        )

    doc_ref = f"document:{document_id}"

    try:
        # Use WHERE id = $doc_id with a RecordID parameter to avoid
        # SurrealDB v3's "Cannot perform subtraction with 'record'
        # and 'table'" error that occurs when the record does not
        # exist in a SCHEMAFULL table with inline FROM {doc_ref}.
        from surrealdb.data.types.record_id import RecordID

        doc_id_obj = RecordID("document", document_id)
        result = await db.query(
            "SELECT * FROM document WHERE id = $doc_id",
            {"doc_id": doc_id_obj},
        )
    except Exception as exc:
        logger.error("Failed to query document %s: %s", document_id, exc)
        raise HTTPException(
            status_code=502,
            detail="Failed to query database.",
        ) from exc

    # query() returns a flat list of dicts when records exist,
    # or an empty list when no records match.
    records: list[dict] = [
        r for r in (result or []) if isinstance(r, dict)
    ]

    if not records:
        logger.warning("Document %s not found", document_id)
        raise HTTPException(
            status_code=404,
            detail=f"Document {document_id} not found.",
        )

    record = records[0]

    created_at_raw = record.get("created_at")
    if created_at_raw is not None:
        # SurrealDB returns a datetime object; convert to ISO string
        # for the Pydantic model (which expects str | None).
        created_at_str = (
            created_at_raw.isoformat()
            if hasattr(created_at_raw, "isoformat")
            else str(created_at_raw)
        )
    else:
        created_at_str = None

    return DocumentStatus(
        document_id=document_id,
        status=record.get("status", "unknown"),
        filename=record.get("filename", ""),
        error_message=record.get("error_message"),
        created_at=created_at_str,
    )


@app.delete(
    "/documents/{document_id}/events",
    response_model=EventsCleared,
)
async def clear_document_events(document_id: str) -> EventsCleared:
    """Clear all extraction results for a document and reset its status.

    Deletes all ``reference`` records linked to events that belong to the
    given document, then deletes all ``event`` records for the document,
    and finally resets the document status to ``"pending"`` with no error.

    This enables reprocessing: after calling this endpoint, re-triggering
    the workflow (e.g. via a new POST to ``/documents`` or a workflow
    restart) will create fresh extraction results.

    Returns HTTP 404 if the document does not exist and HTTP 503 if the
    database is unavailable.
    """
    db: AsyncWsSurrealConnection | None = app.state.db

    if db is None:
        logger.error(
            "DELETE /documents/%s/events rejected — SurrealDB unavailable",
            document_id,
        )
        raise HTTPException(
            status_code=503,
            detail="SurrealDB is not available. Please try again later.",
        )

    doc_ref = f"document:{document_id}"

    # Verify document exists — use WHERE id = $doc_id with a RecordID
    # parameter to avoid SurrealDB v3's subtraction error on nonexistent
    # records in SCHEMAFULL tables.
    try:
        from surrealdb.data.types.record_id import RecordID

        doc_id_obj = RecordID("document", document_id)
        exists_result = await db.query(
            "SELECT * FROM document WHERE id = $doc_id",
            {"doc_id": doc_id_obj},
        )
    except Exception as exc:
        logger.error("Failed to query document %s: %s", document_id, exc)
        raise HTTPException(
            status_code=502,
            detail="Failed to query database.",
        ) from exc

    exists_records: list[dict] = [
        r for r in (exists_result or []) if isinstance(r, dict)
    ]
    if not exists_records:
        logger.warning("Document %s not found for event clear", document_id)
        raise HTTPException(
            status_code=404,
            detail=f"Document {document_id} not found.",
        )

    try:
        # Delete references linked to events for this document
        await db.query(
            "DELETE reference WHERE event IN "
            "(SELECT id FROM event WHERE document = $doc_id)",
            {"doc_id": doc_ref},
        )

        # Delete events for this document
        await db.query(
            "DELETE event WHERE document = $doc_id",
            {"doc_id": doc_ref},
        )

        # Reset document status to pending — use inline ref (variable
        # bindings don't work with UPDATE in SurrealDB v3).
        await db.query(
            f"UPDATE {doc_ref} SET status = 'pending', "
            "error_message = NULL, updated_at = time::now()",
        )

        logger.info(
            "Cleared events and reset status for document %s",
            document_id,
        )
    except Exception as exc:
        logger.error(
            "Failed to clear events for document %s: %s",
            document_id,
            exc,
        )
        raise HTTPException(
            status_code=502,
            detail="Failed to clear extraction results.",
        ) from exc

    return EventsCleared(document_id=document_id, status="pending", events_cleared=True)


# =======================================================================
# Helpers
# =======================================================================


def _surreal_http_url(ws_url: str) -> str:
    """Convert a SurrealDB WebSocket URL to an HTTP base URL.

    ``ws://localhost:8000/rpc`` → ``http://localhost:8000``
    ``wss://host/path/rpc``   → ``https://host/path``
    """
    parsed = urlparse(ws_url)
    scheme = "https" if parsed.scheme == "wss" else "http"
    # Strip trailing /rpc from path
    path = parsed.path
    if path.endswith("/rpc"):
        path = path[: -len("/rpc")]
    return f"{scheme}://{parsed.hostname}:{parsed.port}{path}"


# =======================================================================
# GraphQL proxy endpoint
# =======================================================================


@app.post("/graphql")
async def graphql_proxy(request: Request) -> Response:
    """Proxy GraphQL queries to SurrealDB's auto-GraphQL endpoint.

    Accepts any standard GraphQL POST body (``query`` + optional
    ``variables`` / ``operationName``), injects the SurrealDB auth
    headers (``Surreal-Ns``, ``Surreal-DB``, ``Authorization``), and
    returns the SurrealDB response with the same status code.

    Returns HTTP 503 when SurrealDB is unreachable.
    """
    # Read credentials from lifespan environment (same source as
    # the lifespan function).
    ws_url = os.environ.get("SURREAL_URL", DEFAULT_URL)
    user = os.environ.get("SURREAL_USER", DEFAULT_USER)
    password = os.environ.get("SURREAL_PASS", DEFAULT_PASS)
    ns = os.environ.get("SURREAL_NS", DEFAULT_NS)
    database = os.environ.get("SURREAL_DB", DEFAULT_DB)

    graphql_url = f"{_surreal_http_url(ws_url)}/graphql"

    # Build Basic auth header
    auth_value = base64.b64encode(f"{user}:{password}".encode()).decode("ascii")

    # Read the raw request body (forward as-is to SurrealDB)
    body_bytes = await request.body()
    content_type = request.headers.get("content-type", "application/json")

    headers = {
        "Content-Type": content_type,
        "Surreal-Ns": ns,
        "Surreal-DB": database,
        "Authorization": f"Basic {auth_value}",
    }

    logger.info(
        "Proxying GraphQL request to %s (ns=%s, db=%s)",
        graphql_url,
        ns,
        database,
    )

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                graphql_url,
                content=body_bytes,
                headers=headers,
                timeout=30.0,
            )
    except httpx.ConnectError as exc:
        logger.error(
            "SurrealDB unreachable at %s — returning 503",
            graphql_url,
        )
        raise HTTPException(
            status_code=503,
            detail=f"SurrealDB is not available at {graphql_url}. Please try again later.",
        ) from exc
    except httpx.TimeoutException as exc:
        logger.error(
            "SurrealDB timed out at %s — returning 503",
            graphql_url,
        )
        raise HTTPException(
            status_code=503,
            detail="SurrealDB did not respond in time. Please try again later.",
        ) from exc

    logger.info(
        "GraphQL proxy returned HTTP %d for %s",
        response.status_code,
        graphql_url,
    )

    return FastAPIResponse(
        content=response.content,
        status_code=response.status_code,
        media_type=response.headers.get("content-type", "application/json"),
    )
