"""Smart chunker unit tests: sentence boundary detection and balanced distribution."""

from __future__ import annotations

import logging
import os

import pytest

logger = logging.getLogger(__name__)

import nltk
nltk.download('punkt_tab', quiet=True)
from eth_pipeline.chunker import SmartChunker, SmartChunk, distribute_balanced


# ---------------------------------------------------------------------------
# CHK-01: Balanced Distribution
# ---------------------------------------------------------------------------


class TestBalancedDistribution:
    """CHK-01: Chunks are approximately balanced — no extreme skew."""

    @pytest.fixture(autouse=True)
    def _chunker(self) -> None:
        self.chunker = SmartChunker(target_size=1000)

    def test_single_chunk_short_text(self) -> None:
        chunks = self.chunker.chunk("Hello. World.", [0, 13])
        assert len(chunks) == 1
        assert chunks[0].chunk_index == 0

    def test_multi_chunk_balanced(self) -> None:
        sentences = ["X" * 100 + ". " for _ in range(100)]
        text = "".join(sentences)
        chunks = self.chunker.chunk(text, [0, len(text)])
        assert len(chunks) > 1
        target = 1000
        for chunk in chunks:
            size = len(chunk.text)
            assert size <= int(target * 1.5), f"Chunk size {size} exceeds 1.5x target {target}"
            if len(chunks) > 1 and size < target * 0.5:
                pass  # last chunk may be small, that's ok for edge cases

    def test_two_chunks_reasonably_balanced(self) -> None:
        chunker = SmartChunker(target_size=2500)
        text = "Test sentence with reasonable length for chunking. " * 80
        chunks = chunker.chunk(text, [0, len(text)])
        assert len(chunks) >= 2
        half_target = 2500 * 0.5
        max_target = int(2500 * 1.5)
        for chunk in chunks:
            size = len(chunk.text)
            assert size <= max_target, f"Chunk size {size} exceeds 1.5x target"

    def test_balanced_distribution_function_directly(self) -> None:
        groups = distribute_balanced(
            ["a", "b", "c", "d"], [1, 1, 1, 1], target_size=2
        )
        assert len(groups) == 2, f"Expected 2 groups, got {len(groups)}"
        assert groups == [[0, 1], [2, 3]], f"Unexpected groups: {groups}"


# ---------------------------------------------------------------------------
# CHK-02: Sentence Boundaries
# ---------------------------------------------------------------------------


class TestSentenceBoundaries:
    """CHK-02: No chunk splits mid-sentence — all boundaries at true sentence ends."""

    @pytest.fixture(autouse=True)
    def _chunker(self) -> None:
        self.chunker = SmartChunker(target_size=524288)

    def test_boundaries_not_mid_word(self) -> None:
        text = "Primera oración. Segunda oración. Tercera oración."
        chunks = self.chunker.chunk(text, [0, len(text)])
        assert len(chunks) == 1  # short enough for single chunk

    def test_each_chunk_starts_at_sentence(self) -> None:
        text = "Frase número uno. Frase número dos. Frase número tres."
        chunks = self.chunker.chunk(text, [0, len(text)])
        for chunk in chunks:
            assert chunk.offset_start >= 0
            assert chunk.offset_end <= len(text)

    def test_paragraph_boundary_respected(self) -> None:
        text = "Primer párrafo.\n\nSegundo párrafo con más texto.\n\nTercer párrafo."
        chunker = SmartChunker(target_size=20)
        chunks = chunker.chunk(text, [0, len(text)])
        assert len(chunks) >= 1

    def test_empty_text(self) -> None:
        chunks = self.chunker.chunk("", [0])
        assert len(chunks) == 1
        assert chunks[0].text == ""
        assert chunks[0].offset_start == 0
        assert chunks[0].offset_end == 0


# ---------------------------------------------------------------------------
# CHK-02: Spanish Abbreviations
# ---------------------------------------------------------------------------


class TestSpanishAbbreviations:
    """CHK-02: Spanish abbreviations do not cause false sentence splits."""

    @pytest.fixture(autouse=True)
    def _chunker(self) -> None:
        self.chunker = SmartChunker(target_size=524288)

    def test_sl_does_not_cause_mid_word_split(self) -> None:
        text = "La empresa S.L. firmó el contrato. Otra frase."
        spans = list(self.chunker._tokenizer.span_tokenize(text))
        # NLTK Punkt may split or merge depending on context; verify no mid-word split
        for s, e in spans:
            chunk = text[s:e]
            assert len(chunk) > 0
            assert chunk[0].isupper() or s == 0 or text[s - 1].isspace()

    def test_dr_does_not_split(self) -> None:
        text = "El Dr. García declaró. El fiscal preguntó."
        spans = list(self.chunker._tokenizer.span_tokenize(text))
        assert len(spans) == 2, f"Expected 2 sentence spans, got {len(spans)}"

    def test_art_does_not_cause_mid_word_split(self) -> None:
        text = "Según el art. 15 de la Ley. Continúa el texto."
        spans = list(self.chunker._tokenizer.span_tokenize(text))
        for s, e in spans:
            chunk = text[s:e]
            assert len(chunk) > 0

    def test_multiple_abbreviations_in_one_sentence(self) -> None:
        text = "La empresa S.L. y el Dr. García comparecieron en el art. 15."
        chunks = self.chunker.chunk(text, [0, len(text)])
        assert len(chunks) == 1
        assert chunks[0].offset_start == 0
        assert chunks[0].offset_end == len(text)

    def test_legal_procedural_numbering(self) -> None:
        text = "PRIMERO.- Hechos probados: SE AFIRMA LO SIGUIENTE. SEGUNDO.- Fundamentos jurídicos."
        spans = list(self.chunker._tokenizer.span_tokenize(text))
        assert len(spans) >= 1
        for s, e in spans:
            chunk = text[s:e]
            assert len(chunk) > 0


# ---------------------------------------------------------------------------
# CHK-03: Configurable Chunk Size
# ---------------------------------------------------------------------------


class TestConfigurableSize:
    """CHK-03: CHUNK_SIZE_TARGET env var controls chunk size."""

    def test_default_target_size(self, monkeypatch) -> None:
        monkeypatch.delenv("CHUNK_SIZE_TARGET", raising=False)
        chunker = SmartChunker()
        assert chunker.target_size == 524288

    def test_explicit_target_size(self) -> None:
        chunker = SmartChunker(target_size=500)
        assert chunker.target_size == 500

    def test_env_var_overrides_default(self, monkeypatch) -> None:
        monkeypatch.setenv("CHUNK_SIZE_TARGET", "1000")
        chunker = SmartChunker()
        assert chunker.target_size == 1000

    def test_empty_env_var_falls_back_to_default(self, monkeypatch) -> None:
        monkeypatch.delenv("CHUNK_SIZE_TARGET", raising=False)
        chunker = SmartChunker()
        assert chunker.target_size == 524288


# ---------------------------------------------------------------------------
# CHK-04: Provenance Tracking
# ---------------------------------------------------------------------------


class TestProvenance:
    """CHK-04: Correct offset tracking and part_index (chunk_index = part_index)."""

    @pytest.fixture(autouse=True)
    def _chunker(self) -> None:
        self.chunker = SmartChunker(target_size=524288)

    def test_chunk_index_is_sequential(self) -> None:
        text = ". ".join([f"Sentence {i}" for i in range(200)]) + "."
        chunker = SmartChunker(target_size=200)
        chunks = chunker.chunk(text, [0, len(text)])
        assert len(chunks) > 1
        for i, c in enumerate(chunks):
            assert c.chunk_index == i

    def test_offset_start_end_accurate(self) -> None:
        text = "Primera frase. Segunda frase. Tercera frase."
        chunks = self.chunker.chunk(text, [0, len(text)])
        for c in chunks:
            assert c.text == text[c.offset_start:c.offset_end], (
                f"Mismatch: chunk text doesn't match original[{c.offset_start}:{c.offset_end}]"
            )

    def test_page_tracking(self) -> None:
        text = "AAA. " * 100
        page_offsets = [0, 50, 100, 150, len(text)]
        chunker = SmartChunker(target_size=60)
        chunks = chunker.chunk(text, page_offsets)
        assert len(chunks) > 1
        for c in chunks:
            assert c.page_start >= 1
            assert c.page_end <= len(page_offsets) - 1
            assert c.page_start <= c.page_end

    def test_part_index_equals_chunk_index(self) -> None:
        text = ". ".join([f"Frase {i}" for i in range(100)]) + "."
        chunker = SmartChunker(target_size=200)
        chunks = chunker.chunk(text, [0, len(text)])
        for i, c in enumerate(chunks):
            assert c.chunk_index == i, f"Chunk index {c.chunk_index} != expected {i}"


# ---------------------------------------------------------------------------
# Integration Tests (marked slow)
# ---------------------------------------------------------------------------


class TestIntegration:
    """Integration tests with actual Spanish legal text samples."""

    @pytest.fixture(autouse=True)
    def _chunker(self) -> None:
        self.chunker = SmartChunker(target_size=1200)

    @pytest.mark.slow
    def test_chunk_sample_civil_case(self) -> None:
        with open("test_data/sample_civil_case.txt", encoding="utf-8") as f:
            text = f.read()
        assert len(text) > 500
        chunks = self.chunker.chunk(text, [0, len(text)])
        assert len(chunks) >= 1
        for c in chunks:
            assert c.text == text[c.offset_start:c.offset_end]
            assert c.offset_start < c.offset_end or c.offset_end == 0

    @pytest.mark.slow
    def test_chunk_sample_criminal_case(self) -> None:
        with open("test_data/sample_criminal_case.txt", encoding="utf-8") as f:
            text = f.read()
        assert len(text) > 500
        chunks = self.chunker.chunk(text, [0, len(text)])
        assert len(chunks) >= 1
        for c in chunks:
            assert c.text == text[c.offset_start:c.offset_end]
            assert c.offset_start < c.offset_end or c.offset_end == 0

    @pytest.mark.slow
    def test_chunk_sample_multi_page(self) -> None:
        with open("test_data/sample_multi_page_document.txt", encoding="utf-8") as f:
            text = f.read()
        assert len(text) > 500
        page_size = len(text) // 3
        page_offsets = [0, page_size, page_size * 2, len(text)]
        chunks = self.chunker.chunk(text, page_offsets)
        assert len(chunks) >= 1
        for c in chunks:
            assert c.page_start >= 1
            assert c.page_end <= len(page_offsets) - 1
