from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from eth_pipeline.api import app
from eth_pipeline.api.models import GeoEventItem, GeoEventsResponse
from eth_pipeline.db import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Map"])


def parse_bbox(
    min_lon: float | None,
    min_lat: float | None,
    max_lon: float | None,
    max_lat: float | None,
) -> tuple[float, float, float, float] | None:
    """Validate an optional WGS84 bounding box.

    All-or-none: if any coordinate is provided, all four must be.
    Ranges: lat in [-90, 90], lon in [-180, 180], min <= max.

    Returns None when no bbox was supplied (all four arguments None).
    Raises ValueError with a user-safe message on any violation so the
    route handler can map it to HTTP 400 without leaking internals.
    """
    provided = [min_lon, min_lat, max_lon, max_lat]
    if any(v is not None for v in provided) and any(v is None for v in provided):
        raise ValueError("bbox requires min_lon, min_lat, max_lon, max_lat together")

    if min_lon is None and min_lat is None and max_lon is None and max_lat is None:
        return None

    try:
        min_lon_f = float(min_lon)  # type: ignore[arg-type]
        min_lat_f = float(min_lat)  # type: ignore[arg-type]
        max_lon_f = float(max_lon)  # type: ignore[arg-type]
        max_lat_f = float(max_lat)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError("bbox coordinates must be valid numbers") from exc

    if not (-180.0 <= min_lon_f <= 180.0) or not (-180.0 <= max_lon_f <= 180.0):
        raise ValueError("lon must be within [-180, 180]")
    if not (-90.0 <= min_lat_f <= 90.0) or not (-90.0 <= max_lat_f <= 90.0):
        raise ValueError("lat must be within [-90, 90]")
    if min_lon_f > max_lon_f:
        raise ValueError("min_lon must be <= max_lon")
    if min_lat_f > max_lat_f:
        raise ValueError("min_lat must be <= max_lat")

    return (min_lon_f, min_lat_f, max_lon_f, max_lat_f)


@router.get("/geo/events", response_model=GeoEventsResponse)
async def list_geo_events(
    min_lon: float | None = Query(None),
    min_lat: float | None = Query(None),
    max_lon: float | None = Query(None),
    max_lat: float | None = Query(None),
    limit: int = Query(500, ge=1, le=2000),
) -> GeoEventsResponse:
    """List geolocated event-location pairs, optionally bounded by a bbox."""
    try:
        bbox = parse_bbox(min_lon, min_lat, max_lon, max_lat)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    where_parts: list[str] = ["el.lat IS NOT NULL", "el.lon IS NOT NULL"]
    params: list[object] = []

    if bbox is not None:
        b_min_lon, b_min_lat, b_max_lon, b_max_lat = bbox
        where_parts.append(
            f"el.lat BETWEEN ${len(params) + 1} AND ${len(params) + 2}"
        )
        params.extend([b_min_lat, b_max_lat])
        where_parts.append(
            f"el.lon BETWEEN ${len(params) + 1} AND ${len(params) + 2}"
        )
        params.extend([b_min_lon, b_max_lon])

    where_clause = " AND ".join(where_parts)

    data_sql = (
        "SELECT el.id, el.name, el.location_type, el.lat, el.lon, "
        "ev.id AS event_id, ev.title, ev.time_start, ev.time_end, ev.time_precision, "
        "d.id AS doc_id, d.filename AS doc_filename "
        "FROM event_location el "
        "JOIN event_v2 ev ON ev.id = el.event_id "
        "LEFT JOIN document d ON d.id = ev.document_id "
        f"WHERE {where_clause} "
        "ORDER BY ev.time_start DESC NULLS LAST "
        f"LIMIT ${len(params) + 1}"
    )
    params.append(limit)

    try:
        async with get_db() as conn:
            rows = await conn.fetch(data_sql, *params)
    except Exception as exc:
        logger.error("Failed to query geo events: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Failed to query database.",
        ) from exc

    items: list[GeoEventItem] = []
    for r in rows:
        items.append(GeoEventItem(
            event_id=str(r["event_id"]),
            title=r.get("title", ""),
            time_start=r["time_start"].isoformat() if r.get("time_start") else None,
            time_end=r["time_end"].isoformat() if r.get("time_end") else None,
            time_precision=r.get("time_precision"),
            lat=float(r["lat"]),
            lon=float(r["lon"]),
            location_id=str(r["id"]),
            location_name=r.get("name", ""),
            location_type=r.get("location_type"),
            document_id=str(r["doc_id"]) if r.get("doc_id") else None,
            document_filename=r.get("doc_filename"),
        ))

    logger.info(
        "Listed geo events (bbox=%s, limit=%d) — %d items",
        bbox is not None, limit, len(items),
    )

    return GeoEventsResponse(
        total=len(items),
        items=items,
    )
