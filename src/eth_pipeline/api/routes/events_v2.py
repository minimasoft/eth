from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from eth_pipeline.api import app
from eth_pipeline.api.models import (
    EventListV2Response,
    EventV2ListItem,
)
from eth_pipeline.db import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Events V2"])


@router.get("/events", response_model=EventListV2Response)
async def list_events_v2(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    search: str | None = Query(None),
    document: str | None = Query(None),
    sort: str | None = Query("time_start"),
    order: str | None = Query("desc"),
) -> EventListV2Response:
    """List v7 events with pagination, filter, search, and sort."""
    offset = (page - 1) * per_page

    where_parts: list[str] = ["TRUE"]
    params: list[object] = []

    if search:
        where_parts.append(f"ev.title ILIKE ${len(params) + 1}")
        params.append(f"%{search}%")

    if document:
        where_parts.append(f"ev.document_id = ${len(params) + 1}")
        params.append(document)

    where_clause = " AND ".join(where_parts)

    allowed_sorts = {"time_start", "time_end", "created_at", "title"}
    sort_col = sort if sort in allowed_sorts else "time_start"
    sort_order = "DESC" if (order or "desc").lower().startswith("desc") else "ASC"

    try:
        async with get_db() as conn:
            count_sql = f"SELECT COUNT(*) AS total FROM event_v2 ev WHERE {where_clause}"
            count_row = await conn.fetchrow(count_sql, *params)
            total = count_row["total"] if count_row else 0

            if total > 0:
                data_sql = (
                    f"SELECT ev.*, "
                    f"d.id AS doc_id, d.filename AS doc_filename, "
                    f"el.name AS location_name, "
                    f"(SELECT COUNT(*) FROM event_participant_v2 ep WHERE ep.event_id = ev.id) AS participant_count, "
                    f"(SELECT COUNT(*) FROM event_ref er WHERE er.event_id = ev.id) AS reference_count "
                    f"FROM event_v2 ev "
                    f"LEFT JOIN document d ON d.id = ev.document_id "
                    f"LEFT JOIN event_location el ON el.event_id = ev.id "
                    f"WHERE {where_clause} "
                    f"ORDER BY ev.{sort_col} {sort_order} "
                    f"LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}"
                )
                params.append(per_page)
                params.append(offset)
                data_result = await conn.fetch(data_sql, *params)
            else:
                data_result = []
    except Exception as exc:
        logger.error("Failed to query v7 events: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Failed to query database.",
        ) from exc

    if total == 0:
        pages = 0
    else:
        pages = max(1, (total + per_page - 1) // per_page)

    items: list[EventV2ListItem] = []
    for r in data_result:
        items.append(EventV2ListItem(
            event_id=str(r["id"]),
            title=r.get("title", ""),
            description=r.get("description", ""),
            time_start=r["time_start"].isoformat() if r.get("time_start") else None,
            time_end=r["time_end"].isoformat() if r.get("time_end") else None,
            time_precision=r.get("time_precision"),
            location_name=r.get("location_name"),
            participant_count=r.get("participant_count", 0),
            reference_count=r.get("reference_count", 0),
            document_id=str(r["doc_id"]) if r.get("doc_id") else None,
            document_filename=r.get("doc_filename"),
            extraction_confidence=float(r.get("extraction_confidence", 1.0)),
            created_at=r["created_at"].isoformat() if r.get("created_at") else None,
        ))

    logger.info(
        "Listed v7 events (page=%d, per_page=%d, search=%s) — %d items of %d total",
        page, per_page, search or "", len(items), total,
    )

    return EventListV2Response(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
    )
