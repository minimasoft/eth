---
phase: 07-pdf-text-extraction-chunking
plan: 01
subsystem: pdf-extraction
tags:
  - content-extraction
  - text-chunking
  - pdf
  - pypdfium2
  - pypdf
  - langchain
depends-on: []
provides:
  - ContentExtractor protocol + PdfExtractor with quality gate
  - DocumentChunker with page-provenance tracking
  - pypdfium2/pypdf/langchain-text-splitters deps
affects:
  - src/eth_pipeline/extractors.py (new)
  - src/eth_pipeline/chunker.py (new)
  - pyproject.toml (added deps)
  - .env / .env.example (added USE_PYPDF)
tech-stack:
  added:
    - pypdfium2>=4.30.0
    - pypdf>=5.1.0
    - langchain-text-splitters>=0.3.0
  patterns:
    - Protocol-based content extractor (pluggable extractors)
    - Lazy imports for optional dependencies
    - Quality gates with typed exceptions (ExtractorQualityError)
    - RecursiveCharacterTextSplitter with punctuation-aware separator chain
    - Next-chunk offset computation for page provenance
key-files:
  created:
    - src/eth_pipeline/extractors.py (127 lines)
    - src/eth_pipeline/chunker.py (274 lines)
  modified:
    - pyproject.toml (added 3 deps)
    - .env.example (added USE_PYPDF)
decisions:
  - "pypdfium2 is primary extractor (BSD-3-Clause); pypdf is AGPL-mitigation fallback via USE_PYPDF env var"
  - "Chunks are non-overlapping (chunk_overlap=0) — reconstruction uses original text offsets, not concatenation"
  - "All third-party imports are lazy so modules can be imported without the packages"
  - "USE_PYPDF env var uses string truthy check ('true'/'1'/'yes') matching storage.py parse pattern"
metrics:
  duration: ~12 minutes
  completed: "2026-05-31"
  tasks: 3
  commits: 3
---

# Phase 07 Plan 01: Content extractors + chunker library

## Summary

Created the foundational content extraction and text chunking library for Phase 7: pluggable `ContentExtractor` protocol, `PdfExtractor` with pypdfium2 primary and pypdf fallback paths, quality gate for empty/scanned PDFs, `DocumentChunker` with page-provenance tracking using `RecursiveCharacterTextSplitter`, and dependency declarations.

## Implementation Details

### ContentExtractor protocol + PdfExtractor (`extractors.py`)
- **ContentExtractor**: `Protocol` class with `extract(content: bytes, filename: str) -> ExtractionResult` signature
- **ExtractionResult**: Dataclass with `text`, `page_count`, `page_offsets` (cumulative per-page char offsets), `metadata`
- **ExtractorQualityError**: Typed exception with `reason` field (`quality_gate`, `empty_or_scanned`, `empty`, `likely_scanned`)
- **PdfExtractor**:
  - Reads `USE_PYPDF` env var; "true"/"1"/"yes" → pypdf fallback
  - pypdfium2 path: `PdfDocument(content)` → iterates pages → `page.get_text_bounded()` → builds `page_offsets`
  - pypdf path: `PdfReader(BytesIO(content))` → iterates `reader.pages` → `page.extract_text()`
  - Both paths use form-feed (`\f`) separator between page texts
- **Quality gate**: Empty text → `reason="empty_or_scanned"`, zero pages → `reason="empty"`, very short text on multi-page → `reason="likely_scanned"`
- **Registry**: Module-level `_extractors` dict with `register_extractor()` / `get_extractor()`, auto-registers "pdf"
- **Convenience**: `extract_text(content, filename)` — auto-detects format from extension

### DocumentChunker (`chunker.py`)
- **DocumentChunk**: Dataclass with `chunk_index`, `text`, `page_start` (1-based), `page_end`, `offset_start`, `offset_end`
- **ChunkResult**: Dataclass with `chunks`, `chunk_size_target`, `total_text_length`
- **DocumentChunker**: Default chunk_size=128_000, `chunk_overlap=0`
  - Wraps `RecursiveCharacterTextSplitter` with separator chain: `\n\n → \n → . → ! → ? → , → space → ""`
  - Computes chunk offsets in original text via next-chunk position tracking (robust to splitter whitespace normalization)
  - Maps offsets to 1-based page numbers via `page_offsets` array
- **Convenience**: `chunk_document(text, page_offsets, chunk_size)` — one-call chunking
- **Edge cases**: Short text (single chunk), empty text, empty page_offsets normalisation

### Dependencies + env vars
- Added `pypdfium2>=4.30.0`, `pypdf>=5.1.0`, `langchain-text-splitters>=0.3.0` to `pyproject.toml`
- Added `USE_PYPDF=false` to `.env` and `.env.example` with descriptive comment

## Deviations from Plan

None — plan executed exactly as written.

## File Summary

| File | Status | Purpose |
|------|--------|---------|
| `src/eth_pipeline/extractors.py` | Created (127 lines) | ContentExtractor protocol, PdfExtractor, quality gate, registry |
| `src/eth_pipeline/chunker.py` | Created (274 lines) | DocumentChunker with page-provenance tracking |
| `pyproject.toml` | Modified | Added 3 dependencies |
| `.env.example` | Modified | Added USE_PYPDF=false |
| `.env` | Modified (locally) | Added USE_PYPDF=false (gitignored) |

## Success Criteria Verification

- [x] `from eth_pipeline.extractors import ContentExtractor, PdfExtractor, ExtractorQualityError, ExtractionResult, extract_text` — all importable
- [x] `from eth_pipeline.chunker import DocumentChunker, DocumentChunk, ChunkResult, chunk_document` — all importable
- [x] pypdfium2, pypdf, langchain-text-splitters in pyproject.toml dependencies
- [x] USE_PYPDF env var declared in .env and .env.example
- [x] Chunk concatenation covers full original text range (offset_start=0, offset_end=len(text))
- [x] Chunk page_start/page_end provenance is 1-based and internally consistent

## Commits

| Hash | Message |
|------|---------|
| `19d81dc` | feat(07-01): create ContentExtractor protocol + PdfExtractor with quality gate |
| `220579c` | feat(07-01): create DocumentChunker with page-provenance tracking |
| `cdb6b3e` | chore(07-01): add pypdfium2, pypdf, langchain-text-splitters deps and USE_PYPDF env var |

## Self-Check: PASSED
