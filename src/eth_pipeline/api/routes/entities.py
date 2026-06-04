from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from surrealdb import AsyncWsSurrealConnection

from eth_pipeline.api import app

from eth_pipeline.api.models import (
    EntityListItem,
    EntityListResponse,
    MergeRequest,
    MergeResponse,
    SplitPartition,
    SplitRequest,
    SplitResponse,
)

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
    db: AsyncWsSurrealConnection | None = app.state.db

    if db is None:
        logger.error("GET /entities rejected — SurrealDB unavailable")
        raise HTTPException(
            status_code=503,
            detail="SurrealDB is not available. Please try again later.",
        )

    offset = (page - 1) * per_page

    where_parts: list[str] = ["superseded_by IS NONE"]
    query_params: dict[str, object] = {}

    if search:
        where_parts.append("name LIKE $search")
        query_params["search"] = f"%{search}%"

    if entity_type:
        where_parts.append("entity_type = $entity_type")
        query_params["entity_type"] = entity_type

    where_clause = " AND ".join(where_parts)
    query_params["per_page"] = per_page
    query_params["offset"] = offset

    try:
        count_result = await db.query(
            f"SELECT count() AS total FROM canonical_entity WHERE {where_clause} GROUP ALL",
            query_params,
        )
    except Exception as exc:
        logger.error("Failed to count entities: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Failed to query database.",
        ) from exc

    total = 0
    count_records: list[dict] = [
        r for r in (count_result or []) if isinstance(r, dict)
    ]
    if count_records:
        cnt_val = count_records[0].get("total")
        if isinstance(cnt_val, dict):
            total = int(cnt_val.get("value", 0))
        elif cnt_val is not None:
            total = int(cnt_val)

    if total == 0:
        pages = 0
    else:
        pages = max(1, (total + per_page - 1) // per_page)

    try:
        data_result = await db.query(
            f"SELECT * FROM canonical_entity WHERE {where_clause} "
            "ORDER BY name ASC LIMIT $per_page START $offset",
            query_params,
        )
    except Exception as exc:
        logger.error("Failed to query entities: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Failed to query database.",
        ) from exc

    from surrealdb.data.types.record_id import RecordID

    data_records: list[dict] = [
        r for r in (data_result or []) if isinstance(r, dict)
    ]

    items: list[EntityListItem] = []
    for record in data_records:
        ent_id_val = record.get("id")
        entity_id: str = ""
        if isinstance(ent_id_val, RecordID):
            entity_id = ent_id_val.id
        elif isinstance(ent_id_val, str):
            entity_id = ent_id_val.split(":", 1)[1] if ":" in ent_id_val else ent_id_val

        ent_rid = RecordID("canonical_entity", entity_id)
        ref_count = 0
        try:
            ref_result = await db.query(
                "SELECT count() AS total FROM reference WHERE canonical_entity = $entity_ref GROUP ALL",
                {"entity_ref": ent_rid},
            )
        except Exception as exc:
            logger.warning(
                "Failed to count references for entity %s: %s",
                entity_id,
                exc,
            )
            ref_count = 0
        else:
            ref_records: list[dict] = [
                r for r in (ref_result or []) if isinstance(r, dict)
            ]
            if ref_records:
                cnt_val = ref_records[0].get("total")
                if isinstance(cnt_val, dict):
                    ref_count = int(cnt_val.get("value", 0))
                elif cnt_val is not None:
                    ref_count = int(cnt_val)

        items.append(EntityListItem(
            entity_id=entity_id,
            name=record.get("name", ""),
            entity_type=record.get("entity_type", ""),
            reference_count=ref_count,
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
    db: AsyncWsSurrealConnection | None = app.state.db

    if db is None:
        logger.error("POST /entities/merge rejected — SurrealDB unavailable")
        raise HTTPException(
            status_code=503,
            detail="SurrealDB is not available. Please try again later.",
        )

    from surrealdb.data.types.record_id import RecordID

    source_id_obj = RecordID("canonical_entity", request.source_id)
    target_id_obj = RecordID("canonical_entity", request.target_id)

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
        source_result = await db.query(
            "SELECT * FROM canonical_entity WHERE id = $source_id",
            {"source_id": source_id_obj},
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

    source_records: list[dict] = [
        r for r in (source_result or []) if isinstance(r, dict)
    ]
    if not source_records:
        logger.warning(
            "Merge rejected — source entity %s not found",
            request.source_id,
        )
        raise HTTPException(
            status_code=404,
            detail=f"Source canonical entity {request.source_id} not found.",
        )

    source_record = source_records[0]

    try:
        target_result = await db.query(
            "SELECT * FROM canonical_entity WHERE id = $target_id",
            {"target_id": target_id_obj},
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

    target_records: list[dict] = [
        r for r in (target_result or []) if isinstance(r, dict)
    ]
    if not target_records:
        logger.warning(
            "Merge rejected — target entity %s not found",
            request.target_id,
        )
        raise HTTPException(
            status_code=404,
            detail=f"Target canonical entity {request.target_id} not found.",
        )

    target_record = target_records[0]

    source_type = source_record.get("entity_type")
    target_type = target_record.get("entity_type")
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

    if source_record.get("superseded_by") is not None:
        logger.warning(
            "Merge rejected — source entity %s is already merged (superseded_by=%s)",
            request.source_id,
            source_record["superseded_by"],
        )
        raise HTTPException(
            status_code=400,
            detail=f"Source canonical entity {request.source_id} has already been merged into another entity.",
        )

    if target_record.get("superseded_by") is not None:
        logger.warning(
            "Merge rejected — target entity %s is already merged (superseded_by=%s)",
            request.target_id,
            target_record["superseded_by"],
        )
        raise HTTPException(
            status_code=400,
            detail=f"Target canonical entity {request.target_id} has already been merged into another entity.",
        )

    target_rid = RecordID("canonical_entity", request.target_id)
    source_rid = RecordID("canonical_entity", request.source_id)

    try:
        count_result = await db.query(
            "SELECT count() as cnt FROM reference WHERE canonical_entity = $source_ref",
            {"source_ref": source_rid},
        )
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

    count_records: list[dict] = [
        r for r in (count_result or []) if isinstance(r, dict)
    ]
    rewired_count = 0
    if count_records:
        cnt_val = count_records[0].get("cnt")
        if isinstance(cnt_val, dict):
            rewired_count = int(cnt_val.get("value", 0))
        elif cnt_val is not None:
            rewired_count = int(cnt_val)

    try:
        await db.query(
            "UPDATE reference SET canonical_entity = $target_ref, "
            "resolution_confidence = 1.0, updated_at = time::now() "
            "WHERE canonical_entity = $source_ref",
            {"source_ref": source_rid, "target_ref": target_rid},
        )

        await db.query(
            f"UPDATE canonical_entity:{request.source_id} SET "
            "superseded_by = $target_ref, updated_at = time::now()",
            {"target_ref": target_rid},
        )

        logger.info(
            "Merge complete: source=%s target=%s rewired=%d references",
            request.source_id,
            request.target_id,
            rewired_count,
        )
    except Exception as exc:
        logger.error(
            "Failed to execute merge source=%s target=%s: %s",
            request.source_id,
            request.target_id,
            exc,
        )
        raise HTTPException(
            status_code=502,
            detail="Failed to execute merge operation.",
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
    db: AsyncWsSurrealConnection | None = app.state.db

    if db is None:
        logger.error(
            "POST /entities/%s/%s/split rejected — SurrealDB unavailable",
            entity_type,
            entity_id,
        )
        raise HTTPException(
            status_code=503,
            detail="SurrealDB is not available. Please try again later.",
        )

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

    from surrealdb.data.types.record_id import RecordID

    source_id_obj = RecordID("canonical_entity", entity_id)

    try:
        source_result = await db.query(
            "SELECT * FROM canonical_entity WHERE id = $source_id",
            {"source_id": source_id_obj},
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

    source_records: list[dict] = [
        r for r in (source_result or []) if isinstance(r, dict)
    ]
    if not source_records:
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

    source_rid = RecordID("canonical_entity", entity_id)
    for ref_id in all_ref_ids:
        try:
            ref_result = await db.query(
                "SELECT * FROM reference WHERE id = $ref_id",
                {"ref_id": RecordID("reference", ref_id)},
            )
        except Exception as exc:
            logger.error(
                "Failed to query reference %s: %s",
                ref_id,
                exc,
            )
            raise HTTPException(
                status_code=502,
                detail="Failed to query database.",
            ) from exc

        ref_records: list[dict] = [
            r for r in (ref_result or []) if isinstance(r, dict)
        ]
        if not ref_records:
            logger.warning(
                "Split rejected — reference %s not found",
                ref_id,
            )
            raise HTTPException(
                status_code=400,
                detail=f"Reference {ref_id} not found.",
            )

        ref_record = ref_records[0]
        ref_canonical = ref_record.get("canonical_entity")

        ref_matches = False
        if isinstance(ref_canonical, RecordID):
            ref_matches = ref_canonical == source_rid
        elif isinstance(ref_canonical, str):
            ref_matches = ref_canonical == str(source_rid)

        if not ref_matches:
            logger.warning(
                "Split rejected — reference %s does not point to entity %s (points to %s)",
                ref_id,
                entity_id,
                str(source_rid),
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

    for new_name in groups:
        merged_ref_ids: list[str] = []
        for partition in groups[new_name]:
            merged_ref_ids.extend(partition.reference_ids)

        try:
            create_result = await db.create(
                "canonical_entity",
                {
                    "entity_type": entity_type,
                    "name": new_name,
                    "properties": {
                        "split_from": str(source_rid),
                    },
                    "superseded_by": None,
                },
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

        new_entity_id: str | None = None
        if isinstance(create_result, RecordID):
            new_entity_id = create_result.id
        elif isinstance(create_result, dict):
            created_id = create_result.get("id")
            if isinstance(created_id, RecordID):
                new_entity_id = created_id.id
            elif isinstance(created_id, str):
                if ":" in created_id:
                    new_entity_id = created_id.split(":", 1)[1]
                else:
                    new_entity_id = created_id
        elif isinstance(create_result, list) and len(create_result) > 0:
            first = create_result[0]
            if isinstance(first, dict):
                created_id = first.get("id")
                if isinstance(created_id, RecordID):
                    new_entity_id = created_id.id
                elif isinstance(created_id, str):
                    if ":" in created_id:
                        new_entity_id = created_id.split(":", 1)[1]
                    else:
                        new_entity_id = created_id

        if new_entity_id is None:
            logger.error(
                "Could not parse created entity ID from response: %s",
                str(create_result)[:300],
            )
            raise HTTPException(
                status_code=502,
                detail=f"Failed to parse created entity ID for '{new_name}'.",
            )

        new_entity_rid = RecordID("canonical_entity", new_entity_id)

        for ref_id in merged_ref_ids:
            try:
                await db.query(
                    "UPDATE reference SET canonical_entity = $target_ref, "
                    "resolution_confidence = 1.0, updated_at = time::now() "
                    "WHERE id = $ref_id",
                    {
                        "target_ref": new_entity_rid,
                        "ref_id": RecordID("reference", ref_id),
                    },
                )
            except Exception as exc:
                logger.error(
                    "Failed to update reference %s for new entity '%s': %s",
                    ref_id,
                    new_name,
                    exc,
                )
                raise HTTPException(
                    status_code=502,
                    detail=f"Failed to update reference {ref_id} for '{new_name}'.",
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
