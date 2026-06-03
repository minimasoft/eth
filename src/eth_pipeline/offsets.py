"""
Deterministic page-number and page-relative character-offset computation for
reference records.

This module provides a pure function ``compute_reference_offsets()`` that maps
LLM-extracted ``span_start``/``span_end`` (document-level character offsets) to
page-level positions using existing ``document_chunk`` metadata as the source
of truth.

No LLM involvement — the computation is fully deterministic and repeatable
across Temporal replays.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def reconstruct_page_offsets(chunks: list[dict[str, Any]]) -> list[int]:
    """Reconstruct the page-offsets array from sorted document_chunk records.

    Iterates through chunks in order and records the ``offset_start`` for each
    unique ``page_start`` value.  The resulting list has length
    ``(page_count + 1)`` and follows the same shape as the
    ``page_offsets`` array produced by ``ExtractionResult``.

    Parameters
    ----------
    chunks:
        List of chunk dicts sorted by ``chunk_index`` ascending.  Each dict
        has keys ``chunk_index``, ``offset_start``, ``offset_end``,
        ``page_start``, ``page_end``.  Must be non-empty.

    Returns
    -------
    list[int]
        Cumulative page boundary offsets, e.g. ``[0, 600, 1000]`` for a
        two-page document where page 1 spans offsets 0–599 and page 2 spans
        offsets 600–999.

    Raises
    ------
    ValueError
        If *chunks* is empty.
    """
    if not chunks:
        raise ValueError("reconstruct_page_offsets: chunks list is empty")

    page_offsets: list[int] = []
    seen_pages: set[int] = set()

    for chunk in chunks:
        page_start = chunk.get("page_start", 1)
        offset_start = chunk.get("offset_start", 0)
        if page_start not in seen_pages:
            seen_pages.add(page_start)
            page_offsets.append(offset_start)

    # Ensure first page boundary is always 0
    if not page_offsets or page_offsets[0] != 0:
        page_offsets.insert(0, 0)

    # Append the document end boundary
    page_offsets.append(chunks[-1].get("offset_end", 0))
    page_offsets.sort()

    return page_offsets


def compute_reference_offsets(
    span_start: int,
    span_end: int,
    chunks: list[dict[str, Any]],
    is_plain_text: bool,
) -> dict[str, int | None]:
    """Compute page number and page-relative offsets for a reference span.

    This is a pure function — no side effects, no I/O, no imports from
    Temporal or SurrealDB modules.

    Parameters
    ----------
    span_start:
        Document-level character offset (0-based) where the verbatim span
        begins, as produced by the LLM.
    span_end:
        Document-level character offset (exclusive) where the span ends.
    chunks:
        List of ``document_chunk`` dicts sorted by ``chunk_index`` ascending.
        Must be non-empty.
    is_plain_text:
        ``True`` when the document has no page structure (its MIME type starts
        with ``"text/"``).

    Returns
    -------
    dict
        One of:
        - ``{"page_number": int, "page_offset_start": int,
           "page_offset_end": int}`` on success.
        - ``{"page_number": None, "page_offset_start": None,
           "page_offset_end": None}`` when *is_plain_text* is ``True`` or the
           span is out of range.
    """
    # ---- Plain-text: no page structure ----
    if is_plain_text:
        return {
            "page_number": None,
            "page_offset_start": None,
            "page_offset_end": None,
        }

    # ---- Empty chunks guard ----
    if not chunks:
        return {
            "page_number": None,
            "page_offset_start": None,
            "page_offset_end": None,
        }

    # ---- Out-of-range detection ----
    doc_end = chunks[-1].get("offset_end", 0)
    if span_start < 0 or span_end > doc_end or span_start >= span_end:
        return {
            "page_number": None,
            "page_offset_start": None,
            "page_offset_end": None,
        }

    # ---- Reconstruct page offsets ----
    page_offsets = reconstruct_page_offsets(chunks)

    # ---- Compute page number ----
    page_number: int | None = None
    for i in range(len(page_offsets) - 1):
        if page_offsets[i] <= span_start < page_offsets[i + 1]:
            page_number = i + 1
            break

    if page_number is None:
        # Fallback: last page
        page_number = len(page_offsets) - 1

    # ---- Compute page-relative offsets ----
    page_offset_start = span_start - page_offsets[page_number - 1]
    page_offset_end = span_end - page_offsets[page_number - 1]

    return {
        "page_number": page_number,
        "page_offset_start": page_offset_start,
        "page_offset_end": page_offset_end,
    }
