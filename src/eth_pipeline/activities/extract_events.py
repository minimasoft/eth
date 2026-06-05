"""Extract structured events from document text via OpenRouter LLM."""

from __future__ import annotations

import os

from temporalio import activity

from eth_pipeline.activities._common import _db_params, _extract_query_results
from eth_pipeline.db import get_db
from eth_pipeline.llm import DEFAULT_MODEL, EXTRACTION_CHUNK_SIZE, OpenRouterProvider
from eth_pipeline.llm_usage import record_llm_usage
from eth_pipeline.processing_log import ProcessingLogger


@activity.defn
async def extract_events_activity(document_id: str) -> dict:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    _log = ProcessingLogger(_db_params())
    if not api_key:
        activity.logger.error("OPENROUTER_API_KEY not set — returning degraded result")
        await _log.log(document_id, "extract_events", "warning",
                       "OPENROUTER_API_KEY not set — returning degraded result")
        return {"error": "OPENROUTER_API_KEY not set", "events": []}

    model = os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL)
    provider = OpenRouterProvider(api_key=api_key, model=model)

    params = _db_params()

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
                await _log.log(document_id, "extract_events", "warning",
                               "Document not found in database")
                return {"error": "Document not found", "document_id": document_id}
            text = rows[0].get("text_content") or ""
    except ConnectionError as exc:
        activity.logger.error(
            "PostgreSQL connection failed in extract_events_activity: %s",
            exc,
        )
        await _log.log(document_id, "extract_events", "error",
                       f"Connection failed: {exc}")
        return {"error": str(exc), "document_id": document_id}

    activity.logger.info(
        "extract_events_activity called [document_id=%s] [text_length=%d] [model=%s]",
        document_id,
        len(text),
        model,
    )
    await _log.log(document_id, "extract_events", "info",
                   f"Starting event extraction: {len(text)} chars, model={model}",
                   {"text_length": len(text), "model": model})

    if len(text) > EXTRACTION_CHUNK_SIZE:
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=EXTRACTION_CHUNK_SIZE,
            chunk_overlap=0,
            separators=["\n\n", "\n", ". ", " ", ""],
        )
        chunks = splitter.split_text(text)
        activity.logger.info(
            "Split document into %d chunks for sequential extraction "
            "[document_id=%s]",
            len(chunks),
            document_id,
        )
    else:
        chunks = [text]

    all_events: list[dict] = []
    for i, chunk in enumerate(chunks):
        prior = all_events if all_events else None
        activity.logger.info(
            "Extracting chunk %d/%d [document_id=%s] [chunk_length=%d] "
            "[prior_events=%d]",
            i + 1,
            len(chunks),
            document_id,
            len(chunk),
            len(all_events),
        )
        chunk_result, usage = await provider.extract_events(chunk, prior_events=prior)
        if usage is not None:
            await record_llm_usage(
                db_params=params,
                document_id=document_id,
                step_name="extract_events",
                chunk_index=i,
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
        if isinstance(chunk_result, list):
            chunk_result = {"events": chunk_result}
        chunk_events = chunk_result.get("events", [])
        activity.logger.info(
            "Chunk %d/%d returned %d events [document_id=%s]",
            i + 1,
            len(chunks),
            len(chunk_events),
            document_id,
        )
        await _log.log(document_id, "extract_events", "info",
                       f"Chunk {i+1}/{len(chunks)}: {len(chunk_events)} events extracted",
                       {"chunk_index": i, "total_chunks": len(chunks), "events_in_chunk": len(chunk_events)})
        all_events.extend(chunk_events)

    result = {"events": all_events}
    activity.logger.info(
        "extract_events_activity completed [document_id=%s] [total_events=%d]",
        document_id,
        len(all_events),
    )
    await _log.log(document_id, "extract_events", "info",
                   f"Event extraction completed: {len(all_events)} total events",
                   {"total_events": len(all_events), "chunks_processed": len(chunks)})
    return result
