from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from eth_pipeline.api.models import (
    EntityDeleted,
    EntityDetailReference,
    EntityDetailResponse,
    EntityListItem,
    EntityListResponse,
    MergeRequest,
    MergeResponse,
    SplitPartition,
    SplitRequest,
    SplitResponse,
)
from eth_pipeline.db import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Entities"])


# =======================================================================
# List entities (paginated)
# =======================================================================


@router.get("/entities", response_model=EntityListResponse)
async def list_entities(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    search: str | None = Query(None),
    entity_type: str | None = Query(None),
) -> EntityListResponse:
    """List canonical entities with pagination, search, and type filtering."""
    offset = (page - 1) * per_page

    where_parts: list[str] = ["superseded_by IS NULL"]
    params: list[object] = []

    if search:
        where_parts.append(f"name ILIKE ${len(params) + 1}")
        params.append(f"%{search}%")

    if entity_type:
        where_parts.append(f"entity_type = ${len(params) + 1}")
        params.append(entity_type)

    where_clause = " AND ".join(where_parts)

    try:
        async with get_db() as db:
            total = await db.fetchval(
                f"SELECT COUNT(*) AS total FROM canonical_entity WHERE {where_clause}",
                *params,
            ) or 0
    except Exception as exc:
        logger.error("Failed to count entities: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Failed to query database.",
        ) from exc

    total = int(total)

    if total == 0:
        pages = 0
    else:
        pages = max(1, (total + per_page - 1) // per_page)

    try:
        async with get_db() as db:
            rows = await db.fetch(
                f"SELECT * FROM canonical_entity WHERE {where_clause} "
                f"ORDER BY name ASC LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}",
                *params, per_page, offset,
            )
    except Exception as exc:
        logger.error("Failed to query entities: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Failed to query database.",
        ) from exc

    entity_ids = [str(r["id"]) for r in rows]
    ref_counts: dict[str, int] = {}
    if entity_ids:
        try:
            async with get_db() as db:
                placeholders = ", ".join(f"${i + 1}" for i in range(len(entity_ids)))
                count_rows = await db.fetch(
                    f"SELECT canonical_entity AS canonical_entity_id, COUNT(*) AS cnt FROM reference "
                    f"WHERE canonical_entity IN ({placeholders}) "
                    f"GROUP BY canonical_entity",
                    *entity_ids,
                )
                for cr in count_rows:
                    ref_counts[str(cr["canonical_entity_id"])] = cr["cnt"]

                # Also count references via entity_id column (Phase 17 search-first resolution)
                eid_placeholders = ", ".join(f"${i + 1 + len(entity_ids)}" for i in range(len(entity_ids)))
                eid_rows = await db.fetch(
                    f"SELECT entity_id AS eid, COUNT(*) AS cnt FROM reference "
                    f"WHERE entity_id IN ({eid_placeholders}) "
                    f"AND entity_id IS NOT NULL "
                    f"GROUP BY entity_id",
                    *entity_ids,
                )
                for er in eid_rows:
                    eid = str(er["eid"])
                    ref_counts[eid] = ref_counts.get(eid, 0) + er["cnt"]
        except Exception as exc:
            logger.warning("Failed to batch-count references: %s", exc)

    items: list[EntityListItem] = []
    for row in rows:
        eid = str(row["id"])
        items.append(EntityListItem(
            entity_id=eid,
            name=row.get("name", "") or "",
            entity_type=row.get("entity_type", "") or "",
            reference_count=ref_counts.get(eid, 0),
        ))

    logger.info(
        "Listed entities (page=%d, per_page=%d, search=%s, type=%s) — %d items of %d total",
        page,
        per_page,
        search or "",
        entity_type or "",
        len(items),
        total,
    )

    return EntityListResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
    )


# =======================================================================
# Merge entities endpoint
# =======================================================================


@router.post("/entities/merge", response_model=MergeResponse, status_code=200)
async def merge_entities(request: MergeRequest) -> MergeResponse:
    """Merge two canonical entities of the same type."""

    if request.source_id == request.target_id:
        logger.warning(
            "Merge rejected — self-merge attempted for entity %s",
            request.source_id,
        )
        raise HTTPException(
            status_code=400,
            detail="Cannot merge an entity into itself.",
        )

    try:
        async with get_db() as db:
            source_row = await db.fetchrow(
                "SELECT * FROM canonical_entity WHERE id = $1",
                request.source_id,
            )
    except Exception as exc:
        logger.error(
            "Failed to query source entity %s: %s",
            request.source_id,
            exc,
        )
        raise HTTPException(
            status_code=502,
            detail="Failed to query database.",
        ) from exc

    if not source_row:
        logger.warning(
            "Merge rejected — source entity %s not found",
            request.source_id,
        )
        raise HTTPException(
            status_code=404,
            detail=f"Source canonical entity {request.source_id} not found.",
        )

    try:
        async with get_db() as db:
            target_row = await db.fetchrow(
                "SELECT * FROM canonical_entity WHERE id = $1",
                request.target_id,
            )
    except Exception as exc:
        logger.error(
            "Failed to query target entity %s: %s",
            request.target_id,
            exc,
        )
        raise HTTPException(
            status_code=502,
            detail="Failed to query database.",
        ) from exc

    if not target_row:
        logger.warning(
            "Merge rejected — target entity %s not found",
            request.target_id,
        )
        raise HTTPException(
            status_code=404,
            detail=f"Target canonical entity {request.target_id} not found.",
        )

    source_type = source_row.get("entity_type")
    target_type = target_row.get("entity_type")
    if source_type != target_type:
        logger.warning(
            "Merge rejected — cross-type merge attempted: source=%s (%s), target=%s (%s)",
            request.source_id,
            source_type,
            request.target_id,
            target_type,
        )
        raise HTTPException(
            status_code=400,
            detail=f"Cannot merge entities of different types: source is '{source_type}', target is '{target_type}'.",
        )

    if source_row.get("superseded_by") is not None:
        logger.warning(
            "Merge rejected — source entity %s is already merged (superseded_by=%s)",
            request.source_id,
            source_row["superseded_by"],
        )
        raise HTTPException(
            status_code=400,
            detail=f"Source canonical entity {request.source_id} has already been merged into another entity.",
        )

    if target_row.get("superseded_by") is not None:
        logger.warning(
            "Merge rejected — target entity %s is already merged (superseded_by=%s)",
            request.target_id,
            target_row["superseded_by"],
        )
        raise HTTPException(
            status_code=400,
            detail=f"Target canonical entity {request.target_id} has already been merged into another entity.",
        )

    try:
        async with get_db() as db:
            rewired_count = await db.fetchval(
                "SELECT COUNT(*) AS cnt FROM reference WHERE canonical_entity = $1",
                request.source_id,
            ) or 0
    except Exception as exc:
        logger.error(
            "Failed to count references for source entity %s: %s",
            request.source_id,
            exc,
        )
        raise HTTPException(
            status_code=502,
            detail="Failed to query database during reference count.",
        ) from exc

    rewired_count = int(rewired_count)

    try:
        async with get_db() as db:
            await db.execute(
                "UPDATE reference SET canonical_entity = $1, "
                "resolution_confidence = 1.0, updated_at = NOW() "
                "WHERE canonical_entity = $2",
                request.target_id, request.source_id,
            )

            loc_result = await db.execute(
                "UPDATE event SET location_place_id = $1 "
                "WHERE location_place_id = $2",
                request.target_id, request.source_id,
            )
            loc_affected = int(loc_result.split()[-1]) if loc_result else 0

            part_result = await db.execute(
                "UPDATE event_participant SET out_entity = $1 "
                "WHERE out_entity = $2",
                request.target_id, request.source_id,
            )
            part_affected = int(part_result.split()[-1]) if part_result else 0

            await db.execute(
                "UPDATE canonical_entity SET "
                "superseded_by = $1, updated_at = NOW() "
                "WHERE id = $2",
                request.target_id, request.source_id,
            )

        logger.info(
            "Merge complete: source=%s target=%s rewired=%d references, "
            "%d events' location_place_id, %d event_participant edges",
            request.source_id,
            request.target_id,
            rewired_count,
            loc_affected,
            part_affected,
        )
    except Exception as exc:
        logger.error(
            "Merge failed during reference/location/participant rewiring: source=%s target=%s: %s",
            request.source_id,
            request.target_id,
            exc,
        )
        raise HTTPException(
            status_code=502,
            detail=f"Merge failed during reference/location/participant rewiring: {exc}",
        ) from exc

    return MergeResponse(
        success=True,
        message=f"Merged canonical entity {request.source_id} into {request.target_id}, rewired {rewired_count} references.",
        source_id=request.source_id,
        target_id=request.target_id,
        rewired_count=rewired_count,
    )


# =======================================================================
# Split entity endpoint
# =======================================================================


@router.post(
    "/entities/{entity_type}/{entity_id}/split",
    response_model=SplitResponse,
    status_code=200,
)
async def split_entity(
    entity_type: str,
    entity_id: str,
    request: SplitRequest,
) -> SplitResponse:
    """Split references from a canonical entity into new entities."""

    valid_types = {"place", "person", "object"}
    if entity_type not in valid_types:
        logger.warning(
            "Split rejected — invalid entity_type '%s' (must be one of %s)",
            entity_type,
            sorted(valid_types),
        )
        raise HTTPException(
            status_code=400,
            detail=f"Invalid entity type '{entity_type}'. Must be one of: {', '.join(sorted(valid_types))}.",
        )

    try:
        async with get_db() as db:
            source_row = await db.fetchrow(
                "SELECT * FROM canonical_entity WHERE id = $1",
                entity_id,
            )
    except Exception as exc:
        logger.error(
            "Failed to query source entity %s/%s: %s",
            entity_type,
            entity_id,
            exc,
        )
        raise HTTPException(
            status_code=502,
            detail="Failed to query database.",
        ) from exc

    if not source_row:
        logger.warning(
            "Split rejected — entity %s/%s not found",
            entity_type,
            entity_id,
        )
        raise HTTPException(
            status_code=404,
            detail=f"Canonical entity {entity_id} of type '{entity_type}' not found.",
        )

    if not request.partitions:
        logger.warning(
            "Split rejected — no partitions provided for entity %s",
            entity_id,
        )
        raise HTTPException(
            status_code=400,
            detail="At least one partition is required.",
        )

    for i, partition in enumerate(request.partitions):
        if not partition.reference_ids:
            logger.warning(
                "Split rejected — partition %d has no reference_ids for entity %s",
                i,
                entity_id,
            )
            raise HTTPException(
                status_code=400,
                detail=f"Partition {i} ('{partition.new_entity_name}') has no reference IDs.",
            )

    all_ref_ids: list[str] = []
    for partition in request.partitions:
        all_ref_ids.extend(partition.reference_ids)

    if len(all_ref_ids) != len(set(all_ref_ids)):
        logger.warning(
            "Split rejected — duplicate reference IDs across partitions for entity %s",
            entity_id,
        )
        raise HTTPException(
            status_code=400,
            detail="Duplicate reference IDs found across partitions. Each reference can only be moved once.",
        )

    try:
        async with get_db() as db:
            placeholders = ", ".join(f"${i + 1}" for i in range(len(all_ref_ids)))
            ref_rows = await db.fetch(
                f"SELECT id, canonical_entity AS canonical_entity_id FROM reference "
                f"WHERE id IN ({placeholders})",
                *all_ref_ids,
            )
    except Exception as exc:
        logger.error(
            "Failed to query references during split: %s",
            exc,
        )
        raise HTTPException(
            status_code=502,
            detail="Failed to query database.",
        ) from exc

    ref_map: dict[str, str | None] = {}
    for r in ref_rows:
        ref_map[str(r["id"])] = str(r["canonical_entity_id"]) if r["canonical_entity_id"] else None

    for ref_id in all_ref_ids:
        ref_canonical = ref_map.get(ref_id)
        if ref_canonical is None and ref_id not in ref_map:
            logger.warning(
                "Split rejected — reference %s not found",
                ref_id,
            )
            raise HTTPException(
                status_code=400,
                detail=f"Reference {ref_id} not found.",
            )
        if ref_canonical != entity_id:
            logger.warning(
                "Split rejected — reference %s does not point to entity %s (points to %s)",
                ref_id,
                entity_id,
                ref_canonical,
            )
            raise HTTPException(
                status_code=400,
                detail=f"Reference {ref_id} does not belong to canonical entity {entity_id}.",
            )

    groups: dict[str, list[SplitPartition]] = {}
    for partition in request.partitions:
        name = partition.new_entity_name
        if name not in groups:
            groups[name] = []
        groups[name].append(partition)

    new_entities_info: list[dict] = []
    total_moved = 0

    async with get_db() as db:
        for new_name in groups:
            merged_ref_ids: list[str] = []
            for partition in groups[new_name]:
                merged_ref_ids.extend(partition.reference_ids)

            try:
                row = await db.fetchrow(
                    "INSERT INTO canonical_entity (entity_type, name, properties, superseded_by) "
                    "VALUES ($1, $2, $3, $4) RETURNING *",
                    entity_type,
                    new_name,
                    {"split_from": entity_id},
                    None,
                )
            except Exception as exc:
                logger.error(
                    "Failed to create canonical_entity '%s' during split: %s",
                    new_name,
                    exc,
                )
                raise HTTPException(
                    status_code=502,
                    detail=f"Failed to create canonical entity '{new_name}'.",
                ) from exc

            if not row or not row.get("id"):
                logger.error(
                    "Could not parse created entity ID from response: %s",
                    str(row)[:300],
                )
                raise HTTPException(
                    status_code=502,
                    detail=f"Failed to parse created entity ID for '{new_name}'.",
                )

            new_entity_id = str(row["id"])

            ref_placeholders = ", ".join(f"${i + 1}" for i in range(len(merged_ref_ids)))
            try:
                await db.execute(
                    f"UPDATE reference SET canonical_entity = $1, "
                    f"resolution_confidence = 1.0, updated_at = NOW() "
                    f"WHERE id IN ({ref_placeholders})",
                    new_entity_id, *merged_ref_ids,
                )
            except Exception as exc:
                logger.error(
                    "Failed to update references for new entity '%s': %s",
                    new_name,
                    exc,
                )
                raise HTTPException(
                    status_code=502,
                    detail=f"Failed to update references for '{new_name}'.",
                ) from exc

            new_entities_info.append({
                "name": new_name,
                "entity_id": new_entity_id,
            })
            total_moved += len(merged_ref_ids)

    logger.info(
        "Split complete: entity=%s/%s partitions=%d total_moved=%d new_entities=%s",
        entity_type,
        entity_id,
        len(request.partitions),
        total_moved,
        [e["name"] for e in new_entities_info],
    )

    # Log retention counts for v6.0 structured fields: location_place_id and
    # event_participant edges are NOT transferred to new split entities per
    # the "appropriate partition" principle — new entities are separate from
    # the original and should not inherit its event connections.
    try:
        async with get_db() as db:
            loc_count = await db.fetchval(
                "SELECT COUNT(*) AS cnt FROM event WHERE location_place_id = $1",
                entity_id,
            ) or 0
            part_count = await db.fetchval(
                "SELECT COUNT(*) AS cnt FROM event_participant WHERE out_entity = $1",
                entity_id,
            ) or 0
            loc_count = int(loc_count)
            part_count = int(part_count)
            logger.info(
                "Split entity %s (%s): %d events with location_place_id retained by original, "
                "%d event_participant edges retained by original "
                "(no links transferred to new entities — appropriate partition)",
                entity_id,
                entity_type,
                loc_count,
                part_count,
            )
    except Exception as exc:
        logger.warning(
            "Failed to query location_place_id/event_participant retention counts "
            "for split entity %s: %s",
            entity_id,
            exc,
        )

    return SplitResponse(
        success=True,
        message=(
            f"Split canonical entity {entity_id} into {len(new_entities_info)} new "
            f"entities, moved {total_moved} references."
        ),
        entity_type=entity_type,
        original_entity_id=entity_id,
        new_entities=new_entities_info,
        partition_count=len(new_entities_info),
        total_references_moved=total_moved,
    )


# =======================================================================
# Delete entity
# =======================================================================


@router.delete(
    "/entities/{entity_id}",
    response_model=EntityDeleted,
)
async def delete_entity(entity_id: str) -> EntityDeleted:
    """Delete a canonical entity.

    All references linked to this entity will have their canonical_entity
    and entity_id set to NULL (via ON DELETE SET NULL). Event location
    links, event_entity_link edges, and event_participant entries are
    handled by the corresponding foreign key constraints.
    """
    try:
        async with get_db() as db:
            entity_row = await db.fetchrow(
                "SELECT id FROM canonical_entity WHERE id = $1",
                entity_id,
            )
    except Exception as exc:
        logger.error("Failed to query entity %s: %s", entity_id, exc)
        raise HTTPException(
            status_code=502,
            detail="Failed to query database.",
        ) from exc

    if not entity_row:
        logger.warning("Entity %s not found for deletion", entity_id)
        raise HTTPException(
            status_code=404,
            detail=f"Canonical entity {entity_id} not found.",
        )

    try:
        async with get_db() as db:
            ref_count = await db.fetchval(
                "SELECT COUNT(*) AS total FROM reference "
                "WHERE canonical_entity = $1 OR entity_id = $1",
                entity_id,
            ) or 0

            ref_count = int(ref_count)

            await db.execute(
                "DELETE FROM canonical_entity WHERE id = $1",
                entity_id,
            )

        logger.info(
            "Deleted canonical entity %s (%d references affected)",
            entity_id,
            ref_count,
        )
    except Exception as exc:
        logger.error("Failed to delete entity %s: %s", entity_id, exc)
        raise HTTPException(
            status_code=502,
            detail="Failed to delete canonical entity.",
        ) from exc

    return EntityDeleted(
        entity_id=entity_id,
        entity_deleted=True,
        references_affected=ref_count,
    )


# =======================================================================
# Get entity details (with linked references)
# =======================================================================


@router.get(
    "/entities/{entity_id}",
    response_model=EntityDetailResponse,
)
async def get_entity(entity_id: str) -> EntityDetailResponse:
    """Retrieve a canonical entity with its linked references."""

    try:
        async with get_db() as db:
            entity_row = await db.fetchrow(
                "SELECT * FROM canonical_entity WHERE id = $1",
                entity_id,
            )
    except Exception as exc:
        logger.error("Failed to query entity %s: %s", entity_id, exc)
        raise HTTPException(
            status_code=502,
            detail="Failed to query database.",
        ) from exc

    if not entity_row:
        logger.warning("Entity %s not found", entity_id)
        raise HTTPException(
            status_code=404,
            detail=f"Canonical entity {entity_id} not found.",
        )

    resolved_id = str(entity_row["id"])

    try:
        async with get_db() as db:
            ref_count = await db.fetchval(
                "SELECT COUNT(*) AS total FROM reference WHERE canonical_entity = $1",
                entity_id,
            ) or 0
    except Exception:
        ref_count = 0

    ref_count = int(ref_count)

    try:
        async with get_db() as db:
            ref_rows = await db.fetch(
                "SELECT r.id, r.reference_type, r.verbatim_text, "
                "r.created_at, r.canonical_entity, "
                "e.que_paso AS event_que_paso, e.id AS event_id, "
                "d.filename AS doc_filename, d.id AS doc_id "
                "FROM reference r "
                "LEFT JOIN event e ON r.event = e.id "
                "LEFT JOIN document d ON e.document = d.id "
                "WHERE r.canonical_entity = $1 "
                "ORDER BY r.created_at DESC",
                entity_id,
            )
    except Exception as exc:
        logger.warning("Failed to query references for entity %s: %s", entity_id, exc)
        ref_rows = []

    references: list[EntityDetailReference] = []
    for row in ref_rows:
        references.append(EntityDetailReference(
            reference_id=str(row["id"]),
            reference_type=row.get("reference_type", "") or "",
            verbatim_text=row.get("verbatim_text", "") or "",
            event_que_paso=row.get("event_que_paso"),
            event_id=str(row["event_id"]) if row.get("event_id") else None,
            document_filename=row.get("doc_filename"),
            document_id=str(row["doc_id"]) if row.get("doc_id") else None,
        ))

    logger.info(
        "Entity detail for %s (%s) — %d references",
        resolved_id,
        entity_row.get("name", "") or "",
        len(references),
    )

    return EntityDetailResponse(
        entity_id=resolved_id,
        name=entity_row.get("name", "") or "",
        entity_type=entity_row.get("entity_type", "") or "",
        reference_count=ref_count,
        properties=entity_row.get("properties"),
        references=references,
    )
