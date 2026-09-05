"""
Document text chunking with sentence-level provenance tracking.

Provides ``SmartChunker`` that splits document text into sentence-aware
balanced chunks using NLTK Punkt tokenizer for Spanish.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import ClassVar


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class DocumentChunk:
    """A single chunk of a document with page-level provenance."""

    chunk_index: int
    text: str
    page_start: int
    page_end: int
    offset_start: int
    offset_end: int


# ---------------------------------------------------------------------------
# SmartChunker — sentence-aware balanced chunking with NLTK Punkt
# ---------------------------------------------------------------------------


def distribute_balanced(
    sentences: list[str],
    sentence_lengths: list[int],
    target_size: int,
    min_chunk_ratio: float = 0.5,
) -> list[list[int]]:
    """Distribute sentences into balanced chunk groups.

    Two-pass greedy algorithm with redistribution:
    1. First pass — greedy fill each chunk up to *target_size*.
    2. If the last chunk is below ``target_size * min_chunk_ratio``, merge it
       into the second-to-last chunk.
    3. Pre-check: if that merge collapses everything back into a single
       oversized chunk (total between 1x and ~1.5x target), re-split into
       two balanced chunks at ~51% of the total size so no chunk ever
       exceeds the target.

    Parameters
    ----------
    sentences:
        List of sentence texts (used only for length validation).
    sentence_lengths:
        Character length of each sentence in *sentences*.
    target_size:
        Target character count per chunk.
    min_chunk_ratio:
        Minimum acceptable chunk size as a fraction of *target_size*
        (default 0.5).  Chunks smaller than this trigger redistribution.

    Returns
    -------
    list[list[int]]
        Each inner list contains the sentence indices belonging to that chunk.
    """
    n = len(sentences)
    total_len = sum(sentence_lengths)

    if total_len <= target_size:
        return [list(range(n))]

    chunks = _greedy_fill_with_merge(sentence_lengths, target_size, min_chunk_ratio)

    # Pre-check: the merge above can collapse the document back into a
    # single oversized chunk when total sits between 1x and ~1.5x target
    # (e.g. a 336k-char doc with a 262k target). Force 2 balanced chunks
    # by re-splitting at ~51% of the total size; each half stays under
    # the original target because the collapse zone caps total at 1.5x.
    if len(chunks) == 1 and n > 1:
        chunks = _greedy_fill_with_merge(
            sentence_lengths, math.ceil(total_len * 0.51), min_chunk_ratio
        )

    return chunks


def _greedy_fill_with_merge(
    sentence_lengths: list[int],
    target_size: int,
    min_chunk_ratio: float,
) -> list[list[int]]:
    """Greedy-fill sentences into chunks, then merge an undersized tail.

    Never returns a single chunk when ``sum(sentence_lengths) > target_size``:
    with the re-split target at ~0.51x total, the second chunk is at least
    ~0.49x total, far above the merge threshold (~0.26x total).
    """
    chunks: list[list[int]] = []
    current_chunk: list[int] = []
    current_len = 0

    for i, sent_len in enumerate(sentence_lengths):
        if current_len + sent_len > target_size and current_chunk:
            chunks.append(current_chunk)
            current_chunk = [i]
            current_len = sent_len
        else:
            current_chunk.append(i)
            current_len += sent_len

    if current_chunk:
        chunks.append(current_chunk)

    if len(chunks) > 1:
        last_len = sum(sentence_lengths[i] for i in chunks[-1])
        if last_len < target_size * min_chunk_ratio:
            chunks[-2].extend(chunks[-1])
            chunks.pop()

    return chunks


@dataclass
class SmartChunk:
    """A single chunk produced by ``SmartChunker``.

    Mirrors ``DocumentChunk`` field names so both can feed the same
    dict-conversion pipeline in ``chunk_document_activity``.

    Attributes
    ----------
    chunk_index:
        Zero-based index of this chunk within the document.  Also serves as
        ``part_index`` for the LLM pipeline.
    text:
        The chunk's text content — a contiguous group of complete sentences.
    page_start:
        Page number (1-based) where this chunk's text begins.
    page_end:
        Page number (1-based, inclusive) where this chunk's text ends.
    offset_start:
        Character offset (0-based) where this chunk begins in the full
        document text.
    offset_end:
        Character offset (exclusive) where this chunk ends in the full
        document text.
    """

    chunk_index: int
    text: str
    page_start: int
    page_end: int
    offset_start: int
    offset_end: int


class SmartChunker:
    """Sentence-aware document chunker using NLTK Punkt for Spanish.

    Detects sentence boundaries with NLTK's Spanish Punkt tokenizer, then
    distributes sentences into balanced chunks around a configurable target
    size.  Chunks never split mid-sentence and Spanish abbreviations
    (``S.L.``, ``art.``, ``Dr.``, etc.) are handled correctly by Punkt's
    unsupervised abbreviation learning.

    The chunker uses ``CHUNK_SIZE_TARGET`` env var (default 262144 = 256KB)
    so that target size can be tuned per deployment without code changes.
    """

    DEFAULT_TARGET: ClassVar[int] = 262144  # 256KB in chars (~50-65k tokens Spanish)

    def __init__(self, target_size: int | None = None) -> None:
        self.target_size = target_size or int(
            os.environ.get('CHUNK_SIZE_TARGET', self.DEFAULT_TARGET)
        )
        import nltk
        nltk.download('punkt_tab', quiet=True)
        from nltk.tokenize import _get_punkt_tokenizer
        self._tokenizer = _get_punkt_tokenizer('spanish')

    def chunk(
        self,
        text: str,
        page_offsets: list[int],
    ) -> list[SmartChunk]:
        """Split *text* into sentence-aware balanced chunks.

        Parameters
        ----------
        text:
            Full document text to chunk.
        page_offsets:
            Cumulative character offsets for page boundaries as produced by
            ``ExtractionResult.page_offsets`` (length = ``page_count + 1``).

        Returns
        -------
        list[SmartChunk]
            Chunks with sentence-level provenance.

        Raises
        ------
        ValueError
            If *page_offsets* has fewer than 2 elements or does not end with
            ``len(text)``.
        """
        if len(page_offsets) < 1:
            raise ValueError(
                f"page_offsets must have at least 1 element [got {len(page_offsets)}]"
            )
        if len(page_offsets) == 1:
            page_offsets = [0, len(text)]
        if page_offsets[-1] != len(text):
            raise ValueError(
                f"page_offsets[-1] ({page_offsets[-1]}) does not match len(text) ({len(text)})"
            )

        if len(text) <= self.target_size:
            return [SmartChunk(
                chunk_index=0,
                text=text,
                page_start=1,
                page_end=len(page_offsets) - 1,
                offset_start=0,
                offset_end=len(text),
            )]

        spans = list(self._tokenizer.span_tokenize(text))
        sentences = [text[s:e] for s, e in spans]
        sent_lens = [e - s for s, e in spans]

        groups = distribute_balanced(sentences, sent_lens, self.target_size)

        chunks: list[SmartChunk] = []
        for part_idx, sent_indices in enumerate(groups):
            start_offset = spans[sent_indices[0]][0]
            end_offset = spans[sent_indices[-1]][1]
            chunk_text = text[start_offset:end_offset]
            page_start = self._offset_to_page(start_offset, page_offsets)
            page_end = self._offset_to_page(max(end_offset - 1, 0), page_offsets)

            chunks.append(SmartChunk(
                chunk_index=part_idx,
                text=chunk_text,
                page_start=page_start,
                page_end=page_end,
                offset_start=start_offset,
                offset_end=end_offset,
            ))

        return chunks

    @staticmethod
    def _offset_to_page(offset: int, page_offsets: list[int]) -> int:
        """Convert a 0-based character offset to a 1-based page number.

        Parameters
        ----------
        offset:
            Character offset in the full document text.
        page_offsets:
            Cumulative page offset array from ``ExtractionResult``.

        Returns
        -------
        int
            1-based page number covering *offset*.
        """
        for i in range(len(page_offsets) - 1):
            if page_offsets[i] <= offset < page_offsets[i + 1]:
                return i + 1
        return len(page_offsets) - 1
