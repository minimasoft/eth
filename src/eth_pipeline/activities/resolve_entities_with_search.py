"""Resolve verbatim references using exact-match search first, then LLM grouping + DB dedup."""

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
async def resolve_entities_with_search_activity(document_id: str) -> dict:
    params = _db_params()
    _log = ProcessingLogger(params)

    activity.logger.info(
        "resolve_entities_with_search_activity called "
        "[document_id=%s]",
        document_id,
    )
    await _log.log(document_id, "resolve_entities_search", "info",
                   "Starting search-first entity resolution")

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

            activity.logger.info(
                "Nullifying prior resolution links [document_id=%s] "
                "[ref_count=%d]",
                document_id,
                len(references),
            )
            await conn.execute(
                "UPDATE reference SET canonical_entity = NULL, "
                "entity_id = NULL, resolution_confidence = NULL "
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
            total_llm_calls = 0
            total_exact_matches = 0

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
                                "Failed to update reference %s with "
                                "entity_id %s: %s",
                                rid, matched_ce_id, exc,
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
                                    await conn.execute(
                                        "UPDATE reference SET entity_id = $2, "
                                        "canonical_entity = $3, "
                                        "resolution_confidence = 1.0 "
                                        "WHERE id = $1",
                                        ref.get("id"), entity_id_val, entity_id_val,
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
            "PostgreSQL connection failed in "
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
