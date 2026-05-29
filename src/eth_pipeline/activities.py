"""
Temporal activity definitions for the eth-pipeline.

Activities are the unit of execution invoked by workflows.  Each activity
is a plain async function decorated with ``@activity.defn``.
"""

from __future__ import annotations

import os

from temporalio import activity

from eth_pipeline.db import get_db
from eth_pipeline.llm import DEFAULT_MODEL, OpenRouterProvider

# ---------------------------------------------------------------------------
# SurrealDB connection helpers (read from env at runtime)
# ---------------------------------------------------------------------------


def _db_params() -> dict:
    """Return SurrealDB connection parameters from environment variables.

    Falls back to the same defaults used in ``eth_pipeline.db`` for local
    development when the env vars are not set.
    """
    return {
        "url": os.environ.get("SURREAL_URL", "ws://localhost:8000/rpc"),
        "user": os.environ.get("SURREAL_USER", "root"),
        "password": os.environ.get("SURREAL_PASS", "root"),
        "ns": os.environ.get("SURREAL_NS", "eth"),
        "database": os.environ.get("SURREAL_DB", "pipeline"),
    }


# ---------------------------------------------------------------------------
# Activities
# ---------------------------------------------------------------------------


@activity.defn
async def extract_events_activity(text: str) -> dict:
    """Extract structured events from raw document text via OpenRouter LLM.

    Reads ``OPENROUTER_API_KEY`` and ``OPENROUTER_MODEL`` from environment
    variables at runtime.  Falls back to a degraded error dict when the API
    key is missing, so the activity can be tested in dev without real
    credentials.

    Parameters
    ----------
    text:
        Raw document text from which events should be extracted.

    Returns
    -------
    dict
        Extracted event data matching ``EVENT_EXTRACTION_SCHEMA`` (top-level
        ``"events"`` key), or ``{"error": ..., "events": []}`` when the API
        key is absent.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        activity.logger.error("OPENROUTER_API_KEY not set — returning degraded result")
        return {"error": "OPENROUTER_API_KEY not set", "events": []}

    model = os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL)
    provider = OpenRouterProvider(api_key=api_key, model=model)

    activity.logger.info(
        "extract_events_activity called [text_length=%d] [model=%s]",
        len(text),
        model,
    )

    result = await provider.extract_events(text)
    events = result.get("events", [])
    activity.logger.info(
        "extract_events_activity completed [event_count=%d]",
        len(events),
    )
    return result


@activity.defn
async def update_document_status_activity(
    document_id: str,
    status: str,
    error_message: str | None = None,
) -> dict:
    """Update a document's status (and optional error_message) in SurrealDB.

    Connects to SurrealDB at runtime using environment variables, executes
    ``UPDATE $doc_id SET status = $status, error_message = $error,
    updated_at = time::now()``, and returns a summary dict.

    On connection failure, logs the error and returns an error dict
    (degraded — the workflow can continue or retry).

    Parameters
    ----------
    document_id:
        SurrealDB record ID of the document (e.g. ``"document:abc123"``).
    status:
        New status value (one of ``pending``, ``extracted``, ``processed``,
        ``failed``).
    error_message:
        Optional human-readable error description when ``status="failed"``.

    Returns
    -------
    dict
        ``{"document_id": ..., "status": status}`` on success, or
        ``{"error": ...}`` on connection failure.
    """
    params = _db_params()
    doc_ref = f"document:{document_id}"

    activity.logger.info(
        "update_document_status_activity called [document_id=%s] [status=%s]",
        document_id,
        status,
    )

    try:
        async with get_db(**params) as db:
            # Use inline UPDATE with f-string — SurrealDB v3 does not
            # accept variable-bound doc_refs in UPDATE statements.
            # For error_message, pass null directly via string for None.
            err_literal = "null" if error_message is None else f"'{error_message}'"
            await db.query(
                f"UPDATE {doc_ref} SET status = '{status}', "
                f"error_message = {err_literal}, updated_at = time::now()",
            )
    except ConnectionError as exc:
        activity.logger.error(
            "SurrealDB connection failed in update_document_status_activity: %s",
            exc,
        )
        return {"error": str(exc), "document_id": document_id}
    except Exception as exc:
        activity.logger.error(
            "Unexpected error in update_document_status_activity: %s",
            exc,
        )
        return {"error": str(exc), "document_id": document_id}

    activity.logger.info(
        "update_document_status_activity completed [document_id=%s] [status=%s]",
        document_id,
        status,
    )
    return {"document_id": document_id, "status": status}


@activity.defn
async def store_extraction_results_activity(
    document_id: str,
    result: dict,
) -> dict:
    """Persist extracted events and verbatim references to SurrealDB.

    **Idempotent**: First deletes any existing events and references for this
    document, then recreates them from *result*.  This makes replay safe —
    each execution starts from a clean slate.

    For each event in ``result["events"]``:
      1. Creates an ``event`` record with fields ``que_paso``, ``espacio``,
         ``tiempo``, ``humanos``, ``objetos``, ``document`` (record link),
         and ``extraction_confidence=1.0``.
      2. For each reference in the event's ``references`` array, creates a
         ``reference`` record linked to the created event via the returned
         event ID.

    On success, updates the document status to ``"processed"``.
    On error, updates the document status to ``"failed"`` with an
    ``error_message``.

    Parameters
    ----------
    document_id:
        SurrealDB record ID of the source document (e.g. ``"abc123"``).
    result:
        LLM extraction result dict with top-level ``"events"`` array.  Each
        event must contain at least ``"que_paso"`` and ``"references"``.

    Returns
    -------
    dict
        ``{"document_id": ..., "events_stored": N, "references_stored": M}``
        on success, or ``{"error": ..., "document_id": ...}`` on failure.
    """
    params = _db_params()
    doc_ref = f"document:{document_id}"
    events = result.get("events", [])

    activity.logger.info(
        "store_extraction_results_activity called [document_id=%s] "
        "[event_count=%d]",
        document_id,
        len(events),
    )

    if not events:
        activity.logger.warning(
            "store_extraction_results_activity: no events to store "
            "[document_id=%s]",
            document_id,
        )
        # Still mark as processed — no events is a valid extraction result.
        await update_document_status_activity(document_id, "processed")
        return {"document_id": document_id, "events_stored": 0, "references_stored": 0}

    try:
        async with get_db(**params) as db:
            # ---- Idempotent: delete existing events+references ----
            activity.logger.info(
                "Clearing prior extraction results [document_id=%s]",
                document_id,
            )
            # Inline DELETE with f-string - SurrealDB v3 variable
            # binding doesn't work for doc ref strings in DELETE queries.
            await db.query(
                f"DELETE reference WHERE event IN "
                "(SELECT id FROM event WHERE document = $doc_ref)",
                {"doc_ref": doc_ref},
            )
            await db.query(
                f"DELETE event WHERE document = $doc_ref",
                {"doc_ref": doc_ref},
            )

            # ---- Create events and collect their IDs ----
            total_references = 0
            for event_data in events:
                created = await db.create(
                    "event",
                    {
                        "que_paso": event_data.get("que_paso", ""),
                        "espacio": event_data.get("espacio"),
                        "tiempo": event_data.get("tiempo"),
                        "humanos": event_data.get("humanos"),
                        "objetos": event_data.get("objetos"),
                        "document": doc_ref,
                        "extraction_confidence": 1.0,
                    },
                )

                # The created record's id is typically at created["id"]
                # or the record itself.  SurrealDB returns the full record.
                event_id = None
                if isinstance(created, dict):
                    event_id = created.get("id")
                if event_id is None:
                    # Fallback: create returns a list sometimes
                    if isinstance(created, list) and len(created) > 0:
                        event_id = created[0].get("id") if isinstance(created[0], dict) else None

                if event_id is None:
                    activity.logger.error(
                        "Could not extract event id from create result: %s",
                        created,
                    )
                    continue

                # ---- Create references linked to this event ----
                references = event_data.get("references", [])
                for ref in references:
                    await db.create(
                        "reference",
                        {
                            "reference_type": ref.get("reference_type", ""),
                            "verbatim_text": ref.get("verbatim_text", ""),
                            "span_start": int(ref.get("span_start", 0)),
                            "span_end": int(ref.get("span_end", 0)),
                            "event": event_id,
                        },
                    )
                    total_references += 1

            events_stored = len(events)
            activity.logger.info(
                "Stored %d events and %d references [document_id=%s]",
                events_stored,
                total_references,
                document_id,
            )
    except ConnectionError as exc:
        activity.logger.error(
            "SurrealDB connection failed in store_extraction_results_activity: "
            "%s",
            exc,
        )
        await update_document_status_activity(document_id, "failed", str(exc))
        return {"error": str(exc), "document_id": document_id}
    except Exception as exc:
        activity.logger.error(
            "Unexpected error in store_extraction_results_activity: %s",
            exc,
        )
        await update_document_status_activity(document_id, "failed", str(exc))
        return {"error": str(exc), "document_id": document_id}

    # Mark document as processed
    await update_document_status_activity(document_id, "processed")

    return {
        "document_id": document_id,
        "events_stored": len(events),
        "references_stored": total_references,
    }
