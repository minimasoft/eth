"""API tests for the geo endpoint (GET /geo/events) — Mapa tab backend.

Follows the mimic-the-SQL pattern of tests/test_event_api.py: the suite does
not exercise routes over HTTP; instead each test replays the same parameterized
SQL the route handler runs, against the isolated test database.
"""

from __future__ import annotations

import logging

import asyncpg
import pytest

from eth_pipeline.api.routes.geo import parse_bbox

logger = logging.getLogger(__name__)


async def fetch_geo_events(
    conn: asyncpg.Connection,
    bbox: tuple[float, float, float, float] | None = None,
    limit: int = 500,
) -> list[asyncpg.Record]:
    """Replay the exact parameterized SQL used by GET /geo/events."""
    where_parts: list[str] = ["el.lat IS NOT NULL", "el.lon IS NOT NULL"]
    params: list[object] = []

    if bbox is not None:
        b_min_lon, b_min_lat, b_max_lon, b_max_lat = bbox
        where_parts.append(f"el.lat BETWEEN ${len(params) + 1} AND ${len(params) + 2}")
        params.extend([b_min_lat, b_max_lat])
        where_parts.append(f"el.lon BETWEEN ${len(params) + 1} AND ${len(params) + 2}")
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
    return await conn.fetch(data_sql, *params)


CDMX_BBOX = (-99.60, 19.00, -98.60, 19.70)  # min_lon, min_lat, max_lon, max_lat
EUROPE_BBOX = (-10.0, 35.0, 30.0, 60.0)


class TestGeoEventsQuery:
    """Tests for MAP-01: GET /geo/events (geolocated pairs, bbox filter, limit)."""

    @pytest.mark.asyncio
    async def test_bbox_filters_outside(
        self, db_connection: asyncpg.Connection, v7_test_event: dict
    ) -> None:
        """Point inside the bbox appears; bbox over Europe excludes it."""
        located = await db_connection.execute(
            "UPDATE event_location SET lat = $2, lon = $3 WHERE id = $1",
            "test-events-v7-loc-001", 19.4326, -99.1332,
        )
        assert located == "UPDATE 1", "Fixture location row should have been updated"

        inside = await fetch_geo_events(db_connection, bbox=CDMX_BBOX)
        assert len(inside) >= 1, "Expected CDMX point inside CDMX bbox"
        assert any(
            r["id"] == "test-events-v7-loc-001" for r in inside
        ), "Geolocated fixture location should match the bbox query"
        for r in inside:
            assert CDMX_BBOX[1] <= r["lat"] <= CDMX_BBOX[3], "lat outside bbox"
            assert CDMX_BBOX[0] <= r["lon"] <= CDMX_BBOX[2], "lon outside bbox"

        outside = await fetch_geo_events(db_connection, bbox=EUROPE_BBOX)
        assert not any(
            r["id"] == "test-events-v7-loc-001" for r in outside
        ), "CDMX point must not appear inside a Europe bbox"

    @pytest.mark.asyncio
    async def test_null_coords_excluded(
        self, db_connection: asyncpg.Connection, v7_test_event: dict
    ) -> None:
        """A location with NULL lat/lon never matches the geo query, even inside the bbox."""
        event_id = v7_test_event["event_id"]
        await db_connection.execute(
            "INSERT INTO event_location (id, event_id, name, location_type) "
            "VALUES ($1, $2, $3, $4) "
            "ON CONFLICT (id) DO NOTHING",
            "test-events-v7-loc-002-null",
            event_id,
            "Lugar sin coordenadas",
            "city",
        )
        try:
            rows = await fetch_geo_events(db_connection, bbox=CDMX_BBOX)
            ids = [r["id"] for r in rows]
            assert "test-events-v7-loc-002-null" not in ids, (
                "NULL-coords location must be excluded from geo results"
            )
        finally:
            await db_connection.execute(
                "DELETE FROM event_location WHERE id = $1",
                "test-events-v7-loc-002-null",
            )

    @pytest.mark.asyncio
    async def test_limit_respected(
        self, db_connection: asyncpg.Connection, v7_test_event: dict
    ) -> None:
        """LIMIT caps the number of returned rows."""
        event_id = v7_test_event["event_id"]
        await db_connection.execute(
            "UPDATE event_location SET lat = $2, lon = $3 WHERE id = $1",
            "test-events-v7-loc-001", 19.4326, -99.1332,
        )
        await db_connection.execute(
            "INSERT INTO event_location (id, event_id, name, location_type, lat, lon) "
            "VALUES ($1, $2, $3, $4, $5, $6) "
            "ON CONFLICT (id) DO NOTHING",
            "test-events-v7-loc-003-geo",
            event_id,
            "Segundo lugar",
            "city",
            19.50, -99.10,
        )
        try:
            all_rows = await fetch_geo_events(db_connection, bbox=CDMX_BBOX, limit=500)
            assert len(all_rows) >= 2, "Expected 2 geolocated rows inside bbox"

            capped = await fetch_geo_events(db_connection, bbox=CDMX_BBOX, limit=1)
            assert len(capped) == 1, "LIMIT 1 must cap the result to a single row"
        finally:
            await db_connection.execute(
                "DELETE FROM event_location WHERE id = $1",
                "test-events-v7-loc-003-geo",
            )


class TestParseBbox:
    """Unit tests for MAP-01: parse_bbox validation (no DB, no HTTP)."""

    def test_valid_bbox_returns_tuple(self) -> None:
        result = parse_bbox(-99.60, 19.00, -98.60, 19.70)
        assert result == (-99.60, 19.00, -98.60, 19.70)

    def test_no_bbox_returns_none(self) -> None:
        assert parse_bbox(None, None, None, None) is None

    @pytest.mark.parametrize(
        "missing",
        [
            (None, 19.0, -98.6, 19.7),   # min_lon missing
            (-99.6, None, -98.6, 19.7),  # min_lat missing
            (-99.6, 19.0, None, 19.7),   # max_lon missing
            (-99.6, 19.0, -98.6, None),  # max_lat missing
        ],
    )
    def test_partial_bbox_raises(self, missing: tuple) -> None:
        with pytest.raises(ValueError, match="together"):
            parse_bbox(*missing)

    def test_min_greater_than_max_raises(self) -> None:
        with pytest.raises(ValueError, match="min_lon"):
            parse_bbox(-98.0, 19.0, -99.0, 19.7)
        with pytest.raises(ValueError, match="min_lat"):
            parse_bbox(-99.6, 19.8, -98.6, 19.7)

    def test_lat_out_of_range_raises(self) -> None:
        with pytest.raises(ValueError, match="lat"):
            parse_bbox(-99.6, 95.0, -98.6, 120.0)

    def test_lon_out_of_range_raises(self) -> None:
        with pytest.raises(ValueError, match="lon"):
            parse_bbox(-200.0, 19.0, 200.0, 19.7)
