"""
Temporal workflow definitions for the eth-pipeline.

Workflows orchestrate the multi-step document processing lifecycle:
ingest → event extraction → verbatim reference resolution.

The top-level ``DocumentProcessingWorkflow`` handles two document paths:

* **Blob path** (``has_text_content=False``): binary PDF uploaded via MinIO
  or legacy base64 → ``extract_text_activity`` → ``chunk_document_activity``
  → ``extract_events_activity``
* **Text path** (``has_text_content=True``): plain-text document submitted
  directly → ``extract_events_activity``

Both paths converge on the same ``extract_events_activity`` call, which
queries ``document.text_content`` from SurrealDB internally — never
receives individual chunk records (chunk transparency) or large payloads
through Temporal's serialization layer.
"""

from __future__ import annotations

from datetime import timedelta

from temporalio import activity, workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from eth_pipeline.activities import (  # noqa: TCH004
        chunk_document_activity,
        create_event_canonical_entities_activity,
        extract_events_activity,
        extract_events_v7_activity,
        extract_text_activity,
        get_document_metadata_activity,
        resolve_entities_activity,
        resolve_entities_with_search_activity,
        resolve_references_v7_activity,
        store_events_v7_activity,
        store_extraction_results_activity,
        update_document_status_activity,
    )
    from eth_pipeline.activities._common import _db_params, _extract_query_results
    from eth_pipeline.db import get_db

# Re-export so the worker can register by path.
__all__ = [
    "DocumentProcessingWorkflow",
    "DocumentProcessingV7Workflow",
]


@workflow.defn
class DocumentProcessingWorkflow:
    """Orchestrate document event extraction and persistence.

    This workflow is the top-level coordinator for processing a single
    document.  It supports two paths determined at runtime:

    **Blob path** (binary PDF / legacy base64 without text_content):
    ``extracting_blob`` → ``extracting_text`` → ``chunking`` →
    ``extracting_text`` (LLM) → ``processed``

    **Text path** (document already has text_content):
    ``processing`` → ``chunking`` → ``extracting_text`` (LLM) → ``processed``

    Chunk transparency is guaranteed: ``extract_events_activity`` always
    queries ``document.text_content`` from SurrealDB internally,
    never receives individual chunk records.
    """

    @workflow.run
    async def run(self, document_id: str) -> dict:
        """Execute the document processing workflow.

        Discovers the document type at runtime via
        ``get_document_metadata_activity`` and branches accordingly:

        1. Sets status to ``processing``.
        2. Queries document metadata (blob_format, text_content).
        3. If ``has_text_content`` is ``False`` (blob path):
           - ``extracting_blob`` → ``extract_text_activity``
           - ``extracting_text`` (set by extract_text_activity)
           - ``chunk_document_activity`` → chunks stored + ``chunking``
        4. If ``has_text_content`` is ``True`` (text path):
           - Use text_content directly from metadata
           - ``chunk_document_activity`` → chunks stored + ``chunking``
        5. ``extracting_text`` (LLM) — set before event extraction
        6. ``extract_events_activity(document_id)`` — queries text from
           SurrealDB internally (avoids large Temporal payloads)
         7. ``resolve_entities_with_search_activity(document_id, result)``
         8. ``create_event_canonical_entities_activity(document_id, result)``
         9. ``processed`` — set only after ALL steps complete
        11. Return summary dict with ``document_id``, ``event_count``,
            and ``status``.

        Parameters
        ----------
        document_id:
            Unique identifier of the document being processed.

        Returns
        -------
        dict
            Summary containing ``document_id``, ``event_count``,
            and ``status``.

        Raises
        ------
        Exception
            Any activity failure is re-raised after updating the document
            status to ``failed``.
        """
        try:
            # Step 1: Mark document as processing
            await workflow.execute_activity(
                update_document_status_activity,
                args=[document_id, "processing"],
                start_to_close_timeout=timedelta(seconds=10),
            )

            # Step 2: Get document metadata to determine path
            metadata = await workflow.execute_activity(
                get_document_metadata_activity,
                args=[document_id],
                start_to_close_timeout=timedelta(seconds=10),
            )
            if "error" in metadata:
                raise RuntimeError(metadata["error"])

            # Step 3: Conditional branch
            has_text_content = metadata.get("has_text_content", False)

            if not has_text_content:
                # ---- BLOB PATH (Binary PDF / legacy base64) ----

                # Mark as extracting blob
                await workflow.execute_activity(
                    update_document_status_activity,
                    args=[document_id, "extracting_blob"],
                start_to_close_timeout=timedelta(seconds=60),
                )

                # Extract text from blob
                extraction_result = await workflow.execute_activity(
                    extract_text_activity,
                    args=[document_id],
                start_to_close_timeout=timedelta(seconds=900),
                )
                if "error" in extraction_result:
                    raise RuntimeError(extraction_result["error"])

                # Chunk document
                chunk_result = await workflow.execute_activity(
                    chunk_document_activity,
                    args=[document_id, extraction_result],
                    start_to_close_timeout=timedelta(seconds=30),
                )
                if "error" in chunk_result:
                    raise RuntimeError(chunk_result["error"])
            else:
                # ---- TEXT PATH (Direct text) ----
                workflow.logger.info(
                    "Text path: document %s already has text_content — chunking",
                    document_id,
                )

                # Chunk the text (same as blob path, no page offsets)
                chunk_result = await workflow.execute_activity(
                    chunk_document_activity,
                    args=[document_id, {"page_offsets": [0]}],
                    start_to_close_timeout=timedelta(seconds=30),
                )
                if "error" in chunk_result:
                    workflow.logger.warning(
                        "Chunking failed for text-path document %s: %s",
                        document_id,
                        chunk_result["error"],
                    )

            # Step 4: Mark as extracting events via LLM
            await workflow.execute_activity(
                update_document_status_activity,
                args=[document_id, "extracting_text"],
                start_to_close_timeout=timedelta(seconds=10),
            )

            # Step 5: Extract events from full text (same for both paths)
            # extract_events_activity queries text_content from SurrealDB
            # internally to avoid passing large payloads through Temporal.
            result = await workflow.execute_activity(
                extract_events_activity,
                args=[document_id],
                start_to_close_timeout=timedelta(seconds=900),
                retry_policy=RetryPolicy(
                    maximum_attempts=3,
                    initial_interval=timedelta(seconds=5),
                    backoff_coefficient=2.0,
                ),
            )

            # Step 6: Store extraction results
            store_result = await workflow.execute_activity(
                store_extraction_results_activity,
                args=[document_id, result],
                start_to_close_timeout=timedelta(seconds=120),
            )
            if "error" in store_result:
                raise RuntimeError(store_result["error"])

            # Step 7: Resolve verbatim references (search-first)
            # Runs BEFORE event canonical entity creation so that
            # create_event_canonical_entities_activity finds existing
            # place/person/object entities to link against.
            resolve_result = await workflow.execute_activity(
                resolve_entities_with_search_activity,
                args=[document_id],
                start_to_close_timeout=timedelta(seconds=900),
            )
            if "error" in resolve_result:
                raise RuntimeError(resolve_result["error"])

            # Step 8: Create event canonical entities (links against
            # entities created in step 7)
            event_entity_result = await workflow.execute_activity(
                create_event_canonical_entities_activity,
                args=[document_id],
                start_to_close_timeout=timedelta(seconds=30),
            )
            if "error" in event_entity_result:
                raise RuntimeError(event_entity_result["error"])

            # Step 9: Mark as fully processed (only after all steps complete)
            await workflow.execute_activity(
                update_document_status_activity,
                args=[document_id, "processed"],
                start_to_close_timeout=timedelta(seconds=10),
            )

            # Step 10: Return summary
            events = result.get("events", [])
            return {
                "document_id": document_id,
                "event_count": len(events),
                "status": "processed",
            }

        except Exception as exc:
            # Mark document as failed and re-raise
            await workflow.execute_activity(
                update_document_status_activity,
                args=[document_id, "failed", str(exc)],
                start_to_close_timeout=timedelta(seconds=10),
            )
            raise


# ---------------------------------------------------------------------------
# Helper query activities for the v7 pipeline
# ---------------------------------------------------------------------------


@activity.defn
async def get_document_chunks_activity(document_id: str) -> dict:
    """Fetch all chunks for a document from the document_chunk table."""
    params = _db_params()
    try:
        async with get_db(**params) as conn:
            rows = _extract_query_results(
                await conn.fetch(
                    "SELECT chunk_index, text, offset_start, offset_end "
                    "FROM document_chunk "
                    "WHERE document = $1 "
                    "ORDER BY chunk_index ASC",
                    document_id,
                )
            )
        return {"chunks": rows}
    except Exception as exc:
        activity.logger.error(
            "get_document_chunks_activity failed [document_id=%s]: %s",
            document_id,
            exc,
        )
        return {"error": str(exc), "document_id": document_id}


@activity.defn
async def get_prior_events_activity(document_id: str) -> dict:
    """Fetch up to 10 most recent prior events for context injection."""
    params = _db_params()
    try:
        async with get_db(**params) as conn:
            rows = _extract_query_results(
                await conn.fetch(
                    "SELECT ev.id, ev.title, ev.description, ev.time_start "
                    "FROM event_v2 ev "
                    "JOIN event_document ed ON ev.id = ed.event_id "
                    "WHERE ed.document_id = $1 "
                    "ORDER BY ev.time_start DESC NULLS LAST "
                    "LIMIT 10",
                    document_id,
                )
            )
        prior_events = []
        for row in rows:
            entry = {"id": row["id"], "title": row["title"], "description": row["description"]}
            ts = row.get("time_start")
            if ts is not None:
                entry["time_start"] = str(ts) if not isinstance(ts, str) else ts
            prior_events.append(entry)
        return {"prior_events": prior_events}
    except Exception as exc:
        activity.logger.error(
            "get_prior_events_activity failed [document_id=%s]: %s",
            document_id,
            exc,
        )
        return {"error": str(exc), "document_id": document_id}


# ---------------------------------------------------------------------------
# v7 Document Processing Workflow (Phase 35)
# ---------------------------------------------------------------------------


@workflow.defn
class DocumentProcessingV7Workflow:
    """Orchestrate v7 document event extraction and persistence.

    This workflow processes a single document through the v7 pipeline:
    1. Verify schema_version == 'v7' (route v6 docs to old workflow at caller level)
    2. For each chunk (chunk_index 0..N):
       a. Read up to 10 prior events (compact context: id, title, description)
       b. extract_events_v7_activity(chunk_text, prior_events) — LLM extraction
       c. store_events_v7_activity(chunk_events) — per-chunk commit
    3. resolve_references_v7_activity — post-extraction offset computation
    4. Mark document as processed; return summary
    """

    @workflow.run
    async def run(self, document_id: str) -> dict:
        try:
            await workflow.execute_activity(
                update_document_status_activity,
                args=[document_id, "processing"],
                start_to_close_timeout=timedelta(seconds=10),
            )

            chunks_result = await workflow.execute_activity(
                get_document_chunks_activity,
                args=[document_id],
                start_to_close_timeout=timedelta(seconds=30),
            )
            if "error" in chunks_result:
                raise RuntimeError(chunks_result["error"])
            chunks = chunks_result.get("chunks", [])

            event_count = 0
            for chunk_idx, chunk in enumerate(chunks):
                prior_result = await workflow.execute_activity(
                    get_prior_events_activity,
                    args=[document_id],
                    start_to_close_timeout=timedelta(seconds=10),
                )
                prior_events = prior_result.get("prior_events", [])

                extract_result = await workflow.execute_activity(
                    extract_events_v7_activity,
                    args=[document_id, chunk_idx, chunk["text"], prior_events],
                    start_to_close_timeout=timedelta(seconds=900),
                    retry_policy=RetryPolicy(
                        maximum_attempts=3,
                        initial_interval=timedelta(seconds=5),
                        backoff_coefficient=2.0,
                    ),
                )

                if extract_result.get("refused"):
                    workflow.logger.warning(
                        "Chunk %d refused: %s",
                        chunk_idx,
                        extract_result.get("refusal_reason", "unknown"),
                    )

                store_result = await workflow.execute_activity(
                    store_events_v7_activity,
                    args=[document_id, chunk_idx, extract_result.get("events", [])],
                    start_to_close_timeout=timedelta(seconds=120),
                )
                if "error" in store_result:
                    raise RuntimeError(store_result["error"])

                await workflow.execute_activity(
                    update_document_status_activity,
                    args=[document_id, "extracting_text"],
                    start_to_close_timeout=timedelta(seconds=10),
                )

                event_count += store_result.get("events_stored", 0)

            resolve_result = await workflow.execute_activity(
                resolve_references_v7_activity,
                args=[document_id],
                start_to_close_timeout=timedelta(seconds=120),
            )

            await workflow.execute_activity(
                update_document_status_activity,
                args=[document_id, "processed"],
                start_to_close_timeout=timedelta(seconds=10),
            )

            return {
                "document_id": document_id,
                "event_count": event_count,
                "status": "processed",
                "refs_resolved": resolve_result.get("resolved", 0),
            }

        except Exception as exc:
            await workflow.execute_activity(
                update_document_status_activity,
                args=[document_id, "failed", str(exc)],
                start_to_close_timeout=timedelta(seconds=10),
            )
            raise
