"""Per-chunk commit and replay safety tests for store_events_v7_activity."""

from __future__ import annotations

import logging
import uuid
from unittest.mock import AsyncMock, patch

import asyncpg
import pytest
import pytest_asyncio

from eth_pipeline.db import close_pool

logger = logging.getLogger(__name__)


@pytest_asyncio.fixture
async def _clean_pool() -> None:
    await close_pool()
    yield
    await close_pool()


class TestStoreEventsV7:

    @pytest.mark.asyncio
    async def test_per_chunk_idempotent(self, db_connection: asyncpg.Connection, _clean_pool: None) -> None:
        """Insert 2 events for chunk 0, then insert 2 DIFFERENT events for chunk 0
        — assert only 2 events exist and they match the second insert."""
        from eth_pipeline.activities.store_events_v7 import store_events_v7_activity

        doc_id = uuid.uuid4().hex
        with patch("eth_pipeline.activities.store_events_v7.ProcessingLogger") as mock_logger:
            mock_logger.return_value.log = AsyncMock()
            try:
                await db_connection.execute(
                    "INSERT INTO document (id, mime_type, status) VALUES ($1, 'text/plain', 'pending')",
                    doc_id,
                )

                events_first = [
                    {
                        "title": "Event Alpha",
                        "description": "First insert event A",
                        "references": [
                            {"reference_type": "description", "verbatim_text": "alpha ref",
                             "span_start": 0, "span_end": 9},
                        ],
                    },
                    {
                        "title": "Event Beta",
                        "description": "First insert event B",
                        "references": [],
                    },
                ]

                result1 = await store_events_v7_activity(doc_id, 0, events_first)
                assert result1["events_stored"] == 2
                assert result1["references_stored"] == 1

                events_second = [
                    {
                        "title": "Event Gamma",
                        "description": "Second insert event C",
                        "references": [
                            {"reference_type": "location", "verbatim_text": "gamma ref",
                             "span_start": 0, "span_end": 10},
                        ],
                    },
                    {
                        "title": "Event Delta",
                        "description": "Second insert event D",
                        "references": [],
                    },
                ]

                result2 = await store_events_v7_activity(doc_id, 0, events_second)
                assert result2["events_stored"] == 2

                count = await db_connection.fetchval(
                    "SELECT COUNT(*) FROM event_v2 ev "
                    "JOIN event_document ed ON ev.id = ed.event_id "
                    "WHERE ed.document_id = $1 AND ed.chunk_index = $2",
                    doc_id, 0,
                )
                assert count == 2

                titles = await db_connection.fetch(
                    "SELECT ev.title FROM event_v2 ev "
                    "JOIN event_document ed ON ev.id = ed.event_id "
                    "WHERE ed.document_id = $1 AND ed.chunk_index = $2 "
                    "ORDER BY ev.id",
                    doc_id, 0,
                )
                title_list = [r["title"] for r in titles]
                assert "Event Gamma" in title_list
                assert "Event Delta" in title_list
                assert "Event Alpha" not in title_list
                assert "Event Beta" not in title_list
            finally:
                await db_connection.execute(
                    "DELETE FROM event_v2 WHERE id IN (SELECT event_id FROM event_document WHERE document_id = $1)",
                    doc_id,
                )
                await db_connection.execute("DELETE FROM document WHERE id = $1", doc_id)

    @pytest.mark.asyncio
    async def test_per_chunk_isolation(self, db_connection: asyncpg.Connection, _clean_pool: None) -> None:
        """Insert 2 events for chunk 0, 1 event for chunk 1 — assert chunk 0 has 2 events."""
        from eth_pipeline.activities.store_events_v7 import store_events_v7_activity

        doc_id = uuid.uuid4().hex
        with patch("eth_pipeline.activities.store_events_v7.ProcessingLogger") as mock_logger:
            mock_logger.return_value.log = AsyncMock()
            try:
                await db_connection.execute(
                    "INSERT INTO document (id, mime_type, status) VALUES ($1, 'text/plain', 'pending')",
                    doc_id,
                )

                events_chunk0 = [
                    {"title": "Chunk 0 Event A", "description": "test", "references": []},
                    {"title": "Chunk 0 Event B", "description": "test", "references": []},
                ]
                await store_events_v7_activity(doc_id, 0, events_chunk0)

                events_chunk1 = [
                    {"title": "Chunk 1 Event C", "description": "test", "references": []},
                ]
                await store_events_v7_activity(doc_id, 1, events_chunk1)

                count_c0 = await db_connection.fetchval(
                    "SELECT COUNT(*) FROM event_v2 ev "
                    "JOIN event_document ed ON ev.id = ed.event_id "
                    "WHERE ed.document_id = $1 AND ed.chunk_index = 0",
                    doc_id,
                )
                assert count_c0 == 2

                count_c1 = await db_connection.fetchval(
                    "SELECT COUNT(*) FROM event_v2 ev "
                    "JOIN event_document ed ON ev.id = ed.event_id "
                    "WHERE ed.document_id = $1 AND ed.chunk_index = 1",
                    doc_id,
                )
                assert count_c1 == 1
            finally:
                await db_connection.execute(
                    "DELETE FROM event_v2 WHERE id IN (SELECT event_id FROM event_document WHERE document_id = $1)",
                    doc_id,
                )
                await db_connection.execute("DELETE FROM document WHERE id = $1", doc_id)

    @pytest.mark.asyncio
    async def test_v7_tables_populated(self, db_connection: asyncpg.Connection, _clean_pool: None) -> None:
        """Insert event with location, participants, references — assert all tables populated."""
        from eth_pipeline.activities.store_events_v7 import store_events_v7_activity

        doc_id = uuid.uuid4().hex
        with patch("eth_pipeline.activities.store_events_v7.ProcessingLogger") as mock_logger:
            mock_logger.return_value.log = AsyncMock()
            try:
                await db_connection.execute(
                    "INSERT INTO document (id, mime_type, status) VALUES ($1, 'text/plain', 'pending')",
                    doc_id,
                )

                events = [{
                    "title": "Test Event",
                    "description": "Test description",
                    "location": {"name": "Buenos Aires", "location_type": "city"},
                    "participants": [
                        {"name": "Juan", "role": "subject"},
                        {"name": "Maria", "role": "object"},
                    ],
                    "references": [
                        {"reference_type": "location", "verbatim_text": "en la ciudad",
                         "span_start": 10, "span_end": 23},
                        {"reference_type": "participant", "verbatim_text": "Juan",
                         "span_start": 0, "span_end": 4},
                    ],
                }]

                result = await store_events_v7_activity(doc_id, 0, events)
                assert result["events_stored"] == 1
                assert result["references_stored"] == 2

                ev_count = await db_connection.fetchval(
                    "SELECT COUNT(*) FROM event_v2 ev "
                    "JOIN event_document ed ON ev.id = ed.event_id "
                    "WHERE ed.document_id = $1",
                    doc_id,
                )
                assert ev_count == 1

                loc_count = await db_connection.fetchval(
                    "SELECT COUNT(*) FROM event_location el "
                    "JOIN event_v2 ev ON el.event_id = ev.id "
                    "JOIN event_document ed ON ev.id = ed.event_id "
                    "WHERE ed.document_id = $1",
                    doc_id,
                )
                assert loc_count == 1

                part_count = await db_connection.fetchval(
                    "SELECT COUNT(*) FROM event_participant_v2 ep "
                    "JOIN event_v2 ev ON ep.event_id = ev.id "
                    "JOIN event_document ed ON ev.id = ed.event_id "
                    "WHERE ed.document_id = $1",
                    doc_id,
                )
                assert part_count == 2

                doc_join_count = await db_connection.fetchval(
                    "SELECT COUNT(*) FROM event_document WHERE document_id = $1",
                    doc_id,
                )
                assert doc_join_count == 1

                ref_count = await db_connection.fetchval(
                    "SELECT COUNT(*) FROM event_ref er "
                    "JOIN event_v2 ev ON er.event_id = ev.id "
                    "JOIN event_document ed ON ev.id = ed.event_id "
                    "WHERE ed.document_id = $1",
                    doc_id,
                )
                assert ref_count == 2
            finally:
                await db_connection.execute(
                    "DELETE FROM event_v2 WHERE id IN (SELECT event_id FROM event_document WHERE document_id = $1)",
                    doc_id,
                )
                await db_connection.execute("DELETE FROM document WHERE id = $1", doc_id)

    @pytest.mark.asyncio
    async def test_cascade_delete(self, db_connection: asyncpg.Connection, _clean_pool: None) -> None:
        """Insert event with children, re-insert empty events — assert all child rows deleted via CASCADE."""
        from eth_pipeline.activities.store_events_v7 import store_events_v7_activity

        doc_id = uuid.uuid4().hex
        with patch("eth_pipeline.activities.store_events_v7.ProcessingLogger") as mock_logger:
            mock_logger.return_value.log = AsyncMock()
            try:
                await db_connection.execute(
                    "INSERT INTO document (id, mime_type, status) VALUES ($1, 'text/plain', 'pending')",
                    doc_id,
                )

                events = [{
                    "title": "Cascade Test",
                    "description": "test",
                    "location": {"name": "Madrid", "location_type": "city"},
                    "participants": [{"name": "Pedro", "role": "subject"}],
                    "references": [{"reference_type": "description", "verbatim_text": "cascade ref",
                                    "span_start": 0, "span_end": 11}],
                }]

                await store_events_v7_activity(doc_id, 0, events)

                result = await store_events_v7_activity(doc_id, 0, [])
                assert result["events_stored"] == 0
                assert result["references_stored"] == 0

                ev_count = await db_connection.fetchval(
                    "SELECT COUNT(*) FROM event_v2 ev "
                    "JOIN event_document ed ON ev.id = ed.event_id "
                    "WHERE ed.document_id = $1 AND ed.chunk_index = 0",
                    doc_id,
                )
                assert ev_count == 0

                loc_count = await db_connection.fetchval(
                    "SELECT COUNT(*) FROM event_location el "
                    "JOIN event_v2 ev ON el.event_id = ev.id "
                    "JOIN event_document ed ON ev.id = ed.event_id "
                    "WHERE ed.document_id = $1 AND ed.chunk_index = 0",
                    doc_id,
                )
                assert loc_count == 0

                part_count = await db_connection.fetchval(
                    "SELECT COUNT(*) FROM event_participant_v2 ep "
                    "JOIN event_v2 ev ON ep.event_id = ev.id "
                    "JOIN event_document ed ON ev.id = ed.event_id "
                    "WHERE ed.document_id = $1 AND ed.chunk_index = 0",
                    doc_id,
                )
                assert part_count == 0

                ref_count = await db_connection.fetchval(
                    "SELECT COUNT(*) FROM event_ref er "
                    "JOIN event_v2 ev ON er.event_id = ev.id "
                    "JOIN event_document ed ON ev.id = ed.event_id "
                    "WHERE ed.document_id = $1 AND ed.chunk_index = 0",
                    doc_id,
                )
                assert ref_count == 0
            finally:
                await db_connection.execute("DELETE FROM document WHERE id = $1", doc_id)

    @pytest.mark.asyncio
    async def test_empty_events(self, db_connection: asyncpg.Connection, _clean_pool: None) -> None:
        """Call activity with events=[] — returns success with events_stored=0."""
        from eth_pipeline.activities.store_events_v7 import store_events_v7_activity

        doc_id = uuid.uuid4().hex
        with patch("eth_pipeline.activities.store_events_v7.ProcessingLogger") as mock_logger:
            mock_logger.return_value.log = AsyncMock()
            try:
                await db_connection.execute(
                    "INSERT INTO document (id, mime_type, status) VALUES ($1, 'text/plain', 'pending')",
                    doc_id,
                )

                result = await store_events_v7_activity(doc_id, 0, [])
                assert result["events_stored"] == 0
                assert result["references_stored"] == 0
                assert result["document_id"] == doc_id
            finally:
                await db_connection.execute("DELETE FROM document WHERE id = $1", doc_id)

    @pytest.mark.asyncio
    async def test_reference_type_validation(self, db_connection: asyncpg.Connection, _clean_pool: None) -> None:
        """Event with reference_type not in valid set — that reference is skipped."""
        from eth_pipeline.activities.store_events_v7 import store_events_v7_activity

        doc_id = uuid.uuid4().hex
        with patch("eth_pipeline.activities.store_events_v7.ProcessingLogger") as mock_logger:
            mock_logger.return_value.log = AsyncMock()
            try:
                await db_connection.execute(
                    "INSERT INTO document (id, mime_type, status) VALUES ($1, 'text/plain', 'pending')",
                    doc_id,
                )

                events = [{
                    "title": "Validation Test",
                    "description": "test invalid ref types",
                    "references": [
                        {"reference_type": "location", "verbatim_text": "valid ref",
                         "span_start": 0, "span_end": 9},
                        {"reference_type": "espacio", "verbatim_text": "bad v6 type",
                         "span_start": 0, "span_end": 10},
                        {"reference_type": "unknown", "verbatim_text": "bad unknown type",
                         "span_start": 0, "span_end": 12},
                    ],
                }]

                result = await store_events_v7_activity(doc_id, 0, events)
                assert result["events_stored"] == 1
                assert result["references_stored"] == 1  # only the valid one

                ref_count = await db_connection.fetchval(
                    "SELECT COUNT(*) FROM event_ref er "
                    "JOIN event_v2 ev ON er.event_id = ev.id "
                    "JOIN event_document ed ON ev.id = ed.event_id "
                    "WHERE ed.document_id = $1",
                    doc_id,
                )
                assert ref_count == 1
            finally:
                await db_connection.execute(
                    "DELETE FROM event_v2 WHERE id IN (SELECT event_id FROM event_document WHERE document_id = $1)",
                    doc_id,
                )
                await db_connection.execute("DELETE FROM document WHERE id = $1", doc_id)

    @pytest.mark.asyncio
    async def test_model_provenance_stamped_on_events(
        self, db_connection: asyncpg.Connection, _clean_pool: None
    ) -> None:
        """Events store the provider/model of the document row that produced them."""
        from eth_pipeline.activities.store_events_v7 import store_events_v7_activity

        doc_id = uuid.uuid4().hex
        prov_id = "prov-" + uuid.uuid4().hex[:8]
        with patch("eth_pipeline.activities.store_events_v7.ProcessingLogger") as mock_logger:
            mock_logger.return_value.log = AsyncMock()
            try:
                await db_connection.execute(
                    "INSERT INTO llm_provider (id, name, model, base_url) "
                    "VALUES ($1, $2, 'model-omega', 'http://example.invalid/v1')",
                    prov_id, prov_id,
                )
                await db_connection.execute(
                    "INSERT INTO document (id, mime_type, status, provider_id, model, source_id) "
                    "VALUES ($1, 'text/plain', 'pending', $2, 'model-omega', 'src-0001')",
                    doc_id, prov_id,
                )

                events = [
                    {"title": "Prov A", "description": "a", "references": []},
                    {"title": "Prov B", "description": "b", "references": []},
                ]
                result = await store_events_v7_activity(doc_id, 0, events)
                assert result["events_stored"] == 2

                rows = await db_connection.fetch(
                    "SELECT model, provider_id FROM event_v2 WHERE document_id = $1",
                    doc_id,
                )
                assert len(rows) == 2
                for row in rows:
                    assert row["model"] == "model-omega"
                    assert row["provider_id"] == prov_id
            finally:
                await db_connection.execute(
                    "DELETE FROM event_v2 WHERE id IN (SELECT event_id FROM event_document WHERE document_id = $1)",
                    doc_id,
                )
                await db_connection.execute("DELETE FROM document WHERE id = $1", doc_id)
                await db_connection.execute("DELETE FROM llm_provider WHERE id = $1", prov_id)
