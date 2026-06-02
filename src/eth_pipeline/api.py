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

import asyncio
import base64
import io
import logging
import os
from pathlib import Path
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from urllib.parse import urlparse

import httpx

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response as FastAPIResponse
from fastapi.staticfiles import StaticFiles
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

from eth_pipeline.storage import get_storage_async

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


class DocumentUploadCreated(BaseModel):
    """Response body for a successful ``POST /documents/upload`` (HTTP 201)."""

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

    blob_format: str | None = None
    """Storage format: 'minio' (object-stored) or None (legacy inline)."""

    blob_path: str | None = None
    """S3 object path when blob_format='minio'; None for legacy inline-stored documents."""

    reference_count: int = 0
    """Total number of verbatim references linked to this document via events."""

    entity_count: int = 0
    """Total number of distinct canonical entities linked to this document's references."""

    chunk_count: int = 0
    """Number of text chunks created from this document."""

    text_word_count: int = 0
    """Word count of the document's extracted text content."""


class DocumentListItem(BaseModel):
    """A single document entry in the paginated document list."""

    document_id: str
    """Unique identifier of the document."""

    status: str
    """Current processing status (pending/processing/processed/failed)."""

    filename: str
    """Original filename submitted at creation time."""

    created_at: str | None = None
    """ISO-8601 timestamp of document creation (if available)."""

    error_message: str | None = None
    """Human-readable error description when status is ``failed``."""

    reference_count: int = 0
    """Total number of verbatim references linked to this document via events."""

    entity_count: int = 0
    """Total number of distinct canonical entities linked to this document's references."""

    chunk_count: int = 0
    """Number of text chunks created from this document."""

    text_word_count: int = 0
    """Word count of the document's extracted text content."""


class DocumentListResponse(BaseModel):
    """Paginated response body for ``GET /documents``."""

    items: list[DocumentListItem]
    """List of document entries on the current page."""

    total: int
    """Total number of documents matching the query."""

    page: int
    """Current page number (1-based)."""

    per_page: int
    """Number of items per page."""

    pages: int
    """Total number of pages available."""


class EventsCleared(BaseModel):
    """Response body for ``DELETE /documents/{document_id}/events``."""

    document_id: str
    """Unique identifier of the document whose events were cleared."""

    status: str = "pending"
    """The document status after clearing events."""

    events_cleared: bool = True
    """Whether any events were actually cleared."""


class DocumentDeleted(BaseModel):
    """Response body for ``DELETE /documents/{document_id}`` (full cascade)."""

    document_id: str
    """Unique identifier of the deleted document."""

    document_deleted: bool = True
    """Whether the document record was deleted."""

    orphaned_entities_cleaned: int = 0
    """Number of canonical_entities that were orphaned and removed."""


class HealthResponse(BaseModel):
    """Response body for ``GET /health``."""

    status: str = "ok"


class EntityListItem(BaseModel):
    """A single entity entry in the paginated entity list."""

    entity_id: str
    """Unique identifier (hex portion of the RecordID) of the canonical entity."""

    name: str
    """Display name of the entity."""

    entity_type: str
    """Type of the entity (place/person/object)."""

    reference_count: int = 0
    """Number of references pointing to this entity."""


class EntityListResponse(BaseModel):
    """Paginated response body for ``GET /entities``."""

    items: list[EntityListItem]
    """List of entity entries on the current page."""

    total: int
    """Total number of entities matching the query."""

    page: int
    """Current page number (1-based)."""

    per_page: int
    """Number of items per page."""

    pages: int
    """Total number of pages available."""


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


class ReferenceListItem(BaseModel):
    """A single reference entry in the paginated reference list."""

    reference_id: str
    """Unique identifier of the reference."""

    reference_type: str
    """Type of the reference (espacio/tiempo/humanos/objetos)."""

    verbatim_text: str
    """Verbatim text span from the source document."""

    span_start: int | None = None
    """Character offset (0-based) where the verbatim span begins."""

    span_end: int | None = None
    """Character offset (exclusive) where the verbatim span ends."""

    event_que_paso: str | None = None
    """The que_paso (what happened) from the linked event."""

    event_id: str | None = None
    """Unique identifier of the linked event."""

    document_filename: str | None = None
    """Filename of the source document."""

    document_id: str | None = None
    """Unique identifier of the source document."""

    canonical_entity_name: str | None = None
    """Name of the resolved canonical entity, if any."""


class ReferenceListResponse(BaseModel):
    """Paginated response body for ``GET /references``."""

    items: list[ReferenceListItem]
    """List of reference entries on the current page."""

    total: int
    """Total number of references matching the query."""

    page: int
    """Current page number (1-based)."""

    per_page: int
    """Number of items per page."""

    pages: int
    """Total number of pages available."""


class MergeRequest(BaseModel):
    """Request body for ``POST /entities/merge``.

    Merges one canonical entity (source) into another (target) of the same
    type. All references pointing to the source are re-pointed to the
    target, and the source is soft-deleted via ``superseded_by``.
    """

    source_id: str
    """Record ID (hex portion) of the source canonical entity to absorb."""

    target_id: str
    """Record ID (hex portion) of the target canonical entity (survivor)."""


class MergeResponse(BaseModel):
    """Response body for ``POST /entities/merge``."""

    success: bool = True
    """Whether the merge completed successfully."""

    message: str
    """Human-readable summary of the merge operation."""

    source_id: str
    """Record ID of the source entity that was absorbed."""

    target_id: str
    """Record ID of the target entity (survivor)."""

    rewired_count: int
    """Number of references that were re-pointed from source to target."""


class SplitPartition(BaseModel):
    """A single partition of references to split off into a new canonical entity."""

    new_entity_name: str
    """Name for the new canonical entity that will receive these references."""

    reference_ids: list[str]
    """List of reference record IDs (hex portions) to move to the new entity."""


class SplitRequest(BaseModel):
    """Request body for ``POST /entities/{entity_type}/{entity_id}/split``.

    Partitions one or more groups of references from a source canonical entity
    into new separate canonical entities.  Each partition creates one new entity.
    """

    partitions: list[SplitPartition]
    """One or more partitions of references to split into new entities."""


class SplitResponse(BaseModel):
    """Response body for ``POST /entities/{entity_type}/{entity_id}/split``."""

    success: bool = True
    """Whether the split completed successfully."""

    message: str
    """Human-readable summary of the split operation."""

    entity_type: str
    """Type of the entities involved (place/person/object)."""

    original_entity_id: str
    """Record ID of the original entity that was split."""

    new_entities: list[dict]
    """List of ``{name, entity_id}`` for each created entity."""

    partition_count: int
    """Number of partitions (new entities created)."""

    total_references_moved: int
    """Total number of references moved to new entities."""


class APIInfo(BaseModel):
    """Response body for ``GET /``."""

    name: str
    version: str
    description: str
    endpoints: dict[str, str]


# =======================================================================
# Helpers
# =======================================================================


def _parse_count(raw_result: list | dict | None) -> int:
    """Extract count integer from a SurrealDB count query result."""
    records = [r for r in (raw_result or []) if isinstance(r, dict)]
    if not records:
        return 0
    cnt = records[0].get("total")
    if isinstance(cnt, dict):
        return int(cnt.get("value", 0))
    if cnt is not None:
        return int(cnt)
    return 0


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
    description="Document processing pipeline with Temporal and SurrealDB",
    version="0.1.0",
    lifespan=lifespan,
)

# Serve the web UI from /ui (single-page static application)
STATIC_DIR = Path(__file__).resolve().parent / "static"
if STATIC_DIR.is_dir():
    app.mount(
        "/ui",
        StaticFiles(directory=str(STATIC_DIR), html=True),
        name="ui",
    )
else:
    logger.warning("Static directory %s not found — UI will not be served at /ui", STATIC_DIR)


# =======================================================================
# Endpoints
# =======================================================================


@app.get("/", response_model=APIInfo)
async def root() -> APIInfo:
    """Return basic API information and available endpoints."""
    return APIInfo(
        name="eth-pipeline",
        version="0.1.0",
        description="Document processing pipeline with Temporal and SurrealDB",
        endpoints={
            "/": "This information",
            "/health": "Liveness check",
            "/graphql": "Proxy to SurrealDB auto-GraphQL (POST)",
            "/documents": "List documents (GET) or submit for processing (POST)",
            "/documents/upload": "Upload a binary document file (POST, multipart)",
            "/documents/{document_id}": "Get document status (GET)",
            "/documents/{document_id}/events": "Clear extraction results (DELETE)",
            "/entities": "List canonical entities with pagination, search, and type filter (GET)",
            "/entities/merge": "Merge two canonical entities of the same type (POST)",
            "/entities/{entity_type}/{entity_id}/split": "Partition references across new canonical entities (POST)",
            "/references": "List references with pagination, search, and type filter (GET)",
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
                args=[doc_id],
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


# =======================================================================
# Upload document endpoint (MinIO blob storage)
# =======================================================================

#: Maximum upload file size: 50 MB.
MAX_UPLOAD_SIZE = 50 * 1024 * 1024


@app.post("/documents/upload", response_model=DocumentUploadCreated, status_code=201)
async def upload_document(file: UploadFile = File(...)) -> DocumentUploadCreated:
    """Upload a binary document file for processing.

    Accepts a multipart file upload, stores the binary blob in MinIO
    (with fallback to base64-encoded inline storage if MinIO is
    unavailable), creates a SurrealDB document record with
    ``blob_format="minio"``, and triggers Temporal processing
    (best-effort).

    Returns HTTP 201 with ``{document_id, status}`` on success.
    Returns HTTP 413 if the file exceeds 50 MB.
    Returns HTTP 503 if SurrealDB is unavailable.
    """
    db: AsyncWsSurrealConnection | None = app.state.db

    if db is None:
        logger.error("POST /documents/upload rejected — SurrealDB unavailable")
        raise HTTPException(
            status_code=503,
            detail="SurrealDB is not available. Please try again later.",
        )

    # 1. Validate file
    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="Filename is required.",
        )

    # 2. Generate document ID
    doc_id = str(uuid.uuid4().hex)

    # 3. Determine blob path
    ext = ".bin"
    if "." in file.filename:
        _, ext_candidate = os.path.splitext(file.filename)
        if ext_candidate:
            ext = ext_candidate
    blob_path = f"doc/{doc_id}{ext}"

    # 4. Read file content with size guard
    try:
        content = await file.read()
    except Exception as exc:
        logger.error("Failed to read uploaded file: %s", exc)
        raise HTTPException(
            status_code=400,
            detail="Failed to read uploaded file content.",
        ) from exc

    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds maximum size of {MAX_UPLOAD_SIZE // (1024 * 1024)} MB.",
        )

    # 5. Try MinIO storage (degraded mode: fall back to base64 inline)
    minio_available = False
    try:
        async with get_storage_async() as minio_client:
            content_type = file.content_type or "application/octet-stream"
            await asyncio.to_thread(
                minio_client.put_object,
                os.environ.get("MINIO_BUCKET", "eth-documents"),
                blob_path,
                io.BytesIO(content),
                length=len(content),
                content_type=content_type,
            )
            minio_available = True
            logger.info(
                "Stored blob for document %s in MinIO at %s",
                doc_id,
                blob_path,
            )
    except ConnectionError:
        logger.warning(
            "MinIO unavailable — falling back to base64 inline storage for document %s",
            doc_id,
        )
    except Exception as exc:
        logger.warning(
            "MinIO storage failed for document %s: %s — falling back to base64 inline",
            doc_id,
            exc,
        )

    # 6. Prepare document record
    if minio_available:
        original_blob = ""
        blob_format = "minio"
        stored_blob_path = blob_path
    else:
        original_blob = base64.b64encode(content).decode("ascii")
        blob_format = None
        stored_blob_path = None

    # 7. Create document record in SurrealDB
    try:
        await db.create(
            f"document:{doc_id}",
            {
                "text_content": None,
                "original_blob": original_blob,
                "blob_format": blob_format,
                "blob_path": stored_blob_path,
                "filename": file.filename or f"unnamed_{doc_id}",
                "mime_type": file.content_type or "application/octet-stream",
                "status": "pending",
                "error_message": None,
            },
        )
    except Exception as exc:
        logger.error("Failed to create document in SurrealDB: %s", exc)
        # Clean up MinIO blob if SurrealDB failed after storage
        if minio_available:
            try:
                async with get_storage_async() as cleanup_client:
                    await asyncio.to_thread(
                        cleanup_client.remove_object,
                        os.environ.get("MINIO_BUCKET", "eth-documents"),
                        blob_path,
                    )
                    logger.info("Cleaned up MinIO blob %s after DB failure", blob_path)
            except Exception as cleanup_exc:
                logger.warning(
                    "Failed to clean up MinIO blob %s: %s",
                    blob_path,
                    cleanup_exc,
                )
        raise HTTPException(
            status_code=502,
            detail="Failed to store document in database.",
        ) from exc

    logger.info(
        "Created document %s (filename=%s, blob_format=%s, status=pending)",
        doc_id,
        file.filename,
        blob_format,
    )

    # 8. Trigger Temporal workflow (best-effort)
    temporal = getattr(app.state, "temporal", None)
    if temporal is not None:
        try:
            from eth_pipeline.workflows import DocumentProcessingWorkflow

            await temporal.start_workflow(
                DocumentProcessingWorkflow.run,
                id=f"doc-{doc_id}",
                task_queue="event-extraction",
                args=[doc_id],
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

    return DocumentUploadCreated(document_id=doc_id, status="pending")


# =======================================================================
# Get document status
# =======================================================================
@app.get(
    "/documents/{document_id}",
    response_model=DocumentStatus,
)
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

    # Query visibility counts (non-fatal — defaults to 0 on failure)
    from surrealdb.data.types.record_id import RecordID

    doc_id_obj = RecordID("document", document_id)
    ref_count = 0
    ent_count = 0
    chunk_count = 0
    text_word_count = 0
    try:
        ref_result = await db.query(
            "SELECT count() AS total FROM reference "
            "WHERE event.document = $doc_ref GROUP ALL",
            {"doc_ref": doc_id_obj},
        )
        ref_count = _parse_count(ref_result)

        ent_result = await db.query(
            "SELECT count() AS total FROM reference "
            "WHERE event.document = $doc_ref "
            "AND canonical_entity IS NOT NONE "
            "AND canonical_entity IS NOT NULL "
            "GROUP ALL",
            {"doc_ref": doc_id_obj},
        )
        ent_count = _parse_count(ent_result)

        chunk_result = await db.query(
            "SELECT count() AS total FROM document_chunk WHERE document = $doc_ref",
            {"doc_ref": doc_id_obj},
        )
        chunk_count = _parse_count(chunk_result)

        text_content = record.get("text_content", "") or ""
        text_word_count = len(text_content.split()) if text_content.strip() else 0
    except Exception as exc:
        logger.warning("Failed to query document counts for %s: %s", document_id, exc)

    return DocumentStatus(
        document_id=document_id,
        status=record.get("status", "unknown"),
        filename=record.get("filename", ""),
        error_message=record.get("error_message"),
        created_at=created_at_str,
        blob_format=record.get("blob_format"),
        blob_path=record.get("blob_path"),
        reference_count=ref_count,
        entity_count=ent_count,
        chunk_count=chunk_count,
        text_word_count=text_word_count,
    )


# =======================================================================
# List documents (paginated)
# =======================================================================
@app.get("/documents", response_model=DocumentListResponse)
async def list_documents(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    search: str | None = Query(None),
    status: str | None = Query(None),
) -> DocumentListResponse:
    """List documents with pagination, search, and status filtering.

    Queries SurrealDB for document records matching the optional search
    and status filters, returning a paginated response with metadata.

    Returns HTTP 503 if the database is unavailable and HTTP 502 if a
    query fails.
    """
    db: AsyncWsSurrealConnection | None = app.state.db

    if db is None:
        logger.error("GET /documents rejected — SurrealDB unavailable")
        raise HTTPException(
            status_code=503,
            detail="SurrealDB is not available. Please try again later.",
        )

    offset = (page - 1) * per_page

    # Build dynamic WHERE clause — bind values via $params (safe).
    where_parts: list[str] = ["1 = 1"]
    query_params: dict[str, object] = {}

    if search:
        where_parts.append("filename LIKE $search")
        query_params["search"] = f"%{search}%"

    if status:
        where_parts.append("status = $status")
        query_params["status"] = status

    where_clause = " AND ".join(where_parts)
    query_params["per_page"] = per_page
    query_params["offset"] = offset

    try:
        # Count total matching documents
        count_result = await db.query(
            f"SELECT count() AS total FROM document WHERE {where_clause}",
            query_params,
        )
    except Exception as exc:
        logger.error("Failed to count documents: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Failed to query database.",
        ) from exc

    # Parse count from SurrealDB response
    total = 0
    count_records: list[dict] = [
        r for r in (count_result or []) if isinstance(r, dict)
    ]
    if count_records:
        cnt_val = count_records[0].get("total")
        if isinstance(cnt_val, dict):
            total = int(cnt_val.get("value", 0))
        elif cnt_val is not None:
            total = int(cnt_val)

    if total == 0:
        pages = 0
    else:
        pages = max(1, (total + per_page - 1) // per_page)

    try:
        # Fetch paginated document records
        data_result = await db.query(
            f"SELECT * FROM document WHERE {where_clause} "
            "ORDER BY created_at DESC LIMIT $per_page START $offset",
            query_params,
        )
    except Exception as exc:
        logger.error("Failed to query documents: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Failed to query database.",
        ) from exc

    from surrealdb.data.types.record_id import RecordID

    data_records: list[dict] = [
        r for r in (data_result or []) if isinstance(r, dict)
    ]

    items: list[DocumentListItem] = []
    for record in data_records:
        # Parse document_id from the RecordID or string id field
        doc_id_val = record.get("id")
        doc_id: str = ""
        if isinstance(doc_id_val, RecordID):
            doc_id = doc_id_val.id
        elif isinstance(doc_id_val, str):
            doc_id = doc_id_val.split(":", 1)[1] if ":" in doc_id_val else doc_id_val

        created_at_raw = record.get("created_at")
        if created_at_raw is not None:
            created_at_str = (
                created_at_raw.isoformat()
                if hasattr(created_at_raw, "isoformat")
                else str(created_at_raw)
            )
        else:
            created_at_str = None

        # Query visibility counts for this document
        ref_count = 0
        ent_count = 0
        chunk_count = 0
        twc = 0
        try:
            doc_ref_obj = RecordID("document", doc_id)
            ref_result = await db.query(
                "SELECT count() AS total FROM reference "
                "WHERE event.document = $doc_ref GROUP ALL",
                {"doc_ref": doc_ref_obj},
            )
            ref_count = _parse_count(ref_result)

            ent_result = await db.query(
                "SELECT count() AS total FROM reference "
                "WHERE event.document = $doc_ref "
                "AND canonical_entity IS NOT NONE "
                "AND canonical_entity IS NOT NULL "
                "GROUP ALL",
                {"doc_ref": doc_ref_obj},
            )
            ent_count = _parse_count(ent_result)

            chunk_result = await db.query(
                "SELECT count() AS total FROM document_chunk WHERE document = $doc_ref",
                {"doc_ref": doc_ref_obj},
            )
            chunk_count = _parse_count(chunk_result)

            text_content = record.get("text_content", "") or ""
            twc = len(text_content.split()) if text_content.strip() else 0
        except Exception as exc:
            logger.warning("Failed to query counts for document %s: %s", doc_id, exc)

        items.append(DocumentListItem(
            document_id=doc_id,
            status=record.get("status", "unknown"),
            filename=record.get("filename", ""),
            created_at=created_at_str,
            error_message=record.get("error_message"),
            reference_count=ref_count,
            entity_count=ent_count,
            chunk_count=chunk_count,
            text_word_count=twc,
        ))

    logger.info(
        "Listed documents (page=%d, per_page=%d, search=%s, status=%s) — %d items of %d total",
        page,
        per_page,
        search or "",
        status or "",
        len(items),
        total,
    )

    return DocumentListResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
    )


# =======================================================================
# List entities (paginated)
# =======================================================================
@app.get("/entities", response_model=EntityListResponse)
async def list_entities(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    search: str | None = Query(None),
    entity_type: str | None = Query(None),
) -> EntityListResponse:
    """List canonical entities with pagination, search, and type filtering.

    Queries SurrealDB for canonical entity records matching the optional
    search (by name) and entity_type filters, returning a paginated response
    with metadata and reference counts.

    Returns HTTP 503 if the database is unavailable and HTTP 502 if a
    query fails.
    """
    db: AsyncWsSurrealConnection | None = app.state.db

    if db is None:
        logger.error("GET /entities rejected — SurrealDB unavailable")
        raise HTTPException(
            status_code=503,
            detail="SurrealDB is not available. Please try again later.",
        )

    offset = (page - 1) * per_page

    # Build dynamic WHERE clause — bind values via $params (safe).
    where_parts: list[str] = ["superseded_by IS NONE"]
    query_params: dict[str, object] = {}

    if search:
        where_parts.append("name LIKE $search")
        query_params["search"] = f"%{search}%"

    if entity_type:
        where_parts.append("entity_type = $entity_type")
        query_params["entity_type"] = entity_type

    where_clause = " AND ".join(where_parts)
    query_params["per_page"] = per_page
    query_params["offset"] = offset

    try:
        # Count total matching entities
        count_result = await db.query(
            f"SELECT count() AS total FROM canonical_entity WHERE {where_clause}",
            query_params,
        )
    except Exception as exc:
        logger.error("Failed to count entities: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Failed to query database.",
        ) from exc

    # Parse count from SurrealDB response
    total = 0
    count_records: list[dict] = [
        r for r in (count_result or []) if isinstance(r, dict)
    ]
    if count_records:
        cnt_val = count_records[0].get("total")
        if isinstance(cnt_val, dict):
            total = int(cnt_val.get("value", 0))
        elif cnt_val is not None:
            total = int(cnt_val)

    if total == 0:
        pages = 0
    else:
        pages = max(1, (total + per_page - 1) // per_page)

    try:
        # Fetch paginated entity records
        data_result = await db.query(
            f"SELECT * FROM canonical_entity WHERE {where_clause} "
            "ORDER BY name ASC LIMIT $per_page START $offset",
            query_params,
        )
    except Exception as exc:
        logger.error("Failed to query entities: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Failed to query database.",
        ) from exc

    from surrealdb.data.types.record_id import RecordID

    data_records: list[dict] = [
        r for r in (data_result or []) if isinstance(r, dict)
    ]

    items: list[EntityListItem] = []
    for record in data_records:
        # Parse entity_id from the RecordID or string id field
        ent_id_val = record.get("id")
        entity_id: str = ""
        if isinstance(ent_id_val, RecordID):
            entity_id = ent_id_val.id
        elif isinstance(ent_id_val, str):
            entity_id = ent_id_val.split(":", 1)[1] if ":" in ent_id_val else ent_id_val

        # Count references for this entity
        ent_rid = RecordID("canonical_entity", entity_id)
        ref_count = 0
        try:
            ref_result = await db.query(
                "SELECT count() AS total FROM reference WHERE canonical_entity = $entity_ref GROUP ALL",
                {"entity_ref": ent_rid},
            )
        except Exception as exc:
            logger.warning(
                "Failed to count references for entity %s: %s",
                entity_id,
                exc,
            )
            ref_count = 0
        else:
            ref_records: list[dict] = [
                r for r in (ref_result or []) if isinstance(r, dict)
            ]
            if ref_records:
                cnt_val = ref_records[0].get("total")
                if isinstance(cnt_val, dict):
                    ref_count = int(cnt_val.get("value", 0))
                elif cnt_val is not None:
                    ref_count = int(cnt_val)

        items.append(EntityListItem(
            entity_id=entity_id,
            name=record.get("name", ""),
            entity_type=record.get("entity_type", ""),
            reference_count=ref_count,
        ))

    logger.info(
        "Listed entities (page=%d, per_page=%d, search=%s, type=%s) — %d items of %d total",
        page,
        per_page,
        search or "",
        entity_type or "",
        len(items),
        total,
    )

    return EntityListResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
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
        # Delete document chunks for this document (Phase 8 cascade)
        await db.query(
            "DELETE document_chunk WHERE document = $doc_id",
            {"doc_id": doc_ref},
        )

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

        # Reset document status to pending — clear text_content so
        # reprocessing re-extracts from the blob (empty string
        # triggers has_text_content=False in the workflow).
        await db.query(
            f"UPDATE {doc_ref} SET status = 'pending', "
            "text_content = '', error_message = NULL, "
            "updated_at = time::now()",
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
# Delete document endpoint (full cascade)
# =======================================================================


@app.delete(
    "/documents/{document_id}",
    response_model=DocumentDeleted,
)
async def delete_document(document_id: str) -> DocumentDeleted:
    """Delete a document and all its associated data (full cascade).

    Performs a full cascading delete:
    1.  Deletes all ``document_chunk`` records for the document.
    2.  Deletes all ``reference`` records linked to events that belong to the
        document.
    3.  Deletes all ``event`` records for the document.
    4.  Removes the document record itself.
    5.  Cleans up any ``canonical_entity`` records that have become orphaned
        (zero remaining references).

    Returns HTTP 404 if the document does not exist and HTTP 503 if the
    database is unavailable.
    """
    db: AsyncWsSurrealConnection | None = app.state.db

    if db is None:
        logger.error(
            "DELETE /documents/%s rejected — SurrealDB unavailable",
            document_id,
        )
        raise HTTPException(
            status_code=503,
            detail="SurrealDB is not available. Please try again later.",
        )

    doc_ref = f"document:{document_id}"

    # Verify document exists — use RecordID parameter to avoid SurrealDB v3
    # subtraction error on nonexistent records in SCHEMAFULL tables.
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
        logger.warning("Document %s not found for cascade delete", document_id)
        raise HTTPException(
            status_code=404,
            detail=f"Document {document_id} not found.",
        )

    try:
        # Collect canonical_entity RIDs that may become orphaned
        affected_ce_query = await db.query(
            "SELECT VALUE canonical_entity FROM reference "
            "WHERE event.document = $doc_id "
            "AND canonical_entity IS NOT NONE "
            "AND canonical_entity IS NOT NULL",
            {"doc_id": doc_ref},
        )
        affected_ce_rids = list({
            r for r in (affected_ce_query or [])
            if isinstance(r, str)
        })

        # 1. Delete document chunks for this document
        await db.query(
            "DELETE document_chunk WHERE document = $doc_id",
            {"doc_id": doc_ref},
        )

        # 2. Delete references linked to events for this document
        await db.query(
            "DELETE reference WHERE event IN "
            "(SELECT id FROM event WHERE document = $doc_id)",
            {"doc_id": doc_ref},
        )

        # 3. Delete events for this document
        await db.query(
            "DELETE event WHERE document = $doc_id",
            {"doc_id": doc_ref},
        )

        # 4. Delete the document record itself
        await db.query(
            "DELETE document WHERE id = $doc_id",
            {"doc_id": doc_id_obj},
        )

        # 5. Clean up orphaned canonical_entities
        orphaned = 0
        if affected_ce_rids:
            params = {f"ce_{i}": rid for i, rid in enumerate(affected_ce_rids)}
            rid_list = ", ".join(f"$ce_{i}" for i in range(len(affected_ce_rids)))

            result = await db.query(
                f"DELETE canonical_entity WHERE id IN [{rid_list}] "
                f"AND count((SELECT id FROM reference WHERE canonical_entity = parent.id)) = 0",
                params,
            )
            orphaned = result[0].get("count", 0) if result and isinstance(result[0], dict) else 0

        logger.info(
            "Deleted document %s (cascade complete, %d orphaned entities cleaned)",
            document_id,
            orphaned,
        )

        # ---- Terminate any running Temporal workflow for this document ----
        temporal = getattr(app.state, "temporal", None)
        if temporal is not None:
            workflow_id = f"doc-{document_id}"
            try:
                handle = temporal.get_workflow_handle(workflow_id)
                await handle.terminate(reason="document deleted via API")
                logger.info(
                    "Terminated Temporal workflow %s for deleted document %s",
                    workflow_id,
                    document_id,
                )
            except Exception as exc:
                # Workflow may not exist (already completed or never started)
                logger.info(
                    "No active Temporal workflow to terminate for %s: %s",
                    workflow_id,
                    exc,
                )
    except Exception as exc:
        logger.error(
            "Failed to delete document %s: %s",
            document_id,
            exc,
        )
        raise HTTPException(
            status_code=502,
            detail="Failed to delete document.",
        ) from exc

    return DocumentDeleted(
        document_id=document_id,
        document_deleted=True,
        orphaned_entities_cleaned=orphaned,
    )


# =======================================================================
# Merge entities endpoint
# =======================================================================


@app.post("/entities/merge", response_model=MergeResponse, status_code=200)
async def merge_entities(request: MergeRequest) -> MergeResponse:
    """Merge two canonical entities of the same type.

    Merges the source canonical entity into the target canonical entity:
    1.  Validates that source and target exist and are of the same type.
    2.  Validates that neither entity has already been merged (no
        ``superseded_by`` chain).
    3.  Re-points all references from source to target with
        ``resolution_confidence = 1.0``.
    4.  Soft-deletes the source by setting its ``superseded_by`` to the
        target's record ID.

    Returns the number of references that were re-wired and a summary
    message.
    """
    db: AsyncWsSurrealConnection | None = app.state.db

    if db is None:
        logger.error("POST /entities/merge rejected — SurrealDB unavailable")
        raise HTTPException(
            status_code=503,
            detail="SurrealDB is not available. Please try again later.",
        )

    from surrealdb.data.types.record_id import RecordID

    source_id_obj = RecordID("canonical_entity", request.source_id)
    target_id_obj = RecordID("canonical_entity", request.target_id)

    # 1. Self-merge check
    if request.source_id == request.target_id:
        logger.warning(
            "Merge rejected — self-merge attempted for entity %s",
            request.source_id,
        )
        raise HTTPException(
            status_code=400,
            detail="Cannot merge an entity into itself.",
        )

    # 2. Fetch source entity
    try:
        source_result = await db.query(
            "SELECT * FROM canonical_entity WHERE id = $source_id",
            {"source_id": source_id_obj},
        )
    except Exception as exc:
        logger.error(
            "Failed to query source entity %s: %s",
            request.source_id,
            exc,
        )
        raise HTTPException(
            status_code=502,
            detail="Failed to query database.",
        ) from exc

    source_records: list[dict] = [
        r for r in (source_result or []) if isinstance(r, dict)
    ]
    if not source_records:
        logger.warning(
            "Merge rejected — source entity %s not found",
            request.source_id,
        )
        raise HTTPException(
            status_code=404,
            detail=f"Source canonical entity {request.source_id} not found.",
        )

    source_record = source_records[0]

    # 3. Fetch target entity
    try:
        target_result = await db.query(
            "SELECT * FROM canonical_entity WHERE id = $target_id",
            {"target_id": target_id_obj},
        )
    except Exception as exc:
        logger.error(
            "Failed to query target entity %s: %s",
            request.target_id,
            exc,
        )
        raise HTTPException(
            status_code=502,
            detail="Failed to query database.",
        ) from exc

    target_records: list[dict] = [
        r for r in (target_result or []) if isinstance(r, dict)
    ]
    if not target_records:
        logger.warning(
            "Merge rejected — target entity %s not found",
            request.target_id,
        )
        raise HTTPException(
            status_code=404,
            detail=f"Target canonical entity {request.target_id} not found.",
        )

    target_record = target_records[0]

    # 4. Cross-type check
    source_type = source_record.get("entity_type")
    target_type = target_record.get("entity_type")
    if source_type != target_type:
        logger.warning(
            "Merge rejected — cross-type merge attempted: source=%s (%s), target=%s (%s)",
            request.source_id,
            source_type,
            request.target_id,
            target_type,
        )
        raise HTTPException(
            status_code=400,
            detail=f"Cannot merge entities of different types: source is '{source_type}', target is '{target_type}'.",
        )

    # 5. Already-merged source check
    if source_record.get("superseded_by") is not None:
        logger.warning(
            "Merge rejected — source entity %s is already merged (superseded_by=%s)",
            request.source_id,
            source_record["superseded_by"],
        )
        raise HTTPException(
            status_code=400,
            detail=f"Source canonical entity {request.source_id} has already been merged into another entity.",
        )

    # 6. Already-merged target check
    if target_record.get("superseded_by") is not None:
        logger.warning(
            "Merge rejected — target entity %s is already merged (superseded_by=%s)",
            request.target_id,
            target_record["superseded_by"],
        )
        raise HTTPException(
            status_code=400,
            detail=f"Target canonical entity {request.target_id} has already been merged into another entity.",
        )

    # 7. Count and rewire references from source to target
    target_rid = RecordID("canonical_entity", request.target_id)
    source_rid = RecordID("canonical_entity", request.source_id)

    try:
        # Count references currently pointing to source
        count_result = await db.query(
            "SELECT count() as cnt FROM reference WHERE canonical_entity = $source_ref",
            {"source_ref": source_rid},
        )
    except Exception as exc:
        logger.error(
            "Failed to count references for source entity %s: %s",
            request.source_id,
            exc,
        )
        raise HTTPException(
            status_code=502,
            detail="Failed to query database during reference count.",
        ) from exc

    # SurrealDB returns count as a dict with a nested value
    count_records: list[dict] = [
        r for r in (count_result or []) if isinstance(r, dict)
    ]
    rewired_count = 0
    if count_records:
        cnt_val = count_records[0].get("cnt")
        if isinstance(cnt_val, dict):
            rewired_count = int(cnt_val.get("value", 0))
        elif cnt_val is not None:
            rewired_count = int(cnt_val)

    try:
        # Update references: point from source to target (use RecordID for typed record fields)
        await db.query(
            "UPDATE reference SET canonical_entity = $target_ref, "
            "resolution_confidence = 1.0, updated_at = time::now() "
            "WHERE canonical_entity = $source_ref",
            {"source_ref": source_rid, "target_ref": target_rid},
        )

        # Soft-delete source by setting superseded_by (use RecordID for typed record field)
        await db.query(
            f"UPDATE canonical_entity:{request.source_id} SET "
            "superseded_by = $target_ref, updated_at = time::now()",
            {"target_ref": target_rid},
        )

        logger.info(
            "Merge complete: source=%s target=%s rewired=%d references",
            request.source_id,
            request.target_id,
            rewired_count,
        )
    except Exception as exc:
        logger.error(
            "Failed to execute merge source=%s target=%s: %s",
            request.source_id,
            request.target_id,
            exc,
        )
        raise HTTPException(
            status_code=502,
            detail="Failed to execute merge operation.",
        ) from exc

    return MergeResponse(
        success=True,
        message=f"Merged canonical entity {request.source_id} into {request.target_id}, rewired {rewired_count} references.",
        source_id=request.source_id,
        target_id=request.target_id,
        rewired_count=rewired_count,
    )


# =======================================================================
# Split entity endpoint
# =======================================================================


@app.post(
    "/entities/{entity_type}/{entity_id}/split",
    response_model=SplitResponse,
    status_code=200,
)
async def split_entity(
    entity_type: str,
    entity_id: str,
    request: SplitRequest,
) -> SplitResponse:
    """Split references from a canonical entity into new entities.

    Partitions references belonging to an existing canonical entity into
    one or more new canonical entities (grouped by partition).  Each
    partition creates a new entity with ``properties.split_from`` pointing
    to the original.

    Validation pipeline:
    1. SurrealDB available (503)
    2. entity_type is one of place/person/object (400)
    3. Source entity exists (404)
    4. Partitions not empty (400)
    5. No duplicate reference IDs across partitions (400)
    6. Each reference exists and points to this entity (400)
    """
    db: AsyncWsSurrealConnection | None = app.state.db

    if db is None:
        logger.error(
            "POST /entities/%s/%s/split rejected — SurrealDB unavailable",
            entity_type,
            entity_id,
        )
        raise HTTPException(
            status_code=503,
            detail="SurrealDB is not available. Please try again later.",
        )

    # 1. Validate entity_type is one of the known types
    valid_types = {"place", "person", "object"}
    if entity_type not in valid_types:
        logger.warning(
            "Split rejected — invalid entity_type '%s' (must be one of %s)",
            entity_type,
            sorted(valid_types),
        )
        raise HTTPException(
            status_code=400,
            detail=f"Invalid entity type '{entity_type}'. Must be one of: {', '.join(sorted(valid_types))}.",
        )

    from surrealdb.data.types.record_id import RecordID

    source_id_obj = RecordID("canonical_entity", entity_id)

    # 2. Fetch source entity (must exist)
    try:
        source_result = await db.query(
            "SELECT * FROM canonical_entity WHERE id = $source_id",
            {"source_id": source_id_obj},
        )
    except Exception as exc:
        logger.error(
            "Failed to query source entity %s/%s: %s",
            entity_type,
            entity_id,
            exc,
        )
        raise HTTPException(
            status_code=502,
            detail="Failed to query database.",
        ) from exc

    source_records: list[dict] = [
        r for r in (source_result or []) if isinstance(r, dict)
    ]
    if not source_records:
        logger.warning(
            "Split rejected — entity %s/%s not found",
            entity_type,
            entity_id,
        )
        raise HTTPException(
            status_code=404,
            detail=f"Canonical entity {entity_id} of type '{entity_type}' not found.",
        )

    source_record = source_records[0]

    # 3. Validate partitions not empty
    if not request.partitions:
        logger.warning(
            "Split rejected — no partitions provided for entity %s",
            entity_id,
        )
        raise HTTPException(
            status_code=400,
            detail="At least one partition is required.",
        )

    # 4. Validate all partitions have at least one reference_id
    for i, partition in enumerate(request.partitions):
        if not partition.reference_ids:
            logger.warning(
                "Split rejected — partition %d has no reference_ids for entity %s",
                i,
                entity_id,
            )
            raise HTTPException(
                status_code=400,
                detail=f"Partition {i} ('{partition.new_entity_name}') has no reference IDs.",
            )

    # 5. Check for duplicate reference IDs across all partitions
    all_ref_ids: list[str] = []
    for partition in request.partitions:
        all_ref_ids.extend(partition.reference_ids)

    if len(all_ref_ids) != len(set(all_ref_ids)):
        logger.warning(
            "Split rejected — duplicate reference IDs across partitions for entity %s",
            entity_id,
        )
        raise HTTPException(
            status_code=400,
            detail="Duplicate reference IDs found across partitions. Each reference can only be moved once.",
        )

    # 6. Verify each reference exists and points to this entity
    source_rid = RecordID("canonical_entity", entity_id)
    for ref_id in all_ref_ids:
        try:
            ref_result = await db.query(
                "SELECT * FROM reference WHERE id = $ref_id",
                {"ref_id": RecordID("reference", ref_id)},
            )
        except Exception as exc:
            logger.error(
                "Failed to query reference %s: %s",
                ref_id,
                exc,
            )
            raise HTTPException(
                status_code=502,
                detail="Failed to query database.",
            ) from exc

        ref_records: list[dict] = [
            r for r in (ref_result or []) if isinstance(r, dict)
        ]
        if not ref_records:
            logger.warning(
                "Split rejected — reference %s not found",
                ref_id,
            )
            raise HTTPException(
                status_code=400,
                detail=f"Reference {ref_id} not found.",
            )

        ref_record = ref_records[0]
        ref_canonical = ref_record.get("canonical_entity")

        # Compare against source RecordID — handle both RecordID and string representations
        ref_matches = False
        if isinstance(ref_canonical, RecordID):
            ref_matches = ref_canonical == source_rid
        elif isinstance(ref_canonical, str):
            ref_matches = ref_canonical == str(source_rid)

        if not ref_matches:
            logger.warning(
                "Split rejected — reference %s does not point to entity %s (points to %s)",
                ref_id,
                entity_id,
                ref_canonical_str,
            )
            raise HTTPException(
                status_code=400,
                detail=f"Reference {ref_id} does not belong to canonical entity {entity_id}.",
            )

    # 7. Group partitions by new_entity_name (same name = same new entity)
    groups: dict[str, list[SplitPartition]] = {}
    for partition in request.partitions:
        name = partition.new_entity_name
        if name not in groups:
            groups[name] = []
        groups[name].append(partition)

    # 8. For each unique name: CREATE canonical_entity, then UPDATE references
    new_entities_info: list[dict] = []
    total_moved = 0

    for new_name in groups:
        merged_ref_ids: list[str] = []
        for partition in groups[new_name]:
            merged_ref_ids.extend(partition.reference_ids)

        # 8a. Create the new canonical entity with split_from provenance
        try:
            create_result = await db.create(
                "canonical_entity",
                {
                    "entity_type": entity_type,
                    "name": new_name,
                    "properties": {
                        "split_from": str(source_rid),
                    },
                    "superseded_by": None,
                },
            )
        except Exception as exc:
            logger.error(
                "Failed to create canonical_entity '%s' during split: %s",
                new_name,
                exc,
            )
            raise HTTPException(
                status_code=502,
                detail=f"Failed to create canonical entity '{new_name}'.",
            ) from exc

        # Parse the created entity ID from SurrealDB's create response
        # create() can return RecordID or dict with id field
        new_entity_id: str | None = None
        if isinstance(create_result, RecordID):
            new_entity_id = create_result.id
        elif isinstance(create_result, dict):
            created_id = create_result.get("id")
            if isinstance(created_id, RecordID):
                new_entity_id = created_id.id
            elif isinstance(created_id, str):
                # Parse "canonical_entity:xxx" to extract hex portion
                if ":" in created_id:
                    new_entity_id = created_id.split(":", 1)[1]
                else:
                    new_entity_id = created_id
        elif isinstance(create_result, list) and len(create_result) > 0:
            first = create_result[0]
            if isinstance(first, dict):
                created_id = first.get("id")
                if isinstance(created_id, RecordID):
                    new_entity_id = created_id.id
                elif isinstance(created_id, str):
                    if ":" in created_id:
                        new_entity_id = created_id.split(":", 1)[1]
                    else:
                        new_entity_id = created_id

        if new_entity_id is None:
            logger.error(
                "Could not parse created entity ID from response: %s",
                str(create_result)[:300],
            )
            raise HTTPException(
                status_code=502,
                detail=f"Failed to parse created entity ID for '{new_name}'.",
            )

        new_entity_rid = RecordID("canonical_entity", new_entity_id)

        # 8b. Update each reference in this group to point to the new entity
        for ref_id in merged_ref_ids:
            try:
                await db.query(
                    "UPDATE reference SET canonical_entity = $target_ref, "
                    "resolution_confidence = 1.0, updated_at = time::now() "
                    "WHERE id = $ref_id",
                    {
                        "target_ref": new_entity_rid,
                        "ref_id": RecordID("reference", ref_id),
                    },
                )
            except Exception as exc:
                logger.error(
                    "Failed to update reference %s for new entity '%s': %s",
                    ref_id,
                    new_name,
                    exc,
                )
                raise HTTPException(
                    status_code=502,
                    detail=f"Failed to update reference {ref_id} for '{new_name}'.",
                ) from exc

        new_entities_info.append({
            "name": new_name,
            "entity_id": new_entity_id,
        })
        total_moved += len(merged_ref_ids)

    logger.info(
        "Split complete: entity=%s/%s partitions=%d total_moved=%d new_entities=%s",
        entity_type,
        entity_id,
        len(request.partitions),
        total_moved,
        [e["name"] for e in new_entities_info],
    )

    return SplitResponse(
        success=True,
        message=(
            f"Split canonical entity {entity_id} into {len(new_entities_info)} new "
            f"entities, moved {total_moved} references."
        ),
        entity_type=entity_type,
        original_entity_id=entity_id,
        new_entities=new_entities_info,
        partition_count=len(new_entities_info),
        total_references_moved=total_moved,
    )


# =======================================================================
# List references (paginated)
# =======================================================================
@app.get("/references", response_model=ReferenceListResponse)
async def list_references(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    search: str | None = Query(None),
    reference_type: str | None = Query(None),
) -> ReferenceListResponse:
    """List verbatim references with pagination, search, and type filtering.

    Queries SurrealDB for reference records matching the optional
    search (by verbatim_text) and reference_type filters, returning a
    paginated response with event and document context.

    Returns HTTP 503 if the database is unavailable and HTTP 502 if a
    query fails.
    """
    db: AsyncWsSurrealConnection | None = app.state.db

    if db is None:
        logger.error("GET /references rejected — SurrealDB unavailable")
        raise HTTPException(
            status_code=503,
            detail="SurrealDB is not available. Please try again later.",
        )

    offset = (page - 1) * per_page

    # Build dynamic WHERE clause — bind values via $params (safe).
    where_parts: list[str] = ["1 = 1"]
    query_params: dict[str, object] = {}

    if search:
        where_parts.append("verbatim_text LIKE $search")
        query_params["search"] = f"%{search}%"

    if reference_type:
        where_parts.append("reference_type = $ref_type")
        query_params["ref_type"] = reference_type

    where_clause = " AND ".join(where_parts)
    query_params["per_page"] = per_page
    query_params["offset"] = offset

    try:
        # Count total matching references
        count_result = await db.query(
            f"SELECT count() AS total FROM reference WHERE {where_clause}",
            query_params,
        )
    except Exception as exc:
        logger.error("Failed to count references: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Failed to query database.",
        ) from exc

    # Parse count from SurrealDB response
    total = 0
    count_records: list[dict] = [
        r for r in (count_result or []) if isinstance(r, dict)
    ]
    if count_records:
        cnt_val = count_records[0].get("total")
        if isinstance(cnt_val, dict):
            total = int(cnt_val.get("value", 0))
        elif cnt_val is not None:
            total = int(cnt_val)

    if total == 0:
        pages = 0
    else:
        pages = max(1, (total + per_page - 1) // per_page)

    try:
        # Fetch paginated reference records with nested event/entity data
        data_result = await db.query(
            f"SELECT * FROM reference WHERE {where_clause} "
            "ORDER BY created_at DESC LIMIT $per_page START $offset "
            "FETCH event, event.document, canonical_entity",
            query_params,
        )
    except Exception as exc:
        logger.error("Failed to query references: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Failed to query database.",
        ) from exc

    from surrealdb.data.types.record_id import RecordID

    data_records: list[dict] = [
        r for r in (data_result or []) if isinstance(r, dict)
    ]

    items: list[ReferenceListItem] = []
    for record in data_records:
        ref_id_val = record.get("id")
        reference_id: str = ""
        if isinstance(ref_id_val, RecordID):
            reference_id = ref_id_val.id
        elif isinstance(ref_id_val, str):
            reference_id = ref_id_val.split(":", 1)[1] if ":" in ref_id_val else ref_id_val

        # Extract event context from fetched event record
        event_data = record.get("event")
        event_que_paso: str | None = None
        event_id: str | None = None
        document_filename: str | None = None
        document_id: str | None = None

        if isinstance(event_data, dict):
            event_que_paso = event_data.get("que_paso")
            ev_id_val = event_data.get("id")
            if isinstance(ev_id_val, RecordID):
                event_id = ev_id_val.id
            elif isinstance(ev_id_val, str):
                event_id = ev_id_val.split(":", 1)[1] if ":" in ev_id_val else ev_id_val

            # Extract document context from fetched event.document
            doc_data = event_data.get("document")
            if isinstance(doc_data, dict):
                document_filename = doc_data.get("filename")
                doc_id_val = doc_data.get("id")
                if isinstance(doc_id_val, RecordID):
                    document_id = doc_id_val.id
                elif isinstance(doc_id_val, str):
                    document_id = doc_id_val.split(":", 1)[1] if ":" in doc_id_val else doc_id_val

        # Extract canonical entity name from fetched entity record
        canonical_entity_data = record.get("canonical_entity")
        canonical_entity_name: str | None = None
        if isinstance(canonical_entity_data, dict):
            canonical_entity_name = canonical_entity_data.get("name")

        items.append(ReferenceListItem(
            reference_id=reference_id,
            reference_type=record.get("reference_type", ""),
            verbatim_text=record.get("verbatim_text", ""),
            span_start=record.get("span_start"),
            span_end=record.get("span_end"),
            event_que_paso=event_que_paso,
            event_id=event_id,
            document_filename=document_filename,
            document_id=document_id,
            canonical_entity_name=canonical_entity_name,
        ))

    logger.info(
        "Listed references (page=%d, per_page=%d, search=%s, type=%s) — %d items of %d total",
        page,
        per_page,
        search or "",
        reference_type or "",
        len(items),
        total,
    )

    return ReferenceListResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
    )


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
