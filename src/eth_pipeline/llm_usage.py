"""
Fire-and-forget LLM token usage recorder for Temporal activities.

Each ``record_llm_usage()`` call opens its own SurrealDB connection, writes
one entry to the ``llm_usage`` table, and closes.  This is safe for Temporal
activities — no shared state, no replay contamination.

Entries use deterministic IDs (SHA256(document_id:step_name:chunk_index))
so that Temporal replay produces the same records — no duplicates.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from surrealdb.data.types.record_id import RecordID

from eth_pipeline.db import get_db

__all__ = ["record_llm_usage"]

logger = logging.getLogger(__name__)


async def record_llm_usage(
    db_params: dict[str, Any],
    document_id: str,
    step_name: str,
    chunk_index: int,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    duration_ms: int,
    cached_tokens: int | None = None,
    cache_write_tokens: int | None = None,
    reasoning_tokens: int | None = None,
    cost: float | None = None,
    cost_source: str | None = None,
) -> None:
    """Record a single LLM usage entry into the ``llm_usage`` table.

    Opens a SurrealDB connection, writes one UPSERT entry with a
    deterministic SHA256 record ID, and closes.  Errors are logged at
    WARNING level but never raised — the caller (a Temporal activity)
    continues on failure.

    Parameters
    ----------
    db_params:
        SurrealDB connection parameters dict (url, user, password, ns, database)
        as produced by ``activities._db_params()``.
    document_id:
        SurrealDB record ID hex portion of the document (e.g. ``"abc123"``).
    step_name:
        Processing step name — one of ``"extract_events"``,
        ``"resolve_entities"``, ``"resolve_entities_with_search"``.
    chunk_index:
        Zero-based chunk index within the step (0 for single-call steps).
    model:
        Model identifier as returned by OpenRouter.
    prompt_tokens:
        Number of prompt (input) tokens.
    completion_tokens:
        Number of completion (output) tokens.
    total_tokens:
        Sum of prompt + completion tokens.
    duration_ms:
        Wall-clock HTTP request duration in milliseconds.
    cached_tokens:
        Tokens served from cache (when reported by provider).
    cache_write_tokens:
        Tokens written to cache (when reported by provider).
    reasoning_tokens:
        Reasoning/deep-thinking tokens (when reported by provider).
    cost:
        Estimated monetary cost in USD (when reported by OpenRouter).
    cost_source:
        Source of cost data (``"openrouter"`` when reported by API).
    """
    raw_id = f"{document_id}:{step_name}:{chunk_index}"
    record_id = hashlib.sha256(raw_id.encode("utf-8")).hexdigest()

    doc_record = RecordID("document", document_id)

    try:
        async with get_db(**db_params) as db:
            await db.query(
                "UPSERT type::record('llm_usage', $rid) CONTENT { "
                "document: $doc, step_name: $step, "
                "chunk_index: $chunk, model: $model, "
                "prompt_tokens: $pt, completion_tokens: $ct, total_tokens: $tt, "
                "cached_tokens: $cached, cache_write_tokens: $cache_write, "
                "reasoning_tokens: $reasoning, cost: $cost, cost_source: $cost_source, "
                "duration_ms: $dur "
                "}",
                {
                    "rid": record_id,
                    "doc": doc_record,
                    "step": step_name,
                    "chunk": chunk_index,
                    "model": model,
                    "pt": prompt_tokens,
                    "ct": completion_tokens,
                    "tt": total_tokens,
                    "cached": cached_tokens,
                    "cache_write": cache_write_tokens,
                    "reasoning": reasoning_tokens,
                    "cost": cost,
                    "cost_source": cost_source,
                    "dur": duration_ms,
                },
            )
            logger.debug(
                "Recorded LLM usage [doc=%s] [step=%s] [chunk=%d] "
                "[model=%s] [tokens=%d+%d=%d] [dur=%dms]",
                document_id, step_name, chunk_index, model,
                prompt_tokens, completion_tokens, total_tokens, duration_ms,
            )
    except ConnectionError:
        logger.warning(
            "record_llm_usage: SurrealDB unavailable for document %s step %s",
            document_id,
            step_name,
        )
    except Exception as exc:
        logger.warning(
            "record_llm_usage: write failed for document %s step %s: %s",
            document_id,
            step_name,
            exc,
        )
