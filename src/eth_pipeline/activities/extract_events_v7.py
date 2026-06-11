"""Extract structured events from a single document chunk using the v7 schema.

IMPORTANT: Chunk text is fetched from the DB internally — it is NOT passed
as an activity argument. This avoids bloating Temporal event history with
large payloads (up to ~512KB per chunk). Always pass document_id+chunk_index
and let activities fetch what they need from the database.
"""

from __future__ import annotations

import os

from temporalio import activity

from eth_pipeline.activities._common import _db_params, _extract_query_results
from eth_pipeline.db import get_db
from eth_pipeline.llm import DEFAULT_MODEL, OpenRouterProvider
from eth_pipeline.llm_usage import record_llm_usage
from eth_pipeline.llm_call_recorder import record_llm_call_log
from eth_pipeline.processing_log import ProcessingLogger


@activity.defn
async def extract_events_v7_activity(
    document_id: str,
    chunk_index: int,
    prior_events: list[dict] | None = None,
) -> dict:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    _log = ProcessingLogger(_db_params())
    if not api_key:
        activity.logger.error("OPENROUTER_API_KEY not set — returning degraded result")
        await _log.log(document_id, "extract_events_v7", "warning",
                       "OPENROUTER_API_KEY not set — returning degraded result")
        return {"error": "OPENROUTER_API_KEY not set", "events": []}

    params = _db_params()
    async with get_db(**params) as conn:
        row = _extract_query_results(
            await conn.fetch(
                "SELECT text FROM document_chunk "
                "WHERE document = $1 AND chunk_index = $2",
                document_id,
                chunk_index,
            )
        )
    if not row:
        raise ValueError(
            f"Chunk {chunk_index} not found for document {document_id}"
        )
    chunk_text: str = row[0]["text"]

    model = os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL)
    provider = OpenRouterProvider(api_key=api_key, model=model)

    activity.logger.info(
        "extract_events_v7_activity called [document_id=%s] [chunk_index=%d] [text_length=%d] [model=%s]",
        document_id,
        chunk_index,
        len(chunk_text),
        model,
    )
    await _log.log(document_id, "extract_events_v7", "info",
                   f"Starting v7 event extraction: chunk {chunk_index}, {len(chunk_text)} chars",
                   {"chunk_index": chunk_index, "text_length": len(chunk_text), "model": model})

    try:
        chunk_result, usage = await provider.extract_events_v7(
            chunk_text, prior_events=prior_events
        )
    except RuntimeError as exc:
        msg = str(exc)
        if any(kw in msg.lower() for kw in ("refusal", "empty content", "non-json")):
            activity.logger.warning(
                "LLM v7 refusal detected [document_id=%s] [chunk_index=%d] [reason=%s]",
                document_id,
                chunk_index,
                msg[:200],
            )
            await _log.log(document_id, "extract_events_v7", "warning",
                           f"LLM refusal on chunk {chunk_index}: {msg[:200]}",
                           {"chunk_index": chunk_index, "refusal_reason": msg[:200]})
            return {"events": [], "refused": True, "refusal_reason": msg[:200]}
        raise

    if usage is not None:
        await record_llm_usage(
            db_params=params,
            document_id=document_id,
            step_name="extract_events_v7",
            chunk_index=chunk_index,
            model=model,
            prompt_tokens=usage["prompt_tokens"],
            completion_tokens=usage["completion_tokens"],
            total_tokens=usage["total_tokens"],
            duration_ms=usage["duration_ms"],
            cached_tokens=usage.get("cached_tokens"),
            cache_write_tokens=usage.get("cache_write_tokens"),
            reasoning_tokens=usage.get("reasoning_tokens"),
            cost=usage.get("cost"),
            cost_source="openrouter" if usage.get("cost") is not None else None,
        )
        await record_llm_call_log(
            db_params=params,
            document_id=document_id,
            activity_type="extract_events_v7",
            chunk_index=chunk_index,
            prompt_text=usage["prompt_text"],
            response_text=usage["response_text"],
            model=model,
            prompt_tokens=usage["prompt_tokens"],
            completion_tokens=usage["completion_tokens"],
            total_tokens=usage["total_tokens"],
            duration_ms=usage["duration_ms"],
            cached_tokens=usage.get("cached_tokens"),
            cost=usage.get("cost"),
        )

    if isinstance(chunk_result, list):
        chunk_result = {"events": chunk_result}

    result = {"events": chunk_result.get("events", [])}
    activity.logger.info(
        "extract_events_v7_activity completed [document_id=%s] [chunk_index=%d] [events=%d]",
        document_id,
        chunk_index,
        len(result["events"]),
    )
    await _log.log(document_id, "extract_events_v7", "info",
                   f"V7 extraction completed: {len(result['events'])} events from chunk {chunk_index}",
                   {"chunk_index": chunk_index, "events_extracted": len(result["events"])})
    return result
