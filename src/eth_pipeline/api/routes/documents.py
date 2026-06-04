from __future__ import annotations

import asyncio
import base64
import io
import logging
import os
import uuid

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from surrealdb import AsyncWsSurrealConnection

from eth_pipeline.api import app

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
    _parse_count,
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
        description="Document processing pipeline with Temporal and SurrealDB",
        endpoints={
            "/": "This information",
            "/health": "Liveness check",
            "/graphql": "Proxy to SurrealDB auto-GraphQL (POST)",
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


@router.post("/documents/upload", response_model=DocumentUploadCreated, status_code=201)
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


@router.get(
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
            "SELECT count() AS total FROM document_chunk WHERE document = $doc_ref GROUP ALL",
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
    db: AsyncWsSurrealConnection | None = app.state.db

    if db is None:
        logger.error(
            "GET /documents/%s/logs rejected — SurrealDB unavailable",
            document_id,
        )
        raise HTTPException(
            status_code=503,
            detail="SurrealDB is not available. Please try again later.",
        )

    per_page = 50
    offset = (page - 1) * per_page

    try:
        from surrealdb.data.types.record_id import RecordID

        doc_id_obj = RecordID("document", document_id)
        exists_result = await db.query(
            "SELECT * FROM document WHERE id = $doc_id",
            {"doc_id": doc_id_obj},
        )
    except Exception as exc:
        logger.error(
            "Failed to query document %s: %s", document_id, exc
        )
        raise HTTPException(
            status_code=502,
            detail="Failed to query database.",
        ) from exc

    exists_records: list[dict] = [
        r for r in (exists_result or []) if isinstance(r, dict)
    ]
    if not exists_records:
        logger.warning("Document %s not found for log query", document_id)
        raise HTTPException(
            status_code=404,
            detail=f"Document {document_id} not found.",
        )

    from surrealdb.data.types.record_id import RecordID

    doc_ref_obj = RecordID("document", document_id)

    try:
        count_result = await db.query(
            "SELECT count() AS total FROM document_event_log "
            "WHERE document = $doc_ref GROUP ALL",
            {"doc_ref": doc_ref_obj},
        )
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

    total = _parse_count(count_result)

    if total == 0:
        pages = 0
    else:
        pages = max(1, (total + per_page - 1) // per_page)

    try:
        data_result = await db.query(
            "SELECT * FROM document_event_log "
            "WHERE document = $doc_ref "
            "ORDER BY created_at DESC "
            "LIMIT $limit START $offset",
            {
                "doc_ref": doc_ref_obj,
                "limit": per_page,
                "offset": offset,
            },
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

    data_records: list[dict] = [
        r for r in (data_result or []) if isinstance(r, dict)
    ]

    items: list[ProcessingLogListItem] = []
    for record in data_records:
        entry_id_val = record.get("id")
        entry_id: str = ""
        if isinstance(entry_id_val, RecordID):
            entry_id = str(entry_id_val.id)
        elif isinstance(entry_id_val, str):
            entry_id = (
                entry_id_val.split(":", 1)[1]
                if ":" in entry_id_val
                else entry_id_val
            )

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
    db: AsyncWsSurrealConnection | None = app.state.db

    if db is None:
        logger.error("GET /documents/%s/tokens rejected — SurrealDB unavailable", document_id)
        raise HTTPException(
            status_code=503,
            detail="SurrealDB is not available. Please try again later.",
        )

    from surrealdb.data.types.record_id import RecordID

    doc_id_obj = RecordID("document", document_id)

    try:
        result = await db.query(
            "SELECT "
            "math::sum(prompt_tokens) as prompt_tokens, "
            "math::sum(completion_tokens) as completion_tokens, "
            "math::sum(total_tokens) as total_tokens, "
            "math::sum(cached_tokens) as cached_tokens, "
            "math::sum(cost) as total_cost, "
            "math::sum(duration_ms) as duration_ms, "
            "count() as record_count "
            "FROM llm_usage WHERE document = $doc GROUP ALL",
            {"doc": doc_id_obj},
        )
    except Exception as exc:
        logger.error("Failed to query token usage for %s: %s", document_id, exc)
        raise HTTPException(
            status_code=502,
            detail="Failed to query token usage.",
        ) from exc

    records: list[dict] = [r for r in (result or []) if isinstance(r, dict)]

    if not records or records[0].get("record_count", 0) == 0:
        logger.info("No token data for document %s", document_id)
        return DocumentTokenUsage(has_data=False)

    row = records[0]
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
            f"SELECT count() AS total FROM document WHERE {where_clause} GROUP ALL",
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

    # Batched token aggregation: one extra query for all documents on this page
    document_rids: list[RecordID] = []
    for record in data_records:
        doc_id_val = record.get("id")
        if isinstance(doc_id_val, RecordID):
            document_rids.append(doc_id_val)
        elif isinstance(doc_id_val, str):
            parts = doc_id_val.split(":", 1)
            doc_id = parts[1] if len(parts) > 1 else parts[0]
            document_rids.append(RecordID("document", doc_id))

    token_map: dict[str, dict] = {}
    if document_rids:
        try:
            token_result = await db.query(
                "SELECT document, "
                "math::sum(prompt_tokens) as prompt_tokens, "
                "math::sum(completion_tokens) as completion_tokens, "
                "math::sum(total_tokens) as total_tokens, "
                "math::sum(cached_tokens) as cached_tokens, "
                "math::sum(cost) as total_cost, "
                "math::sum(duration_ms) as duration_ms "
                "FROM llm_usage "
                "WHERE document INSIDE $docs "
                "GROUP BY document",
                {"docs": document_rids},
            )
            token_rows: list[dict] = [
                r for r in (token_result or []) if isinstance(r, dict)
            ]
            for row in token_rows:
                doc_ref = row.get("document")
                if doc_ref is not None:
                    token_map[str(doc_ref)] = row
        except Exception as exc:
            logger.warning("Failed to query batched token data: %s", exc)

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
                "SELECT count() AS total FROM document_chunk WHERE document = $doc_ref GROUP ALL",
                {"doc_ref": doc_ref_obj},
            )
            chunk_count = _parse_count(chunk_result)

            text_content = record.get("text_content", "") or ""
            twc = len(text_content.split()) if text_content.strip() else 0
        except Exception as exc:
            logger.warning("Failed to query counts for document %s: %s", doc_id, exc)

        token_data = token_map.get(f"document:{doc_id}", {})

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
# Clear document events endpoint
# =======================================================================


@router.delete(
    "/documents/{document_id}/events",
    response_model=EventsCleared,
)
async def clear_document_events(document_id: str) -> EventsCleared:
    """Clear all extraction results for a document and reset its status."""
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
        await db.query(
            "DELETE event_entity_link WHERE event IN ("
            "SELECT id FROM canonical_entity "
            "WHERE entity_type = 'event' AND properties.document_id = $doc_id"
            ")",
            {"doc_id": document_id},
        )

        await db.query(
            "DELETE document_event_log WHERE document = $doc_id",
            {"doc_id": doc_id_obj},
        )

        await db.query(
            "DELETE llm_usage WHERE document = $doc_id",
            {"doc_id": doc_id_obj},
        )

        await db.query(
            "DELETE document WHERE id = $doc_id",
            {"doc_id": doc_id_obj},
        )

        # Delete event-type canonical entities created for this document
        await db.query(
            "DELETE canonical_entity "
            "WHERE entity_type = 'event' AND properties.document_id = $doc_id",
            {"doc_id": document_id},
        )

        orphaned = 0
        if affected_ce_rids:
            deduplicated = list({str(r) for r in affected_ce_rids})
            params = {f"ce_{i}": rid for i, rid in enumerate(affected_ce_rids)}
            rid_list = ", ".join(f"$ce_{i}" for i in range(len(affected_ce_rids)))

            orphaned = len(deduplicated)

            await db.query(
                f"DELETE canonical_entity WHERE id IN [{rid_list}]",
                params,
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
