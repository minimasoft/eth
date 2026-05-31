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
