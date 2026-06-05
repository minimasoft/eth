"""Create canonical_entity records for extracted events."""

from __future__ import annotations

import uuid

from temporalio import activity

from eth_pipeline.activities._common import _db_params, _extract_query_results
from eth_pipeline.db import get_db
from eth_pipeline.processing_log import ProcessingLogger


@activity.defn
async def create_event_canonical_entities_activity(
    document_id: str,
) -> dict:
    params = _db_params()
    _log = ProcessingLogger(params)

    activity.logger.info(
        "create_event_canonical_entities_activity called "
        "[document_id=%s]",
        document_id,
    )
    await _log.log(document_id, "create_event_entities", "info",
                   "Starting event canonical entity creation")

    try:
        async with get_db(**params) as conn:
            count_row = await conn.fetchrow(
                "SELECT COUNT(*)::int AS count FROM event WHERE document = $1",
                document_id,
            )
            event_count = count_row["count"] if count_row else 0

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

            activity.logger.info(
                "Nullifying prior event entities [document_id=%s]",
                document_id,
            )
            await _log.log(document_id, "create_event_entities", "info",
                           "Deleting prior event entities for this document")

            await conn.execute(
                "DELETE FROM event_entity_link WHERE event IN ("
                "SELECT id FROM canonical_entity "
                "WHERE entity_type = 'event' AND properties->>'document_id' = $1"
                ")",
                document_id,
            )
            await conn.execute(
                "DELETE FROM canonical_entity "
                "WHERE entity_type = 'event' AND properties->>'document_id' = $1",
                document_id,
            )

            stored_events = _extract_query_results(
                await conn.fetch(
                    "SELECT * FROM event WHERE document = $1",
                    document_id,
                )
            )

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

            entities_created = 0
            links_created = 0

            for event in stored_events:
                que_paso = event.get("que_paso", "") or ""
                tiempo = event.get("tiempo") or ""
                espacio = event.get("espacio") or ""
                humanos = event.get("humanos") or ""
                objetos = event.get("objetos") or ""

                truncated = que_paso[:80].strip()
                if len(que_paso) > 80:
                    name = f"Event: {truncated}..."
                else:
                    name = f"Event: {truncated}"

                props = {
                    "title": que_paso[:80],
                    "description": que_paso,
                    "time_range": tiempo,
                    "location": espacio,
                    "participants": humanos,
                    "objects": objetos,
                    "document_id": document_id,
                }

                entity_id = uuid.uuid4().hex
                entity_result = await conn.fetchrow(
                    "INSERT INTO canonical_entity (id, name, entity_type, properties) "
                    "VALUES ($1, $2, 'event', $3) RETURNING id",
                    entity_id, name, props,
                )
                if not entity_result:
                    activity.logger.warning(
                        "Failed to create event canonical entity "
                        "[document_id=%s] [que_paso=%.40s]",
                        document_id,
                        que_paso,
                    )
                    continue

                event_entity_rid = entity_result["id"]
                entities_created += 1

                for field_value, entity_type_filter, role in [
                    (espacio, "place", "location"),
                    (humanos, "person", "participant"),
                    (objetos, "object", "object"),
                ]:
                    if not field_value:
                        continue

                    matched_entities = _extract_query_results(
                        await conn.fetch(
                            "SELECT id, name FROM canonical_entity "
                            "WHERE entity_type = $1 "
                            "AND name ILIKE '%' || $2 || '%'",
                            entity_type_filter, field_value,
                        )
                    )

                    reverse_entities = _extract_query_results(
                        await conn.fetch(
                            "SELECT id, name FROM canonical_entity "
                            "WHERE entity_type = $1 "
                            "AND $2 ILIKE '%' || name || '%'",
                            entity_type_filter, field_value,
                        )
                    )

                    seen_ids: set[str] = set()
                    for match in matched_entities + reverse_entities:
                        match_id = match.get("id")
                        match_id_str = str(match_id) if match_id else ""
                        if match_id_str and match_id_str not in seen_ids:
                            seen_ids.add(match_id_str)
                            try:
                                link_id = uuid.uuid4().hex
                                await conn.execute(
                                    "INSERT INTO event_entity_link "
                                    "(id, event, entity, relationship_type, role, confidence) "
                                    "VALUES ($1, $2, $3, 'involves', $4, 0.7)",
                                    link_id, event_entity_rid, match_id, role,
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
            "PostgreSQL connection failed in "
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
