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

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from eth_pipeline.activities import (  # noqa: TCH004
        chunk_document_activity,
        extract_events_activity,
        extract_text_activity,
        get_document_metadata_activity,
        resolve_entities_activity,
        store_extraction_results_activity,
        update_document_status_activity,
    )

# Re-export so the worker can register by path.
__all__ = [
    "DocumentProcessingWorkflow",
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
        7. ``store_extraction_results_activity(document_id, result)``
        8. ``resolve_entities_activity(document_id, result)``
        9. ``processed`` — set only after ALL steps complete
        10. Return summary dict with ``document_id``, ``event_count``,
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
                    start_to_close_timeout=timedelta(seconds=10),
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

            # Step 5: Store extraction results
            store_result = await workflow.execute_activity(
                store_extraction_results_activity,
                args=[document_id, result],
                start_to_close_timeout=timedelta(seconds=10),
            )
            if "error" in store_result:
                raise RuntimeError(store_result["error"])

            # Step 6: Resolve verbatim references
            resolve_result = await workflow.execute_activity(
                resolve_entities_activity,
                args=[document_id, result],
                start_to_close_timeout=timedelta(seconds=30),
            )
            if "error" in resolve_result:
                raise RuntimeError(resolve_result["error"])

            # Step 7: Mark as fully processed (only after all steps complete)
            await workflow.execute_activity(
                update_document_status_activity,
                args=[document_id, "processed"],
                start_to_close_timeout=timedelta(seconds=10),
            )

            # Step 8: Return summary
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
