"""
Unit tests for ``eth_pipeline.offsets`` — deterministic page-number and
page-relative character-offset computation.

All test data is in-memory dict lists — no SurrealDB connection required.
"""

from __future__ import annotations

import pytest

from eth_pipeline.offsets import (
    compute_reference_offsets,
    reconstruct_page_offsets,
)

# ============================================================================
# Test fixtures — document_chunk data shapes
# ============================================================================

# 2-page document, 3 chunks: chunk 1 crosses pages 1→2
CHUNKS_2PAGE = [
    {"chunk_index": 0, "offset_start": 0, "offset_end": 300,
     "page_start": 1, "page_end": 1},
    {"chunk_index": 1, "offset_start": 300, "offset_end": 600,
     "page_start": 1, "page_end": 2},
    {"chunk_index": 2, "offset_start": 600, "offset_end": 1000,
     "page_start": 2, "page_end": 2},
]

# Single-page multi-chunk document
CHUNKS_1PAGE = [
    {"chunk_index": 0, "offset_start": 0, "offset_end": 500,
     "page_start": 1, "page_end": 1},
    {"chunk_index": 1, "offset_start": 500, "offset_end": 1000,
     "page_start": 1, "page_end": 1},
]

# Single chunk (tiny document)
CHUNKS_SINGLE = [
    {"chunk_index": 0, "offset_start": 0, "offset_end": 200,
     "page_start": 1, "page_end": 1},
]


# ============================================================================
# reconstruct_page_offsets tests
# ============================================================================


class TestReconstructPageOffsets:
    """Unit tests for ``reconstruct_page_offsets()``."""

    def test_reconstruct_page_offsets_2page(self) -> None:
        """2-page document produces [0, 600, 1000]."""
        result = reconstruct_page_offsets(CHUNKS_2PAGE)
        assert result == [0, 600, 1000]

    def test_reconstruct_page_offsets_1page(self) -> None:
        """Single-page multi-chunk document produces [0, 1000]."""
        result = reconstruct_page_offsets(CHUNKS_1PAGE)
        assert result == [0, 1000]

    def test_reconstruct_page_offsets_single(self) -> None:
        """Single-chunk document produces [0, 200]."""
        result = reconstruct_page_offsets(CHUNKS_SINGLE)
        assert result == [0, 200]


# ============================================================================
# compute_reference_offsets tests
# ============================================================================


class TestComputeReferenceOffsets:
    """Unit tests for ``compute_reference_offsets()``."""

    # ---- Page number tests ----

    def test_page_number_first_page(self) -> None:
        """Span on first page returns page_number=1."""
        result = compute_reference_offsets(150, 200, CHUNKS_2PAGE, False)
        assert result == {"page_number": 1, "page_offset_start": 150,
                          "page_offset_end": 200}

    def test_page_number_second_page(self) -> None:
        """Span on second page returns page_number=2."""
        result = compute_reference_offsets(700, 750, CHUNKS_2PAGE, False)
        assert result == {"page_number": 2, "page_offset_start": 100,
                          "page_offset_end": 150}

    def test_page_number_exact_boundary(self) -> None:
        """Span starting exactly at a chunk boundary resolves to the
        correct page (page_start=1 for offset 300, which is still in
        chunk 1's page_start range)."""
        result = compute_reference_offsets(300, 350, CHUNKS_2PAGE, False)
        assert result == {"page_number": 1, "page_offset_start": 300,
                          "page_offset_end": 350}

    # ---- Plain-text ----

    def test_plain_text_returns_nulls(self) -> None:
        """Plain-text documents return all-null offsets."""
        result = compute_reference_offsets(100, 200, CHUNKS_2PAGE, True)
        assert result == {"page_number": None, "page_offset_start": None,
                          "page_offset_end": None}

    # ---- Out-of-range ----

    def test_out_of_range_span_negative(self) -> None:
        """Negative span_start returns null offsets."""
        result = compute_reference_offsets(-1, 50, CHUNKS_2PAGE, False)
        assert result["page_number"] is None
        assert result["page_offset_start"] is None
        assert result["page_offset_end"] is None

    def test_out_of_range_span_beyond_end(self) -> None:
        """Span beyond document end returns null offsets."""
        result = compute_reference_offsets(50, 2000, CHUNKS_2PAGE, False)
        assert result["page_number"] is None
        assert result["page_offset_start"] is None
        assert result["page_offset_end"] is None

    def test_span_start_gte_span_end(self) -> None:
        """span_start >= span_end returns null offsets."""
        result = compute_reference_offsets(500, 400, CHUNKS_2PAGE, False)
        assert result["page_number"] is None
        assert result["page_offset_start"] is None
        assert result["page_offset_end"] is None

    # ---- Single chunk ----

    def test_single_chunk_offsets(self) -> None:
        """Single-chunk document produces correct page-relative offsets."""
        result = compute_reference_offsets(50, 100, CHUNKS_SINGLE, False)
        assert result == {"page_number": 1, "page_offset_start": 50,
                          "page_offset_end": 100}

    def test_full_document_span(self) -> None:
        """Span covering the full single-chunk document."""
        result = compute_reference_offsets(0, 200, CHUNKS_SINGLE, False)
        assert result == {"page_number": 1, "page_offset_start": 0,
                          "page_offset_end": 200}

    # ---- Determinism (purity) check ----

    def test_deterministic_output(self) -> None:
        """Same input always produces same output (pure function)."""
        r1 = compute_reference_offsets(150, 200, CHUNKS_2PAGE, False)
        r2 = compute_reference_offsets(150, 200, CHUNKS_2PAGE, False)
        assert r1 == r2
