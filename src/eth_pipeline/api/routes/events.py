from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from surrealdb import AsyncWsSurrealConnection

from eth_pipeline.api import app

from eth_pipeline.api.models import EventListItem, EventListResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Events"])


# =======================================================================
# List events (paginated)
# =======================================================================


@router.get("/events", response_model=EventListResponse)
async def list_events(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    search: str | None = Query(None),
    document: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    entity_type: str | None = Query(None),
    entity_id: str | None = Query(None),
) -> EventListResponse:
    """List extracted events with pagination and filtering.

    v6.0: supports date_range, entity filtering, and structured event fields.
    """
    db: AsyncWsSurrealConnection | None = app.state.db

    if db is None:
        logger.error("GET /events rejected — SurrealDB unavailable")
        raise HTTPException(
            status_code=503,
            detail="SurrealDB is not available. Please try again later.",
        )

    offset = (page - 1) * per_page

    where_parts: list[str] = ["1 = 1"]
    query_params: dict[str, object] = {}

    if search:
        where_parts.append("que_paso LIKE $search")
        query_params["search"] = f"%{search}%"

    if document:
        from surrealdb.data.types.record_id import RecordID
        where_parts.append("document = $doc_rid")
        query_params["doc_rid"] = RecordID("document", document)

    if date_from:
        where_parts.append("time_window.start >= $date_from")
        query_params["date_from"] = date_from

    if date_to:
        where_parts.append("time_window.end <= $date_to")
        query_params["date_to"] = date_to

    if entity_type or entity_id:
        from surrealdb.data.types.record_id import RecordID
        if entity_type:
            where_parts.append(
                "id IN (SELECT VALUE in FROM event_participant "
                "WHERE out.entity_type = $ent_type)"
            )
            query_params["ent_type"] = entity_type
        if entity_id:
            where_parts.append(
                "id IN (SELECT VALUE in FROM event_participant "
                "WHERE out = $ent_rid)"
            )
            query_params["ent_rid"] = RecordID("canonical_entity", entity_id)

    where_clause = " AND ".join(where_parts)
    query_params["per_page"] = per_page
    query_params["offset"] = offset

    try:
        count_result = await db.query(
            f"SELECT count() AS total FROM event WHERE {where_clause} GROUP ALL",
            query_params,
        )
    except Exception as exc:
        logger.error("Failed to count events: %s", exc)
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
            f"SELECT *, "
            "count(<-event_participant) AS participant_count, "
            "count(<-reference) AS reference_count "
            f"FROM event WHERE {where_clause} "
            "ORDER BY created_at DESC LIMIT $per_page START $offset "
            "FETCH document, location_place_id",
            query_params,
        )
    except Exception as exc:
        logger.error("Failed to query events: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Failed to query database.",
        ) from exc

    from surrealdb.data.types.record_id import RecordID

    data_records: list[dict] = [
        r for r in (data_result or []) if isinstance(r, dict)
    ]

    items: list[EventListItem] = []
    for record in data_records:
        ev_id_val = record.get("id")
        event_id: str = ""
        if isinstance(ev_id_val, RecordID):
            event_id = ev_id_val.id
        elif isinstance(ev_id_val, str):
            event_id = ev_id_val.split(":", 1)[1] if ":" in ev_id_val else ev_id_val

        doc_data = record.get("document")
        document_id: str | None = None
        document_filename: str | None = None
        if isinstance(doc_data, dict):
            doc_id_val = doc_data.get("id")
            if isinstance(doc_id_val, RecordID):
                document_id = doc_id_val.id
            elif isinstance(doc_id_val, str):
                document_id = doc_id_val.split(":", 1)[1] if ":" in doc_id_val else doc_id_val
            document_filename = doc_data.get("filename")

        loc_data = record.get("location_place_id")
        location_place_name: str | None = None
        if isinstance(loc_data, dict):
            location_place_name = loc_data.get("name")

        pcount = record.get("participant_count")
        rcount = record.get("reference_count")

        items.append(EventListItem(
            event_id=event_id,
            que_paso=record.get("que_paso", ""),
            espacio=record.get("espacio"),
            tiempo=record.get("tiempo"),
            humanos=record.get("humanos"),
            objetos=record.get("objetos"),
            time_window=record.get("time_window"),
            location_point=record.get("location_point"),
            location_place_name=location_place_name,
            participant_count=int(pcount) if pcount else 0,
            reference_count=int(rcount) if rcount else 0,
            document_id=document_id,
            document_filename=document_filename,
            extraction_confidence=float(record.get("extraction_confidence", 1.0)),
            created_at=record.get("created_at"),
        ))

    logger.info(
        "Listed events (page=%d, per_page=%d, search=%s) — %d items of %d total",
        page, per_page, search or "", len(items), total,
    )

    return EventListResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
    )
