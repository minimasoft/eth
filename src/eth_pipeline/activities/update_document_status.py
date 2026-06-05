"""Update a document's status in PostgreSQL."""

from __future__ import annotations

from temporalio import activity

from eth_pipeline.activities._common import _db_params
from eth_pipeline.db import get_db
from eth_pipeline.processing_log import ProcessingLogger


@activity.defn
async def update_document_status_activity(
    document_id: str,
    status: str,
    error_message: str | None = None,
) -> dict:
    params = _db_params()
    _log = ProcessingLogger(params)

    activity.logger.info(
        "update_document_status_activity called [document_id=%s] [status=%s]",
        document_id,
        status,
    )
    await _log.log(document_id, "update_status", "info",
                   f"Setting status to {status}",
                   {"new_status": status, "error_message": error_message})

    try:
        async with get_db(**params) as conn:
            if error_message is None:
                await conn.execute(
                    "UPDATE document SET status = $2, "
                    "error_message = NULL, updated_at = NOW() "
                    "WHERE id = $1",
                    document_id, status,
                )
            else:
                await conn.execute(
                    "UPDATE document SET status = $2, "
                    "error_message = $3, updated_at = NOW() "
                    "WHERE id = $1",
                    document_id, status, error_message,
                )
    except ConnectionError as exc:
        activity.logger.error(
            "PostgreSQL connection failed in update_document_status_activity: %s",
            exc,
        )
        await _log.log(document_id, "update_status", "error",
                       f"Failed to update status to {status}: {exc}")
        return {"error": str(exc), "document_id": document_id}
    except Exception as exc:
        activity.logger.error(
            "Unexpected error in update_document_status_activity: %s",
            exc,
        )
        await _log.log(document_id, "update_status", "error",
                       f"Failed to update status to {status}: {exc}")
        return {"error": str(exc), "document_id": document_id}

    activity.logger.info(
        "update_document_status_activity completed [document_id=%s] [status=%s]",
        document_id,
        status,
    )

    if status == "failed" and error_message:
        await _log.log(document_id, "update_status", "error",
                       f"Document processing failed: {error_message}")

    return {"document_id": document_id, "status": status}
