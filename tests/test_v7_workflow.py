"""Integration tests for DocumentProcessingV7Workflow — per-chunk isolation, prior-context passing, and v6 activity non-invocation."""

from __future__ import annotations

import datetime
import inspect
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


def _dt(day: int) -> datetime.datetime:
    return datetime.datetime(2024, 1, day, tzinfo=datetime.timezone.utc)


class TestV7WorkflowIntegration:

    @pytest.mark.asyncio
    async def test_per_chunk_commit_isolation(self, db_connection: asyncpg.Connection, _clean_pool: None) -> None:
        """Insert 3 chunks, store for chunk 0+1, skip chunk 2 — assert events survive independently."""
        from eth_pipeline.activities.store_events_v7 import store_events_v7_activity

        doc_id = uuid.uuid4().hex
        with patch("eth_pipeline.activities.store_events_v7.ProcessingLogger") as mock_logger:
            mock_logger.return_value.log = AsyncMock()
            try:
                await db_connection.execute(
                    "INSERT INTO document (id, mime_type, status) VALUES ($1, 'text/plain', 'pending')",
                    doc_id,
                )

                result0 = await store_events_v7_activity(doc_id, 0, [
                    {"title": "Chunk 0 Event A", "description": "test", "references": []},
                    {"title": "Chunk 0 Event B", "description": "test", "references": []},
                ])
                assert result0["events_stored"] == 2

                result1 = await store_events_v7_activity(doc_id, 1, [
                    {"title": "Chunk 1 Event C", "description": "test", "references": []},
                ])
                assert result1["events_stored"] == 1

                total = await db_connection.fetchval(
                    "SELECT COUNT(*) FROM event_v2 ev "
                    "JOIN event_document ed ON ev.id = ed.event_id "
                    "WHERE ed.document_id = $1",
                    doc_id,
                )
                assert total == 3
            finally:
                await db_connection.execute(
                    "DELETE FROM event_v2 WHERE id IN (SELECT event_id FROM event_document WHERE document_id = $1)",
                    doc_id,
                )
                await db_connection.execute("DELETE FROM document WHERE id = $1", doc_id)

    @pytest.mark.asyncio
    async def test_prior_context_passed(self, db_connection: asyncpg.Connection, _clean_pool: None) -> None:
        """Populate 3 prior events, call get_prior_events_activity — assert correct structure and ordering."""
        from eth_pipeline.workflows import get_prior_events_activity

        doc_id = uuid.uuid4().hex
        try:
            await db_connection.execute(
                "INSERT INTO document (id, mime_type, status) VALUES ($1, 'text/plain', 'pending')",
                doc_id,
            )

            event_ids = [uuid.uuid4().hex for _ in range(3)]
            for i, eid in enumerate(event_ids):
                await db_connection.execute(
                    "INSERT INTO event_v2 (id, document_id, title, description, time_start) "
                    "VALUES ($1, $2, $3, $4, $5)",
                    eid, doc_id,
                    f"Event {i + 1}",
                    f"Description {i + 1}",
                    _dt(i + 1),
                )
                await db_connection.execute(
                    "INSERT INTO event_document (id, event_id, document_id, chunk_index) "
                    "VALUES ($1, $2, $3, $4)",
                    uuid.uuid4().hex, eid, doc_id, i,
                )

            result = await get_prior_events_activity(doc_id)
            assert "prior_events" in result
            prior = result["prior_events"]
            assert len(prior) == 3
            assert prior[0]["id"] == event_ids[2]
            assert prior[2]["id"] == event_ids[0]
            for entry in prior:
                assert "id" in entry
                assert "title" in entry
                assert "description" in entry
                assert "time_start" in entry
        finally:
            await db_connection.execute(
                "DELETE FROM event_v2 WHERE id IN (SELECT event_id FROM event_document WHERE document_id = $1)",
                doc_id,
            )
            await db_connection.execute("DELETE FROM document WHERE id = $1", doc_id)

    def test_v6_activities_not_called_for_v7(self) -> None:
        """Static test: verify v7 workflow source does NOT reference v6 activities."""
        from eth_pipeline.workflows import DocumentProcessingV7Workflow

        source = inspect.getsource(DocumentProcessingV7Workflow.run)
        v6_names = [
            "extract_events_activity",
            "store_extraction_results_activity",
            "resolve_entities_activity",
            "resolve_entities_with_search_activity",
            "create_event_canonical_entities_activity",
        ]
        for name in v6_names:
            assert name not in source, f"v7 workflow should NOT reference v6 activity '{name}'"

    @pytest.mark.asyncio
    async def test_prior_context_capped_at_10(self, db_connection: asyncpg.Connection, _clean_pool: None) -> None:
        """Insert 15 prior events, call get_prior_events_activity — assert exactly 10 returned."""
        from eth_pipeline.workflows import get_prior_events_activity

        doc_id = uuid.uuid4().hex
        try:
            await db_connection.execute(
                "INSERT INTO document (id, mime_type, status) VALUES ($1, 'text/plain', 'pending')",
                doc_id,
            )

            for i in range(15):
                eid = uuid.uuid4().hex
                await db_connection.execute(
                    "INSERT INTO event_v2 (id, document_id, title, description, time_start) "
                    "VALUES ($1, $2, $3, $4, $5)",
                    eid, doc_id,
                    f"Event {i}",
                    f"Description {i}",
                    _dt(i + 1),
                )
                await db_connection.execute(
                    "INSERT INTO event_document (id, event_id, document_id, chunk_index) "
                    "VALUES ($1, $2, $3, $4)",
                    uuid.uuid4().hex, eid, doc_id, 0,
                )

            result = await get_prior_events_activity(doc_id)
            prior = result["prior_events"]
            assert len(prior) == 10
        finally:
            await db_connection.execute(
                "DELETE FROM event_v2 WHERE id IN (SELECT event_id FROM event_document WHERE document_id = $1)",
                doc_id,
            )
            await db_connection.execute("DELETE FROM document WHERE id = $1", doc_id)

    def test_workflow_imports_parse(self) -> None:
        """Static test: assert DocumentProcessingV7Workflow is importable with a run method."""
        from eth_pipeline.workflows import DocumentProcessingV7Workflow
        import inspect as _inspect

        assert _inspect.isclass(DocumentProcessingV7Workflow)
        assert hasattr(DocumentProcessingV7Workflow, "run")
        assert callable(DocumentProcessingV7Workflow.run)
