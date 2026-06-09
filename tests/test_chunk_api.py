"""API tests for chunk text endpoint (Phase 36)."""

from __future__ import annotations

import logging

import asyncpg
import pytest

logger = logging.getLogger(__name__)


class TestChunkText:
    """Tests for API-03: GET /documents/{id}/chunks/{part_index}."""

    @pytest.mark.asyncio
    async def test_chunk_text_with_offsets(
        self, db_connection: asyncpg.Connection, v7_test_chunk: dict
    ) -> None:
        """Query document_chunk by fixture's doc_id and chunk_index, verify text and offsets."""
        doc_id = v7_test_chunk["document_id"]
        chunk_idx = v7_test_chunk["chunk_index"]

        chunk_row = await db_connection.fetchrow(
            "SELECT chunk_index, text, offset_start, offset_end "
            "FROM document_chunk "
            "WHERE document = $1 AND chunk_index = $2",
            doc_id, chunk_idx,
        )
        assert chunk_row is not None, "Chunk row should exist for fixture data"

        assert chunk_row["chunk_index"] == chunk_idx
        assert chunk_row["text"] == (
            "Texto de prueba para el chunk 0. Contiene información relevante."
        )
        assert chunk_row["offset_start"] == 0
        assert chunk_row["offset_end"] == 61

        chunk_text = chunk_row["text"] or ""
        chunk_offset_start = 0
        chunk_offset_end = len(chunk_text)
        assert chunk_offset_start == 0
        assert chunk_offset_end == 64

    @pytest.mark.asyncio
    async def test_chunk_404(
        self, db_connection: asyncpg.Connection
    ) -> None:
        """Verify None return for nonexistent document_id and out-of-range chunk_index."""
        chunk_row = await db_connection.fetchrow(
            "SELECT chunk_index, text, offset_start, offset_end "
            "FROM document_chunk "
            "WHERE document = $1 AND chunk_index = $2",
            "nonexistent-doc-id", 0,
        )
        assert chunk_row is None, "Expected None for nonexistent document_id"

        chunk_row2 = await db_connection.fetchrow(
            "SELECT chunk_index, text, offset_start, offset_end "
            "FROM document_chunk "
            "WHERE document = $1 AND chunk_index = $2",
            "test-events-v7-doc-001", 999,
        )
        assert chunk_row2 is None, "Expected None for out-of-range chunk_index (999)"

    @pytest.mark.asyncio
    async def test_chunk_empty_text(
        self, db_connection: asyncpg.Connection, v7_test_document: str
    ) -> None:
        """Insert chunk with empty text, verify 'or \"\"' fallback handles it correctly."""
        empty_chunk_id = "test-events-v7-chk-empty"
        try:
            await db_connection.execute(
                "INSERT INTO document_chunk "
                "(id, chunk_index, text, page_start, page_end, "
                "offset_start, offset_end, document) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8) "
                "ON CONFLICT (id) DO NOTHING",
                empty_chunk_id, 1, "", 1, 1, 62, 62, v7_test_document,
            )

            chunk_row = await db_connection.fetchrow(
                "SELECT chunk_index, text, offset_start, offset_end "
                "FROM document_chunk "
                "WHERE document = $1 AND chunk_index = $2",
                v7_test_document, 1,
            )
            assert chunk_row is not None, "Chunk row should exist for empty text test"
            assert chunk_row["text"] == ""

            chunk_text = chunk_row["text"] or ""
            assert chunk_text == ""
            assert len(chunk_text) == 0
        finally:
            await db_connection.execute(
                "DELETE FROM document_chunk WHERE id = $1", empty_chunk_id,
            )
