"""Resolve verbatim references to canonical entities using LLM grouping + DB dedup."""

from __future__ import annotations

import os
import uuid

from temporalio import activity

from eth_pipeline.activities._common import (
    _create_canonical_entity,
    _db_params,
    _extract_query_results,
    _normalize,
)
from eth_pipeline.db import get_db
from eth_pipeline.llm import DEFAULT_MODEL, OpenRouterProvider
from eth_pipeline.llm_usage import record_llm_usage
from eth_pipeline.processing_log import ProcessingLogger


@activity.defn
async def resolve_entities_activity(document_id: str) -> dict:
    params = _db_params()
    _log = ProcessingLogger(params)

    activity.logger.info(
        "resolve_entities_activity called [document_id=%s]",
        document_id,
    )
    await _log.log(document_id, "resolve_entities", "info",
                   "Starting entity resolution")

    try:
        async with get_db(**params) as conn:
            count_row = await conn.fetchrow(
                "SELECT COUNT(*)::int AS count FROM event WHERE document = $1",
                document_id,
            )
            event_count = count_row["count"] if count_row else 0

            if event_count == 0:
                activity.logger.info(
                    "No events — nothing to resolve [document_id=%s]",
                    document_id,
                )
                await _log.log(document_id, "resolve_entities", "warning",
                               "No events — nothing to resolve")
                return {"document_id": document_id, "resolved": 0, "created": 0, "skipped": 0}

            references = _extract_query_results(
                await conn.fetch(
                    "SELECT r.* FROM reference r "
                    "JOIN event e ON r.event = e.id "
                    "WHERE e.document = $1",
                    document_id,
                )
            )

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

            activity.logger.info(
                "Nullifying prior resolution links [document_id=%s] [ref_count=%d]",
                document_id,
                len(references),
            )
            await conn.execute(
                "UPDATE reference SET canonical_entity = NULL, "
                "resolution_confidence = NULL "
                "WHERE event IN (SELECT id FROM event WHERE document = $1)",
                document_id,
            )

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
                            await db_conn.execute(
                                "UPDATE reference SET entity_id = $2, "
                                "canonical_entity = $3, "
                                "resolution_confidence = 1.0 "
                                "WHERE id = $1",
                                rid, matched_ce_id, matched_ce_id,
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

                existing_entities = _extract_query_results(
                    await conn.fetch(
                        "SELECT id, name, entity_type, properties "
                        "FROM canonical_entity WHERE entity_type = $1",
                        entity_type,
                    )
                )

                activity.logger.info(
                    "Resolving %d %s references [document_id=%s]",
                    len(refs), entity_type, document_id,
                )
                await _log.log(document_id, "resolve_entities", "info",
                               f"Resolving {len(refs)} {entity_type} references")

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
                                    conn, vt, entity_type, [rid],
                                    existing_entities,
                                )
                                total_resolved += linked
                        continue

                    verbatim_to_refs: dict[str, list[str]] = {}
                    for r in batch:
                        vt = r.get("verbatim_text", "")
                        rid = r.get("id")
                        if vt and rid:
                            verbatim_to_refs.setdefault(vt, []).append(rid)

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
                            conn, entity_name, inferred_type,
                            group_ref_ids, existing_entities,
                        )
                        total_resolved += linked

            place_refs = _extract_query_results(
                await conn.fetch(
                    "SELECT r.event, r.canonical_entity FROM reference r "
                    "JOIN event e ON r.event = e.id "
                    "WHERE e.document = $1 "
                    "AND r.reference_type = 'espacio' "
                    "AND r.canonical_entity IS NOT NULL",
                    document_id,
                )
            )
            if place_refs:
                event_to_place: dict[str, str] = {}
                for pr in place_refs:
                    evt = pr.get("event")
                    ce = pr.get("canonical_entity")
                    if evt and ce:
                        event_to_place[str(evt)] = ce
                for eid, ce_id in event_to_place.items():
                    try:
                        await conn.execute(
                            "UPDATE event SET location_place_id = $2 WHERE id = $1",
                            eid, ce_id,
                        )
                    except Exception as exc:
                        activity.logger.warning(
                            "Failed to set location_place_id on event %s: %s",
                            eid, exc,
                        )

            person_refs = _extract_query_results(
                await conn.fetch(
                    "SELECT r.event, r.canonical_entity, r.verbatim_text FROM reference r "
                    "JOIN event e ON r.event = e.id "
                    "WHERE e.document = $1 "
                    "AND r.reference_type = 'humanos' "
                    "AND r.canonical_entity IS NOT NULL",
                    document_id,
                )
            )
            if person_refs:
                event_person_pairs = set()
                for pr in person_refs:
                    evt = pr.get("event")
                    ce = pr.get("canonical_entity")
                    if evt and ce:
                        event_person_pairs.add((str(evt), str(ce)))
                for eid, ce_id in event_person_pairs:
                    try:
                        participant_id = uuid.uuid4().hex
                        await conn.execute(
                            "INSERT INTO event_participant "
                            "(id, in_event, out_entity, role, confidence) "
                            "VALUES ($1, $2, $3, 'subject', 1.0)",
                            participant_id, eid, ce_id,
                        )
                    except Exception as exc:
                        activity.logger.warning(
                            "Failed to INSERT event_participant "
                            "event=%s entity=%s: %s",
                            eid, ce_id, exc,
                        )

            activity.logger.info(
                "resolve_entities_activity completed [document_id=%s] "
                "[resolved=%d] [created=%d] [skipped=%d] "
                "[location_links=%d] [participant_edges=%d]",
                document_id,
                total_resolved,
                total_created,
                skipped_count,
                len(event_to_place) if place_refs else 0,
                len(event_person_pairs) if person_refs else 0,
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
            "PostgreSQL connection failed in resolve_entities_activity: %s",
            exc,
        )
        await _log.log(document_id, "resolve_entities", "error",
                       f"Connection failed: {exc}")
        return {"error": str(exc), "document_id": document_id}
    except Exception as exc:
        activity.logger.error(
            "Unexpected error in resolve_entities_activity: %s",
            exc,
        )
        await _log.log(document_id, "resolve_entities", "error",
                       f"Unexpected error: {exc}")
        return {"error": str(exc), "document_id": document_id}
