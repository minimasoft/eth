"""Resolve verbatim references to document-absolute character offsets in source chunks."""

from __future__ import annotations

import re

from temporalio import activity

from eth_pipeline.activities._common import _db_params, _extract_query_results
from eth_pipeline.db import get_db
from eth_pipeline.processing_log import ProcessingLogger


@activity.defn
async def resolve_references_v7_activity(document_id: str) -> dict:
    params = _db_params()
    _log = ProcessingLogger(params)

    activity.logger.info(
        "resolve_references_v7_activity called [document_id=%s]",
        document_id,
    )

    try:
        async with get_db(**params) as conn:
            ref_rows = _extract_query_results(
                await conn.fetch(
                    "SELECT er.id, er.verbatim_text, er.span_start, er.span_end, "
                    "er.chunk_index, er.event_id "
                    "FROM event_ref er "
                    "JOIN event_document ed ON er.event_id = ed.event_id "
                    "WHERE ed.document_id = $1 "
                    "ORDER BY er.chunk_index, er.id",
                    document_id,
                )
            )

            chunk_rows = _extract_query_results(
                await conn.fetch(
                    "SELECT chunk_index, text, offset_start, offset_end "
                    "FROM document_chunk "
                    "WHERE document = $1 "
                    "ORDER BY chunk_index ASC",
                    document_id,
                )
            )
            chunk_map: dict[int, dict] = {row["chunk_index"]: row for row in chunk_rows}

            resolved = 0
            for ref in ref_rows:
                chunk = chunk_map.get(ref["chunk_index"])
                if chunk is None:
                    continue

                verbatim = ref["verbatim_text"]
                if not verbatim:
                    continue

                pos = chunk["text"].find(verbatim)
                if pos == -1:
                    match = re.search(re.escape(verbatim), chunk["text"], re.IGNORECASE)
                    if match:
                        pos = match.start()

                if pos == -1:
                    activity.logger.warning(
                        "verbatim_text not found in chunk [document_id=%s] "
                        "[chunk_index=%d] [ref_id=%s] [text=%.80s]",
                        document_id,
                        ref["chunk_index"],
                        ref["id"],
                        verbatim,
                    )
                    continue

                doc_span_start = chunk["offset_start"] + pos
                doc_span_end = doc_span_start + len(verbatim)

                await conn.execute(
                    "UPDATE event_ref SET span_start = $1, span_end = $2 WHERE id = $3",
                    doc_span_start,
                    doc_span_end,
                    ref["id"],
                )
                resolved += 1

    except ConnectionError as exc:
        activity.logger.error(
            "PostgreSQL connection failed in resolve_references_v7_activity: %s",
            exc,
        )
        await _log.log(document_id, "resolve_refs_v7", "error",
                       f"Connection failed: {exc}")
        return {"error": str(exc), "document_id": document_id}
    except Exception as exc:
        import json
        import traceback

        error_detail = {
            "type": type(exc).__name__,
            "message": str(exc),
            "repr": repr(exc),
            "traceback": traceback.format_exc()[-2000:],
            "document_id": document_id,
        }
        activity.logger.error(
            "Unexpected error in resolve_references_v7_activity: %s",
            json.dumps(error_detail, default=str),
        )
        await _log.log(document_id, "resolve_refs_v7", "error",
                       f"Unexpected error: {type(exc).__name__}: {exc}")
        return {"error": str(exc), "document_id": document_id}

    activity.logger.info(
        "resolve_references_v7_activity completed [document_id=%s] [resolved=%d/%d]",
        document_id,
        resolved,
        len(ref_rows),
    )
    await _log.log(document_id, "resolve_refs_v7", "info",
                   f"Reference resolution complete: {resolved}/{len(ref_rows)} resolved")

    return {
        "document_id": document_id,
        "resolved": resolved,
        "total": len(ref_rows),
    }
