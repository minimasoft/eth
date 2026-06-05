from __future__ import annotations

import asyncio
import base64
import io
import logging
import os
import uuid

import asyncpg
from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from eth_pipeline.api import app
from eth_pipeline.db import get_db

from eth_pipeline.api.models import (
    APIInfo,
    DocumentCreated,
    DocumentDeleted,
    DocumentInput,
    DocumentListItem,
    DocumentListResponse,
    DocumentStatus,
    DocumentTokenUsage,
    DocumentUploadCreated,
    EventsCleared,
    HealthResponse,
    ProcessingLogListItem,
    ProcessingLogListResponse,
)

from eth_pipeline.storage import get_storage_async

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Documents"])

#: Maximum upload file size: 50 MB.
MAX_UPLOAD_SIZE = 50 * 1024 * 1024


# =======================================================================
# Root endpoint
# =======================================================================


@router.get("/", response_model=APIInfo)
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
            "/documents/upload": "Upload a binary document file (POST, multipart)",
            "/documents/{document_id}": "Get document status (GET)",
            "/documents/{document_id}/events": "Clear extraction results (DELETE)",
            "/documents/{document_id}/logs": "Get processing log entries for a document (GET)",
            "/entities": "List canonical entities with pagination, search, and type filter (GET)",
            "/entities/merge": "Merge two canonical entities of the same type (POST)",
            "/entities/{entity_type}/{entity_id}/split": "Partition references across new canonical entities (POST)",
            "/references": "List references with pagination, search, and type filter (GET)",
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


# =======================================================================
# Create document endpoint
# =======================================================================


@router.post("/documents", response_model=DocumentCreated, status_code=201)
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

    original_blob = base64.b64encode(input.text.encode("utf-8")).decode("ascii")

    try:
        async with get_db() as conn:
            await conn.execute(
                "INSERT INTO document (id, text_content, original_blob, filename, mime_type, status, error_message) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7)",
                doc_id,
                input.text,
                original_blob,
                input.filename,
                input.mime_type or "text/plain",
                "pending",
                None,
            )
    except Exception as exc:
        logger.error("Failed to create document in PostgreSQL: %s", exc)
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


@router.post("/documents/upload", response_model=DocumentUploadCreated, status_code=201)
async def upload_document(file: UploadFile = File(...)) -> DocumentUploadCreated:
    """Upload a binary document file for processing.

    Accepts a multipart file upload, stores the binary blob in MinIO
    (with fallback to base64-encoded inline storage if MinIO is
    unavailable), creates a PostgreSQL document record with
    ``blob_format="minio"``, and triggers Temporal processing
    (best-effort).

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

    # 7. Create document record in PostgreSQL
    try:
        async with get_db() as conn:
            await conn.execute(
                "INSERT INTO document (id, text_content, original_blob, blob_format, blob_path, filename, mime_type, status, error_message) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)",
                doc_id,
                None,
                original_blob,
                blob_format,
                stored_blob_path,
                file.filename or f"unnamed_{doc_id}",
                file.content_type or "application/octet-stream",
                "pending",
                None,
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


@router.get(
    "/documents/{document_id}",
    response_model=DocumentStatus,
)
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
                "SELECT * FROM document WHERE id = $1",
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
    ref_count = 0
    ent_count = 0
    chunk_count = 0
    text_word_count = 0
    try:
        async with get_db() as conn:
            ref_row = await conn.fetchrow(
                "SELECT COUNT(*) AS total FROM reference "
                "WHERE event IN (SELECT id FROM event WHERE document = $1)",
                document_id,
            )
            ref_count = ref_row["total"] if ref_row else 0

            ent_row = await conn.fetchrow(
                "SELECT COUNT(*) AS total FROM reference "
                "WHERE event IN (SELECT id FROM event WHERE document = $1) "
                "AND canonical_entity IS NOT NULL",
                document_id,
            )
            ent_count = ent_row["total"] if ent_row else 0

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
    )


# =======================================================================
# Get document processing logs (paginated)
# =======================================================================


@router.get(
    "/documents/{document_id}/logs",
    response_model=ProcessingLogListResponse,
)
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
# List documents (paginated)
# =======================================================================


@router.get("/documents/{document_id}/tokens", response_model=DocumentTokenUsage)
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
                f"SELECT * FROM document WHERE {where_clause} "
                "ORDER BY created_at DESC LIMIT $1 OFFSET $2",
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
        ref_count = 0
        ent_count = 0
        chunk_count = 0
        twc = 0
        try:
            async with get_db() as conn:
                ref_row = await conn.fetchrow(
                    "SELECT COUNT(*) AS total FROM reference "
                    "WHERE event IN (SELECT id FROM event WHERE document = $1)",
                    doc_id,
                )
                ref_count = ref_row["total"] if ref_row else 0

                ent_row = await conn.fetchrow(
                    "SELECT COUNT(*) AS total FROM reference "
                    "WHERE event IN (SELECT id FROM event WHERE document = $1) "
                    "AND canonical_entity IS NOT NULL",
                    doc_id,
                )
                ent_count = ent_row["total"] if ent_row else 0

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
            # --- Step 0: Collect event-type canonical entity IDs for this doc ---
            event_ce_rows = await conn.fetch(
                "SELECT id FROM canonical_entity "
                "WHERE entity_type = 'event' AND properties->>'document_id' = $1",
                document_id,
            )

            # --- Step 1: Delete event_participant edges (v6.0) ---
            try:
                await conn.execute(
                    "DELETE FROM event_participant WHERE "
                    "in_event IN (SELECT id FROM event WHERE document = $1)",
                    document_id,
                )
            except Exception as exc:
                logger.warning(
                    "event_participant cleanup skipped (table may not exist yet): %s",
                    exc,
                )

            # --- Step 1a: Collect non-event entities linked via event_entity_link ---
            # Collect BEFORE Step 1b deletes the edges, so we know which entities
            # to check for orphan status after references are deleted.
            eel_entity_rows = await conn.fetch(
                "SELECT entity FROM event_entity_link "
                "WHERE event IN ("
                "  SELECT id FROM canonical_entity "
                "  WHERE entity_type = 'event' AND properties->>'document_id' = $1"
                ")",
                document_id,
            )
            eel_entity_ids = list({
                str(r["entity"]) for r in eel_entity_rows
                if r["entity"] is not None
            })

            # --- Step 1b: Delete event_entity_link edges ---
            await conn.execute(
                "DELETE FROM event_entity_link WHERE event IN ("
                "SELECT id FROM canonical_entity "
                "WHERE entity_type = 'event' AND properties->>'document_id' = $1"
                ")",
                document_id,
            )

            # --- Step 2: Collect affected canonical_entities from references ---
            affected_ce_rows = await conn.fetch(
                "SELECT canonical_entity FROM reference "
                "WHERE event IN (SELECT id FROM event WHERE document = $1) "
                "AND canonical_entity IS NOT NULL",
                document_id,
            )
            affected_eid_rows = await conn.fetch(
                "SELECT entity_id FROM reference "
                "WHERE event IN (SELECT id FROM event WHERE document = $1) "
                "AND entity_id IS NOT NULL",
                document_id,
            )
            affected_ce_ids = list(set(
                str(r["canonical_entity"]) for r in affected_ce_rows
                if r["canonical_entity"] is not None
            ) | set(
                str(r["entity_id"]) for r in affected_eid_rows
                if r["entity_id"] is not None
            ))

            # --- Steps 3-6: Delete dependent records (CASCADE handles most) ---
            # event_participant, event_entity_link, reference, event,
            # document_chunk, document_event_log, llm_usage are all
            # cascaded from event/document deletions, but we delete
            # them explicitly for explicit ordering.

            await conn.execute(
                "DELETE FROM reference WHERE event IN "
                "(SELECT id FROM event WHERE document = $1)",
                document_id,
            )

            await conn.execute(
                "DELETE FROM event WHERE document = $1",
                document_id,
            )

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

            # --- Step 7: Delete event-type canonical entities for this doc ---
            await conn.execute(
                "DELETE FROM canonical_entity WHERE entity_type = 'event' "
                "AND properties->>'document_id' = $1",
                document_id,
            )

            # --- Step 8: Delete orphaned canonical entities (no refs remain) ---
            orphaned = 0
            for ent_id in affected_ce_ids:
                count_row = await conn.fetchrow(
                    "SELECT COUNT(*) AS total FROM reference "
                    "WHERE canonical_entity = $1 "
                    "OR entity_id = $1",
                    ent_id,
                )
                remaining = count_row["total"] if count_row else 0

                if remaining == 0:
                    await conn.execute(
                        "DELETE FROM canonical_entity WHERE id = $1",
                        ent_id,
                    )
                    orphaned += 1

            # --- Step 8b: Delete orphaned non-event entities from event_entity_link ---
            # Use eel_entity_ids collected in Step 1a (before edges were deleted)
            eel_ids = [
                eid for eid in eel_entity_ids
                if eid not in affected_ce_ids
            ]
            for ent_id in eel_ids:
                ref_row = await conn.fetchrow(
                    "SELECT COUNT(*) AS total FROM reference "
                    "WHERE canonical_entity = $1 "
                    "OR entity_id = $1",
                    ent_id,
                )
                ref_remaining = ref_row["total"] if ref_row else 0

                eel_row = await conn.fetchrow(
                    "SELECT COUNT(*) AS total FROM event_entity_link "
                    "WHERE entity = $1",
                    ent_id,
                )
                eel_remaining = eel_row["total"] if eel_row else 0

                if ref_remaining == 0 and eel_remaining == 0:
                    await conn.execute(
                        "DELETE FROM canonical_entity WHERE id = $1",
                        ent_id,
                    )
                    orphaned += 1

            # --- Step 9: Delete the document ---
            await conn.execute(
                "DELETE FROM document WHERE id = $1",
                document_id,
            )

        logger.info(
            "Deleted document %s (cascade complete, %d orphaned entities cleaned)",
            document_id,
            orphaned,
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
        orphaned_entities_cleaned=orphaned,
    )


# =======================================================================
# Clear document events endpoint
# =======================================================================


@router.delete(
    "/documents/{document_id}/events",
    response_model=EventsCleared,
)
async def clear_document_events(document_id: str) -> EventsCleared:
    """Clear all extraction results for a document and reset its status."""
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
        logger.warning("Document %s not found for event clear", document_id)
        raise HTTPException(
            status_code=404,
            detail=f"Document {document_id} not found.",
        )

    try:
        async with get_db() as conn:
            # Delete event_participant edges for events of this doc (v6.0)
            await conn.execute(
                "DELETE FROM event_participant WHERE "
                "in_event IN (SELECT id FROM event WHERE document = $1)",
                document_id,
            )

            # Delete event_entity_link edges for event-type entities of this doc
            await conn.execute(
                "DELETE FROM event_entity_link WHERE event IN ("
                "SELECT id FROM canonical_entity "
                "WHERE entity_type = 'event' AND properties->>'document_id' = $1"
                ")",
                document_id,
            )

            await conn.execute(
                "DELETE FROM document_chunk WHERE document = $1",
                document_id,
            )

            await conn.execute(
                "DELETE FROM reference WHERE event IN "
                "(SELECT id FROM event WHERE document = $1)",
                document_id,
            )

            await conn.execute(
                "DELETE FROM event WHERE document = $1",
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

            # Delete event-type canonical entities for this doc
            await conn.execute(
                "DELETE FROM canonical_entity WHERE entity_type = 'event' "
                "AND properties->>'document_id' = $1",
                document_id,
            )

            await conn.execute(
                "UPDATE document SET status = 'pending', "
                "text_content = '', error_message = NULL, "
                "updated_at = NOW() WHERE id = $1",
                document_id,
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
