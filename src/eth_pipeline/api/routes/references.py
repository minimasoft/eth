from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from eth_pipeline.api import app
from eth_pipeline.api.models import ReferenceListItem, ReferenceListResponse
from eth_pipeline.db import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["References"])


@router.get("/references", response_model=ReferenceListResponse)
async def list_references(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    search: str | None = Query(None),
    reference_type: str | None = Query(None),
    document: str | None = Query(None),
    event_element: str | None = Query(None),
    entity_type: str | None = Query(None),
    entity_id: str | None = Query(None),
) -> ReferenceListResponse:
    """List verbatim references with pagination, search, and filtering."""
    offset = (page - 1) * per_page

    where_parts: list[str] = ["TRUE"]
    params: list[object] = []

    if search:
        where_parts.append(f"r.verbatim_text ILIKE ${len(params) + 1}")
        params.append(f"%{search}%")

    if reference_type:
        where_parts.append(f"r.reference_type = ${len(params) + 1}")
        params.append(reference_type)

    if document:
        where_parts.append(f"e.document = ${len(params) + 1}")
        params.append(document)

    if event_element:
        where_parts.append(f"r.element_field = ${len(params) + 1}")
        params.append(event_element)

    if entity_type:
        where_parts.append(f"ce.entity_type = ${len(params) + 1}")
        params.append(entity_type)

    if entity_id:
        where_parts.append(f"r.canonical_entity = ${len(params) + 1}")
        params.append(entity_id)

    where_clause = " AND ".join(where_parts)

    try:
        async with get_db() as db:
            count_sql = (
                f"SELECT COUNT(*) AS total FROM reference r "
                f"LEFT JOIN event e ON e.id = r.event "
                f"LEFT JOIN canonical_entity ce ON ce.id = r.canonical_entity "
                f"WHERE {where_clause}"
            )
            count_row = await db.fetchrow(count_sql, *params)
            total = count_row["total"] if count_row else 0

            if total > 0:
                data_sql = (
                    f"SELECT r.*, "
                    f"e.id AS ev_id, e.que_paso AS ev_que_paso, "
                    f"d.id AS doc_id, d.filename AS doc_filename, "
                    f"d.text_content AS doc_text_content, "
                    f"ce.id AS ce_id, ce.name AS ce_name, ce.entity_type AS ce_type "
                    f"FROM reference r "
                    f"LEFT JOIN event e ON e.id = r.event "
                    f"LEFT JOIN document d ON d.id = e.document "
                    f"LEFT JOIN canonical_entity ce ON ce.id = r.canonical_entity "
                    f"WHERE {where_clause} "
                    f"ORDER BY r.created_at DESC "
                    f"LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}"
                )
                params.append(per_page)
                params.append(offset)
                data_result = await db.fetch(data_sql, *params)
            else:
                data_result = []
    except Exception as exc:
        logger.error("Failed to query references: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Failed to query database.",
        ) from exc

    if total == 0:
        pages = 0
    else:
        pages = max(1, (total + per_page - 1) // per_page)

    items: list[ReferenceListItem] = []
    for record in data_result:
        # Compute context_excerpt from document text_content and span data
        context_excerpt = None
        doc_text = record.get("doc_text_content")
        span_start = record.get("span_start")
        span_end = record.get("span_end")
        if doc_text and span_start is not None and span_end is not None:
            ctx_before = 80
            ctx_after = 80
            start = max(0, span_start - ctx_before)
            end = min(len(doc_text), span_end + ctx_after)
            excerpt = doc_text[start:end]
            # If the excerpt doesn't start at the beginning of text, prefix with "..."
            if start > 0:
                excerpt = "..." + excerpt
            # If the excerpt doesn't end at the end of text, suffix with "..."
            if end < len(doc_text):
                excerpt = excerpt + "..."
            context_excerpt = excerpt

        items.append(ReferenceListItem(
            reference_id=str(record["id"]),
            reference_type=record.get("reference_type", ""),
            verbatim_text=record.get("verbatim_text", ""),
            span_start=record.get("span_start"),
            span_end=record.get("span_end"),
            page_number=record.get("page_number"),
            page_offset_start=record.get("page_offset_start"),
            page_offset_end=record.get("page_offset_end"),
            context_excerpt=context_excerpt,
            element_field=record.get("element_field"),
            reference_index=record.get("reference_index"),
            resolution_confidence=record.get("resolution_confidence"),
            event_que_paso=record.get("ev_que_paso"),
            event_id=str(record["ev_id"]) if record.get("ev_id") else None,
            document_filename=record.get("doc_filename"),
            document_id=str(record["doc_id"]) if record.get("doc_id") else None,
            canonical_entity_name=record.get("ce_name"),
            canonical_entity_id=str(record["ce_id"]) if record.get("ce_id") else None,
            canonical_entity_type=record.get("ce_type"),
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
