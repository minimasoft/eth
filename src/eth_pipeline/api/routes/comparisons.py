from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from eth_pipeline.api.models import (
    ComparisonDocument,
    ComparisonEvent,
    ComparisonResponse,
)
from eth_pipeline.db import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Comparisons"])


@router.get("/comparisons/{source_id}", response_model=ComparisonResponse)
async def get_comparison(source_id: str) -> ComparisonResponse:
    """Cross-model comparison data for one source group.

    ``source_id`` may be either the source group id shared by upload
    fan-out siblings or a plain document id (a document always belongs to
    its own group), so any row can seed a comparison view.

    Returns every document row (model run) of the group plus every event
    extracted by any of them, each tagged with its model and the document
    span footprint used to align equivalent events across models.
    """
    try:
        async with get_db() as conn:
            doc_rows = await conn.fetch(
                "SELECT d.id, d.filename, d.status, d.provider_id, d.model, "
                "p.name AS provider_name, "
                "(SELECT COUNT(*) FROM event_v2 ev WHERE ev.document_id = d.id) AS event_count "
                "FROM document d "
                "LEFT JOIN llm_provider p ON p.id = d.provider_id "
                "WHERE d.source_id = $1 OR d.id = $1 "
                "ORDER BY d.created_at",
                source_id,
            )

            if not doc_rows:
                raise HTTPException(
                    status_code=404,
                    detail=f"No documents found for source: {source_id}",
                )

            doc_ids = [str(r["id"]) for r in doc_rows]

            event_rows = await conn.fetch(
                "SELECT ev.id, ev.document_id, ev.model, ev.provider_id, "
                "prov.name AS provider_name, "
                "ev.title, ev.description, ev.time_start, ev.time_end, "
                "(SELECT el.name FROM event_location el "
                " WHERE el.event_id = ev.id ORDER BY el.id LIMIT 1) AS location_name, "
                "(SELECT COUNT(*) FROM event_participant_v2 ep "
                " WHERE ep.event_id = ev.id) AS participant_count, "
                "(SELECT COUNT(*) FROM event_ref er "
                " WHERE er.event_id = ev.id) AS reference_count, "
                "(SELECT MIN(ed.chunk_index) FROM event_document ed "
                " WHERE ed.event_id = ev.id) AS chunk_index, "
                "(SELECT MIN(er.span_start) FROM event_ref er "
                " WHERE er.event_id = ev.id) AS span_start, "
                "(SELECT er.span_end FROM event_ref er "
                " WHERE er.event_id = ev.id ORDER BY er.span_start LIMIT 1) AS span_end "
                "FROM event_v2 ev "
                "LEFT JOIN llm_provider prov ON prov.id = ev.provider_id "
                "WHERE ev.document_id = ANY($1::text[]) "
                "ORDER BY ev.time_start NULLS LAST, ev.id",
                doc_ids,
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to query comparison for %s: %s", source_id, exc)
        raise HTTPException(
            status_code=502,
            detail="Failed to query database.",
        ) from exc

    resolved_source = source_id
    documents = [
        ComparisonDocument(
            document_id=str(r["id"]),
            filename=r.get("filename", ""),
            status=r.get("status", "unknown"),
            provider_id=r.get("provider_id"),
            provider_name=r.get("provider_name"),
            model=r.get("model"),
            event_count=int(r.get("event_count", 0) or 0),
        )
        for r in doc_rows
    ]

    events = [
        ComparisonEvent(
            event_id=str(r["id"]),
            document_id=str(r["document_id"]),
            model=r.get("model"),
            provider_name=r.get("provider_name"),
            title=r.get("title", ""),
            description=r.get("description", "") or "",
            time_start=r["time_start"].isoformat() if r.get("time_start") else None,
            time_end=r["time_end"].isoformat() if r.get("time_end") else None,
            location_name=r.get("location_name"),
            participant_count=int(r.get("participant_count", 0) or 0),
            reference_count=int(r.get("reference_count", 0) or 0),
            chunk_index=r.get("chunk_index"),
            span_start=r.get("span_start"),
            span_end=r.get("span_end"),
        )
        for r in event_rows
    ]

    logger.info(
        "Comparison for %s — %d model runs, %d events",
        source_id, len(documents), len(events),
    )

    return ComparisonResponse(
        source_id=resolved_source,
        filename=documents[0].filename if documents else None,
        documents=documents,
        events=events,
    )
