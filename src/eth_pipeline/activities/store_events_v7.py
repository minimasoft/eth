"""Persist v7 extracted events with per-chunk delete-then-insert replay safety."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import uuid

from temporalio import activity

from eth_pipeline.activities._common import _db_params, _extract_query_results
from eth_pipeline.db import get_db
from eth_pipeline.processing_log import ProcessingLogger


def _parse_date(val: str | None) -> datetime | None:
    """Convert an LLM-returned date string to a timezone-aware datetime."""
    if val is None:
        return None
    if isinstance(val, datetime):
        if val.tzinfo is None:
            return val.replace(tzinfo=timezone.utc)
        return val
    if isinstance(val, str):
        val = val.strip()
        if not val:
            return None
        if val.endswith("Z"):
            val = val[:-1]
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(val, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
    return None


@activity.defn
async def store_events_v7_activity(
    document_id: str,
    chunk_index: int,
    events: list[dict],
) -> dict:
    params = _db_params()
    _log = ProcessingLogger(params)

    activity.logger.info(
        "store_events_v7_activity called [document_id=%s] [chunk_index=%d] [event_count=%d]",
        document_id,
        chunk_index,
        len(events),
    )
    await _log.log(document_id, "store_events_v7", "info",
                   f"Starting storage of chunk {chunk_index}: {len(events)} events")

    if not events:
        activity.logger.info(
            "No events to store for chunk %d [document_id=%s]",
            chunk_index,
            document_id,
        )
        await _log.log(document_id, "store_events_v7", "info",
                       f"No events to store for chunk {chunk_index}")
        try:
            async with get_db(**params) as conn:
                async with conn.transaction():
                    await conn.execute(
                        "DELETE FROM event_v2 WHERE id IN ("
                        "SELECT event_id FROM event_document "
                        "WHERE document_id = $1 AND chunk_index = $2"
                        ")",
                        document_id,
                        chunk_index,
                    )
        except ConnectionError:
            pass
        return {
            "document_id": document_id,
            "chunk_index": chunk_index,
            "events_stored": 0,
            "references_stored": 0,
        }

    try:
        async with get_db(**params) as conn:
            async with conn.transaction():
                await conn.execute(
                    "DELETE FROM event_v2 WHERE id IN ("
                    "SELECT event_id FROM event_document "
                    "WHERE document_id = $1 AND chunk_index = $2"
                    ")",
                    document_id,
                    chunk_index,
                )

                total_references = 0
                for ev in events:
                    parsed_start = _parse_date(ev.get("time_start"))
                    parsed_end = _parse_date(ev.get("time_end"))
                    if parsed_start is None:
                        activity.logger.warning(
                            "Event has missing or unparseable time_start: %s",
                            json.dumps(ev, default=str),
                        )
                    event_id = uuid.uuid4().hex
                    await conn.execute(
                        "INSERT INTO event_v2 "
                        "(id, document_id, title, description, "
                        "time_start, time_end, time_precision, "
                        "extraction_confidence) "
                        "VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
                        event_id,
                        document_id,
                        ev.get("title", ""),
                        ev.get("description", ""),
                        parsed_start,
                        parsed_end,
                        ev.get("time_precision"),
                        1.0,
                    )

                    loc = ev.get("location")
                    if loc and isinstance(loc, dict) and loc.get("name"):
                        loc_id = uuid.uuid4().hex
                        await conn.execute(
                            "INSERT INTO event_location "
                            "(id, event_id, name, location_type) "
                            "VALUES ($1, $2, $3, $4)",
                            loc_id,
                            event_id,
                            loc["name"],
                            loc.get("location_type"),
                        )

                    for p in (ev.get("participants") or []):
                        p_name = str(p.get("name", "")).strip()
                        p_role = str(p.get("role", "subject"))
                        if not p_name:
                            continue
                        participant_id = uuid.uuid4().hex
                        await conn.execute(
                            "INSERT INTO event_participant_v2 "
                            "(id, event_id, name, role, confidence) "
                            "VALUES ($1, $2, $3, $4, $5)",
                            participant_id,
                            event_id,
                            p_name,
                            p_role,
                            1.0,
                        )

                    ed_id = uuid.uuid4().hex
                    await conn.execute(
                        "INSERT INTO event_document "
                        "(id, event_id, document_id, chunk_index) "
                        "VALUES ($1, $2, $3, $4)",
                        ed_id,
                        event_id,
                        document_id,
                        chunk_index,
                    )

                    for ref in (ev.get("references") or []):
                        ref_type = ref.get("reference_type", "")
                        if ref_type not in ("location", "participant", "time", "description"):
                            activity.logger.warning(
                                "Skipping reference with invalid reference_type='%s' "
                                "[document_id=%s] [chunk_index=%d]",
                                ref_type,
                                document_id,
                                chunk_index,
                            )
                            continue
                        vt = ref.get("verbatim_text", "")
                        ss = int(ref.get("span_start", 0))
                        se = int(ref.get("span_end", 0))
                        ref_id = uuid.uuid4().hex
                        await conn.execute(
                            "INSERT INTO event_ref "
                            "(id, event_id, reference_type, verbatim_text, "
                            "span_start, span_end, chunk_index) "
                            "VALUES ($1, $2, $3, $4, $5, $6, $7)",
                            ref_id,
                            event_id,
                            ref_type,
                            vt,
                            ss,
                            se,
                            chunk_index,
                        )
                        total_references += 1

    except ConnectionError as exc:
        activity.logger.error(
            "PostgreSQL connection failed in store_events_v7_activity: %s",
            exc,
        )
        await _log.log(document_id, "store_events_v7", "error",
                       f"Connection failed: {exc}")
        return {"error": str(exc), "document_id": document_id}
    except Exception as exc:
        import traceback

        error_detail = {
            "type": type(exc).__name__,
            "message": str(exc),
            "repr": repr(exc),
            "traceback": traceback.format_exc()[-2000:],
            "document_id": document_id,
        }
        activity.logger.error(
            "Unexpected error in store_events_v7_activity: %s",
            json.dumps(error_detail, default=str),
        )
        await _log.log(document_id, "store_events_v7", "error",
                       f"Unexpected error: {type(exc).__name__}: {exc}")
        return {"error": str(exc), "document_id": document_id}

    activity.logger.info(
        "Stored %d events and %d references [document_id=%s] [chunk_index=%d]",
        len(events),
        total_references,
        document_id,
        chunk_index,
    )
    await _log.log(document_id, "store_events_v7", "info",
                   f"Stored {len(events)} events and {total_references} references "
                   f"for chunk {chunk_index}",
                   {"events_stored": len(events),
                    "references_stored": total_references,
                    "chunk_index": chunk_index})

    return {
        "document_id": document_id,
        "chunk_index": chunk_index,
        "events_stored": len(events),
        "references_stored": total_references,
    }
