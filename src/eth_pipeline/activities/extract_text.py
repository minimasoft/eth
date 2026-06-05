"""Extract text from a blob-stored document (PDF or plain text)."""

from __future__ import annotations

import base64
import os

from temporalio import activity

from eth_pipeline.activities._common import (
    _db_params,
    _extract_query_results,
    _get_blob_from_minio,
)
from eth_pipeline.db import get_db
from eth_pipeline.extractors import ExtractorQualityError, PdfExtractor
from eth_pipeline.processing_log import ProcessingLogger


@activity.defn
async def extract_text_activity(document_id: str) -> dict:
    params = _db_params()
    _log = ProcessingLogger(params)

    activity.logger.info(
        "extract_text_activity called [document_id=%s]",
        document_id,
    )
    await _log.log(document_id, "extract_text", "info",
                   "Starting text extraction")

    try:
        async with get_db(**params) as conn:
            rows = _extract_query_results(
                await conn.fetch(
                    "SELECT * FROM document WHERE id = $1",
                    document_id,
                )
            )
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

            if blob_format == "minio":
                content = await _get_blob_from_minio(blob_path)
            else:
                content = base64.b64decode(original_blob.encode("ascii"))

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

            if doc_format == "pdf":
                extractor = PdfExtractor()
                try:
                    result = extractor.extract(content, filename=filename)
                except ExtractorQualityError as exc:
                    await conn.execute(
                        "UPDATE document SET status = 'failed', "
                        "error_message = $2, updated_at = NOW() "
                        "WHERE id = $1",
                        document_id, str(exc),
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
                    await conn.execute(
                        "UPDATE document SET status = 'failed', "
                        "error_message = $2, updated_at = NOW() "
                        "WHERE id = $1",
                        document_id, msg,
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
                await conn.execute(
                    "UPDATE document SET status = 'failed', "
                    "error_message = $2, updated_at = NOW() "
                    "WHERE id = $1",
                    document_id, msg,
                )
                return {"error": msg, "document_id": document_id}

            await conn.execute(
                "UPDATE document SET text_content = $2, "
                "status = 'extracting_text', "
                "_page_count = $3, "
                "updated_at = NOW() "
                "WHERE id = $1",
                document_id, text, page_count,
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
