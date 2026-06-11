"""Query helper activities for the v7 pipeline.

Fetches document chunks and prior events from PostgreSQL for context
injection during LLM-based event extraction.
"""

from __future__ import annotations

from temporalio import activity

from eth_pipeline.activities._common import _db_params, _extract_query_results
from eth_pipeline.db import get_db


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
