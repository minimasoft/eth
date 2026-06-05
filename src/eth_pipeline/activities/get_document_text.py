"""Retrieve the full reconstructed text content for a document."""

from __future__ import annotations

from temporalio import activity

from eth_pipeline.activities._common import _db_params, _extract_query_results
from eth_pipeline.db import get_db
from eth_pipeline.processing_log import ProcessingLogger


@activity.defn
async def get_document_text_activity(document_id: str) -> dict:
    params = _db_params()
    _log = ProcessingLogger(params)

    activity.logger.info(
        "get_document_text_activity called [document_id=%s]",
        document_id,
    )
    await _log.log(document_id, "get_document_text", "info",
                   "Starting document text retrieval")

    try:
        async with get_db(**params) as conn:
            rows = _extract_query_results(
                await conn.fetch(
                    "SELECT text_content FROM document WHERE id = $1",
                    document_id,
                )
            )
            if not rows:
                activity.logger.warning(
                    "Document not found [document_id=%s]",
                    document_id,
                )
                await _log.log(document_id, "get_document_text", "warning",
                               "Document not found in database")
                return {"error": "Document not found", "document_id": document_id}

            text_content = rows[0].get("text_content") or ""

            activity.logger.info(
                "get_document_text_activity completed "
                "[document_id=%s] [text_length=%d]",
                document_id,
                len(text_content),
            )
            await _log.log(document_id, "get_document_text", "info",
                           f"Text retrieval completed: {len(text_content)} bytes",
                           {"text_length": len(text_content)})

            return {
                "document_id": document_id,
                "text_content": text_content,
                "text_length": len(text_content),
            }

    except ConnectionError as exc:
        activity.logger.error(
            "PostgreSQL connection failed in get_document_text_activity: %s",
            exc,
        )
        await _log.log(document_id, "get_document_text", "error",
                       f"PostgreSQL connection failed: {exc}")
        return {"error": str(exc), "document_id": document_id}
    except Exception as exc:
        activity.logger.error(
            "Unexpected error in get_document_text_activity: %s",
            exc,
        )
        await _log.log(document_id, "get_document_text", "error",
                       f"Unexpected error: {exc}")
        return {"error": str(exc), "document_id": document_id}
