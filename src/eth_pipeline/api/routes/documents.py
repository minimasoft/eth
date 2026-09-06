from __future__ import annotations

import asyncio
import base64
import io
import logging
import os
import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from eth_pipeline.api import app
from eth_pipeline.db import get_db
from eth_pipeline.passcodes import require_passcode

from eth_pipeline import providers as provider_svc

from eth_pipeline.api.models import (
    APIInfo,
    ChunkTextResponse,
    DocumentCreated,
    DocumentDeleted,
    DocumentInput,
    DocumentListItem,
    DocumentListResponse,
    DocumentStatus,
    DocumentTokenUsage,
    DocumentUploadCreated,
    HealthResponse,
    LlmCallLogListItem,
    LlmCallLogListResponse,
    ProcessingLogListItem,
    ProcessingLogListResponse,
)

from eth_pipeline.storage import get_storage_async

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Documents"])

#: Maximum upload file size: 50 MB.
MAX_UPLOAD_SIZE = 50 * 1024 * 1024

#: Allowed LLM modes for per-send extraction (T-SK4-01 allowlist).
_ALLOWED_LLM_MODES = {"thinking", "instruct"}


def _normalize_llm_mode(value: str) -> str:
    """Normalize and validate a client-supplied llm_mode (HTTP 400 otherwise)."""
    mode = (value or "").strip().lower()
    if mode not in _ALLOWED_LLM_MODES:
        raise HTTPException(
            status_code=400,
            detail="llm_mode must be 'thinking' or 'instruct'.",
        )
    return mode


async def _resolve_provider(provider_id: str | None) -> dict:
    """Resolve a provider id to ``{provider_id, provider_name, model}``.

    Falls back to the env-backed default provider when *provider_id* is None.
    Raises HTTPException(404) if the requested provider does not exist.
    """
    if not provider_id:
        provider_id = provider_svc.DEFAULT_PROVIDER_ID
    provider = await provider_svc.resolve_provider(provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail=f"Provider {provider_id!r} not found.")
    return {
        "provider_id": provider["id"],
        "provider_name": provider["name"],
        "model": provider["model"],
    }


# =======================================================================
# Root endpoint
# =======================================================================


@router.get("/", response_model=APIInfo)
@require_passcode("C")
async def root() -> APIInfo:
    """Return basic API information and available endpoints."""
    return APIInfo(
        name="eth-pipeline",
        version="0.1.0",
        description="Document processing pipeline with Temporal and PostgreSQL",
        endpoints={
            "/": "This information",
            "/health": "Liveness check",
            "/documents": "List documents (GET) or submit for processing (POST)",
            "/documents/upload": "Upload a binary document file (POST, multipart, fan-out via repeated provider_ids)",
            "/documents/{document_id}": "Get document status (GET) or delete cascade (DELETE)",
            "/documents/{document_id}/logs": "Get processing log entries for a document (GET)",
            "/documents/{document_id}/llm-calls": "Get LLM call log entries for a document (GET)",
            "/documents/{document_id}/tokens": "Get aggregated token usage for a document (GET)",
            "/events": "List extracted events with model provenance (GET; filters: search, document, source, model)",
            "/events/{event_id}": "Get event detail with locations, participants, references (GET)",
            "/comparisons/{source_id}": "Cross-model comparison of events extracted from one source document (GET)",
            "/api/providers": "Manage LLM providers (GET/POST/DELETE)",
        },
    )


# =======================================================================
# Health endpoint
# =======================================================================


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness check endpoint.

    Returns ``{"status": "ok"}`` regardless of database state so that
    orchestrators (Docker, Kubernetes) can monitor the process itself.
    """
    return HealthResponse(status="ok")


async def _start_workflow(doc_id: str) -> None:
    """Best-effort start of the Temporal document workflow for *doc_id*."""
    temporal = getattr(app.state, "temporal", None)
    if temporal is not None:
        try:
            from eth_pipeline.workflows import DocumentProcessingV7Workflow

            await temporal.start_workflow(
                DocumentProcessingV7Workflow.run,
                id=f"doc-{doc_id}",
                task_queue="event-extraction",
                args=[doc_id],
                id_conflict_policy=1,  # USE_EXISTING
            )
            logger.info("Temporal workflow started for document %s", doc_id)
        except Exception as exc:  # noqa: BLE001
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


# =======================================================================
# Create document endpoint
# =======================================================================


@router.post("/documents", response_model=DocumentCreated, status_code=201)
@require_passcode("A")
async def create_document(input: DocumentInput) -> DocumentCreated:
    """Ingest a new document into the pipeline.

    The document is stored in PostgreSQL with status ``"pending"`` for
    later extraction by the Temporal workflow.  If the database is not
    available the endpoint returns HTTP 503.

    When Temporal is connected, a workflow is started automatically to
    process the document.  If Temporal is unavailable the document is
    still stored and can be processed later.
    """
    doc_id = str(uuid.uuid4().hex)

    provider = await _resolve_provider(input.provider_id)
    llm_mode = _normalize_llm_mode(input.llm_mode)

    original_blob = base64.b64encode(input.text.encode("utf-8")).decode("ascii")

    try:
        async with get_db() as conn:
            await conn.execute(
                "INSERT INTO document (id, text_content, original_blob, filename, mime_type, status, error_message, provider_id, model, source_id, llm_mode) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)",
                doc_id,
                input.text,
                original_blob,
                input.filename,
                input.mime_type or "text/plain",
                "pending",
                None,
                provider["provider_id"],
                provider["model"],
                doc_id,
                llm_mode,
            )
    except Exception as exc:
        logger.error("Failed to create document in PostgreSQL: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Failed to store document in database.",
        ) from exc

    logger.info(
        "Created document %s (filename=%s, status=pending, model=%s)",
        doc_id,
        input.filename,
        provider["model"],
    )

    # ---- Trigger Temporal workflow (best-effort) ----
    await _start_workflow(doc_id)

    return DocumentCreated(document_id=doc_id, status="pending", source_id=doc_id)


# =======================================================================
# Upload document endpoint (MinIO blob storage)
# =======================================================================


@router.post("/documents/upload", response_model=DocumentUploadCreated, status_code=201)
@require_passcode("A")
async def upload_document(
    file: Annotated[UploadFile, File(...)],
    provider_ids: Annotated[list[str], Form()] = [],  # noqa: B006 — FastAPI Form default
    llm_mode: Annotated[str, Form()] = "thinking",
) -> DocumentUploadCreated:
    """Upload a binary document file for processing.

    Accepts a multipart file upload, stores the binary blob in MinIO
    (with fallback to base64-encoded inline storage if MinIO is
    unavailable), creates one PostgreSQL document record per selected
    provider (fan-out), and triggers Temporal processing (best-effort).

    ``provider_ids`` may be repeated to send the file to multiple LLM
    providers.  When empty, the env-backed default provider is used.

    Returns HTTP 201 with ``{document_id, status}`` on success.
    Returns HTTP 413 if the file exceeds 50 MB.
    Returns HTTP 503 if the database is unavailable.
    """
    # 1. Validate file
    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="Filename is required.",
        )

    # 1b. Validate llm_mode (T-SK4-01: server-side allowlist, reject early
    #     before any blob write).
    llm_mode = _normalize_llm_mode(llm_mode)

    # 2. Determine effective providers (fan-out list). Resolve before any
    #    blob write so a bad provider id costs nothing, and de-duplicate
    #    repeated ids while preserving order.
    unique_ids = list(dict.fromkeys(provider_ids)) if provider_ids else [None]
    selected = [await _resolve_provider(pid) for pid in unique_ids]

    # 3. Generate document ID
    doc_id = str(uuid.uuid4().hex)

    # 4. Determine blob path
    ext = ".bin"
    if "." in file.filename:
        _, ext_candidate = os.path.splitext(file.filename)
        if ext_candidate:
            ext = ext_candidate
    blob_path = f"doc/{doc_id}{ext}"

    # 5. Read file content with size guard
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

    # 6. Try MinIO storage (degraded mode: fall back to base64 inline)
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

    # 7. Prepare document record(s). All fan-out rows share the same blob.
    if minio_available:
        original_blob = ""
        blob_format = "minio"
        stored_blob_path = blob_path
    else:
        original_blob = base64.b64encode(content).decode("ascii")
        blob_format = None
        stored_blob_path = None

    inserted_ids: list[str] = []
    source_id = str(uuid.uuid4().hex)
    try:
        async with get_db() as conn:
            for _provider in selected:
                row_id = str(uuid.uuid4().hex)
                inserted_ids.append(row_id)
                await conn.execute(
                    "INSERT INTO document (id, text_content, original_blob, blob_format, blob_path, "
                    "filename, mime_type, status, error_message, provider_id, model, source_id, llm_mode) "
                    "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)",
                    row_id,
                    None,
                    original_blob,
                    blob_format,
                    stored_blob_path,
                    file.filename or f"unnamed_{row_id}",
                    file.content_type or "application/octet-stream",
                    "pending",
                    None,
                    _provider["provider_id"],
                    _provider["model"],
                    source_id,
                    llm_mode,
                )
    except Exception as exc:
        logger.error("Failed to create document in PostgreSQL: %s", exc)
        # Clean up MinIO blob if database failed after storage
        if minio_available:
            try:
                async with get_storage_async() as cleanup_client:
                    await asyncio.to_thread(
                        cleanup_client.remove_object,
                        os.environ.get("MINIO_BUCKET", "eth-documents"),
                        blob_path,
                    )
                    logger.info("Cleaned up MinIO blob %s after DB failure", blob_path)
            except Exception as cleanup_exc:  # noqa: BLE001
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
        "Created document (filename=%s, blob_format=%s, fanout=%d)",
        file.filename,
        blob_format,
        len(inserted_ids),
    )

    # 8. Trigger Temporal workflow per inserted row (best-effort). Fan-out
    #    creates one document row per selected provider; each runs its own
    #    workflow against its own row id.
    for row_id in inserted_ids:
        await _start_workflow(row_id)

    return DocumentUploadCreated(
        document_id=inserted_ids[0],
        status="pending",
        document_ids=inserted_ids,
        source_id=source_id,
    )


# =======================================================================
# Get document status
# =======================================================================


@router.get(
    "/documents/{document_id}",
    response_model=DocumentStatus,
)
@require_passcode("C")
async def get_document(document_id: str) -> DocumentStatus:
    """Retrieve document status and metadata.

    Queries PostgreSQL for the document record identified by ``document_id``
    and returns its current status, filename, error message, and creation
    timestamp.

    Returns HTTP 404 if the document does not exist and HTTP 503 if the
    database is unavailable.
    """
    try:
        async with get_db() as conn:
            row = await conn.fetchrow(
                "SELECT d.*, p.name AS provider_name "
                "FROM document d "
                "LEFT JOIN llm_provider p ON p.id = d.provider_id "
                "WHERE d.id = $1",
                document_id,
            )
    except Exception as exc:
        logger.error("Failed to query document %s: %s", document_id, exc)
        raise HTTPException(
            status_code=502,
            detail="Failed to query database.",
        ) from exc

    if row is None:
        logger.warning("Document %s not found", document_id)
        raise HTTPException(
            status_code=404,
            detail=f"Document {document_id} not found.",
        )

    created_at_raw = row.get("created_at")
    if created_at_raw is not None:
        created_at_str = (
            created_at_raw.isoformat()
            if hasattr(created_at_raw, "isoformat")
            else str(created_at_raw)
        )
    else:
        created_at_str = None

    # Query visibility counts (non-fatal — defaults to 0 on failure)
    evt_count = 0
    ref_count = 0
    ent_count = 0
    chunk_count = 0
    text_word_count = 0
    try:
        async with get_db() as conn:
            evt_row = await conn.fetchrow(
                "SELECT COUNT(*) AS total FROM event_v2 WHERE document_id = $1",
                document_id,
            )
            evt_count = evt_row["total"] if evt_row else 0

            chunk_row = await conn.fetchrow(
                "SELECT COUNT(*) AS total FROM document_chunk WHERE document = $1",
                document_id,
            )
            chunk_count = chunk_row["total"] if chunk_row else 0

            text_content = row.get("text_content", "") or ""
            text_word_count = len(text_content.split()) if text_content.strip() else 0
    except Exception as exc:
        logger.warning("Failed to query document counts for %s: %s", document_id, exc)

    return DocumentStatus(
        document_id=document_id,
        status=row.get("status", "unknown"),
        filename=row.get("filename", ""),
        error_message=row.get("error_message"),
        created_at=created_at_str,
        blob_format=row.get("blob_format"),
        blob_path=row.get("blob_path"),
        reference_count=ref_count,
        entity_count=ent_count,
        chunk_count=chunk_count,
        text_word_count=text_word_count,
        provider_id=row.get("provider_id"),
        provider_name=row.get("provider_name"),
        model=row.get("model"),
        source_id=row.get("source_id"),
    )


@router.get(
    "/documents/{document_id}/chunks/{part_index}",
    response_model=ChunkTextResponse,
)
@require_passcode("C")
async def get_chunk_text(
    document_id: str,
    part_index: int,
) -> ChunkTextResponse:
    """Get chunk text content with absolute and chunk-relative offset info."""
    try:
        async with get_db() as conn:
            chunk_row = await conn.fetchrow(
                "SELECT chunk_index, text, offset_start, offset_end "
                "FROM document_chunk "
                "WHERE document = $1 AND chunk_index = $2",
                document_id,
                part_index,
            )
    except Exception as exc:
        logger.error("Failed to query chunk for document %s part %d: %s", document_id, part_index, exc)
        raise HTTPException(
            status_code=502,
            detail="Failed to query database.",
        ) from exc

    if not chunk_row:
        logger.warning("Chunk not found: document %s, part %d", document_id, part_index)
        raise HTTPException(
            status_code=404,
            detail=f"Chunk not found: document {document_id}, part {part_index}",
        )

    chunk_text = chunk_row["text"] or ""
    chunk_offset_start = 0
    chunk_offset_end = len(chunk_text)

    logger.info("Chunk text for %s part %d — %d chars", document_id, part_index, len(chunk_text))

    return ChunkTextResponse(
        document_id=document_id,
        part_index=part_index,
        text=chunk_text,
        offset_start=chunk_row["offset_start"],
        offset_end=chunk_row["offset_end"],
        chunk_offset_start=chunk_offset_start,
        chunk_offset_end=chunk_offset_end,
    )


# =======================================================================
# Get document processing logs (paginated)
# =======================================================================


@router.get(
    "/documents/{document_id}/logs",
    response_model=ProcessingLogListResponse,
)
@require_passcode("C")
async def get_document_logs(
    document_id: str,
    page: int = Query(1, ge=1),
) -> ProcessingLogListResponse:
    """Retrieve processing log entries for a document (paginated, newest first)."""
    per_page = 50
    offset = (page - 1) * per_page

    # Verify document exists
    try:
        async with get_db() as conn:
            doc_row = await conn.fetchrow(
                "SELECT id FROM document WHERE id = $1",
                document_id,
            )
    except Exception as exc:
        logger.error(
            "Failed to query document %s: %s", document_id, exc
        )
        raise HTTPException(
            status_code=502,
            detail="Failed to query database.",
        ) from exc

    if doc_row is None:
        logger.warning("Document %s not found for log query", document_id)
        raise HTTPException(
            status_code=404,
            detail=f"Document {document_id} not found.",
        )

    try:
        async with get_db() as conn:
            total_row = await conn.fetchrow(
                "SELECT COUNT(*) AS total FROM document_event_log "
                "WHERE document = $1",
                document_id,
            )
            total = total_row["total"] if total_row else 0
    except Exception as exc:
        logger.error(
            "Failed to count log entries for document %s: %s",
            document_id,
            exc,
        )
        raise HTTPException(
            status_code=502,
            detail="Failed to query database.",
        ) from exc

    if total == 0:
        pages = 0
    else:
        pages = max(1, (total + per_page - 1) // per_page)

    try:
        async with get_db() as conn:
            rows = await conn.fetch(
                "SELECT * FROM document_event_log "
                "WHERE document = $1 "
                "ORDER BY created_at DESC "
                "LIMIT $2 OFFSET $3",
                document_id,
                per_page,
                offset,
            )
    except Exception as exc:
        logger.error(
            "Failed to query log entries for document %s: %s",
            document_id,
            exc,
        )
        raise HTTPException(
            status_code=502,
            detail="Failed to query database.",
        ) from exc

    items: list[ProcessingLogListItem] = []
    for record in rows:
        entry_id: str = record.get("id", "")

        created_at_raw = record.get("created_at")
        created_at_str: str | None = None
        if created_at_raw is not None:
            created_at_str = (
                created_at_raw.isoformat()
                if hasattr(created_at_raw, "isoformat")
                else str(created_at_raw)
            )

        items.append(ProcessingLogListItem(
            id=entry_id,
            document_id=document_id,
            step_name=record.get("step_name", ""),
            severity=record.get("severity", ""),
            message=record.get("message", ""),
            details=record.get("details"),
            created_at=created_at_str,
        ))

    logger.info(
        "Listed processing logs for document %s (page=%d) — %d items of %d total",
        document_id,
        page,
        len(items),
        total,
    )

    return ProcessingLogListResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
    )


# =======================================================================
# Get document LLM call logs (paginated)
# =======================================================================


@router.get(
    "/documents/{document_id}/llm-calls",
    response_model=LlmCallLogListResponse,
)
@require_passcode("C")
async def get_document_llm_calls(
    document_id: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
) -> LlmCallLogListResponse:
    """Retrieve LLM call log entries for a document (paginated, oldest first)."""
    offset = (page - 1) * per_page

    # Verify document exists (D-06)
    try:
        async with get_db() as conn:
            doc_row = await conn.fetchrow(
                "SELECT id FROM document WHERE id = $1",
                document_id,
            )
    except Exception as exc:
        logger.error(
            "Failed to query document %s: %s", document_id, exc
        )
        raise HTTPException(
            status_code=502,
            detail="Failed to query database.",
        ) from exc

    if doc_row is None:
        logger.warning("Document %s not found for LLM call log query", document_id)
        raise HTTPException(
            status_code=404,
            detail=f"Document {document_id} not found.",
        )

    # Count total entries (D-08: empty returns pages=1, not 404)
    try:
        async with get_db() as conn:
            total_row = await conn.fetchrow(
                "SELECT COUNT(*) AS total FROM llm_call_log "
                "WHERE document = $1",
                document_id,
            )
            total = total_row["total"] if total_row else 0
    except Exception as exc:
        logger.error(
            "Failed to count LLM call log entries for document %s: %s",
            document_id,
            exc,
        )
        raise HTTPException(
            status_code=502,
            detail="Failed to query database.",
        ) from exc

    if total == 0:
        pages = 1  # D-08: empty → pages=1, not 0
    else:
        pages = max(1, (total + per_page - 1) // per_page)

    # Fetch page of results sorted by timestamp ASC (D-02)
    try:
        async with get_db() as conn:
            rows = await conn.fetch(
                "SELECT * FROM llm_call_log "
                "WHERE document = $1 "
                "ORDER BY timestamp ASC "
                "LIMIT $2 OFFSET $3",
                document_id,
                per_page,
                offset,
            )
    except Exception as exc:
        logger.error(
            "Failed to query LLM call log entries for document %s: %s",
            document_id,
            exc,
        )
        raise HTTPException(
            status_code=502,
            detail="Failed to query database.",
        ) from exc

    items: list[LlmCallLogListItem] = []
    for record in rows:
        # Convert timestamp to ISO-8601 string (same pattern as created_at_str)
        timestamp_raw = record.get("timestamp")
        timestamp_str: str | None = None
        if timestamp_raw is not None:
            timestamp_str = (
                timestamp_raw.isoformat()
                if hasattr(timestamp_raw, "isoformat")
                else str(timestamp_raw)
            )

        items.append(LlmCallLogListItem(
            id=record.get("id", ""),
            document_id=document_id,
            prompt_text=record.get("prompt_text"),      # D-01: include full text
            response_text=record.get("response_text"),    # D-01: include full text
            prompt_tokens=record.get("prompt_tokens"),
            completion_tokens=record.get("completion_tokens"),
            total_tokens=record.get("total_tokens"),
            cached_tokens=record.get("cached_tokens"),
            cost=record.get("cost"),
            duration_ms=record.get("duration_ms"),
            model=record.get("model"),
            activity_type=record.get("activity_type"),
            timestamp=timestamp_str,
        ))

    logger.info(
        "Listed LLM call logs for document %s (page=%d) — %d items of %d total",
        document_id,
        page,
        len(items),
        total,
    )

    return LlmCallLogListResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
    )


# =======================================================================
# List documents (paginated)
# =======================================================================


@router.get("/documents/{document_id}/tokens", response_model=DocumentTokenUsage)
@require_passcode("C")
async def get_document_tokens(document_id: str) -> DocumentTokenUsage:
    """Retrieve aggregated token usage for a single document."""
    try:
        async with get_db() as conn:
            row = await conn.fetchrow(
                "SELECT "
                "SUM(prompt_tokens) as prompt_tokens, "
                "SUM(completion_tokens) as completion_tokens, "
                "SUM(total_tokens) as total_tokens, "
                "SUM(cached_tokens) as cached_tokens, "
                "SUM(cost) as total_cost, "
                "SUM(duration_ms) as duration_ms, "
                "COUNT(*) as record_count "
                "FROM llm_usage WHERE document = $1",
                document_id,
            )
    except Exception as exc:
        logger.error("Failed to query token usage for %s: %s", document_id, exc)
        raise HTTPException(
            status_code=502,
            detail="Failed to query token usage.",
        ) from exc

    if not row or row.get("record_count", 0) == 0:
        logger.info("No token data for document %s", document_id)
        return DocumentTokenUsage(has_data=False)

    return DocumentTokenUsage(
        has_data=True,
        prompt_tokens=row.get("prompt_tokens") or 0,
        completion_tokens=row.get("completion_tokens") or 0,
        total_tokens=row.get("total_tokens") or 0,
        cached_tokens=row.get("cached_tokens") or 0,
        total_cost=row.get("total_cost"),
        duration_ms=row.get("duration_ms") or 0,
    )


@router.get("/documents", response_model=DocumentListResponse)
@require_passcode("C")
async def list_documents(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    search: str | None = Query(None),
    status: str | None = Query(None),
) -> DocumentListResponse:
    """List documents with pagination, search, and status filtering."""
    offset = (page - 1) * per_page

    # Build dynamic WHERE clause with positional params
    params: list[object] = []
    where_parts: list[str] = ["1 = 1"]

    if search:
        params.append(f"%{search}%")
        where_parts.append(f"filename LIKE ${len(params)}")

    if status:
        params.append(status)
        where_parts.append(f"status = ${len(params)}")

    where_clause = " AND ".join(where_parts)

    try:
        async with get_db() as conn:
            total_row = await conn.fetchrow(
                f"SELECT COUNT(*) AS total FROM document WHERE {where_clause}",
                *params,
            )
            total = total_row["total"] if total_row else 0
    except Exception as exc:
        logger.error("Failed to count documents: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Failed to query database.",
        ) from exc

    if total == 0:
        pages = 0
    else:
        pages = max(1, (total + per_page - 1) // per_page)

    # Build data query with additional pagination params
    data_params = params.copy()
    data_params.append(per_page)
    data_params.append(offset)

    try:
        async with get_db() as conn:
            rows = await conn.fetch(
                f"SELECT d.*, p.name AS provider_name "
                f"FROM document d "
                f"LEFT JOIN llm_provider p ON p.id = d.provider_id "
                f"WHERE {where_clause} "
                "ORDER BY d.created_at DESC LIMIT $1 OFFSET $2",
                *data_params,
            )
    except Exception as exc:
        logger.error("Failed to query documents: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Failed to query database.",
        ) from exc

    # Batched token aggregation: one extra query for all documents on this page
    document_ids: list[str] = []
    for record in rows:
        doc_id_val = record.get("id")
        if isinstance(doc_id_val, str):
            document_ids.append(doc_id_val)

    token_map: dict[str, dict] = {}
    if document_ids:
        try:
            async with get_db() as conn:
                token_rows = await conn.fetch(
                    "SELECT document, "
                    "SUM(prompt_tokens) as prompt_tokens, "
                    "SUM(completion_tokens) as completion_tokens, "
                    "SUM(total_tokens) as total_tokens, "
                    "SUM(cached_tokens) as cached_tokens, "
                    "SUM(cost) as total_cost, "
                    "SUM(duration_ms) as duration_ms "
                    "FROM llm_usage "
                    "WHERE document = ANY($1::text[]) "
                    "GROUP BY document",
                    document_ids,
                )
                for token_row in token_rows:
                    doc_ref = token_row.get("document")
                    if doc_ref is not None:
                        token_map[str(doc_ref)] = dict(token_row)
        except Exception as exc:
            logger.warning("Failed to query batched token data: %s", exc)

    source_ids: list[str] = []
    for record in rows:
        src_val = record.get("source_id")
        if isinstance(src_val, str) and src_val not in source_ids:
            source_ids.append(src_val)

    source_count_map: dict[str, int] = {}
    if source_ids:
        try:
            async with get_db() as conn:
                count_rows = await conn.fetch(
                    "SELECT source_id, COUNT(*) AS n FROM document "
                    "WHERE source_id = ANY($1::text[]) "
                    "GROUP BY source_id",
                    source_ids,
                )
                for count_row in count_rows:
                    source_count_map[str(count_row["source_id"])] = int(count_row["n"])
        except Exception as exc:
            logger.warning("Failed to query batched source counts: %s", exc)

    items: list[DocumentListItem] = []
    for record in rows:
        doc_id = record.get("id", "")

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
        evt_count = 0
        ref_count = 0
        ent_count = 0
        chunk_count = 0
        twc = 0
        try:
            async with get_db() as conn:
                evt_row = await conn.fetchrow(
                    "SELECT COUNT(*) AS total FROM event_v2 WHERE document_id = $1",
                    doc_id,
                )
                evt_count = evt_row["total"] if evt_row else 0

                chunk_row = await conn.fetchrow(
                    "SELECT COUNT(*) AS total FROM document_chunk WHERE document = $1",
                    doc_id,
                )
                chunk_count = chunk_row["total"] if chunk_row else 0

                text_content = record.get("text_content", "") or ""
                twc = len(text_content.split()) if text_content.strip() else 0
        except Exception as exc:
            logger.warning("Failed to query counts for document %s: %s", doc_id, exc)

        token_data = token_map.get(doc_id, {})

        items.append(DocumentListItem(
            document_id=doc_id,
            status=record.get("status", "unknown"),
            filename=record.get("filename", ""),
            created_at=created_at_str,
            error_message=record.get("error_message"),
            event_count=evt_count,
            reference_count=ref_count,
            entity_count=ent_count,
            chunk_count=chunk_count,
            text_word_count=twc,
            prompt_tokens=token_data.get("prompt_tokens") or 0 if token_data else 0,
            completion_tokens=token_data.get("completion_tokens") or 0 if token_data else 0,
            total_tokens=token_data.get("total_tokens") or 0 if token_data else 0,
            cached_tokens=token_data.get("cached_tokens") or 0 if token_data else 0,
            total_cost=token_data.get("total_cost") if token_data else None,
            duration_ms=token_data.get("duration_ms") or 0 if token_data else 0,
            provider_id=record.get("provider_id"),
            provider_name=record.get("provider_name"),
            model=record.get("model"),
            source_id=record.get("source_id"),
            model_count=(
                source_count_map.get(record.get("source_id"), 1)
                if record.get("source_id") else 1
            ),
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
# Delete document endpoint (full cascade)
# =======================================================================


@router.delete(
    "/documents/{document_id}",
    response_model=DocumentDeleted,
)
@require_passcode("B")
async def delete_document(document_id: str) -> DocumentDeleted:
    """Delete a document and all its associated data.

    With ON DELETE CASCADE foreign keys, deleting events, references,
    document_chunks, etc. is handled automatically when the document
    is deleted.  Canonical entities are cleaned up separately since
    they may be referenced by multiple documents.
    """
    # Verify document exists
    try:
        async with get_db() as conn:
            doc_row = await conn.fetchrow(
                "SELECT id FROM document WHERE id = $1",
                document_id,
            )
    except Exception as exc:
        logger.error("Failed to query document %s: %s", document_id, exc)
        raise HTTPException(
            status_code=502,
            detail="Failed to query database.",
        ) from exc

    if doc_row is None:
        logger.warning("Document %s not found for cascade delete", document_id)
        raise HTTPException(
            status_code=404,
            detail=f"Document {document_id} not found.",
        )

    try:
        async with get_db() as conn:
            # Delete shared v7+ related records
            await conn.execute(
                "DELETE FROM document_chunk WHERE document = $1",
                document_id,
            )
            await conn.execute(
                "DELETE FROM document_event_log WHERE document = $1",
                document_id,
            )
            await conn.execute(
                "DELETE FROM llm_usage WHERE document = $1",
                document_id,
            )
            await conn.execute(
                "DELETE FROM llm_call_log WHERE document = $1",
                document_id,
            )
            # Delete event_v2 records and their related tables
            await conn.execute(
                "DELETE FROM event_ref WHERE event_id IN (SELECT id FROM event_v2 WHERE document_id = $1)",
                document_id,
            )
            await conn.execute(
                "DELETE FROM event_participant_v2 WHERE event_id IN (SELECT id FROM event_v2 WHERE document_id = $1)",
                document_id,
            )
            await conn.execute(
                "DELETE FROM event_location WHERE event_id IN (SELECT id FROM event_v2 WHERE document_id = $1)",
                document_id,
            )
            await conn.execute(
                "DELETE FROM event_document WHERE document_id = $1",
                document_id,
            )
            await conn.execute(
                "DELETE FROM event_v2 WHERE document_id = $1",
                document_id,
            )
            # Delete the document itself
            await conn.execute(
                "DELETE FROM document WHERE id = $1",
                document_id,
            )

        logger.info(
            "Deleted document %s (cascade complete)",
            document_id,
        )

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
    )

