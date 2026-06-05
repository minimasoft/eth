from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from eth_pipeline.api import app
from eth_pipeline.api.models import EventListItem, EventListResponse
from eth_pipeline.db import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Events"])


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
    """List extracted events with pagination and filtering."""
    offset = (page - 1) * per_page

    where_parts: list[str] = ["TRUE"]
    params: list[object] = []

    if search:
        where_parts.append(f"e.que_paso ILIKE ${len(params) + 1}")
        params.append(f"%{search}%")

    if document:
        where_parts.append(f"e.document = ${len(params) + 1}")
        params.append(document)

    if date_from:
        where_parts.append(f"e.time_window->>'start' >= ${len(params) + 1}")
        params.append(date_from)

    if date_to:
        where_parts.append(f"e.time_window->>'end' <= ${len(params) + 1}")
        params.append(date_to)

    if entity_type or entity_id:
        if entity_type:
            where_parts.append(
                f"e.id IN ("
                f"SELECT ep.in_event FROM event_participant ep "
                f"JOIN canonical_entity ce ON ce.id = ep.out_entity "
                f"WHERE ce.entity_type = ${len(params) + 1}"
                f")"
            )
            params.append(entity_type)
        if entity_id:
            where_parts.append(
                f"e.id IN ("
                f"SELECT ep.in_event FROM event_participant ep "
                f"WHERE ep.out_entity = ${len(params) + 1}"
                f")"
            )
            params.append(entity_id)

    where_clause = " AND ".join(where_parts)

    try:
        async with get_db() as db:
            count_sql = f"SELECT COUNT(*) AS total FROM event e WHERE {where_clause}"
            count_row = await db.fetchrow(count_sql, *params)
            total = count_row["total"] if count_row else 0

            if total > 0:
                data_sql = (
                    f"SELECT e.*, "
                    f"d.id AS doc_id, d.filename AS doc_filename, "
                    f"ce.name AS loc_place_name, "
                    f"(SELECT COUNT(*) FROM event_participant ep WHERE ep.in_event = e.id) AS participant_count, "
                    f"(SELECT COUNT(*) FROM reference r WHERE r.event = e.id) AS reference_count "
                    f"FROM event e "
                    f"LEFT JOIN document d ON d.id = e.document "
                    f"LEFT JOIN canonical_entity ce ON ce.id = e.location_place_id "
                    f"WHERE {where_clause} "
                    f"ORDER BY e.created_at DESC "
                    f"LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}"
                )
                params.append(per_page)
                params.append(offset)
                data_result = await db.fetch(data_sql, *params)
            else:
                data_result = []
    except Exception as exc:
        logger.error("Failed to query events: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Failed to query database.",
        ) from exc

    if total == 0:
        pages = 0
    else:
        pages = max(1, (total + per_page - 1) // per_page)

    items: list[EventListItem] = []
    for record in data_result:
        items.append(EventListItem(
            event_id=str(record["id"]),
            que_paso=record.get("que_paso", ""),
            espacio=record.get("espacio"),
            tiempo=record.get("tiempo"),
            humanos=record.get("humanos"),
            objetos=record.get("objetos"),
            time_window=record.get("time_window"),
            location_point=record.get("location_point"),
            location_place_name=record.get("loc_place_name"),
            participant_count=record.get("participant_count", 0),
            reference_count=record.get("reference_count", 0),
            document_id=str(record["doc_id"]) if record.get("doc_id") else None,
            document_filename=record.get("doc_filename"),
            extraction_confidence=float(record.get("extraction_confidence", 1.0)),
            created_at=(
                record["created_at"].isoformat()
                if record.get("created_at") and hasattr(record["created_at"], "isoformat")
                else str(record["created_at"]) if record.get("created_at") else None
            ),
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
