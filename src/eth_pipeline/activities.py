"""
Temporal activity definitions for the eth-pipeline.

Activities are the unit of execution invoked by workflows.  Each activity
is a plain async function decorated with ``@activity.defn``.
"""

from __future__ import annotations

import asyncio
import base64
import io
import os

from surrealdb.data.types.record_id import RecordID

from temporalio import activity

from eth_pipeline.chunker import DocumentChunker
from eth_pipeline.db import get_db
from eth_pipeline.extractors import (
    ExtractorQualityError,
    PdfExtractor,
)
from eth_pipeline.llm import DEFAULT_MODEL, OpenRouterProvider
from eth_pipeline.storage import get_storage

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


async def _get_blob_from_minio(blob_path: str) -> bytes:
    """Fetch a binary blob from MinIO asynchronously.

    The ``get_storage()`` context manager is synchronous, so we wrap it in
    ``asyncio.to_thread()`` to avoid blocking the Temporal worker's event
    loop.

    Parameters
    ----------
    blob_path:
        Object path within the configured MinIO bucket.

    Returns
    -------
    bytes
        The blob's raw content.

    Raises
    ------
    ConnectionError
        If MinIO is unreachable.
    OSError
        If the object cannot be read.
    """
    bucket = os.environ.get("MINIO_BUCKET", "eth-documents")

    def _fetch() -> bytes:
        with get_storage() as client:
            response = client.get_object(bucket, blob_path)
            data = response.read()
            response.close()
            response.release_conn()
            return data

    return await asyncio.to_thread(_fetch)


# ---------------------------------------------------------------------------
# Activities
# ---------------------------------------------------------------------------


@activity.defn
async def extract_events_activity(document_id: str) -> dict:
    """Extract structured events from document text via OpenRouter LLM.

    Queries ``text_content`` directly from SurrealDB (same pattern as
    ``resolve_entities_activity``) to avoid passing large payloads through
    Temporal's serialization layer.

    Reads ``OPENROUTER_API_KEY`` and ``OPENROUTER_MODEL`` from environment
    variables at runtime.  Falls back to a degraded error dict when the API
    key is missing, so the activity can be tested in dev without real
    credentials.

    Parameters
    ----------
    document_id:
        SurrealDB record ID of the document (e.g. ``"abc123"``).

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

    params = _db_params()
    doc_ref = f"document:{document_id}"

    try:
        async with get_db(**params) as db:
            raw = await db.query(f"SELECT text_content FROM {doc_ref}")
            rows = _extract_query_results(raw)
            if not rows:
                activity.logger.warning(
                    "Document not found [document_id=%s]",
                    document_id,
                )
                return {"error": "Document not found", "document_id": document_id}
            text = rows[0].get("text_content") or ""
    except ConnectionError as exc:
        activity.logger.error(
            "SurrealDB connection failed in extract_events_activity: %s",
            exc,
        )
        return {"error": str(exc), "document_id": document_id}

    activity.logger.info(
        "extract_events_activity called [document_id=%s] [text_length=%d] [model=%s]",
        document_id,
        len(text),
        model,
    )

    result = await provider.extract_events(text)
    events = result.get("events", [])
    activity.logger.info(
        "extract_events_activity completed [document_id=%s] [event_count=%d]",
        document_id,
        len(events),
    )
    return result


@activity.defn
async def resolve_entities_activity(document_id: str, result: dict) -> dict:
    """Resolve verbatim references to canonical entities using LLM matching.

    **Replay-safe**: First nullifies any prior ``canonical_entity`` and
    ``resolution_confidence`` links on all references for this document, then
    re-resolves from scratch.  This guarantees idempotency across retries.

    References are grouped by ``reference_type`` with the following mapping::

        espacio  → place   (resolved)
        humanos  → person  (resolved)
        objetos  → object  (resolved)
        tiempo   → skipped (not resolved — temporal references lack a
                  canonical entity category in this model)

    For each present reference type, the activity:
      1. Queries existing ``canonical_entity`` records of that type.
      2. Calls ``OpenRouterProvider.resolve_references()`` (batched per type).
      3. Applies results: creates new canonical entities when the LLM says
         ``create_new``, links references to existing entities via
         ``match_existing``, or creates tentative entities for ``uncertain``.
      4. Updates each reference's ``canonical_entity`` and
         ``resolution_confidence`` fields.

    LLM failures for individual type batches are logged but do **not** block
    resolution of other reference types.

    Parameters
    ----------
    document_id:
        SurrealDB record ID of the document (e.g. ``"abc123"``).
    result:
        LLM extraction result dict (top-level ``"events"`` array).  The
        document's ``text_content`` is queried directly from SurrealDB for
        the LLM context window.

    Returns
    -------
    dict
        ``{"document_id": ..., "resolved": N, "created": N, "skipped": N}``
        on success, or ``{"error": ..., "document_id": ...}`` on failure.
    """
    params = _db_params()
    doc_ref = f"document:{document_id}"
    events = result.get("events", [])

    activity.logger.info(
        "resolve_entities_activity called [document_id=%s] [event_count=%d]",
        document_id,
        len(events),
    )

    if not events:
        activity.logger.info(
            "No events — nothing to resolve [document_id=%s]",
            document_id,
        )
        return {"document_id": document_id, "resolved": 0, "created": 0, "skipped": 0}

    try:
        async with get_db(**params) as db:
            # ------------------------------------------------------------------
            # 1. Query all references for this document
            # ------------------------------------------------------------------
            refs_raw = await db.query(
                "SELECT * FROM reference WHERE event IN "
                "(SELECT id FROM event WHERE document = $doc_ref)",
                {"doc_ref": doc_ref},
            )
            references = _extract_query_results(refs_raw)

            if not references:
                activity.logger.info(
                    "No references found [document_id=%s]",
                    document_id,
                )
                return {
                    "document_id": document_id,
                    "resolved": 0,
                    "created": 0,
                    "skipped": 0,
                }

            # ------------------------------------------------------------------
            # 2. Nullify prior resolution links (replay safety)
            # ------------------------------------------------------------------
            activity.logger.info(
                "Nullifying prior resolution links [document_id=%s] [ref_count=%d]",
                document_id,
                len(references),
            )
            await db.query(
                "UPDATE reference SET canonical_entity = null, "
                "resolution_confidence = null "
                "WHERE event IN (SELECT id FROM event WHERE document = $doc_ref)",
                {"doc_ref": doc_ref},
            )

            # ------------------------------------------------------------------
            # 3. Group references by mapped entity type
            # ------------------------------------------------------------------
            type_map = {"espacio": "place", "humanos": "person", "objetos": "object"}
            skip_types = {"tiempo"}

            groups: dict[str, list[dict]] = {}
            for ref in references:
                ref_type = ref.get("reference_type", "")
                if ref_type in skip_types:
                    continue
                mapped = type_map.get(ref_type)
                if mapped:
                    groups.setdefault(mapped, []).append(ref)

            skipped_count = len(
                [r for r in references if r.get("reference_type") in skip_types]
            )

            # ------------------------------------------------------------------
            # Fetch document context for LLM prompts
            # ------------------------------------------------------------------
            doc_raw = await db.query(
                f"SELECT text_content FROM {doc_ref}",
            )
            doc_rows = _extract_query_results(doc_raw)
            document_context = doc_rows[0].get("text_content", "") if doc_rows else ""

            # ------------------------------------------------------------------
            # 4. Resolve each type group via LLM
            # ------------------------------------------------------------------
            api_key = os.environ.get("OPENROUTER_API_KEY")
            if not api_key:
                activity.logger.error(
                    "OPENROUTER_API_KEY not set — cannot resolve entities "
                    "[document_id=%s]",
                    document_id,
                )
                return {
                    "error": "OPENROUTER_API_KEY not set",
                    "document_id": document_id,
                }

            model = os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL)
            provider = OpenRouterProvider(api_key=api_key, model=model)

            total_resolved = 0
            total_created = 0

            for entity_type, refs in groups.items():
                if not refs:
                    continue

                # Query existing canonical entities of this type
                existing_raw = await db.query(
                    "SELECT * FROM canonical_entity WHERE entity_type = $type",
                    {"type": entity_type},
                )
                existing_entities = _extract_query_results(existing_raw)

                activity.logger.info(
                    "Resolving %d %s references against %d existing entities "
                    "[document_id=%s]",
                    len(refs),
                    entity_type,
                    len(existing_entities),
                    document_id,
                )

                # ---- LLM batch resolution ----
                try:
                    resolution = await provider.resolve_references(
                        references=refs,
                        existing_entities=existing_entities,
                        document_context=document_context,
                    )
                except Exception as exc:
                    activity.logger.error(
                        "LLM resolution failed for %s references "
                        "[document_id=%s]: %s",
                        entity_type,
                        document_id,
                        exc,
                    )
                    continue

                resolutions = resolution.get("resolutions", [])
                if not resolutions:
                    activity.logger.warning(
                        "LLM returned empty resolutions for %s references "
                        "[document_id=%s]",
                        entity_type,
                        document_id,
                    )
                    continue

                # Build verbatim_text → [ref_id] lookup
                verbatim_to_refs: dict[str, list[str]] = {}
                for r in refs:
                    vt = r.get("verbatim_text", "")
                    rid = r.get("id")
                    if vt and rid:
                        verbatim_to_refs.setdefault(vt, []).append(rid)

                # ---- Apply each resolution ----
                for res in resolutions:
                    ref_text = res.get("reference_verbatim", "")
                    action = res.get("action", "uncertain")
                    confidence = float(res.get("confidence", 0.5))
                    matched_ids = verbatim_to_refs.get(ref_text, [])

                    if not matched_ids:
                        activity.logger.debug(
                            "No matching reference for verbatim '%s' "
                            "[document_id=%s]",
                            ref_text,
                            document_id,
                        )
                        continue

                    if action == "create_new":
                        ce_id = await _create_canonical_entity(
                            db,
                            res.get("new_entity_name", ref_text),
                            res.get("new_entity_type", entity_type),
                            res.get("new_entity_properties") or {},
                        )
                    elif action == "match_existing":
                        ce_id = res.get("matched_entity_id")
                    else:  # uncertain
                        # Create a tentative entity for later human review
                        ce_id = await _create_canonical_entity(
                            db,
                            res.get("new_entity_name", ref_text),
                            res.get("new_entity_type", entity_type),
                            res.get("new_entity_properties") or {},
                        )

                    if ce_id:
                        total_created += 1 if action in ("create_new", "uncertain") else 0
                        for rid in matched_ids:
                            try:
                                # SurrealDB Python SDK supports UPDATE with
                                # variable binding for SET values even when
                                # the target uses an f-string record ref.
                                await db.query(
                                    f"UPDATE {rid} SET "
                                    f"canonical_entity = $ce, "
                                    f"resolution_confidence = $conf",
                                    {"ce": ce_id, "conf": confidence},
                                )
                                total_resolved += 1
                            except Exception as exc:
                                activity.logger.error(
                                    "Failed to update reference %s with "
                                    "canonical_entity %s: %s",
                                    rid,
                                    ce_id,
                                    exc,
                                )

            activity.logger.info(
                "resolve_entities_activity completed [document_id=%s] "
                "[resolved=%d] [created=%d] [skipped=%d]",
                document_id,
                total_resolved,
                total_created,
                skipped_count,
            )

            return {
                "document_id": document_id,
                "resolved": total_resolved,
                "created": total_created,
                "skipped": skipped_count,
            }

    except ConnectionError as exc:
        activity.logger.error(
            "SurrealDB connection failed in resolve_entities_activity: %s",
            exc,
        )
        return {"error": str(exc), "document_id": document_id}
    except Exception as exc:
        activity.logger.error(
            "Unexpected error in resolve_entities_activity: %s",
            exc,
        )
        return {"error": str(exc), "document_id": document_id}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_query_results(raw: list | dict | None) -> list[dict]:
    """Extract result rows from a SurrealDB ``db.query()`` response.

    SurrealDB ``query()`` returns a list of response statements, each being
    a dict with a ``"result"`` key containing the actual rows.  This helper
    normalises the various shapes into a flat list of row dicts.
    """
    if not raw:
        return []
    if isinstance(raw, dict):
        rows = raw.get("result", [])
        return rows if isinstance(rows, list) else [rows] if isinstance(rows, dict) else []
    if isinstance(raw, list):
        # Each element may be a dict with a "result" key, or already a list
        flat: list[dict] = []
        for item in raw:
            if isinstance(item, dict) and "result" in item:
                rows = item["result"]
                if isinstance(rows, list):
                    flat.extend(rows)
                elif isinstance(rows, dict):
                    flat.append(rows)
            elif isinstance(item, list):
                flat.extend(item)
            elif isinstance(item, dict):
                flat.append(item)
        return flat
    return []


async def _create_canonical_entity(
    db,
    name: str,
    entity_type: str,
    properties: dict | None,
) -> str | None:
    """Create a ``canonical_entity`` record and return its SurrealDB record ID.

    Returns ``None`` if creation fails or the result cannot be parsed.
    """
    data: dict = {
        "name": name,
        "entity_type": entity_type,
        "properties": properties or {},
    }
    try:
        created = await db.create("canonical_entity", data)
        if isinstance(created, dict):
            return created.get("id")
        if isinstance(created, list) and created:
            first = created[0]
            if isinstance(first, dict):
                return first.get("id")
    except Exception as exc:
        logger = activity.logger if hasattr(activity, "logger") else __import__("logging").getLogger(__name__)
        logger.error(
            "Failed to create canonical_entity [name=%s] [type=%s]: %s",
            name,
            entity_type,
            exc,
        )
    return None


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
            if error_message is None:
                await db.query(
                    f"UPDATE {doc_ref} SET status = $status, "
                    "error_message = null, updated_at = time::now()",
                    {"status": status},
                )
            else:
                await db.query(
                    f"UPDATE {doc_ref} SET status = $status, "
                    "error_message = $error_message, updated_at = time::now()",
                    {"status": status, "error_message": error_message},
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
    doc_record = RecordID("document", document_id)
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
                        "document": doc_record,
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


# ---------------------------------------------------------------------------
# PDF Text Extraction + Chunking activities (Phase 7)
# ---------------------------------------------------------------------------


@activity.defn
async def extract_text_activity(document_id: str) -> dict:
    """Extract text from a blob-stored document.

    Reads the document record from SurrealDB to get ``blob_format``,
    ``blob_path``, ``filename``, and ``mime_type``.  If
    ``blob_format == "minio"``, fetches the blob from MinIO; otherwise
    decodes ``original_blob`` (legacy base64).

    Then detects the document format from the filename extension and
    mime type and branches accordingly:

    * **PDF** (``.pdf`` / ``application/pdf``) — runs ``PdfExtractor``.
    * **Plain text** (``.txt``, ``.md``, extensionless with text mime,
      or unknown) — decodes as UTF-8 with synthetic ``page_offsets``.
    * **Unsupported** — marks the document as ``failed`` with a clear
      error message.

    Updates ``document.status`` to ``"extracting_text"`` and populates
    ``text_content`` on success.  Sets ``status`` to ``"failed"`` with
    ``error_message`` on extraction failure.

    Parameters
    ----------
    document_id:
        SurrealDB record ID of the document (e.g. ``"abc123"``).

    Returns
    -------
    dict
        ``{"document_id": ..., "text_length": N, "page_count": N,
        "page_offsets": [...]}`` on success, or
        ``{"error": ..., "document_id": ...}`` on failure.
    """
    params = _db_params()
    doc_ref = f"document:{document_id}"

    activity.logger.info(
        "extract_text_activity called [document_id=%s]",
        document_id,
    )

    try:
        async with get_db(**params) as db:
            raw = await db.query(
                f"SELECT * FROM {doc_ref}",
            )
            rows = _extract_query_results(raw)
            if not rows:
                activity.logger.warning(
                    "Document not found [document_id=%s]",
                    document_id,
                )
                return {"error": "Document not found", "document_id": document_id}

            doc = rows[0]
            blob_format = doc.get("blob_format")
            blob_path = doc.get("blob_path", "")
            original_blob = doc.get("original_blob", "")
            filename = doc.get("filename", "")
            mime_type = doc.get("mime_type", "")

            # ---- Get binary content ----
            if blob_format == "minio":
                content = await _get_blob_from_minio(blob_path)
            else:
                # Legacy: base64-encoded inline blob
                content = base64.b64decode(original_blob.encode("ascii"))

            # ---- Detect format from filename / mime_type ----
            ext = os.path.splitext(filename)[1].lower() if filename else ""
            mime = (mime_type or "").lower()

            if ext == ".pdf" or mime == "application/pdf":
                doc_format = "pdf"
            elif ext in (".txt", ".md") or mime in ("text/plain", "text/markdown"):
                doc_format = "plain_text"
            elif not ext and (not mime or mime in ("text/plain", "application/octet-stream", "")):
                doc_format = "plain_text"
            else:
                doc_format = "unsupported"

            # ---- Branch on format ----
            if doc_format == "pdf":
                extractor = PdfExtractor()
                try:
                    result = extractor.extract(content, filename=filename)
                except ExtractorQualityError as exc:
                    await db.query(
                        f"UPDATE {doc_ref} SET status = 'failed', "
                        f"error_message = $msg, updated_at = time::now()",
                        {"msg": str(exc)},
                    )
                    activity.logger.warning(
                        "Quality gate failed [document_id=%s] [reason=%s]: %s",
                        document_id,
                        exc.reason,
                        exc,
                    )
                    return {
                        "error": str(exc),
                        "document_id": document_id,
                        "reason": exc.reason,
                    }

                text = result.text
                page_count = result.page_count
                page_offsets = result.page_offsets

            elif doc_format == "plain_text":
                try:
                    text = content.decode("utf-8")
                except UnicodeDecodeError as exc:
                    msg = f"Failed to decode plain-text file as UTF-8: {exc}"
                    activity.logger.warning(
                        "Text decode failed [document_id=%s]: %s",
                        document_id,
                        msg,
                    )
                    await db.query(
                        f"UPDATE {doc_ref} SET status = 'failed', "
                        f"error_message = $msg, updated_at = time::now()",
                        {"msg": msg},
                    )
                    return {"error": msg, "document_id": document_id}

                page_count = 1
                page_offsets = [0, len(text)]

            else:
                ext_display = ext if ext else "(none)"
                msg = (
                    f"Unsupported document format: extension '{ext_display}' "
                    f"(mime: {mime_type or '(none)'}). "
                    f"Only PDF and plain text are supported."
                )
                activity.logger.warning(
                    "Unsupported format [document_id=%s] [ext=%s] [mime=%s]",
                    document_id,
                    ext_display,
                    mime_type,
                )
                await db.query(
                    f"UPDATE {doc_ref} SET status = 'failed', "
                    f"error_message = $msg, updated_at = time::now()",
                    {"msg": msg},
                )
                return {"error": msg, "document_id": document_id}

            # ---- Update document record ----
            await db.query(
                f"UPDATE {doc_ref} SET text_content = $text, "
                f"status = 'extracting_text', "
                f"_page_count = $page_count, "
                f"updated_at = time::now()",
                {
                    "text": text,
                    "page_count": page_count,
                },
            )

            activity.logger.info(
                "extract_text_activity completed [document_id=%s] "
                "[text_length=%d] [page_count=%d]",
                document_id,
                len(text),
                page_count,
            )

            return {
                "document_id": document_id,
                "text_length": len(text),
                "page_count": page_count,
                "page_offsets": page_offsets,
            }

    except ConnectionError as exc:
        activity.logger.error(
            "Connection failed in extract_text_activity: %s",
            exc,
        )
        return {"error": str(exc), "document_id": document_id}
    except Exception as exc:
        activity.logger.error(
            "Unexpected error in extract_text_activity: %s",
            exc,
        )
        return {"error": str(exc), "document_id": document_id}


@activity.defn
async def chunk_document_activity(document_id: str, extraction_result: dict) -> dict:
    """Chunk a document's extracted text and store chunks in SurrealDB.

    Takes the extraction result dict (from ``extract_text_activity``)
    containing ``text_length``, ``page_count``, and ``page_offsets``.
    Queries ``text_content`` from SurrealDB, runs ``DocumentChunker``,
    deletes any existing chunks for this document, inserts fresh chunk
    records, and returns lightweight metadata (no chunk text in the
    return payload — avoids Temporal 2 MB payload limit).

    Parameters
    ----------
    document_id:
        SurrealDB record ID of the document.
    extraction_result:
        Dict from ``extract_text_activity`` with ``page_offsets``.

    Returns
    -------
    dict
        ``{"document_id": ..., "chunk_count": N}`` on success, or
        ``{"error": ..., "document_id": ...}`` on failure.
    """
    params = _db_params()
    doc_ref = f"document:{document_id}"

    activity.logger.info(
        "chunk_document_activity called [document_id=%s]",
        document_id,
    )

    try:
        async with get_db(**params) as db:
            raw = await db.query(
                f"SELECT text_content FROM {doc_ref}",
            )
            rows = _extract_query_results(raw)
            if not rows:
                return {"error": "Document not found", "document_id": document_id}

            text = rows[0].get("text_content", "")
            page_offsets = extraction_result.get("page_offsets", [0])

            # ---- Run DocumentChunker ----
            chunker = DocumentChunker()
            chunk_result = chunker.chunk(text, page_offsets)

            # ---- Build serializable chunk payloads ----
            chunks: list[dict] = []
            for c in chunk_result.chunks:
                chunks.append({
                    "chunk_index": c.chunk_index,
                    "text": c.text,
                    "page_start": c.page_start,
                    "page_end": c.page_end,
                    "offset_start": c.offset_start,
                    "offset_end": c.offset_end,
                })

            # ---- Idempotent: delete existing chunks ----
            await db.query(
                "DELETE document_chunk WHERE document = $doc_ref",
                {"doc_ref": doc_ref},
            )

            # ---- Insert new chunks ----
            doc_rid = RecordID("document", document_id)
            for chunk in chunks:
                await db.create(
                    "document_chunk",
                    {
                        "chunk_index": chunk["chunk_index"],
                        "text": chunk["text"],
                        "page_start": chunk["page_start"],
                        "page_end": chunk["page_end"],
                        "offset_start": chunk["offset_start"],
                        "offset_end": chunk["offset_end"],
                        "document": doc_rid,
                    },
                )

            # ---- Update document status ----
            if chunks:
                await db.query(
                    f"UPDATE {doc_ref} SET status = 'processed', "
                    f"updated_at = time::now()",
                )
            else:
                activity.logger.warning(
                    "No chunks to store [document_id=%s]",
                    document_id,
                )
                await db.query(
                    f"UPDATE {doc_ref} SET status = 'processed', "
                    f"updated_at = time::now()",
                )

            activity.logger.info(
                "chunk_document_activity completed [document_id=%s] "
                "[chunk_count=%d]",
                document_id,
                len(chunks),
            )

            return {
                "document_id": document_id,
                "chunk_count": len(chunks),
            }

    except ConnectionError as exc:
        activity.logger.error(
            "Connection failed in chunk_document_activity: %s",
            exc,
        )
        return {"error": str(exc), "document_id": document_id}
    except Exception as exc:
        activity.logger.error(
            "Unexpected error in chunk_document_activity: %s",
            exc,
        )
        try:
            async with get_db(**params) as db:
                await db.query(
                    f"UPDATE {doc_ref} SET status = 'failed', "
                    f"error_message = $msg, updated_at = time::now()",
                    {"msg": str(exc)},
                )
        except Exception:
            pass
        return {"error": str(exc), "document_id": document_id}


# ---------------------------------------------------------------------------
# Helper query activities (Phase 8)
# ---------------------------------------------------------------------------


@activity.defn
async def get_document_metadata_activity(document_id: str) -> dict:
    """Retrieve document metadata to determine processing path.

    Queries ``blob_format``, ``text_content``, ``filename``, and
    ``mime_type`` for the given document.  The workflow uses this to
    decide whether to follow the blob path (need to extract text from
    binary source) or the text path (text already available).

    Parameters
    ----------
    document_id:
        SurrealDB record ID of the document (e.g. ``"abc123"``).

    Returns
    -------
    dict
        ``{"document_id": ..., "blob_format": ...|None,
        "has_text_content": bool, "text_content": str}`` on success,
        or ``{"error": ..., "document_id": ...}`` on connection failure.
    """
    params = _db_params()
    doc_ref = f"document:{document_id}"

    activity.logger.info(
        "get_document_metadata_activity called [document_id=%s]",
        document_id,
    )

    try:
        async with get_db(**params) as db:
            raw = await db.query(
                f"SELECT blob_format, text_content, filename, mime_type "
                f"FROM {doc_ref}",
            )
            rows = _extract_query_results(raw)
            if not rows:
                activity.logger.warning(
                    "Document not found [document_id=%s]",
                    document_id,
                )
                return {"error": "Document not found", "document_id": document_id}

            doc = rows[0]
            text_content = doc.get("text_content")
            has_text_content = text_content is not None and text_content != ""

            activity.logger.info(
                "get_document_metadata_activity completed "
                "[document_id=%s] [blob_format=%s] [has_text_content=%s]",
                document_id,
                doc.get("blob_format"),
                has_text_content,
            )

            return {
                "document_id": document_id,
                "blob_format": doc.get("blob_format"),
                "has_text_content": has_text_content,
                "text_content": text_content if has_text_content else "",
            }

    except ConnectionError as exc:
        activity.logger.error(
            "SurrealDB connection failed in get_document_metadata_activity: %s",
            exc,
        )
        return {"error": str(exc), "document_id": document_id}
    except Exception as exc:
        activity.logger.error(
            "Unexpected error in get_document_metadata_activity: %s",
            exc,
        )
        return {"error": str(exc), "document_id": document_id}


@activity.defn
async def get_document_text_activity(document_id: str) -> dict:
    """Retrieve the full reconstructed text content for a document.

    Queries ``text_content`` from the document record.  Used by the blob
    path of the workflow to obtain the full text after extraction and
    chunk storage — guaranteeing chunk transparency (``extract_events_activity``
    never sees individual chunk records).

    Parameters
    ----------
    document_id:
        SurrealDB record ID of the document (e.g. ``"abc123"``).

    Returns
    -------
    dict
        ``{"document_id": ..., "text_content": str, "text_length": int}``
        on success, or ``{"error": ..., "document_id": ...}`` on
        connection failure.
    """
    params = _db_params()
    doc_ref = f"document:{document_id}"

    activity.logger.info(
        "get_document_text_activity called [document_id=%s]",
        document_id,
    )

    try:
        async with get_db(**params) as db:
            raw = await db.query(
                f"SELECT text_content FROM {doc_ref}",
            )
            rows = _extract_query_results(raw)
            if not rows:
                activity.logger.warning(
                    "Document not found [document_id=%s]",
                    document_id,
                )
                return {"error": "Document not found", "document_id": document_id}

            text_content = rows[0].get("text_content") or ""

            activity.logger.info(
                "get_document_text_activity completed "
                "[document_id=%s] [text_length=%d]",
                document_id,
                len(text_content),
            )

            return {
                "document_id": document_id,
                "text_content": text_content,
                "text_length": len(text_content),
            }

    except ConnectionError as exc:
        activity.logger.error(
            "SurrealDB connection failed in get_document_text_activity: %s",
            exc,
        )
        return {"error": str(exc), "document_id": document_id}
    except Exception as exc:
        activity.logger.error(
            "Unexpected error in get_document_text_activity: %s",
            exc,
        )
        return {"error": str(exc), "document_id": document_id}
