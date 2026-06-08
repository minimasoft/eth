"""
Fire-and-forget LLM call log recorder for Temporal activities.

Each ``record_llm_call_log()`` call opens its own PostgreSQL connection, writes
one entry to the ``llm_call_log`` table, and closes.  This is safe for Temporal
activities — no shared state, no replay contamination.

Entries use deterministic IDs (SHA256(document_id:activity_type:chunk_index))
so that Temporal replay produces the same records — no duplicates.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any

from eth_pipeline.db import get_db

__all__ = ["record_llm_call_log"]

logger = logging.getLogger(__name__)


async def record_llm_call_log(
    db_params: dict[str, Any],
    document_id: str,
    activity_type: str,
    chunk_index: int,
    prompt_text: str,
    response_text: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    duration_ms: int,
    cached_tokens: int | None = None,
    cost: float | None = None,
) -> None:
    """Record a single LLM call into the ``llm_call_log`` table.

    Opens a PostgreSQL connection, writes one UPSERT entry with a
    deterministic SHA256 record ID, and closes.  Errors are logged at
    WARNING level but never raised — the caller (a Temporal activity)
    continues on failure.

    Parameters
    ----------
    db_params:
        PostgreSQL connection parameters dict (host, port, user, password, database)
        as produced by ``activities._db_params()``.
    document_id:
        Document ID (e.g. ``"abc123"``).
    activity_type:
        Activity type label — one of ``"extract_events"``,
        ``"resolve_entities"``, ``"resolve_entities_with_search"``.
    chunk_index:
        Zero-based chunk index within the activity (0 for single-call steps).
    prompt_text:
        Full prompt text sent to the LLM.
    response_text:
        Full response text received from the LLM.
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
    cost:
        Estimated monetary cost in USD (when reported by OpenRouter).
    """
    raw_id = f"{document_id}:{activity_type}:{chunk_index}"
    record_id = hashlib.sha256(raw_id.encode("utf-8")).hexdigest()
    timestamp = datetime.now(timezone.utc)

    try:
        async with get_db(**db_params) as conn:
            await conn.execute(
                "INSERT INTO llm_call_log "
                "(id, document, activity_type, chunk_index, prompt_text, "
                "response_text, model, prompt_tokens, completion_tokens, "
                "total_tokens, cached_tokens, cost, duration_ms, timestamp) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14) "
                "ON CONFLICT (id) DO UPDATE SET "
                "prompt_text = $5, response_text = $6, model = $7, "
                "prompt_tokens = $8, completion_tokens = $9, "
                "total_tokens = $10, duration_ms = $13",
                record_id, document_id, activity_type, chunk_index,
                prompt_text, response_text, model,
                prompt_tokens, completion_tokens, total_tokens,
                cached_tokens, cost, duration_ms, timestamp,
            )
            logger.debug(
                "Recorded LLM call log [doc=%s] [activity=%s] [chunk=%d] "
                "[model=%s] [tokens=%d+%d=%d] [dur=%dms]",
                document_id, activity_type, chunk_index, model,
                prompt_tokens, completion_tokens, total_tokens, duration_ms,
            )
    except ConnectionError:
        logger.warning(
            "record_llm_call_log: PostgreSQL unavailable for document %s activity %s",
            document_id,
            activity_type,
        )
    except Exception as exc:
        logger.warning(
            "record_llm_call_log: write failed for document %s activity %s: %s",
            document_id,
            activity_type,
            exc,
        )
