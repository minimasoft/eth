from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from surrealdb import AsyncWsSurrealConnection

from eth_pipeline.api import app

from eth_pipeline.api.models import ReferenceListItem, ReferenceListResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["References"])


# =======================================================================
# List references (paginated)
# =======================================================================


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
    """List verbatim references with pagination, search, and filtering.

    New v6.0 filters: document (ID), event_element (tiempo/humanos/espacio/objetos),
    entity_type (place/person/object), entity_id (canonical entity ID).
    """
    db: AsyncWsSurrealConnection | None = app.state.db

    if db is None:
        logger.error("GET /references rejected — SurrealDB unavailable")
        raise HTTPException(
            status_code=503,
            detail="SurrealDB is not available. Please try again later.",
        )

    offset = (page - 1) * per_page

    where_parts: list[str] = ["1 = 1"]
    query_params: dict[str, object] = {}

    if search:
        where_parts.append("verbatim_text LIKE $search")
        query_params["search"] = f"%{search}%"

    if reference_type:
        where_parts.append("reference_type = $ref_type")
        query_params["ref_type"] = reference_type

    if document:
        where_parts.append("event.document = $doc_rid")
        from surrealdb.data.types.record_id import RecordID
        query_params["doc_rid"] = RecordID("document", document)

    if event_element:
        where_parts.append("element_field = $ef")
        query_params["ef"] = event_element

    if entity_type:
        where_parts.append("canonical_entity.entity_type = $ce_type")
        query_params["ce_type"] = entity_type

    if entity_id:
        where_parts.append("canonical_entity = $ce_rid")
        from surrealdb.data.types.record_id import RecordID
        query_params["ce_rid"] = RecordID("canonical_entity", entity_id)

    where_clause = " AND ".join(where_parts)
    query_params["per_page"] = per_page
    query_params["offset"] = offset

    try:
        count_result = await db.query(
            f"SELECT count() AS total FROM reference WHERE {where_clause} GROUP ALL",
            query_params,
        )
    except Exception as exc:
        logger.error("Failed to count references: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Failed to query database.",
        ) from exc

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

            doc_data = event_data.get("document")
            if isinstance(doc_data, dict):
                document_filename = doc_data.get("filename")
                doc_id_val = doc_data.get("id")
                if isinstance(doc_id_val, RecordID):
                    document_id = doc_id_val.id
                elif isinstance(doc_id_val, str):
                    document_id = doc_id_val.split(":", 1)[1] if ":" in doc_id_val else doc_id_val

        canonical_entity_data = record.get("canonical_entity")
        canonical_entity_name: str | None = None
        canonical_entity_id: str | None = None
        canonical_entity_type: str | None = None
        if isinstance(canonical_entity_data, dict):
            canonical_entity_name = canonical_entity_data.get("name")
            ce_id_val = canonical_entity_data.get("id")
            if isinstance(ce_id_val, RecordID):
                canonical_entity_id = ce_id_val.id
            elif isinstance(ce_id_val, str):
                canonical_entity_id = ce_id_val.split(":", 1)[1] if ":" in ce_id_val else ce_id_val
            canonical_entity_type = canonical_entity_data.get("entity_type")

        items.append(ReferenceListItem(
            reference_id=reference_id,
            reference_type=record.get("reference_type", ""),
            verbatim_text=record.get("verbatim_text", ""),
            span_start=record.get("span_start"),
            span_end=record.get("span_end"),
            page_number=record.get("page_number"),
            element_field=record.get("element_field"),
            reference_index=record.get("reference_index"),
            resolution_confidence=record.get("resolution_confidence"),
            event_que_paso=event_que_paso,
            event_id=event_id,
            document_filename=document_filename,
            document_id=document_id,
            canonical_entity_name=canonical_entity_name,
            canonical_entity_id=canonical_entity_id,
            canonical_entity_type=canonical_entity_type,
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
