"""
Fire-and-forget per-document processing audit logger for Temporal activities.

Each ``log()`` call opens its own PostgreSQL connection, writes
one entry, and closes.  This is safe for Temporal activities
— no shared state, no replay contamination.

Log entries use deterministic IDs (SHA256(document_id + step_name +
sequence_number)[:16]) so that Temporal replay produces the same
records — no duplicates, no orphaned entries.
"""

from __future__ import annotations

import hashlib
import logging

from eth_pipeline.db import get_db

__all__ = ["ProcessingLogger"]

logger = logging.getLogger(__name__)

VALID_SEVERITIES = frozenset({"info", "warning", "error"})
"""Accepted severity values matching the document_event_log schema ASSERT."""

MAX_ENTRIES_PER_DOCUMENT = 100
"""Hard cap on the number of log entries per document (per D-08)."""


class ProcessingLogger:
    """Fire-and-forget per-document processing audit logger.

    Each log() call opens its own PostgreSQL connection, writes
    one entry, and closes.  This is safe for Temporal activities
    — no shared state, no replay contamination.

    Parameters
    ----------
    db_params:
        PostgreSQL connection parameters dict (host, port, user, password, database)
        as produced by activities._db_params().
    """

    def __init__(self, db_params: dict) -> None:
        self._db_params = db_params
        self._seq_counter: dict[str, int] = {}

    async def log(
        self,
        document_id: str,
        step_name: str,
        severity: str,
        message: str,
        details: dict | None = None,
    ) -> None:
        """Write a single log entry for a document processing step.

        Parameters
        ----------
        document_id:
            Document ID (e.g. ``"abc123"``).
        step_name:
            Processing step name (e.g. ``"extract_text"``,
            ``"extract_events"``).
        severity:
            Log severity — one of ``"info"``, ``"warning"``, ``"error"``.
            Invalid values default to ``"info"``.
        message:
            Human-readable log message.
        details:
            Optional structured metadata attached to this entry.
        """
        if severity not in VALID_SEVERITIES:
            logger.warning(
                "Invalid severity '%s' for document %s step %s — defaulting to 'info'",
                severity,
                document_id,
                step_name,
            )
            severity = "info"

        key = f"{document_id}:{step_name}"
        seq = self._seq_counter.get(key, 0)
        self._seq_counter[key] = seq + 1

        raw = f"{document_id}{step_name}{seq}"
        record_id = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

        try:
            async with get_db(**self._db_params) as conn:
                row = await conn.fetchrow(
                    "SELECT COUNT(*) AS total FROM document_event_log WHERE document = $1",
                    document_id,
                )
                count = row["total"] if row else 0
                if count >= MAX_ENTRIES_PER_DOCUMENT:
                    logger.warning(
                        "Processing log cap reached for document %s — skipping entry",
                        document_id,
                    )
                    return

                if details is None:
                    await conn.execute(
                        "INSERT INTO document_event_log (id, document, step_name, severity, message, details) "
                        "VALUES ($1, $2, $3, $4, $5, NULL) "
                        "ON CONFLICT (id) DO UPDATE SET step_name = $3, severity = $4, message = $5, details = NULL",
                        record_id, document_id, step_name, severity, message,
                    )
                else:
                    await conn.execute(
                        "INSERT INTO document_event_log (id, document, step_name, severity, message, details) "
                        "VALUES ($1, $2, $3, $4, $5, $6) "
                        "ON CONFLICT (id) DO UPDATE SET step_name = $3, severity = $4, message = $5, details = $6",
                        record_id, document_id, step_name, severity, message, details,
                    )
        except ConnectionError:
            logger.warning(
                "ProcessingLogger: PostgreSQL unavailable for document %s",
                document_id,
            )
        except Exception as exc:
            logger.warning(
                "ProcessingLogger: write failed for document %s: %s",
                document_id,
                exc,
            )
