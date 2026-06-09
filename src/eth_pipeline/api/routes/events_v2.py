from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from eth_pipeline.api import app
from eth_pipeline.api.models import (
    EventListV2Response,
    EventLocationDetail,
    EventParticipantDetail,
    EventRefDetail,
    EventV2DetailResponse,
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


@router.get("/events/{event_id}", response_model=EventV2DetailResponse)
async def get_event_v2_detail(event_id: str) -> EventV2DetailResponse:
    """Retrieve full v7 event detail with locations, participants, and references."""

    try:
        async with get_db() as conn:
            event_row = await conn.fetchrow(
                "SELECT ev.*, d.id AS doc_id, d.filename AS doc_filename "
                "FROM event_v2 ev "
                "LEFT JOIN document d ON d.id = ev.document_id "
                "WHERE ev.id = $1",
                event_id,
            )

            if event_row is None:
                logger.warning("Event %s not found", event_id)
                raise HTTPException(
                    status_code=404,
                    detail=f"Event not found: {event_id}",
                )

            locations = await conn.fetch(
                "SELECT id, name, location_type, geom "
                "FROM event_location "
                "WHERE event_id = $1 "
                "ORDER BY id",
                event_id,
            )

            participants = await conn.fetch(
                "SELECT id, name, role, confidence "
                "FROM event_participant_v2 "
                "WHERE event_id = $1 "
                "ORDER BY id",
                event_id,
            )

            references = await conn.fetch(
                "SELECT id, reference_type, verbatim_text, span_start, span_end, chunk_index "
                "FROM event_ref "
                "WHERE event_id = $1 "
                "ORDER BY chunk_index, span_start",
                event_id,
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to query event detail for %s: %s", event_id, exc)
        raise HTTPException(
            status_code=502,
            detail="Failed to query database.",
        ) from exc

    logger.info(
        "Event detail for %s — %d locations, %d participants, %d references",
        event_id, len(locations), len(participants), len(references),
    )

    return EventV2DetailResponse(
        event_id=str(event_row["id"]),
        title=event_row.get("title", ""),
        description=event_row.get("description", ""),
        time_start=event_row["time_start"].isoformat() if event_row.get("time_start") else None,
        time_end=event_row["time_end"].isoformat() if event_row.get("time_end") else None,
        time_precision=event_row.get("time_precision"),
        extraction_confidence=float(event_row.get("extraction_confidence", 1.0)),
        document_id=str(event_row["doc_id"]) if event_row.get("doc_id") else None,
        document_filename=event_row.get("doc_filename"),
        locations=[
            EventLocationDetail(
                location_id=str(loc["id"]),
                name=loc["name"],
                location_type=loc.get("location_type"),
                geom=loc.get("geom"),
            )
            for loc in locations
        ],
        participants=[
            EventParticipantDetail(
                participant_id=str(p["id"]),
                name=p["name"],
                role=p.get("role", ""),
                confidence=float(p["confidence"]) if p.get("confidence") else None,
            )
            for p in participants
        ],
        references=[
            EventRefDetail(
                reference_id=str(r["id"]),
                reference_type=r["reference_type"],
                verbatim_text=r["verbatim_text"],
                span_start=r.get("span_start"),
                span_end=r.get("span_end"),
                chunk_index=r.get("chunk_index"),
            )
            for r in references
        ],
        created_at=event_row["created_at"].isoformat() if event_row.get("created_at") else None,
        updated_at=event_row["updated_at"].isoformat() if event_row.get("updated_at") else None,
    )
