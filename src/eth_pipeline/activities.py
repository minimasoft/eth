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
import time
import unicodedata

from surrealdb.data.types.record_id import RecordID

from temporalio import activity

from eth_pipeline.chunker import DocumentChunker
from eth_pipeline.db import get_db
from eth_pipeline.offsets import compute_reference_offsets
from eth_pipeline.extractors import (
    ExtractorQualityError,
    PdfExtractor,
)
from eth_pipeline.llm import DEFAULT_MODEL, EXTRACTION_CHUNK_SIZE, OpenRouterProvider
from eth_pipeline.llm_usage import record_llm_usage
from eth_pipeline.processing_log import ProcessingLogger
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
    _log = ProcessingLogger(_db_params())
    if not api_key:
        activity.logger.error("OPENROUTER_API_KEY not set — returning degraded result")
        await _log.log(document_id, "extract_events", "warning",
                       "OPENROUTER_API_KEY not set — returning degraded result")
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
                await _log.log(document_id, "extract_events", "warning",
                               "Document not found in database")
                return {"error": "Document not found", "document_id": document_id}
            text = rows[0].get("text_content") or ""
    except ConnectionError as exc:
        activity.logger.error(
            "SurrealDB connection failed in extract_events_activity: %s",
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

    # ---- Sequential chunked extraction ----
    # Split long documents into chunks and process each with accumulated
    # prior events, so each LLM call stays within the context window.
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


@activity.defn
async def resolve_entities_activity(document_id: str) -> dict:
    """Resolve verbatim references to canonical entities using LLM grouping + DB dedup.

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
      1. Batches references by estimated token count (≤~240K tokens per batch).
      2. Calls ``OpenRouterProvider.resolve_references()`` to group references
         into entities (LLM infers entity names/types — no document context sent).
      3. For each LLM entity group, programmatically matches against existing
         ``canonical_entity`` records (NFD+casefold exact match → fuzzy
         bidirectional CONTAINS → create new).
      4. Links each reference to the matched or created entity.

    LLM failures for individual batches are logged but do **not** block
    resolution of other reference types.

    Queries event count and references directly from SurrealDB — does NOT
    accept the LLM extraction result dict.

    Parameters
    ----------
    document_id:
        SurrealDB record ID of the document (e.g. ``"abc123"``).

    Returns
    -------
    dict
        ``{"document_id": ..., "resolved": N, "created": N, "skipped": N}``
        on success, or ``{"error": ..., "document_id": ...}`` on failure.
    """
    params = _db_params()
    _log = ProcessingLogger(params)
    doc_rid = RecordID("document", document_id)

    activity.logger.info(
        "resolve_entities_activity called [document_id=%s]",
        document_id,
    )
    await _log.log(document_id, "resolve_entities", "info",
                   "Starting entity resolution")

    try:
        async with get_db(**params) as db:
            # ------------------------------------------------------------------
            # 0. Early-return: query event count from DB
            # ------------------------------------------------------------------
            count_raw = await db.query(
                "SELECT count() FROM event WHERE document = $doc_rid GROUP ALL",
                {"doc_rid": doc_rid},
            )
            count_rows = _extract_query_results(count_raw)
            event_count = count_rows[0].get("count", 0) if count_rows else 0

            if event_count == 0:
                activity.logger.info(
                    "No events — nothing to resolve [document_id=%s]",
                    document_id,
                )
                await _log.log(document_id, "resolve_entities", "warning",
                               "No events — nothing to resolve")
                return {"document_id": document_id, "resolved": 0, "created": 0, "skipped": 0}

            # ------------------------------------------------------------------
            # 1. Query all references for this document
            # ------------------------------------------------------------------
            refs_raw = await db.query(
                "SELECT * FROM reference WHERE event.document = $doc_rid",
                {"doc_rid": doc_rid},
            )
            references = _extract_query_results(refs_raw)

            if not references:
                activity.logger.info(
                    "No references found [document_id=%s]",
                    document_id,
                )
                await _log.log(document_id, "resolve_entities", "info",
                               "No references found for this document")
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
                "WHERE event.document = $doc_rid",
                {"doc_rid": doc_rid},
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
            # 4. Resolve each type group via batched LLM grouping + code-side DB dedup
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

            def _normalize(text: str) -> str:
                nfd = unicodedata.normalize("NFD", text)
                stripped = "".join(c for c in nfd if unicodedata.combining(c) == 0)
                return stripped.casefold()

            async def _dedup_and_link(
                db_conn,
                entity_name: str,
                entity_type: str,
                ref_ids: list[str],
                existing_entities_list: list[dict],
            ) -> int:
                nonlocal total_created
                norm_name = _normalize(entity_name)
                matched_ce_id = None

                for ent in existing_entities_list:
                    ent_name = ent.get("name", "")
                    if ent_name and _normalize(ent_name) == norm_name:
                        matched_ce_id = ent.get("id")
                        break

                if matched_ce_id is None and existing_entities_list:
                    for ent in existing_entities_list:
                        ent_name = ent.get("name", "") or ""
                        if norm_name in _normalize(ent_name) or _normalize(ent_name) in norm_name:
                            matched_ce_id = ent.get("id")
                            break

                if matched_ce_id is None:
                    created_id = await _create_canonical_entity(
                        db_conn, entity_name, entity_type, {},
                    )
                    if created_id:
                        matched_ce_id = created_id
                        total_created += 1

                linked = 0
                if matched_ce_id:
                    for rid in ref_ids:
                        try:
                            await db_conn.query(
                                f"UPDATE {rid} SET "
                                f"entity_id = $eid, "
                                f"canonical_entity = $ce, "
                                f"resolution_confidence = 1.0",
                                {"eid": matched_ce_id, "ce": matched_ce_id},
                            )
                            linked += 1
                        except Exception as exc:
                            activity.logger.error(
                                "Failed to update reference %s: %s",
                                rid, exc,
                            )
                return linked

            for entity_type, refs in groups.items():
                if not refs:
                    continue

                existing_raw = await db.query(
                    "SELECT id, name, entity_type, properties "
                    "FROM canonical_entity WHERE entity_type = $type",
                    {"type": entity_type},
                )
                existing_entities = _extract_query_results(existing_raw)

                activity.logger.info(
                    "Resolving %d %s references [document_id=%s]",
                    len(refs), entity_type, document_id,
                )
                await _log.log(document_id, "resolve_entities", "info",
                               f"Resolving {len(refs)} {entity_type} references")

                # Batch refs and call LLM for grouping
                batches = OpenRouterProvider.batch_references(refs)

                for batch_idx, batch in enumerate(batches):
                    activity.logger.info(
                        "LLM grouping batch %d/%d [type=%s] [refs=%d] "
                        "[document_id=%s]",
                        batch_idx + 1, len(batches), entity_type,
                        len(batch), document_id,
                    )

                    try:
                        resolution, usage = await provider.resolve_references(
                            references=batch,
                        )
                    except Exception as exc:
                        activity.logger.error(
                            "LLM grouping failed for %s batch %d/%d "
                            "[document_id=%s]: %s",
                            entity_type, batch_idx + 1, len(batches),
                            document_id, exc,
                        )
                        await _log.log(document_id, "resolve_entities", "warning",
                                       f"LLM grouping failed for {entity_type} "
                                       f"batch {batch_idx + 1}/{len(batches)}",
                                       {"error": str(exc)[:200]})
                        continue

                    if usage is not None:
                        await record_llm_usage(
                            db_params=params,
                            document_id=document_id,
                            step_name="resolve_entities",
                            chunk_index=batch_idx,
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

                    groups_from_llm = resolution.get("groups", [])
                    if not groups_from_llm:
                        activity.logger.warning(
                            "LLM returned no groups for %s batch %d/%d "
                            "[document_id=%s] — treating each reference "
                            "as its own entity",
                            entity_type, batch_idx + 1, len(batches),
                            document_id,
                        )
                        for ref in batch:
                            vt = ref.get("verbatim_text", "") or "unknown"
                            rid = ref.get("id")
                            if rid:
                                linked = await _dedup_and_link(
                                    db, vt, entity_type, [rid],
                                    existing_entities,
                                )
                                total_resolved += linked
                        continue

                    # Build verbatim_text → [ref_id] lookup
                    verbatim_to_refs: dict[str, list[str]] = {}
                    for r in batch:
                        vt = r.get("verbatim_text", "")
                        rid = r.get("id")
                        if vt and rid:
                            verbatim_to_refs.setdefault(vt, []).append(rid)

                    # Apply LLM groups: match/merge with DB per group
                    for ent_group in groups_from_llm:
                        entity_name = ent_group.get("entity_name", "").strip()
                        inferred_type = ent_group.get("entity_type", entity_type)
                        verbatim_texts = ent_group.get("verbatim_texts", [])

                        if not entity_name or not verbatim_texts:
                            continue

                        group_ref_ids: list[str] = []
                        for vt in verbatim_texts:
                            ids = verbatim_to_refs.get(vt, [])
                            group_ref_ids.extend(ids)

                        if not group_ref_ids:
                            continue

                        linked = await _dedup_and_link(
                            db, entity_name, inferred_type,
                            group_ref_ids, existing_entities,
                        )
                        total_resolved += linked

            activity.logger.info(
                "resolve_entities_activity completed [document_id=%s] "
                "[resolved=%d] [created=%d] [skipped=%d]",
                document_id,
                total_resolved,
                total_created,
                skipped_count,
            )
            await _log.log(document_id, "resolve_entities", "info",
                           f"Resolution completed: {total_resolved} resolved, "
                           f"{total_created} created, {skipped_count} skipped",
                           {"resolved": total_resolved, "created": total_created,
                            "skipped": skipped_count})

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
        await _log.log(document_id, "resolve_entities", "error",
                       f"SurrealDB connection failed: {exc}")
        return {"error": str(exc), "document_id": document_id}
    except Exception as exc:
        activity.logger.error(
            "Unexpected error in resolve_entities_activity: %s",
            exc,
        )
        await _log.log(document_id, "resolve_entities", "error",
                       f"Unexpected error: {exc}")
        return {"error": str(exc), "document_id": document_id}


@activity.defn
async def resolve_entities_with_search_activity(document_id: str) -> dict:
    """Resolve verbatim references to canonical entities using grouping + DB dedup.

    **Replay-safe**: First nullifies any prior ``canonical_entity``,
    ``entity_id``, and ``resolution_confidence`` links on all references
    for this document, then re-resolves from scratch.

    **Flow:**
      1. Exact match (NFD+casefold normalized) — if a reference's verbatim
         text matches an existing entity name exactly, set ``entity_id``
         and ``canonical_entity`` directly without an LLM call.
      2. LLM grouping — remaining references are sent to the LLM in batches
         (each batch ≤ ~240K estimated tokens). The LLM groups references
         that refer to the same entity and infers entity names/types.
      3. DB dedup — for each LLM entity group, programmatically match
         against existing ``canonical_entity`` records (exact NFD+casefold
         match → fuzzy bidirectional CONTAINS → create new). This avoids
         sending the full document text or existing entity lists to the LLM.

    References are grouped by ``reference_type`` with the same mapping as
    ``resolve_entities_activity``.

    Queries event count and references directly from SurrealDB — does NOT
    accept the LLM extraction result dict.

    Parameters
    ----------
    document_id:
        SurrealDB record ID of the document (e.g. ``"abc123"``).

    Returns
    -------
    dict
        ``{"document_id": ..., "resolved": N, "created": N, "skipped": N,
        "llm_calls": N, "exact_matches": N}`` on success, or
        ``{"error": ..., "document_id": ...}`` on failure.
    """
    params = _db_params()
    _log = ProcessingLogger(params)
    doc_rid = RecordID("document", document_id)

    activity.logger.info(
        "resolve_entities_with_search_activity called "
        "[document_id=%s]",
        document_id,
    )
    await _log.log(document_id, "resolve_entities_search", "info",
                   "Starting search-first entity resolution")

    try:
        async with get_db(**params) as db:
            # ------------------------------------------------------------------
            # 0. Early-return: query event count from DB
            # ------------------------------------------------------------------
            count_raw = await db.query(
                "SELECT count() FROM event WHERE document = $doc_rid GROUP ALL",
                {"doc_rid": doc_rid},
            )
            count_rows = _extract_query_results(count_raw)
            event_count = count_rows[0].get("count", 0) if count_rows else 0

            if event_count == 0:
                activity.logger.info(
                    "No events — nothing to resolve [document_id=%s]",
                    document_id,
                )
                await _log.log(document_id, "resolve_entities_search", "warning",
                               "No events — nothing to resolve")
                return {
                    "document_id": document_id,
                    "resolved": 0,
                    "created": 0,
                    "skipped": 0,
                    "llm_calls": 0,
                    "exact_matches": 0,
                }

            activity.logger.info(
                "Found %d stored events [document_id=%s]",
                event_count,
                document_id,
            )
            # ------------------------------------------------------------------
            # 1. Query all references for this document
            # ------------------------------------------------------------------
            refs_raw = await db.query(
                "SELECT * FROM reference WHERE event.document = $doc_rid",
                {"doc_rid": doc_rid},
            )
            references = _extract_query_results(refs_raw)

            if not references:
                activity.logger.info(
                    "No references found [document_id=%s]",
                    document_id,
                )
                await _log.log(document_id, "resolve_entities_search", "info",
                               "No references found for this document")
                return {
                    "document_id": document_id,
                    "resolved": 0,
                    "created": 0,
                    "skipped": 0,
                    "llm_calls": 0,
                    "exact_matches": 0,
                }

            # ------------------------------------------------------------------
            # 2. Nullify prior resolution links (replay safety)
            # ------------------------------------------------------------------
            activity.logger.info(
                "Nullifying prior resolution links [document_id=%s] "
                "[ref_count=%d]",
                document_id,
                len(references),
            )
            await db.query(
                "UPDATE reference SET canonical_entity = null, "
                "entity_id = null, resolution_confidence = null "
                "WHERE event.document = $doc_rid",
                {"doc_rid": doc_rid},
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
            # 4. Resolve each type group via batched LLM grouping + code-side DB dedup
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
            total_llm_calls = 0
            total_exact_matches = 0

            def _normalize(text: str) -> str:
                nfd = unicodedata.normalize("NFD", text)
                stripped = "".join(c for c in nfd if unicodedata.combining(c) == 0)
                return stripped.casefold()

            async def _dedup_and_link(
                db_conn,
                entity_name: str,
                entity_type: str,
                ref_ids: list[str],
                existing_entities_list: list[dict],
            ) -> int:
                """Match entity_name against DB, create if new, link all ref_ids.

                Returns the number of references resolved.
                """
                nonlocal total_created
                norm_name = _normalize(entity_name)
                matched_ce_id = None

                # 1. Exact match (NFD+casefold) against existing entities
                for ent in existing_entities_list:
                    ent_name = ent.get("name", "")
                    if ent_name and _normalize(ent_name) == norm_name:
                        matched_ce_id = ent.get("id")
                        break

                # 2. Fuzzy match (bidirectional CONTAINS) if no exact match
                if matched_ce_id is None and existing_entities_list:
                    for ent in existing_entities_list:
                        ent_name = ent.get("name", "") or ""
                        if norm_name in _normalize(ent_name) or _normalize(ent_name) in norm_name:
                            matched_ce_id = ent.get("id")
                            break

                # 3. Create new entity if no match
                if matched_ce_id is None:
                    created_id = await _create_canonical_entity(
                        db_conn, entity_name, entity_type, {},
                    )
                    if created_id:
                        matched_ce_id = created_id
                        total_created += 1

                # 4. Link all references to the matched/created entity
                linked = 0
                if matched_ce_id:
                    for rid in ref_ids:
                        try:
                            await db_conn.query(
                                f"UPDATE {rid} SET "
                                f"entity_id = $eid, "
                                f"canonical_entity = $ce, "
                                f"resolution_confidence = 1.0",
                                {"eid": matched_ce_id, "ce": matched_ce_id},
                            )
                            linked += 1
                        except Exception as exc:
                            activity.logger.error(
                                "Failed to update reference %s with "
                                "entity_id %s: %s",
                                rid, matched_ce_id, exc,
                            )
                return linked

            for entity_type, refs in groups.items():
                if not refs:
                    continue

                # Query existing canonical entities of this type
                existing_raw = await db.query(
                    "SELECT id, name, entity_type, properties "
                    "FROM canonical_entity WHERE entity_type = $type",
                    {"type": entity_type},
                )
                existing_entities = _extract_query_results(existing_raw)

                activity.logger.info(
                    "Grouping resolution [type=%s] [refs=%d] "
                    "[existing_entities=%d] [document_id=%s]",
                    entity_type,
                    len(refs),
                    len(existing_entities),
                    document_id,
                )
                await _log.log(document_id, "resolve_entities_search", "info",
                               f"Grouping resolution for {len(refs)} "
                               f"{entity_type} references")

                # ---------------------------------------------------------------
                # 4a. Exact match pass (NFD + casefold) — no LLM needed
                # ---------------------------------------------------------------
                remaining_refs: list[dict] = []
                exact_match_count = 0

                for ref in refs:
                    vt = ref.get("verbatim_text", "")
                    if not vt:
                        remaining_refs.append(ref)
                        continue

                    norm_vt = _normalize(vt)
                    matched = False

                    for entity in existing_entities:
                        entity_name = entity.get("name", "")
                        if entity_name and _normalize(entity_name) == norm_vt:
                            entity_id_val = entity.get("id")
                            if entity_id_val:
                                try:
                                    await db.query(
                                        f"UPDATE {ref.get('id')} SET "
                                        f"entity_id = $eid, "
                                        f"canonical_entity = $ce, "
                                        f"resolution_confidence = 1.0",
                                        {"eid": entity_id_val, "ce": entity_id_val},
                                    )
                                    total_resolved += 1
                                    exact_match_count += 1
                                    total_exact_matches += 1
                                    matched = True
                                    activity.logger.info(
                                        "Exact match [ref=%s] → [entity=%s] "
                                        "[document_id=%s]",
                                        ref.get("id"),
                                        entity_id_val,
                                        document_id,
                                    )
                                except Exception as exc:
                                    activity.logger.error(
                                        "Failed to update exact-match "
                                        "reference %s: %s",
                                        ref.get("id"),
                                        exc,
                                    )
                            break

                    if not matched:
                        remaining_refs.append(ref)

                activity.logger.info(
                    "Grouping resolution [type=%s]: %d exact matches, "
                    "%d references for LLM grouping [document_id=%s]",
                    entity_type,
                    exact_match_count,
                    len(remaining_refs),
                    document_id,
                )
                await _log.log(document_id, "resolve_entities_search", "info",
                               f"{entity_type}: {exact_match_count} exact matches, "
                               f"{len(remaining_refs)} for LLM grouping",
                               {
                                   "entity_type": entity_type,
                                   "exact_matches": exact_match_count,
                                   "llm_refs": len(remaining_refs),
                               })

                # ---------------------------------------------------------------
                # 4b. Batch remaining refs and call LLM for grouping
                # ---------------------------------------------------------------
                if not remaining_refs:
                    continue

                batches = OpenRouterProvider.batch_references(remaining_refs)

                for batch_idx, batch in enumerate(batches):
                    activity.logger.info(
                        "LLM grouping batch %d/%d [type=%s] [refs=%d] "
                        "[document_id=%s]",
                        batch_idx + 1, len(batches), entity_type,
                        len(batch), document_id,
                    )

                    try:
                        resolution, usage = await provider.resolve_references(
                            references=batch,
                        )
                        total_llm_calls += 1
                    except Exception as exc:
                        activity.logger.error(
                            "LLM grouping failed for %s batch %d/%d "
                            "[document_id=%s]: %s",
                            entity_type, batch_idx + 1, len(batches),
                            document_id, exc,
                        )
                        await _log.log(document_id, "resolve_entities_search",
                                       "warning",
                                       f"LLM grouping failed for {entity_type} "
                                       f"batch {batch_idx + 1}/{len(batches)}",
                                       {"error": str(exc)[:200]})
                        continue

                    if usage is not None:
                        await record_llm_usage(
                            db_params=params,
                            document_id=document_id,
                            step_name="resolve_entities_with_search",
                            chunk_index=batch_idx,
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

                    groups_from_llm = resolution.get("groups", [])
                    if not groups_from_llm:
                        activity.logger.warning(
                            "LLM returned no groups for %s batch %d/%d "
                            "[document_id=%s] — treating each reference "
                            "as its own entity",
                            entity_type, batch_idx + 1, len(batches),
                            document_id,
                        )
                        # Fallback: treat each reference as its own entity
                        for ref in batch:
                            vt = ref.get("verbatim_text", "") or "unknown"
                            rid = ref.get("id")
                            if rid:
                                linked = await _dedup_and_link(
                                    db, vt, entity_type, [rid],
                                    existing_entities,
                                )
                                total_resolved += linked
                        continue

                    # ---------------------------------------------------------------
                    # 4c. Build verbatim_text → [ref_id] lookup
                    # ---------------------------------------------------------------
                    verbatim_to_refs: dict[str, list[str]] = {}
                    for r in batch:
                        vt = r.get("verbatim_text", "")
                        rid = r.get("id")
                        if vt and rid:
                            verbatim_to_refs.setdefault(vt, []).append(rid)

                    # ---------------------------------------------------------------
                    # 4d. Apply LLM groups: match/merge with DB per group
                    # ---------------------------------------------------------------
                    for ent_group in groups_from_llm:
                        entity_name = ent_group.get("entity_name", "").strip()
                        inferred_type = ent_group.get("entity_type", entity_type)
                        verbatim_texts = ent_group.get("verbatim_texts", [])

                        if not entity_name or not verbatim_texts:
                            continue

                        # Collect all ref IDs that match this group's verbatim texts
                        group_ref_ids: list[str] = []
                        for vt in verbatim_texts:
                            ids = verbatim_to_refs.get(vt, [])
                            group_ref_ids.extend(ids)

                        if not group_ref_ids:
                            continue

                        linked = await _dedup_and_link(
                            db, entity_name, inferred_type,
                            group_ref_ids, existing_entities,
                        )
                        total_resolved += linked

            activity.logger.info(
                "resolve_entities_with_search_activity completed "
                "[document_id=%s] [exact_matches=%d] [llm_calls=%d] "
                "[resolved=%d] [created=%d] [skipped=%d]",
                document_id,
                total_exact_matches,
                total_llm_calls,
                total_resolved,
                total_created,
                skipped_count,
            )
            await _log.log(document_id, "resolve_entities_search", "info",
                           f"Search-first resolution completed: "
                           f"{total_exact_matches} exact matches, "
                           f"{total_llm_calls} LLM calls, "
                           f"{total_resolved} resolved, "
                           f"{total_created} created, "
                           f"{skipped_count} skipped",
                           {
                               "exact_matches": total_exact_matches,
                               "llm_calls": total_llm_calls,
                               "resolved": total_resolved,
                               "created": total_created,
                               "skipped": skipped_count,
                           })

            return {
                "document_id": document_id,
                "resolved": total_resolved,
                "created": total_created,
                "skipped": skipped_count,
                "llm_calls": total_llm_calls,
                "exact_matches": total_exact_matches,
            }

    except ConnectionError as exc:
        activity.logger.error(
            "SurrealDB connection failed in "
            "resolve_entities_with_search_activity: %s",
            exc,
        )
        await _log.log(document_id, "resolve_entities_search", "error",
                       f"Connection failed: {exc}")
        return {"error": str(exc), "document_id": document_id}
    except Exception as exc:
        activity.logger.error(
            "Unexpected error in "
            "resolve_entities_with_search_activity: %s",
            exc,
        )
        await _log.log(document_id, "resolve_entities_search", "error",
                       f"Unexpected error: {exc}")
        return {"error": str(exc), "document_id": document_id}


@activity.defn
async def create_event_canonical_entities_activity(
    document_id: str,
) -> dict:
    """Create canonical_entity records for extracted events.

    **Replay-safe**: First deletes any prior event-type canonical entities
    scoped to this document (and their event_entity_link edges), then
    recreates them from scratch. This guarantees idempotency across retries.

    Queries stored events directly from SurrealDB — does NOT accept the LLM
    extraction result dict.  This avoids passing large payloads through
    Temporal serialization and ensures the activity works with actual stored
    data.

    For each stored event:
      1. Creates a ``canonical_entity`` record with ``entity_type="event"``
         and properties mapped from event fields.
      2. Creates ``event_entity_link`` RELATE edges to matching
         place/person/object canonical entities via verbatim text CONTAINS
         matching on the event's ``espacio``, ``humanos``, and ``objetos``
         fields.

    Parameters
    ----------
    document_id:
        SurrealDB record ID of the source document (e.g. ``"abc123"``).

    Returns
    -------
    dict
        ``{"document_id": ..., "events_processed": N, "entities_created": N,
        "links_created": N}`` on success, or
        ``{"error": ..., "document_id": ...}`` on failure.
    """
    params = _db_params()
    _log = ProcessingLogger(params)
    doc_rid = RecordID("document", document_id)

    activity.logger.info(
        "create_event_canonical_entities_activity called "
        "[document_id=%s]",
        document_id,
    )
    await _log.log(document_id, "create_event_entities", "info",
                   "Starting event canonical entity creation")

    try:
        async with get_db(**params) as db:
            # ------------------------------------------------------------------
            # 0. Early-return: query event count from DB
            # ------------------------------------------------------------------
            count_raw = await db.query(
                "SELECT count() FROM event WHERE document = $doc_rid GROUP ALL",
                {"doc_rid": doc_rid},
            )
            count_rows = _extract_query_results(count_raw)
            event_count = count_rows[0].get("count", 0) if count_rows else 0

            if event_count == 0:
                activity.logger.info(
                    "No stored events — nothing to create [document_id=%s]",
                    document_id,
                )
                await _log.log(document_id, "create_event_entities", "warning",
                               "No stored events — nothing to create")
                return {
                    "document_id": document_id,
                    "events_processed": 0,
                    "entities_created": 0,
                    "links_created": 0,
                }

            activity.logger.info(
                "Found %d stored events [document_id=%s]",
                event_count,
                document_id,
            )
            await _log.log(document_id, "create_event_entities", "info",
                           f"Found {event_count} stored events for canonical entity creation",
                           {"event_count": event_count})

            # ------------------------------------------------------------------
            # 1. Nullify: delete prior event entities and their links
            # ------------------------------------------------------------------
            activity.logger.info(
                "Nullifying prior event entities [document_id=%s]",
                document_id,
            )
            await _log.log(document_id, "create_event_entities", "info",
                           "Deleting prior event entities for this document")

            # Delete links first (foreign-key order)
            await db.query(
                "DELETE event_entity_link WHERE event IN ("
                "SELECT id FROM canonical_entity "
                "WHERE entity_type = 'event' AND properties.document_id = $doc_id"
                ")",
                {"doc_id": document_id},
            )
            await db.query(
                "DELETE canonical_entity "
                "WHERE entity_type = 'event' AND properties.document_id = $doc_id",
                {"doc_id": document_id},
            )

            # ------------------------------------------------------------------
            # 2. Query stored events for this document
            # ------------------------------------------------------------------
            events_raw = await db.query(
                "SELECT * FROM event WHERE document = $doc_rid",
                {"doc_rid": doc_rid},
            )
            stored_events = _extract_query_results(events_raw)

            if not stored_events:
                activity.logger.info(
                    "No stored events found in DB [document_id=%s]",
                    document_id,
                )
                await _log.log(document_id, "create_event_entities", "warning",
                               "No stored events found — nothing to create")
                return {
                    "document_id": document_id,
                    "events_processed": 0,
                    "entities_created": 0,
                    "links_created": 0,
                }

            # ------------------------------------------------------------------
            # 3. For each stored event, create canonical_entity and RELATE edges
            # ------------------------------------------------------------------
            entities_created = 0
            links_created = 0

            for event in stored_events:
                que_paso = event.get("que_paso", "") or ""
                tiempo = event.get("tiempo") or ""
                espacio = event.get("espacio") or ""
                humanos = event.get("humanos") or ""
                objetos = event.get("objetos") or ""

                # ---- Build entity name ----
                truncated = que_paso[:80].strip()
                if len(que_paso) > 80:
                    name = f"Event: {truncated}..."
                else:
                    name = f"Event: {truncated}"

                # ---- Build properties dict ----
                props = {
                    "title": que_paso[:80],
                    "description": que_paso,
                    "time_range": tiempo,
                    "location": espacio,
                    "participants": humanos,
                    "objects": objetos,
                    "document_id": document_id,
                }

                # ---- Create canonical_entity record ----
                entity_result = await db.query(
                    "CREATE canonical_entity CONTENT { "
                    "name: $name, "
                    "entity_type: 'event', "
                    "properties: $props "
                    "} RETURN id",
                    {
                        "name": name,
                        "props": props,
                    },
                )
                created_rows = _extract_query_results(entity_result)
                if not created_rows:
                    activity.logger.warning(
                        "Failed to create event canonical entity "
                        "[document_id=%s] [que_paso=%.40s]",
                        document_id,
                        que_paso,
                    )
                    continue

                event_entity_rid = created_rows[0].get("id")
                entities_created += 1

                # ---- 4. RELATE edges ----
                # Match espacio (→location) against 'place' entities
                for field_value, entity_type_filter, role in [
                    (espacio, "place", "location"),
                    (humanos, "person", "participant"),
                    (objetos, "object", "object"),
                ]:
                    if not field_value:
                        continue

                    # Query existing entities by CONTAINS matching
                    matched_raw = await db.query(
                        "SELECT id, name FROM canonical_entity "
                        "WHERE entity_type = $etype "
                        "AND name CONTAINS $value",
                        {
                            "etype": entity_type_filter,
                            "value": field_value,
                        },
                    )
                    matched_entities = _extract_query_results(matched_raw)

                    # Also check the reverse: verbatim text CONTAINS entity name
                    reverse_raw = await db.query(
                        "SELECT id, name FROM canonical_entity "
                        "WHERE entity_type = $etype "
                        "AND $value CONTAINS name",
                        {
                            "etype": entity_type_filter,
                            "value": field_value,
                        },
                    )
                    reverse_entities = _extract_query_results(reverse_raw)

                    # Combine, deduplicate by id
                    seen_ids: set[str] = set()
                    for match in matched_entities + reverse_entities:
                        match_id = match.get("id")
                        match_id_str = str(match_id) if match_id else ""
                        if match_id_str and match_id_str not in seen_ids:
                            seen_ids.add(match_id_str)
                            try:
                                await db.query(
                                    "CREATE event_entity_link CONTENT { "
                                    "event: $event_rid, "
                                    "entity: $entity_rid, "
                                    "relationship_type: 'involves', "
                                    "role: $role, "
                                    "confidence: 0.7 "
                                    "}",
                                    {
                                        "event_rid": event_entity_rid,
                                        "entity_rid": match_id,
                                        "role": role,
                                    },
                                )
                                links_created += 1
                            except Exception as exc:
                                activity.logger.warning(
                                    "Failed to create event_entity_link "
                                    "[event=%s] [entity=%s]: %s",
                                    event_entity_rid,
                                    match_id,
                                    exc,
                                )

            activity.logger.info(
                "create_event_canonical_entities_activity completed "
                "[document_id=%s] [events_processed=%d] "
                "[entities_created=%d] [links_created=%d]",
                document_id,
                len(stored_events),
                entities_created,
                links_created,
            )
            await _log.log(document_id, "create_event_entities", "info",
                           f"Created {entities_created} event entities with "
                           f"{links_created} links",
                           {
                               "events_processed": len(stored_events),
                               "entities_created": entities_created,
                               "links_created": links_created,
                           })

            return {
                "document_id": document_id,
                "events_processed": len(stored_events),
                "entities_created": entities_created,
                "links_created": links_created,
            }

    except ConnectionError as exc:
        activity.logger.error(
            "SurrealDB connection failed in "
            "create_event_canonical_entities_activity: %s",
            exc,
        )
        await _log.log(document_id, "create_event_entities", "error",
                       f"Connection failed: {exc}")
        return {"error": str(exc), "document_id": document_id}
    except Exception as exc:
        activity.logger.error(
            "Unexpected error in create_event_canonical_entities_activity: %s",
            exc,
        )
        await _log.log(document_id, "create_event_entities", "error",
                       f"Unexpected error: {exc}")
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
    _log = ProcessingLogger(params)
    doc_ref = f"document:{document_id}"

    activity.logger.info(
        "update_document_status_activity called [document_id=%s] [status=%s]",
        document_id,
        status,
    )
    await _log.log(document_id, "update_status", "info",
                   f"Setting status to {status}",
                   {"new_status": status, "error_message": error_message})

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
        await _log.log(document_id, "update_status", "error",
                       f"Failed to update status to {status}: {exc}")
        return {"error": str(exc), "document_id": document_id}
    except Exception as exc:
        activity.logger.error(
            "Unexpected error in update_document_status_activity: %s",
            exc,
        )
        await _log.log(document_id, "update_status", "error",
                       f"Failed to update status to {status}: {exc}")
        return {"error": str(exc), "document_id": document_id}

    activity.logger.info(
        "update_document_status_activity completed [document_id=%s] [status=%s]",
        document_id,
        status,
    )

    if status == "failed" and error_message:
        await _log.log(document_id, "update_status", "error",
                       f"Document processing failed: {error_message}")

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
    _log = ProcessingLogger(params)
    doc_rid = RecordID("document", document_id)
    doc_record = doc_rid
    events = result.get("events", [])

    activity.logger.info(
        "store_extraction_results_activity called [document_id=%s] "
        "[event_count=%d]",
        document_id,
        len(events),
    )
    await _log.log(document_id, "store_results", "info",
                   f"Starting storage of {len(events)} events")

    if not events:
        activity.logger.warning(
            "store_extraction_results_activity: no events to store "
            "[document_id=%s]",
            document_id,
        )
        await _log.log(document_id, "store_results", "warning",
                       "No events to store — marking as processed")
        # Still mark as processed — no events is a valid extraction result.
        await update_document_status_activity(document_id, "processed")
        return {"document_id": document_id, "events_stored": 0, "references_stored": 0}

    try:
        async with get_db(**params) as db:
            # ---- Idempotent: delete existing events+references ----
            # NOTE: llm_usage records are intentionally NOT deleted here.
            # They are a separate audit/telemetry concern (Phase 19) and
            # must survive extraction-result replays. Deleting them would
            # wipe token/cost tracking data accumulated by earlier LLM
            # call activities (extract_events, resolve_entities, etc.).
            activity.logger.info(
                "Clearing prior extraction results [document_id=%s]",
                document_id,
            )
            await db.query(
                "DELETE reference WHERE event IN "
                "(SELECT id FROM event WHERE document = $doc_rid)",
                {"doc_rid": doc_rid},
            )
            await db.query(
                "DELETE event WHERE document = $doc_rid",
                {"doc_rid": doc_rid},
            )

            # ---- Query document metadata and chunks for offset computation ----
            doc_rows = _extract_query_results(
                await db.query(
                    "SELECT mime_type FROM ONLY $doc_rid",
                    {"doc_rid": doc_rid},
                )
            )
            mime_type = doc_rows[0].get("mime_type", "") if doc_rows else ""
            is_plain_text = mime_type.startswith("text/")

            chunk_rows = _extract_query_results(
                await db.query(
                    "SELECT chunk_index, page_start, page_end, "
                    "offset_start, offset_end "
                    "FROM document_chunk "
                    "WHERE document = $doc_rid "
                    "ORDER BY chunk_index ASC",
                    {"doc_rid": doc_rid},
                )
            )
            if not chunk_rows:
                activity.logger.warning(
                    "No document_chunk records found for offset computation "
                    "[document_id=%s]",
                    document_id,
                )
                await _log.log(document_id, "store_results", "warning",
                               "No document_chunk records found — offsets will be null")

            # ---- Create events and collect their IDs ----
            total_references = 0
            for event_data in events:
                # Use raw SQL CREATE with explicit null for nullable fields.
                # SurrealDB Python SDK's db.create() converts Python None to
                # NONE (field-with-no-value) instead of null, which SCHEMAFULL
                # rejects for nullable string|record fields.
                event_result = await db.query(
                    "CREATE event CONTENT { "
                    "que_paso: $que_paso, "
                    "espacio: $espacio, "
                    "tiempo: $tiempo, "
                    "humanos: $humanos, "
                    "objetos: $objetos, "
                    "document: $document, "
                    "extraction_confidence: 1.0 "
                    "} RETURN id",
                    {
                        "que_paso": event_data.get("que_paso", ""),
                        "espacio": event_data.get("espacio") or "",
                        "tiempo": event_data.get("tiempo") or "",
                        "humanos": event_data.get("humanos") or "",
                        "objetos": event_data.get("objetos") or "",
                        "document": doc_record,
                    },
                )
                created = _extract_query_results(event_result)
                if not created:
                    activity.logger.error(
                        "Could not extract event id from create result: %s",
                        event_result,
                    )
                    continue
                event_rid = created[0].get("id")
                if not isinstance(event_rid, RecordID):
                    activity.logger.error(
                        "Unexpected event id type: %s", event_rid,
                    )
                    continue

                # ---- Create references linked to this event ----
                references = event_data.get("references", [])
                for ref in references:
                    raw_ss = ref.get("span_start")
                    raw_se = ref.get("span_end")
                    ss = int(raw_ss) if raw_ss is not None else 0
                    se = int(raw_se) if raw_se is not None else 0

                    ref_type = ref.get("reference_type", "")
                    if ref_type not in ("espacio", "tiempo", "humanos", "objetos"):
                        activity.logger.warning(
                            "Skipping reference with invalid reference_type='%s' "
                            "[document_id=%s] [verbatim_text=%.40s]",
                            ref_type,
                            document_id,
                            ref.get("verbatim_text", ""),
                        )
                        await _log.log(document_id, "store_results", "warning",
                                       f"Ignored reference with invalid reference_type='{ref_type}': "
                                       f"{(ref.get('verbatim_text', '') or '')[:80]}")
                        continue

                    if chunk_rows:
                        offset_result = compute_reference_offsets(
                            span_start=ss,
                            span_end=se,
                            chunks=chunk_rows,
                            is_plain_text=is_plain_text,
                        )
                    else:
                        offset_result = {
                            "page_number": None,
                            "page_offset_start": None,
                            "page_offset_end": None,
                        }

                    # Log warning for out-of-range spans
                    if (
                        offset_result["page_number"] is None
                        and not is_plain_text
                        and chunk_rows
                    ):
                        activity.logger.warning(
                            "Reference span out of range [document_id=%s] "
                            "[span_start=%d, span_end=%d, text_length=%d] — "
                            "setting offsets to null",
                            document_id,
                            ss,
                            se,
                            chunk_rows[-1]["offset_end"],
                        )
                        await _log.log(document_id, "store_results", "warning",
                                       f"Reference span out of range: span_start={ss}, span_end={se}")

                    await db.query(
                        "CREATE reference CONTENT { "
                        "reference_type: $ref_type, "
                        "verbatim_text: $vt, "
                        "span_start: $ss, "
                        "span_end: $se, "
                        "page_number: $pn, "
                        "page_offset_start: $pos, "
                        "page_offset_end: $poe, "
                        "event: $evt "
                        "}",
                        {
                            "ref_type": ref_type,
                            "vt": ref.get("verbatim_text", ""),
                            "ss": ss,
                            "se": se,
                            "pn": offset_result["page_number"],
                            "pos": offset_result["page_offset_start"],
                            "poe": offset_result["page_offset_end"],
                            "evt": event_rid,
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
            await _log.log(document_id, "store_results", "info",
                           f"Stored {events_stored} events and {total_references} references",
                           {"events_stored": events_stored, "references_stored": total_references})
    except ConnectionError as exc:
        activity.logger.error(
            "SurrealDB connection failed in store_extraction_results_activity: "
            "%s",
            exc,
        )
        await _log.log(document_id, "store_results", "error",
                       f"Connection failed: {exc}")
        await update_document_status_activity(document_id, "failed", str(exc))
        return {"error": str(exc), "document_id": document_id}
    except Exception as exc:
        activity.logger.error(
            "Unexpected error in store_extraction_results_activity: %s",
            exc,
        )
        await _log.log(document_id, "store_results", "error",
                       f"Unexpected error: {exc}")
        await update_document_status_activity(document_id, "failed", str(exc))
        return {"error": str(exc), "document_id": document_id}

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
    _log = ProcessingLogger(params)
    doc_ref = f"document:{document_id}"

    activity.logger.info(
        "extract_text_activity called [document_id=%s]",
        document_id,
    )
    await _log.log(document_id, "extract_text", "info",
                   "Starting text extraction")

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
                    await _log.log(document_id, "extract_text", "warning",
                                   f"Quality gate failed: {exc.reason}",
                                   {"reason": exc.reason})
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
                    await _log.log(document_id, "extract_text", "error",
                                   f"UTF-8 decode failed for plain-text file: {exc}")
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
                await _log.log(document_id, "extract_text", "error",
                               f"Unsupported format: {ext_display} (mime: {mime_type})")
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
            await _log.log(document_id, "extract_text", "info",
                           f"Text extraction completed: {len(text)} bytes, {page_count} pages",
                           {"text_length": len(text), "page_count": page_count})

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
        await _log.log(document_id, "extract_text", "error",
                       f"Connection failed: {exc}")
        return {"error": str(exc), "document_id": document_id}
    except Exception as exc:
        activity.logger.error(
            "Unexpected error in extract_text_activity: %s",
            exc,
        )
        await _log.log(document_id, "extract_text", "error",
                       f"Unexpected error: {exc}")
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
    _log = ProcessingLogger(params)
    doc_ref = f"document:{document_id}"

    activity.logger.info(
        "chunk_document_activity called [document_id=%s]",
        document_id,
    )
    await _log.log(document_id, "chunk_document", "info",
                   "Starting document chunking")

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
            if not chunks:
                activity.logger.warning(
                    "No chunks to store [document_id=%s]",
                    document_id,
                )
                await _log.log(document_id, "chunk_document", "warning",
                               "No chunks generated — document may be empty")

            await db.query(
                f"UPDATE {doc_ref} SET status = 'chunking', "
                "updated_at = time::now()",
            )

            activity.logger.info(
                "chunk_document_activity completed [document_id=%s] "
                "[chunk_count=%d]",
                document_id,
                len(chunks),
            )
            await _log.log(document_id, "chunk_document", "info",
                           f"Chunking completed: {len(chunks)} chunks",
                           {"chunk_count": len(chunks)})

            return {
                "document_id": document_id,
                "chunk_count": len(chunks),
            }

    except ConnectionError as exc:
        activity.logger.error(
            "Connection failed in chunk_document_activity: %s",
            exc,
        )
        await _log.log(document_id, "chunk_document", "error",
                       f"Connection failed: {exc}")
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
    _log = ProcessingLogger(params)
    doc_ref = f"document:{document_id}"

    activity.logger.info(
        "get_document_metadata_activity called [document_id=%s]",
        document_id,
    )
    await _log.log(document_id, "get_document_metadata", "info",
                   "Starting document metadata retrieval")

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
                await _log.log(document_id, "get_document_metadata", "warning",
                               "Document not found in database")
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
            await _log.log(document_id, "get_document_metadata", "info",
                           f"Metadata retrieved: blob_format={doc.get('blob_format')}, "
                           f"has_text_content={has_text_content}",
                           {"blob_format": doc.get("blob_format"),
                            "has_text_content": has_text_content})

            return {
                "document_id": document_id,
                "blob_format": doc.get("blob_format"),
                "has_text_content": has_text_content,
            }

    except ConnectionError as exc:
        activity.logger.error(
            "SurrealDB connection failed in get_document_metadata_activity: %s",
            exc,
        )
        await _log.log(document_id, "get_document_metadata", "error",
                       f"SurrealDB connection failed: {exc}")
        return {"error": str(exc), "document_id": document_id}
    except Exception as exc:
        activity.logger.error(
            "Unexpected error in get_document_metadata_activity: %s",
            exc,
        )
        await _log.log(document_id, "get_document_metadata", "error",
                       f"Unexpected error: {exc}")
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
    _log = ProcessingLogger(params)
    doc_ref = f"document:{document_id}"

    activity.logger.info(
        "get_document_text_activity called [document_id=%s]",
        document_id,
    )
    await _log.log(document_id, "get_document_text", "info",
                   "Starting document text retrieval")

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
                await _log.log(document_id, "get_document_text", "warning",
                               "Document not found in database")
                return {"error": "Document not found", "document_id": document_id}

            text_content = rows[0].get("text_content") or ""

            activity.logger.info(
                "get_document_text_activity completed "
                "[document_id=%s] [text_length=%d]",
                document_id,
                len(text_content),
            )
            await _log.log(document_id, "get_document_text", "info",
                           f"Text retrieval completed: {len(text_content)} bytes",
                           {"text_length": len(text_content)})

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
        await _log.log(document_id, "get_document_text", "error",
                       f"SurrealDB connection failed: {exc}")
        return {"error": str(exc), "document_id": document_id}
    except Exception as exc:
        activity.logger.error(
            "Unexpected error in get_document_text_activity: %s",
            exc,
        )
        await _log.log(document_id, "get_document_text", "error",
                       f"Unexpected error: {exc}")
        return {"error": str(exc), "document_id": document_id}
