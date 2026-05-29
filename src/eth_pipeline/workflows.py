"""
Temporal workflow definitions for the eth-pipeline.

Workflows orchestrate the multi-step document processing lifecycle:
ingest → event extraction → verbatim reference resolution.
"""

from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from eth_pipeline.activities import (  # noqa: TCH004
        extract_events_activity,
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
    Ethereum document.  It:
      1. Marks the document as ``processing``.
      2. Delegates raw-text event extraction to ``extract_events_activity``.
      3. Persists extracted events and verbatim references to SurrealDB
         via ``store_extraction_results_activity``.
      4. Marks the document as ``processed`` (or ``failed`` on error).
      5. Returns a summary dict.
    """

    @workflow.run
    async def run(self, document_id: str, text: str) -> dict:
        """Execute the document processing workflow.

        Parameters
        ----------
        document_id:
            Unique identifier of the document being processed.
        text:
            Raw document text to analyse.

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

            # Step 2: Extract events from raw text (with retries)
            result = await workflow.execute_activity(
                extract_events_activity,
                text,
                start_to_close_timeout=timedelta(seconds=60),
                retry_policy=RetryPolicy(
                    maximum_attempts=3,  # initial + 2 retries
                    initial_interval=timedelta(seconds=5),
                    backoff_coefficient=2.0,
                ),
            )

            # Step 3: Store extraction results in SurrealDB
            await workflow.execute_activity(
                store_extraction_results_activity,
                args=[document_id, result],
                start_to_close_timeout=timedelta(seconds=10),
            )

            # Step 4: Return summary
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
