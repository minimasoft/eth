"""Persist extracted events and verbatim references to PostgreSQL."""

from __future__ import annotations

import os
import uuid

from temporalio import activity

from eth_pipeline.activities._common import (
    _db_params,
    _extract_query_results,
    _normalize,
)
from eth_pipeline.activities.update_document_status import (
    update_document_status_activity,
)
from eth_pipeline.db import get_db
from eth_pipeline.offsets import compute_reference_offsets
from eth_pipeline.processing_log import ProcessingLogger


@activity.defn
async def store_extraction_results_activity(
    document_id: str,
    result: dict,
) -> dict:
    params = _db_params()
    _log = ProcessingLogger(params)
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
        await update_document_status_activity(document_id, "processed")
        return {"document_id": document_id, "events_stored": 0, "references_stored": 0}

    try:
        async with get_db(**params) as conn:
            activity.logger.info(
                "Clearing prior extraction results [document_id=%s]",
                document_id,
            )
            await conn.execute(
                "DELETE FROM event_participant WHERE in_event IN "
                "(SELECT id FROM event WHERE document = $1)",
                document_id,
            )
            await conn.execute(
                "DELETE FROM reference WHERE event IN "
                "(SELECT id FROM event WHERE document = $1)",
                document_id,
            )
            await conn.execute(
                "DELETE FROM event WHERE document = $1",
                document_id,
            )

            doc_rows = _extract_query_results(
                await conn.fetch(
                    "SELECT mime_type FROM document WHERE id = $1",
                    document_id,
                )
            )
            mime_type = doc_rows[0].get("mime_type", "") if doc_rows else ""
            is_plain_text = mime_type.startswith("text/")

            chunk_rows = _extract_query_results(
                await conn.fetch(
                    "SELECT chunk_index, page_start, page_end, "
                    "offset_start, offset_end "
                    "FROM document_chunk "
                    "WHERE document = $1 "
                    "ORDER BY chunk_index ASC",
                    document_id,
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

            total_references = 0
            dedup_refs_skipped = 0
            seen_refs: set[tuple[str, str, str]] = set()
            for event_idx, event_data in enumerate(events):
                time_window = None
                ds = event_data.get("date_start")
                de = event_data.get("date_end")
                if ds or de:
                    time_window = {}
                    if ds:
                        time_window["start"] = ds
                    if de:
                        time_window["end"] = de
                    dp = event_data.get("date_precision")
                    if dp:
                        time_window["precision"] = dp

                location_point = None
                loc = event_data.get("location")
                if loc and isinstance(loc, dict):
                    location_point = {}
                    if loc.get("place_name"):
                        location_point["label"] = str(loc["place_name"])
                    if loc.get("lat") is not None:
                        location_point["lat"] = float(loc["lat"])
                    if loc.get("lon") is not None:
                        location_point["lon"] = float(loc["lon"])

                location_place_id = None
                if location_point and location_point.get("label"):
                    loc_row = await conn.fetchrow(
                        "SELECT id FROM canonical_entity "
                        "WHERE entity_type = 'place' AND name = $1 "
                        "LIMIT 1",
                        str(location_point["label"]),
                    )
                    if loc_row:
                        location_place_id = loc_row["id"]
                    else:
                        loc_create_id = uuid.uuid4().hex
                        loc_create = await conn.fetchrow(
                            "INSERT INTO canonical_entity (id, entity_type, name, properties) "
                            "VALUES ($1, 'place', $2, $3) RETURNING id",
                            loc_create_id,
                            str(location_point["label"]),
                            {
                                "lat": location_point.get("lat"),
                                "lon": location_point.get("lon"),
                            },
                        )
                        if loc_create:
                            location_place_id = loc_create["id"]

                event_id = uuid.uuid4().hex
                event_result = await conn.fetchrow(
                    "INSERT INTO event "
                    "(id, que_paso, espacio, tiempo, humanos, objetos, "
                    "time_window, location_point, location_place_id, document, "
                    "extraction_confidence) "
                    "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, 1.0) "
                    "RETURNING id",
                    event_id,
                    event_data.get("que_paso", ""),
                    event_data.get("espacio") or "",
                    event_data.get("tiempo") or "",
                    event_data.get("humanos") or "",
                    event_data.get("objetos") or "",
                    time_window,
                    location_point,
                    location_place_id,
                    document_id,
                )
                if not event_result:
                    activity.logger.error(
                        "Could not extract event id from create result",
                    )
                    continue
                event_rid = event_result["id"]

                participants = event_data.get("participants") or []
                for p in participants:
                    p_name = str(p.get("name", "")).strip()
                    p_role = str(p.get("role", "subject"))
                    if not p_name:
                        continue
                    try:
                        p_row = await conn.fetchrow(
                            "SELECT id FROM canonical_entity "
                            "WHERE entity_type = 'person' AND name = $1 "
                            "LIMIT 1",
                            p_name,
                        )
                        if p_row:
                            p_rid = p_row["id"]
                        else:
                            p_create_id = uuid.uuid4().hex
                            p_create = await conn.fetchrow(
                                "INSERT INTO canonical_entity (id, entity_type, name, properties) "
                                "VALUES ($1, 'person', $2, '{}'::jsonb) RETURNING id",
                                p_create_id, p_name,
                            )
                            if not p_create:
                                continue
                            p_rid = p_create["id"]
                        participant_id = uuid.uuid4().hex
                        await conn.execute(
                            "INSERT INTO event_participant "
                            "(id, in_event, out_entity, role, confidence) "
                            "VALUES ($1, $2, $3, $4, 1.0)",
                            participant_id, event_rid, p_rid, p_role,
                        )
                    except Exception as exc:
                        activity.logger.warning(
                            "Failed to create event_participant edge "
                            "[event=%s] [participant=%s]: %s",
                            event_rid, p_name, exc,
                        )

                references = event_data.get("references", [])
                for ref_idx, ref in enumerate(references):
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

                    element_field = ref.get("element_field", ref_type)

                    vt = ref.get("verbatim_text", "") or ""
                    dedup_key = (_normalize(vt), str(event_rid), element_field)
                    if dedup_key in seen_refs:
                        dedup_refs_skipped += 1
                        continue
                    seen_refs.add(dedup_key)

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

                    ref_id = uuid.uuid4().hex
                    await conn.execute(
                        "INSERT INTO reference "
                        "(id, reference_type, verbatim_text, span_start, span_end, "
                        "page_number, page_offset_start, page_offset_end, "
                        "element_field, reference_index, event) "
                        "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)",
                        ref_id, ref_type, vt, ss, se,
                        offset_result["page_number"],
                        offset_result["page_offset_start"],
                        offset_result["page_offset_end"],
                        element_field, ref_idx, event_rid,
                    )
                    total_references += 1

            events_stored = len(events)
            activity.logger.info(
                "Stored %d events and %d references [document_id=%s] "
                "[dedup_skipped=%d]",
                events_stored,
                total_references,
                document_id,
                dedup_refs_skipped,
            )
            await _log.log(document_id, "store_results", "info",
                           f"Stored {events_stored} events and {total_references} references",
                           {"events_stored": events_stored,
                            "references_stored": total_references,
                            "dedup_skipped": dedup_refs_skipped})
    except ConnectionError as exc:
        activity.logger.error(
            "PostgreSQL connection failed in store_extraction_results_activity: "
            "%s",
            exc,
        )
        await _log.log(document_id, "store_results", "error",
                       f"Connection failed: {exc}")
        await update_document_status_activity(document_id, "failed", str(exc))
        return {"error": str(exc), "document_id": document_id}
    except Exception as exc:
        import traceback, json
        error_detail = {
            "type": type(exc).__name__,
            "message": str(exc),
            "repr": repr(exc),
            "traceback": traceback.format_exc()[-2000:],
            "document_id": document_id,
        }
        activity.logger.error(
            "Unexpected error in store_extraction_results_activity: %s",
            json.dumps(error_detail, default=str),
        )
        await _log.log(document_id, "store_results", "error",
                       f"Unexpected error: {type(exc).__name__}: {exc}")
        await update_document_status_activity(document_id, "failed", str(exc))
        return {"error": str(exc), "document_id": document_id}

    return {
        "document_id": document_id,
        "events_stored": len(events),
        "references_stored": total_references,
    }
