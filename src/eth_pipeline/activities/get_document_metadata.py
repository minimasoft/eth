"""Retrieve document metadata to determine processing path."""

from __future__ import annotations

from temporalio import activity

from eth_pipeline.activities._common import _db_params, _extract_query_results
from eth_pipeline.db import get_db
from eth_pipeline.processing_log import ProcessingLogger


@activity.defn
async def get_document_metadata_activity(document_id: str) -> dict:
    params = _db_params()
    _log = ProcessingLogger(params)

    activity.logger.info(
        "get_document_metadata_activity called [document_id=%s]",
        document_id,
    )
    await _log.log(document_id, "get_document_metadata", "info",
                   "Starting document metadata retrieval")

    try:
        async with get_db(**params) as conn:
            rows = _extract_query_results(
                await conn.fetch(
                    "SELECT blob_format, text_content, filename, mime_type "
                    "FROM document WHERE id = $1",
                    document_id,
                )
            )
            if not rows:
                activity.logger.warning(
                    "Document not found [document_id=%s]",
                    document_id,
                )
                await _log.log(document_id, "get_document_metadata", "warning",
                               "Document not found in database")
                return {"error": "Document not found", "document_id": document_id}

            doc = rows[0]
            text_content = doc.get("text_content")
            has_text_content = text_content is not None and text_content != ""

            activity.logger.info(
                "get_document_metadata_activity completed "
                "[document_id=%s] [blob_format=%s] [has_text_content=%s]",
                document_id,
                doc.get("blob_format"),
                has_text_content,
            )
            await _log.log(document_id, "get_document_metadata", "info",
                           f"Metadata retrieved: blob_format={doc.get('blob_format')}, "
                           f"has_text_content={has_text_content}",
                           {"blob_format": doc.get("blob_format"),
                            "has_text_content": has_text_content})

            return {
                "document_id": document_id,
                "blob_format": doc.get("blob_format"),
                "has_text_content": has_text_content,
            }

    except ConnectionError as exc:
        activity.logger.error(
            "PostgreSQL connection failed in get_document_metadata_activity: %s",
            exc,
        )
        await _log.log(document_id, "get_document_metadata", "error",
                       f"PostgreSQL connection failed: {exc}")
        return {"error": str(exc), "document_id": document_id}
    except Exception as exc:
        activity.logger.error(
            "Unexpected error in get_document_metadata_activity: %s",
            exc,
        )
        await _log.log(document_id, "get_document_metadata", "error",
                       f"Unexpected error: {exc}")
        return {"error": str(exc), "document_id": document_id}
