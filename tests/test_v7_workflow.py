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

    @pytest.mark.asyncio
    async def test_workflow_run_executes_extract_activity(self) -> None:
        """Execute run() with patched execute_activity — must not raise NameError.

        Regression test for the undefined `model` name in the extract activity
        args, which failed every v7 document on the first chunk. Also asserts
        no LLM config travels through Temporal-visible activity args.
        """
        from eth_pipeline.workflows import DocumentProcessingV7Workflow

        returns = {
            "get_document_metadata_activity": {"has_text_content": True},
            "get_document_chunks_activity": {"chunks": ["chunk text"]},
            "get_prior_events_activity": {"prior_events": []},
            "extract_events_v7_activity": {"events": []},
            "store_events_v7_activity": {"events_stored": 0},
            "resolve_references_v7_activity": {"resolved": 0},
        }
        calls: list[tuple[str, list]] = []

        async def fake_execute_activity(activity_fn, **kwargs):
            name = getattr(activity_fn, "__name__", str(activity_fn))
            calls.append((name, list(kwargs.get("args", []))))
            return returns.get(name, {})

        with patch("temporalio.workflow.execute_activity", fake_execute_activity):
            result = await DocumentProcessingV7Workflow().run("doc-repro-1")

        assert result["status"] == "processed"
        extract_calls = [c for c in calls if c[0] == "extract_events_v7_activity"]
        assert len(extract_calls) == 1
        assert extract_calls[0][1] == ["doc-repro-1", 0, [], 1]

    @pytest.mark.asyncio
    async def test_get_document_metadata_returns_model(
        self, db_connection: asyncpg.Connection, _clean_pool: None
    ) -> None:
        """Regression for B2: metadata activity must return document.model."""
        from eth_pipeline.activities.get_document_metadata import (
            get_document_metadata_activity,
        )

        doc_id = uuid.uuid4().hex
        prov_id = uuid.uuid4().hex
        try:
            await db_connection.execute(
                "INSERT INTO llm_provider (id, name, model, base_url, is_default) "
                "VALUES ($1, $2, $3, $4, FALSE)",
                prov_id, f"meta-{prov_id}", "meta/model-Z", "https://meta.example",
            )
            await db_connection.execute(
                "INSERT INTO document (id, mime_type, status, provider_id, model) "
                "VALUES ($1, 'text/plain', 'pending', $2, $3)",
                doc_id, prov_id, "row/model-B",
            )

            result = await get_document_metadata_activity(doc_id)
            assert result.get("model") == "row/model-B"
        finally:
            await db_connection.execute("DELETE FROM document WHERE id = $1", doc_id)
            await db_connection.execute("DELETE FROM llm_provider WHERE id = $1", prov_id)

    @pytest.mark.asyncio
    async def test_upload_creates_one_document_for_selected_provider(
        self, db_connection: asyncpg.Connection, _clean_pool: None
    ) -> None:
        """One upload with one provider_id form field yields exactly ONE row.

        Regression for the removed multi-provider fan-out: the upload
        endpoint must insert a single document whose model matches the
        selected provider.
        """
        import httpx

        from eth_pipeline.api import app

        p1 = uuid.uuid4().hex
        m1 = "single/model-one"
        try:
            await db_connection.execute(
                "INSERT INTO llm_provider (id, name, model, base_url, is_default) "
                "VALUES ($1, $2, $3, $4, FALSE)",
                p1, f"single-a-{p1[:8]}", m1, "https://single.example",
            )

            boundary = "----singleboundary1234"
            file_bytes = b"El Sr. Juan Perez firmo el contrato en Buenos Aires."

            def field(name: str, value: str) -> str:
                return (
                    f"--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                    f"{value}\r\n"
                )

            body = (
                field("provider_id", p1)
                + f"--{boundary}\r\n"
                'Content-Disposition: form-data; name="file"; filename="single.txt"\r\n'
                "Content-Type: text/plain\r\n\r\n"
            ).encode() + file_bytes + f"\r\n--{boundary}--\r\n".encode()

            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://testserver"
            ) as client:
                resp = await client.post(
                    "/documents/upload?passcode=AAAAA",
                    content=body,
                    headers={"content-type": f"multipart/form-data; boundary={boundary}"},
                )
            assert resp.status_code == 201, resp.text

            payload = resp.json()
            assert len(payload["document_ids"]) == 1

            rows = await db_connection.fetch(
                "SELECT id, provider_id, model FROM document WHERE provider_id = $1",
                p1,
            )
            assert len(rows) == 1, "upload must create exactly one document row"
            assert rows[0]["model"] == m1
            assert rows[0]["id"] == payload["document_ids"][0]
        finally:
            await db_connection.execute("DELETE FROM document WHERE provider_id = $1", p1)
            await db_connection.execute("DELETE FROM llm_provider WHERE id = $1", p1)

    @pytest.mark.asyncio
    async def test_upload_without_provider_uses_default_provider(
        self, db_connection: asyncpg.Connection, _clean_pool: None
    ) -> None:
        """One upload with no provider_id field falls back to the default provider."""
        import httpx

        from eth_pipeline.api import app
        from eth_pipeline.providers import default_provider_model

        try:
            # The default provider row is normally seeded by the app lifespan,
            # which ASGITransport does not run — seed it explicitly.
            await db_connection.execute(
                "INSERT INTO llm_provider (id, name, model, base_url, api_key, is_default) "
                "VALUES ('default', 'default', $1, 'https://default.example', NULL, TRUE) "
                "ON CONFLICT (id) DO NOTHING",
                default_provider_model(),
            )

            boundary = "----defaultboundary1234"
            file_bytes = b"El Sr. Juan Perez firmo el contrato en Buenos Aires."

            body = (
                f"--{boundary}\r\n"
                'Content-Disposition: form-data; name="file"; filename="default.txt"\r\n'
                "Content-Type: text/plain\r\n\r\n"
            ).encode() + file_bytes + f"\r\n--{boundary}--\r\n".encode()

            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://testserver"
            ) as client:
                resp = await client.post(
                    "/documents/upload?passcode=AAAAA",
                    content=body,
                    headers={"content-type": f"multipart/form-data; boundary={boundary}"},
                )
            assert resp.status_code == 201, resp.text

            rows = await db_connection.fetch(
                "SELECT id, provider_id, model FROM document WHERE provider_id = 'default'"
            )
            assert len(rows) == 1, "upload must create exactly one document row"
            assert rows[0]["model"] == default_provider_model()
        finally:
            await db_connection.execute(
                "DELETE FROM document WHERE provider_id = 'default' AND filename = 'default.txt'"
            )
            await db_connection.execute("DELETE FROM llm_provider WHERE id = 'default'")
