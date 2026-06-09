"""Chunk a document's extracted text and store chunks in PostgreSQL."""

from __future__ import annotations

import uuid

from temporalio import activity

from eth_pipeline.activities._common import _db_params
from eth_pipeline.chunker import DocumentChunker, SmartChunker
from eth_pipeline.db import get_db
from eth_pipeline.processing_log import ProcessingLogger


@activity.defn
async def chunk_document_activity(document_id: str, extraction_result: dict) -> dict:
    params = _db_params()
    _log = ProcessingLogger(params)

    activity.logger.info(
        "chunk_document_activity called [document_id=%s]",
        document_id,
    )
    await _log.log(document_id, "chunk_document", "info",
                   "Starting document chunking")

    try:
        async with get_db(**params) as conn:
            row = await conn.fetchrow(
                "SELECT text_content, schema_version FROM document WHERE id = $1",
                document_id,
            )
            if not row:
                return {"error": "Document not found", "document_id": document_id}

            text = row['text_content']
            schema_version = row['schema_version']
            page_offsets = extraction_result.get("page_offsets", [0])

            if schema_version == 'v7':
                chunker = SmartChunker()
                chunks = chunker.chunk(text, page_offsets)
            else:
                chunker = DocumentChunker()
                chunk_result = chunker.chunk(text, page_offsets)
                chunks = chunk_result.chunks

            chunks_dicts: list[dict] = []
            for c in chunks:
                chunks.append({
                    "chunk_index": c.chunk_index,
                    "text": c.text,
                    "page_start": c.page_start,
                    "page_end": c.page_end,
                    "offset_start": c.offset_start,
                    "offset_end": c.offset_end,
                })

            await conn.execute(
                "DELETE FROM document_chunk WHERE document = $1",
                document_id,
            )

            for chunk in chunks_dicts:
                chunk_id = uuid.uuid4().hex
                await conn.execute(
                    "INSERT INTO document_chunk "
                    "(id, chunk_index, text, page_start, page_end, "
                    "offset_start, offset_end, document) "
                    "VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
                    chunk_id,
                    chunk["chunk_index"],
                    chunk["text"],
                    chunk["page_start"],
                    chunk["page_end"],
                    chunk["offset_start"],
                    chunk["offset_end"],
                    document_id,
                )

            if not chunks_dicts:
                activity.logger.warning(
                    "No chunks to store [document_id=%s]",
                    document_id,
                )
                await _log.log(document_id, "chunk_document", "warning",
                               "No chunks generated — document may be empty")

            await conn.execute(
                "UPDATE document SET status = 'chunking', "
                "updated_at = NOW() "
                "WHERE id = $1",
                document_id,
            )

            activity.logger.info(
                "chunk_document_activity completed [document_id=%s] "
                "[chunk_count=%d]",
                document_id,
                len(chunks_dicts),
            )
            await _log.log(document_id, "chunk_document", "info",
                           f"Chunking completed: {len(chunks_dicts)} chunks",
                           {"chunk_count": len(chunks_dicts)})

            return {
                "document_id": document_id,
                "chunk_count": len(chunks_dicts),
                "schema_version": schema_version,
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
            async with get_db(**params) as conn:
                await conn.execute(
                    "UPDATE document SET status = 'failed', "
                    "error_message = $2, updated_at = NOW() "
                    "WHERE id = $1",
                    document_id, str(exc),
                )
        except Exception:
            pass
        return {"error": str(exc), "document_id": document_id}
