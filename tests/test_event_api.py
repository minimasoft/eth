"""API tests for v7 event endpoints (Phase 36)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import asyncpg
import pytest

logger = logging.getLogger(__name__)


class TestEventListV2:
    """Tests for API-01: GET /events (paginated list with filter/search/sort)."""

    @pytest.mark.asyncio
    async def test_pagination_envelope(
        self, db_connection: asyncpg.Connection, v7_test_event: dict
    ) -> None:
        """Query event_v2 with COUNT + SELECT using LIMIT/OFFSET, verify pagination envelope."""
        count_row = await db_connection.fetchrow(
            "SELECT COUNT(*) AS total FROM event_v2 ev WHERE TRUE"
        )
        total = count_row["total"] if count_row else 0
        assert total >= 1, "Expected at least 1 event from fixture"

        rows = await db_connection.fetch(
            "SELECT ev.* FROM event_v2 ev WHERE TRUE "
            "ORDER BY ev.time_start DESC LIMIT $1 OFFSET $2",
            20, 0,
        )
        assert len(rows) >= 1, "Expected at least 1 event row in data query"

        row = rows[0]
        expected_columns = [
            "id", "title", "description", "time_start", "time_end",
            "time_precision", "extraction_confidence", "document_id",
            "created_at", "updated_at",
        ]
        for col in expected_columns:
            assert col in row.keys(), f"Column '{col}' missing from event_v2 row"

        pages = max(1, (total + 20 - 1) // 20)
        assert pages >= 1

    @pytest.mark.asyncio
    async def test_filter_by_document(
        self, db_connection: asyncpg.Connection, v7_test_event: dict
    ) -> None:
        """Verify WHERE ev.document_id = $1 filters correctly."""
        doc_id = v7_test_event["document_id"]

        count_row = await db_connection.fetchrow(
            "SELECT COUNT(*) AS total FROM event_v2 ev WHERE ev.document_id = $1",
            doc_id,
        )
        total = count_row["total"] if count_row else 0
        assert total >= 1, "Expected at least 1 event matching document filter"

        rows = await db_connection.fetch(
            "SELECT ev.* FROM event_v2 ev WHERE ev.document_id = $1 "
            "ORDER BY ev.time_start DESC LIMIT $2 OFFSET $3",
            doc_id, 20, 0,
        )
        for row in rows:
            assert row["document_id"] == doc_id, (
                f"Row document_id {row['document_id']} does not match filter {doc_id}"
            )

        neg_row = await db_connection.fetchrow(
            "SELECT COUNT(*) AS total FROM event_v2 ev WHERE ev.document_id = $1",
            "nonexistent-id",
        )
        neg_total = neg_row["total"] if neg_row else 0
        assert neg_total == 0, "Expected 0 results for nonexistent document_id filter"

    @pytest.mark.asyncio
    async def test_search_by_title(
        self, db_connection: asyncpg.Connection, v7_test_event: dict
    ) -> None:
        """Verify ILIKE search matches seeded event title."""
        match_row = await db_connection.fetchrow(
            "SELECT COUNT(*) AS total FROM event_v2 ev WHERE ev.title ILIKE $1",
            "%Reunión%",
        )
        match_total = match_row["total"] if match_row else 0
        assert match_total >= 1, "Expected at least 1 event matching ILIKE '%Reunión%'"

        no_match_row = await db_connection.fetchrow(
            "SELECT COUNT(*) AS total FROM event_v2 ev WHERE ev.title ILIKE $1",
            "%ZZZZNOTEXIST%",
        )
        no_match_total = no_match_row["total"] if no_match_row else 0
        assert no_match_total == 0, "Expected 0 results for non-matching search"

    @pytest.mark.asyncio
    async def test_sort_by_time(
        self, db_connection: asyncpg.Connection, v7_test_event: dict
    ) -> None:
        """Seed a second event with different time_start, verify ASC/DESC sort order."""
        second_id = "test-events-v7-ev-002"
        try:
            await db_connection.execute(
                "INSERT INTO event_v2 (id, document_id, title, description, "
                "time_start, time_end, extraction_confidence) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7) "
                "ON CONFLICT (id) DO NOTHING",
                second_id,
                v7_test_event["document_id"],
                "Evento anterior",
                "Evento más antiguo para sort test",
                datetime(2023, 1, 1, tzinfo=timezone.utc),
                datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
                0.85,
            )

            desc_rows = await db_connection.fetch(
                "SELECT ev.* FROM event_v2 ev WHERE TRUE "
                "ORDER BY ev.time_start DESC LIMIT $1 OFFSET $2",
                20, 0,
            )
            assert len(desc_rows) >= 2, "Expected at least 2 events for sort test"
            assert desc_rows[0]["title"] == "Reunión de prueba", (
                "DESC order: first row should be newest (2024-06-01 > 2023-01-01)"
            )

            asc_rows = await db_connection.fetch(
                "SELECT ev.* FROM event_v2 ev WHERE TRUE "
                "ORDER BY ev.time_start ASC LIMIT $1 OFFSET $2",
                20, 0,
            )
            assert asc_rows[0]["title"] == "Evento anterior", (
                "ASC order: first row should be oldest (2023-01-01 < 2024-06-01)"
            )
        finally:
            await db_connection.execute("DELETE FROM event_v2 WHERE id = $1", second_id)


class TestEventDetailV2:
    """Tests for API-02: GET /events/{id} (detail with locations, participants, refs)."""

    @pytest.mark.asyncio
    async def test_full_detail(
        self, db_connection: asyncpg.Connection, v7_test_event: dict
    ) -> None:
        """Query event + locations + participants + references via separate queries."""
        event_id = v7_test_event["event_id"]

        event_row = await db_connection.fetchrow(
            "SELECT ev.* FROM event_v2 ev WHERE ev.id = $1", event_id,
        )
        assert event_row is not None, "Event row should exist"
        assert event_row["title"] == "Reunión de prueba"
        assert event_row["description"], "Description should not be empty"
        assert event_row["time_start"] is not None
        assert event_row["time_end"] is not None
        assert event_row["extraction_confidence"] == 0.95

        loc_rows = await db_connection.fetch(
            "SELECT * FROM event_location WHERE event_id = $1", event_id,
        )
        assert len(loc_rows) >= 1, "Expected at least 1 location"
        assert loc_rows[0]["name"] == "Ciudad de México"
        assert loc_rows[0]["location_type"] == "city"

        par_rows = await db_connection.fetch(
            "SELECT * FROM event_participant_v2 WHERE event_id = $1", event_id,
        )
        assert len(par_rows) >= 1, "Expected at least 1 participant"
        assert par_rows[0]["name"] == "Juan Pérez"
        assert par_rows[0]["role"] == "testigo"

        ref_rows = await db_connection.fetch(
            "SELECT * FROM event_ref WHERE event_id = $1 "
            "ORDER BY chunk_index, span_start",
            event_id,
        )
        assert len(ref_rows) >= 1, "Expected at least 1 reference"
        assert ref_rows[0]["reference_type"] == "verbatim"
        assert ref_rows[0]["verbatim_text"] == "el testigo declaró..."
        assert ref_rows[0]["span_start"] == 10
        assert ref_rows[0]["span_end"] == 30

    @pytest.mark.asyncio
    async def test_404(
        self, db_connection: asyncpg.Connection
    ) -> None:
        """Verify fetchrow returns None for nonexistent event_id."""
        got_row = await db_connection.fetchrow(
            "SELECT ev.* FROM event_v2 ev WHERE ev.id = $1",
            "totally-nonexistent-event-id",
        )
        assert got_row is None, "Expected None for nonexistent event_id"
