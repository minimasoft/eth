"""
Temporal workflow definitions for the eth-pipeline.

Workflows orchestrate the multi-step document processing lifecycle:
ingest -> event extraction -> verbatim reference resolution.

``DocumentProcessingV7Workflow`` is the single v7 pipeline workflow
that orchestrates text extraction, chunking, v7 event extraction,
reference resolution, and status tracking.
"""

from __future__ import annotations

from datetime import timedelta

from temporalio import activity, workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from eth_pipeline.activities import (  # noqa: TCH004
        chunk_document_activity,
        extract_events_v7_activity,
        extract_text_activity,
        get_document_metadata_activity,
        get_document_text_activity,
        resolve_references_v7_activity,
        store_events_v7_activity,
        update_document_status_activity,
    )
    from eth_pipeline.activities._common import _db_params, _extract_query_results
    from eth_pipeline.db import get_db

# Re-export so the worker can register by path.
__all__ = [
    "DocumentProcessingV7Workflow",
]


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
