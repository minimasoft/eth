"""Unit tests for post-extraction reference offset resolution."""

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


class TestOffsetResolution:

    @pytest.mark.asyncio
    async def test_offsets_resolved(self, db_connection: asyncpg.Connection, _clean_pool: None) -> None:
        """Insert event_ref with verbatim_text found in chunk — assert document-absolute offsets."""
        from eth_pipeline.activities.resolve_references_v7 import resolve_references_v7_activity

        doc_id = uuid.uuid4().hex
        event_id = uuid.uuid4().hex
        ref_id = uuid.uuid4().hex

        with patch("eth_pipeline.activities.resolve_references_v7.ProcessingLogger") as mock_logger:
            mock_logger.return_value.log = AsyncMock()
            try:
                await db_connection.execute(
                    "INSERT INTO document (id, mime_type, status) VALUES ($1, 'text/plain', 'pending')",
                    doc_id,
                )
                chunk_text = "El día 15 de enero, en la ciudad de Buenos Aires, se firmó un acuerdo importante."
                await db_connection.execute(
                    "INSERT INTO document_chunk (id, chunk_index, text, offset_start, offset_end, document) "
                    "VALUES ($1, $2, $3, $4, $5, $6)",
                    uuid.uuid4().hex, 0, chunk_text, 1000, 1000 + len(chunk_text), doc_id,
                )
                await db_connection.execute(
                    "INSERT INTO event_v2 (id, document_id, title, description) "
                    "VALUES ($1, $2, 'Test', 'desc')",
                    event_id, doc_id,
                )
                await db_connection.execute(
                    "INSERT INTO event_document (id, event_id, document_id, chunk_index) "
                    "VALUES ($1, $2, $3, $4)",
                    uuid.uuid4().hex, event_id, doc_id, 0,
                )
                await db_connection.execute(
                    "INSERT INTO event_ref (id, event_id, reference_type, verbatim_text, "
                    "span_start, span_end, chunk_index) "
                    "VALUES ($1, $2, 'location', $3, $4, $5, $6)",
                    ref_id, event_id, "Buenos Aires", 0, 12, 0,
                )

                result = await resolve_references_v7_activity(doc_id)
                assert result["resolved"] >= 1
                assert result["total"] >= 1

                row = await db_connection.fetchrow(
                    "SELECT span_start, span_end FROM event_ref WHERE id = $1",
                    ref_id,
                )
                # "Buenos Aires" starts at position 36 in the chunk text
                # offset_start = 1000, so doc_span_start = 1000 + 36 = 1036
                assert row["span_start"] == 1036
                assert row["span_end"] == 1036 + len("Buenos Aires")
            finally:
                await db_connection.execute(
                    "DELETE FROM event_ref WHERE id IN (SELECT id FROM event_ref WHERE event_id = $1)",
                    event_id,
                )
                await db_connection.execute(
                    "DELETE FROM event_v2 WHERE id = $1",
                    event_id,
                )
                await db_connection.execute("DELETE FROM document_chunk WHERE document = $1", doc_id)
                await db_connection.execute("DELETE FROM document WHERE id = $1", doc_id)

    @pytest.mark.asyncio
    async def test_text_not_found_in_chunk(self, db_connection: asyncpg.Connection, _clean_pool: None) -> None:
        """verbatim_text not in chunk — offsets remain unchanged."""
        from eth_pipeline.activities.resolve_references_v7 import resolve_references_v7_activity

        doc_id = uuid.uuid4().hex
        event_id = uuid.uuid4().hex
        ref_id = uuid.uuid4().hex

        with patch("eth_pipeline.activities.resolve_references_v7.ProcessingLogger") as mock_logger:
            mock_logger.return_value.log = AsyncMock()
            try:
                await db_connection.execute(
                    "INSERT INTO document (id, mime_type, status) VALUES ($1, 'text/plain', 'pending')",
                    doc_id,
                )
                chunk_text = "Some completely different text content here."
                await db_connection.execute(
                    "INSERT INTO document_chunk (id, chunk_index, text, offset_start, offset_end, document) "
                    "VALUES ($1, $2, $3, $4, $5, $6)",
                    uuid.uuid4().hex, 0, chunk_text, 500, 500 + len(chunk_text), doc_id,
                )
                await db_connection.execute(
                    "INSERT INTO event_v2 (id, document_id, title, description) "
                    "VALUES ($1, $2, 'Test', 'desc')",
                    event_id, doc_id,
                )
                await db_connection.execute(
                    "INSERT INTO event_document (id, event_id, document_id, chunk_index) "
                    "VALUES ($1, $2, $3, $4)",
                    uuid.uuid4().hex, event_id, doc_id, 0,
                )
                await db_connection.execute(
                    "INSERT INTO event_ref (id, event_id, reference_type, verbatim_text, "
                    "span_start, span_end, chunk_index) "
                    "VALUES ($1, $2, 'description', $3, $4, $5, $6)",
                    ref_id, event_id, "xyzmissing", 99, 110, 0,
                )

                result = await resolve_references_v7_activity(doc_id)
                assert result["resolved"] == 0
                assert result["total"] == 1

                row = await db_connection.fetchrow(
                    "SELECT span_start, span_end FROM event_ref WHERE id = $1",
                    ref_id,
                )
                assert row["span_start"] == 99
                assert row["span_end"] == 110
            finally:
                await db_connection.execute(
                    "DELETE FROM event_ref WHERE id IN (SELECT id FROM event_ref WHERE event_id = $1)",
                    event_id,
                )
                await db_connection.execute(
                    "DELETE FROM event_v2 WHERE id = $1",
                    event_id,
                )
                await db_connection.execute("DELETE FROM document_chunk WHERE document = $1", doc_id)
                await db_connection.execute("DELETE FROM document WHERE id = $1", doc_id)

    @pytest.mark.asyncio
    async def test_case_insensitive_fallback(self, db_connection: asyncpg.Connection, _clean_pool: None) -> None:
        """verbatim_text 'Hola' in chunk as 'hola' — case-insensitive match, offsets resolved."""
        from eth_pipeline.activities.resolve_references_v7 import resolve_references_v7_activity

        doc_id = uuid.uuid4().hex
        event_id = uuid.uuid4().hex
        ref_id = uuid.uuid4().hex

        with patch("eth_pipeline.activities.resolve_references_v7.ProcessingLogger") as mock_logger:
            mock_logger.return_value.log = AsyncMock()
            try:
                await db_connection.execute(
                    "INSERT INTO document (id, mime_type, status) VALUES ($1, 'text/plain', 'pending')",
                    doc_id,
                )
                chunk_text = "Saludo inicial: hola mundo, bienvenidos."
                await db_connection.execute(
                    "INSERT INTO document_chunk (id, chunk_index, text, offset_start, offset_end, document) "
                    "VALUES ($1, $2, $3, $4, $5, $6)",
                    uuid.uuid4().hex, 0, chunk_text, 200, 200 + len(chunk_text), doc_id,
                )
                await db_connection.execute(
                    "INSERT INTO event_v2 (id, document_id, title, description) "
                    "VALUES ($1, $2, 'Test', 'desc')",
                    event_id, doc_id,
                )
                await db_connection.execute(
                    "INSERT INTO event_document (id, event_id, document_id, chunk_index) "
                    "VALUES ($1, $2, $3, $4)",
                    uuid.uuid4().hex, event_id, doc_id, 0,
                )
                await db_connection.execute(
                    "INSERT INTO event_ref (id, event_id, reference_type, verbatim_text, "
                    "span_start, span_end, chunk_index) "
                    "VALUES ($1, $2, 'description', $3, $4, $5, $6)",
                    ref_id, event_id, "Hola", 0, 4, 0,
                )

                result = await resolve_references_v7_activity(doc_id)
                assert result["resolved"] >= 1

                row = await db_connection.fetchrow(
                    "SELECT span_start, span_end FROM event_ref WHERE id = $1",
                    ref_id,
                )
                assert row["span_start"] == 200 + 16  # "hola" starts at index 16 in chunk
                assert row["span_end"] == 200 + 16 + 4
            finally:
                await db_connection.execute(
                    "DELETE FROM event_ref WHERE id IN (SELECT id FROM event_ref WHERE event_id = $1)",
                    event_id,
                )
                await db_connection.execute(
                    "DELETE FROM event_v2 WHERE id = $1",
                    event_id,
                )
                await db_connection.execute("DELETE FROM document_chunk WHERE document = $1", doc_id)
                await db_connection.execute("DELETE FROM document WHERE id = $1", doc_id)

    @pytest.mark.asyncio
    async def test_multi_byte_characters(self, db_connection: asyncpg.Connection, _clean_pool: None) -> None:
        """verbatim_text with ñ/á/ü characters — offsets correctly account for code points."""
        from eth_pipeline.activities.resolve_references_v7 import resolve_references_v7_activity

        doc_id = uuid.uuid4().hex
        event_id = uuid.uuid4().hex
        ref_id = uuid.uuid4().hex
        search_text = "años"

        with patch("eth_pipeline.activities.resolve_references_v7.ProcessingLogger") as mock_logger:
            mock_logger.return_value.log = AsyncMock()
            try:
                await db_connection.execute(
                    "INSERT INTO document (id, mime_type, status) VALUES ($1, 'text/plain', 'pending')",
                    doc_id,
                )
                chunk_text = "Hace muchos años, en un lugar lejano..."
                await db_connection.execute(
                    "INSERT INTO document_chunk (id, chunk_index, text, offset_start, offset_end, document) "
                    "VALUES ($1, $2, $3, $4, $5, $6)",
                    uuid.uuid4().hex, 0, chunk_text, 0, len(chunk_text), doc_id,
                )
                await db_connection.execute(
                    "INSERT INTO event_v2 (id, document_id, title, description) "
                    "VALUES ($1, $2, 'Test', 'desc')",
                    event_id, doc_id,
                )
                await db_connection.execute(
                    "INSERT INTO event_document (id, event_id, document_id, chunk_index) "
                    "VALUES ($1, $2, $3, $4)",
                    uuid.uuid4().hex, event_id, doc_id, 0,
                )
                await db_connection.execute(
                    "INSERT INTO event_ref (id, event_id, reference_type, verbatim_text, "
                    "span_start, span_end, chunk_index) "
                    "VALUES ($1, $2, 'description', $3, $4, $5, $6)",
                    ref_id, event_id, search_text, 0, 4, 0,
                )

                result = await resolve_references_v7_activity(doc_id)
                assert result["resolved"] >= 1

                row = await db_connection.fetchrow(
                    "SELECT span_start, span_end FROM event_ref WHERE id = $1",
                    ref_id,
                )
                # "años" starts at index 12 in "Hace muchos años,..."
                assert row["span_start"] == 12
                assert row["span_end"] == 12 + len(search_text)
            finally:
                await db_connection.execute(
                    "DELETE FROM event_ref WHERE id IN (SELECT id FROM event_ref WHERE event_id = $1)",
                    event_id,
                )
                await db_connection.execute(
                    "DELETE FROM event_v2 WHERE id = $1",
                    event_id,
                )
                await db_connection.execute("DELETE FROM document_chunk WHERE document = $1", doc_id)
                await db_connection.execute("DELETE FROM document WHERE id = $1", doc_id)

    @pytest.mark.asyncio
    async def test_empty_references(self, db_connection: asyncpg.Connection, _clean_pool: None) -> None:
        """Document with zero event_ref rows — returns resolved=0, total=0."""
        from eth_pipeline.activities.resolve_references_v7 import resolve_references_v7_activity

        doc_id = uuid.uuid4().hex
        with patch("eth_pipeline.activities.resolve_references_v7.ProcessingLogger") as mock_logger:
            mock_logger.return_value.log = AsyncMock()
            try:
                await db_connection.execute(
                    "INSERT INTO document (id, mime_type, status) VALUES ($1, 'text/plain', 'pending')",
                    doc_id,
                )
                result = await resolve_references_v7_activity(doc_id)
                assert result["resolved"] == 0
                assert result["total"] == 0
                assert result["document_id"] == doc_id
            finally:
                await db_connection.execute("DELETE FROM document WHERE id = $1", doc_id)
