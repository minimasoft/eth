"""
Document text chunking with page-level provenance tracking.

Provides ``DocumentChunker`` that splits document text into chunks using
``RecursiveCharacterTextSplitter`` (from ``langchain-text-splitters``) and
tracks which page range each chunk covers via the ``page_offsets`` array from
``ExtractionResult``.

Chunks are non-overlapping (``chunk_overlap=0``) and their character offsets
refer to positions in the original document text.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import ClassVar


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class DocumentChunk:
    """A single chunk of a document with page-level provenance.

    Attributes
    ----------
    chunk_index:
        Zero-based index of this chunk within the document.
    text:
        The chunk's text content.
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


@dataclass
class ChunkResult:
    """Result from ``DocumentChunker``.

    Attributes
    ----------
    chunks:
        The produced chunks.
    chunk_size_target:
        Target chunk size used.
    total_text_length:
        Length of the full document text.
    """

    chunks: list[DocumentChunk]
    chunk_size_target: int
    total_text_length: int


# ---------------------------------------------------------------------------
# DocumentChunker
# ---------------------------------------------------------------------------


class DocumentChunker:
    """Split document text into chunks with page-provenance tracking.

    Uses ``RecursiveCharacterTextSplitter`` with paragraph/punctuation-aware
    boundaries.  Tracks which page range each chunk covers by mapping
    character offsets to page numbers via the ``page_offsets`` array from
    ``ExtractionResult``.

    Chunks are contiguous and non-overlapping.  Each chunk's
    ``offset_start``/``offset_end`` refers to its position in the original
    document text, enabling exact reconstruction by the caller.
    """

    DEFAULT_CHUNK_SIZE: ClassVar[int] = 128_000  # ~128k chars

    def __init__(
        self,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = 0,
    ) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk(
        self,
        text: str,
        page_offsets: list[int],
    ) -> ChunkResult:
        """Split *text* into chunks with page-provenance tracking.

        Parameters
        ----------
        text:
            Full document text to chunk.
        page_offsets:
            Cumulative character offsets for page boundaries as produced by
            ``ExtractionResult.page_offsets`` (length = ``page_count + 1``).

        Returns
        -------
        ChunkResult
            Chunks with provenance metadata.

        Raises
        ------
        ValueError
            If *page_offsets* has fewer than 2 elements or does not end with
            ``len(text)``.
        """
        # ---- Validate inputs ----
        if len(page_offsets) < 1:
            raise ValueError(
                f"page_offsets must have at least 1 element [got {len(page_offsets)}]"
            )
        if len(page_offsets) == 1:
            # Single-element array means zero pages (empty document).
            # Normalise to two-element array for downstream code.
            page_offsets = [0, len(text)]
        if page_offsets[-1] != len(text):
            raise ValueError(
                f"page_offsets[-1] ({page_offsets[-1]}) does not match len(text) ({len(text)})"
            )

        # ---- Short text: single chunk ----
        if len(text) <= self.chunk_size:
            chunk = DocumentChunk(
                chunk_index=0,
                text=text,
                page_start=1,
                page_end=len(page_offsets) - 1,
                offset_start=0,
                offset_end=len(text),
            )
            return ChunkResult(
                chunks=[chunk],
                chunk_size_target=self.chunk_size,
                total_text_length=len(text),
            )

        # ---- Lazy import ----
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            separators=["\n\n", "\n", ".", "!", "?", ",", " ", ""],
            length_function=len,
        )

        chunk_texts: list[str] = splitter.split_text(text)

        # ---- Build chunks with provenance ----
        chunks: list[DocumentChunk] = []
        # Pre-compute chunk start positions in the original text
        chunk_starts: list[int] = []
        search_pos = 0

        for i, chunk_text in enumerate(chunk_texts):
            if not chunk_text:
                chunk_starts.append(len(text))
            else:
                pos = text.find(chunk_text, search_pos)
                if pos == -1:
                    pos = search_pos
                chunk_starts.append(pos)
                search_pos = pos + len(chunk_text)

        # Compute offsets: each chunk's start is its position in the original
        # text; its end is the start of the next chunk (or len(text) for last).
        for idx, chunk_text in enumerate(chunk_texts):
            offset_start = chunk_starts[idx]
            if idx + 1 < len(chunk_starts):
                offset_end = chunk_starts[idx + 1]
            else:
                offset_end = len(text)

            # Map offsets to pages (1-based)
            page_start = self._offset_to_page(offset_start, page_offsets)
            page_end = self._offset_to_page(max(offset_end - 1, 0), page_offsets)

            chunks.append(DocumentChunk(
                chunk_index=idx,
                text=chunk_text,
                page_start=page_start,
                page_end=page_end,
                offset_start=offset_start,
                offset_end=offset_end,
            ))

        return ChunkResult(
            chunks=chunks,
            chunk_size_target=self.chunk_size,
            total_text_length=len(text),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

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
        # Fallback: last page
        return len(page_offsets) - 1


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------


def chunk_document(
    text: str,
    page_offsets: list[int],
    chunk_size: int = DocumentChunker.DEFAULT_CHUNK_SIZE,
) -> ChunkResult:
    """Convenience function: chunk *text* with page-provenance tracking.

    Parameters
    ----------
    text:
        Full document text to chunk.
    page_offsets:
        Cumulative page offset array from ``ExtractionResult``.
    chunk_size:
        Target chunk size in characters (default: 128 000).

    Returns
    -------
    ChunkResult
        Chunks with provenance metadata.
    """
    return DocumentChunker(chunk_size=chunk_size).chunk(text, page_offsets)


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

    chunks: list[list[int]] = []
    current_chunk: list[int] = []
    current_len = 0

    for i in range(n):
        sent_len = sentence_lengths[i]
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

    The chunker uses ``CHUNK_SIZE_TARGET`` env var (default 524288 = 512KB)
    so that target size can be tuned per deployment without code changes.
    """

    DEFAULT_TARGET: ClassVar[int] = 524288  # 512KB in chars

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
