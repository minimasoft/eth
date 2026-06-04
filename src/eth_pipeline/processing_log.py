"""
Fire-and-forget per-document processing audit logger for Temporal activities.

Each ``log()`` call opens its own SurrealDB connection, writes
one entry, and closes.  This is safe for Temporal activities
— no shared state, no replay contamination.

Log entries use deterministic IDs (SHA256(document_id + step_name +
sequence_number)[:16]) so that Temporal replay produces the same
records — no duplicates, no orphaned entries.
"""

from __future__ import annotations

import hashlib
import logging

from surrealdb.data.types.record_id import RecordID

from eth_pipeline.db import get_db

__all__ = ["ProcessingLogger"]

logger = logging.getLogger(__name__)

VALID_SEVERITIES = frozenset({"info", "warning", "error"})
"""Accepted severity values matching the document_event_log schema ASSERT."""

MAX_ENTRIES_PER_DOCUMENT = 100
"""Hard cap on the number of log entries per document (per D-08)."""


class ProcessingLogger:
    """Fire-and-forget per-document processing audit logger.

    Each log() call opens its own SurrealDB connection, writes
    one entry, and closes.  This is safe for Temporal activities
    — no shared state, no replay contamination.

    Parameters
    ----------
    db_params:
        SurrealDB connection parameters dict (url, user, password, ns, database)
        as produced by activities._db_params().
    """

    def __init__(self, db_params: dict) -> None:
        self._db_params = db_params
        # Sequence counter keyed by f"{document_id}:{step_name}"
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
            SurrealDB record ID hex portion of the document
            (e.g. ``"abc123"``).
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
        # 1. Validate severity
        if severity not in VALID_SEVERITIES:
            logger.warning(
                "Invalid severity '%s' for document %s step %s — defaulting to 'info'",
                severity,
                document_id,
                step_name,
            )
            severity = "info"

        # 2. Compute sequence number
        key = f"{document_id}:{step_name}"
        seq = self._seq_counter.get(key, 0)
        self._seq_counter[key] = seq + 1

        # 3. Compute deterministic record ID
        raw = f"{document_id}{step_name}{seq}"
        record_id = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

        # 4-7. Open connection, check cap, write entry (fire-and-forget)
        try:
            async with get_db(**self._db_params) as db:
                # 5. Enforce 100-entry cap
                doc_ref = f"document:{document_id}"
                count_result = await db.query(
                    "SELECT count() AS total FROM document_event_log "
                    "WHERE document = $doc_ref GROUP ALL",
                    {"doc_ref": doc_ref},
                )
                count = _parse_count(count_result)
                if count >= MAX_ENTRIES_PER_DOCUMENT:
                    logger.warning(
                        "Processing log cap reached for document %s — skipping entry",
                        document_id,
                    )
                    return

                # 6. Write the log entry (UPSERT with CONTENT — creates on first call,
                # updates on Temporal replay; created_at omitted because it has
                # READONLY constraint and DEFAULT time::now()).
                doc_record = RecordID("document", document_id)
                if details is None:
                    await db.query(
                        "UPSERT type::record('document_event_log', $rid) CONTENT { "
                        "document: $doc, step_name: $step, "
                        "severity: $sev, message: $msg, details: null "
                        "}",
                        {
                            "rid": record_id,
                            "doc": doc_record,
                            "step": step_name,
                            "sev": severity,
                            "msg": message,
                        },
                    )
                else:
                    await db.query(
                        "UPSERT type::record('document_event_log', $rid) CONTENT { "
                        "document: $doc, step_name: $step, "
                        "severity: $sev, message: $msg, details: $det "
                        "}",
                        {
                            "rid": record_id,
                            "doc": doc_record,
                            "step": step_name,
                            "sev": severity,
                            "msg": message,
                            "det": details,
                        },
                    )
        except ConnectionError:
            logger.warning(
                "ProcessingLogger: SurrealDB unavailable for document %s",
                document_id,
            )
        except Exception as exc:
            logger.warning(
                "ProcessingLogger: write failed for document %s: %s",
                document_id,
                exc,
            )


def _parse_count(raw_result: list | dict | None) -> int:
    """Extract count integer from a SurrealDB count query result.

    Mirrors the same helper in ``eth_pipeline.api``.
    """
    records: list[dict] = [
        r for r in (raw_result or []) if isinstance(r, dict)
    ]
    if not records:
        return 0
    cnt = records[0].get("total")
    if isinstance(cnt, dict):
        return int(cnt.get("value", 0))
    if cnt is not None:
        return int(cnt)
    return 0
