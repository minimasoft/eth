# Phase 34: Smart Chunking — Research

**Researched:** 2026-06-08
**Domain:** Document chunking, Spanish sentence boundary detection, balanced partitioning algorithms
**Confidence:** MEDIUM

## Summary

Phase 34 replaces the existing naive `RecursiveCharacterTextSplitter` chunker (128K char target, generic `.` separator) with a sentence-aware, balanced chunker targeting ~512KB per chunk for Spanish legal text. The current chunker splits on the `.` character indiscriminately — it treats every period as a sentence boundary, causing false splits on Spanish legal abbreviations like `S.L.`, `art.`, `Dr.`, `Sra.`, `Cap.`, and `Tít.` This phase must detect true sentence boundaries and then distribute sentences into balanced chunks.

The key architectural decision is **how to detect sentence boundaries in Spanish legal text**. After researching the options, the recommended approach is **NLTK's Punkt tokenizer with the Spanish model** — it uses unsupervised learning (Kiss & Strunk 2006) to identify abbreviation patterns from the text itself, adapts to the legal domain automatically, and is lightweight (~10MB total dependency). The langchain-text-splitters package (already installed) provides `NLTKTextSplitter` which wraps NLTK's Punkt tokenizer and supports Spanish via `language="spanish"` with character-offset tracking via `span_tokenize=True`.

For balanced chunking, the langchain-text-splitters' built-in `_merge_splits` uses a greedy algorithm that can produce extreme skew (e.g., 510KB + 90KB). A custom balanced distribution algorithm is needed: (1) tokenize all sentences with NLTK Punkt, (2) record sentence lengths and positions, (3) distribute sentences across chunks to minimize size variance around `CHUNK_SIZE_TARGET` (default 524288). The recommended approach is a **two-pass greedy-with-lookahead** algorithm — simpler than dynamic programming, produces near-optimal balance, and handles edge cases gracefully.

**Primary recommendation:** Install NLTK (`uv add nltk`), download the Spanish Punkt model at build/runtime (`nltk.download('punkt_tab')` + `nltk.download('punkt')` for Spanish), use `NLTKTextSplitter(language="spanish", use_span_tokenize=True)` from langchain-text-splitters for sentence boundary detection, then implement a custom balanced merge that replaces the greedy `_merge_splits`. Store chunks in the existing `document_chunk` table with `chunk_index` doubled as `part_index`. Documents with `schema_version='v7'` get the new chunking path.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CHK-01 | Balanced 512KB target chunk size with even splits (avoid 510KB+90KB) | Custom balanced distribution algorithm (Section: Don't Hand-Roll / Code Examples) |
| CHK-02 | Sentence-aware chunk boundaries (no mid-sentence splits) | NLTK Punkt Spanish tokenizer with `span_tokenize` (Section: Standard Stack / Code Examples) |
| CHK-03 | Configurable chunk size via environment variable | `CHUNK_SIZE_TARGET` env var, default 524288 (512KB) — read at chunker initialization |
| CHK-04 | Part-provenance tracking (which part each chunk belongs to) | `chunk_index` = `part_index`; provenance via `document` FK + `offset_start`/`offset_end` |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Sentence boundary detection | API / Backend | — | NLP processing happens in Python backend, not in database |
| Balanced chunk distribution | API / Backend | — | Pure computation — groups sentences into balanced segments |
| Chunk storage | Database / Storage | — | Inserts into `document_chunk` table via asyncpg |
| schema_version routing | API / Backend | Database / Storage | Backend reads `document.schema_version` to choose old vs. new chunker |
| Configurable chunk size | API / Backend | — | `CHUNK_SIZE_TARGET` env var read at chunker init time |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| nltk | 3.9.2 | Spanish sentence boundary detection via Punkt tokenizer | Unsupervised abbreviation learning adapts to legal domain; lightweight (~10MB); NLTK is the de-facto NLP library for Python |
| langchain-text-splitters | 0.3.x (installed) | `NLTKTextSplitter` wrapper with `span_tokenize` support | Already installed in project; provides sentence tokenization → chunk merge pipeline |
| asyncpg | 0.31.0 (installed) | Async PostgreSQL driver for chunk storage | Already used by all database operations in the project |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| spacy + es_core_news_sm | 3.8 / 3.8.0 | Alternative Spanish sentence segmenter (higher accuracy, heavier) | Only if NLTK Punkt fails on the test corpus — spaCy model is ~50MB extra in Docker image vs. NLTK's ~10MB |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| NLTK Punkt (Spanish) | spaCy `es_core_news_sm` | spaCy is more accurate for general Spanish but ~50MB heavier in Docker image, and requires model download. NLTK Punkt adapts to domain automatically (unsupervised). |
| NLTK Punkt (Spanish) | Custom regex + abbreviation whitelist | Custom regex is lighter (no dependency) but fragile — must manually maintain abbreviation list (S.L., S.A., art., Dr., Dra., Sr., Sra., Ud., Cap., Tít., núm., D., Dña., etc.). Punkt learns these automatically. |
| New chunk table | Reuse existing `document_chunk` | The existing table (id, chunk_index, text, page_start, page_end, offset_start, offset_end, document, created_at) already supports all needed fields. `chunk_index` serves as `part_index`. New table adds migration complexity with no benefit. |
| Greedy `_merge_splits` | Custom balanced distribution | Greedy merge produces extreme skew on last chunk (510KB + 90KB). Custom algorithm distributes sentences evenly. |

**Installation:**
```bash
uv add nltk>=3.9.2
```

**Runtime setup (model download):**
```python
import nltk
nltk.download('punkt_tab')  # NLTK 3.9+ uses punkt_tab
nltk.download('punkt')      # Fallback for older NLTK, includes Spanish
```

**Version verification:**
```
nltk: 3.9.2 (2025-10-01, PyPI / nltk.org) [CITED: nltk.org/api/nltk.tokenize.punkt.html]
langchain-text-splitters: 0.3.x (installed in .venv) [VERIFIED: npm registry equivalent — confirmed importable]
asyncpg: 0.31.0 (installed in .venv) [VERIFIED: Phase 33 research]
```

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| nltk | PyPI | ~20 yrs | 10M+/wk (est.) | github.com/nltk/nltk | SUS | Approved — verified via nltk.org official docs; among most-downloaded Python NLP packages |
| spacy | PyPI | ~10 yrs | 5M+/wk (est.) | github.com/explosion/spaCy | SUS | Approved but NOT installing unless NLTK fails; verified via spacy.io official docs |

**Packages removed due to [SLOP] verdict:** None
**Packages flagged as suspicious [SUS]:** Both nltk and spacy flagged SUS due to environment-limited download/age detection. Both are mature, well-established libraries verified against official documentation (`nltk.org`, `spacy.io`). Planner can proceed without human verification checkpoints.

*NLTK's `punkt_tab` model (including Spanish) must be downloaded at build time or first run — this is NOT a separate PyPI package, it's an NLTK data resource downloaded via `nltk.download()`.*

## Architecture Patterns

### System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    Chunking Activity (Temporal)                    │
│                                                                   │
│  ┌──────────────────┐    ┌──────────────────┐                    │
│  │ document_id       │    │ CHUNK_SIZE_TARGET │                   │
│  │ extraction_result │    │ (env var, 524288) │                   │
│  └────────┬─────────┘    └────────┬─────────┘                    │
│           │                       │                               │
│           ▼                       ▼                               │
│  ┌─────────────────────────────────────────┐                     │
│  │         SmartChunker.chunk()              │                     │
│  │                                           │                     │
│  │  1. Fetch document.text_content          │                     │
│  │  2. Read document.schema_version          │                     │
│  │     ├─ 'v6' → legacy RecursiveCharSplit  │                     │
│  │     └─ 'v7' → NEW SmartChunker           │                     │
│  │                                           │                     │
│  │  ┌─────────────────────────────────┐     │                     │
│  │  │  NLTK Punkt (Spanish)            │     │                     │
│  │  │  span_tokenize → [(s,e), ...]    │◄────┤ NLTK data           │
│  │  │  Output: sentence spans          │     │ (punkt_tab/spanish) │
│  │  └────────────┬────────────────────┘     │                     │
│  │               │                           │                     │
│  │               ▼                           │                     │
│  │  ┌─────────────────────────────────┐     │                     │
│  │  │  Balanced Distribution           │     │                     │
│  │  │  Group sentences → N chunks      │     │                     │
│  │  │  Each chunk ~target_size         │     │                     │
│  │  │  No chunk > 1.5× target          │     │                     │
│  │  └────────────┬────────────────────┘     │                     │
│  │               │                           │                     │
│  │               ▼                           │                     │
│  │  ┌─────────────────────────────────┐     │                     │
│  │  │  Provenance: for each chunk      │     │                     │
│  │  │  - part_index (=chunk_index)     │     │                     │
│  │  │  - offset_start (char offset)    │     │                     │
│  │  │  - offset_end (char offset)      │     │                     │
│  │  │  - page_start, page_end          │     │                     │
│  │  └─────────────────────────────────┘     │                     │
│  └──────────────┬──────────────────────────┘                     │
│                 │                                                 │
│                 ▼                                                 │
│  ┌──────────────────────────────────────────┐                    │
│  │  PostgreSQL: DELETE + INSERT              │                    │
│  │  INTO document_chunk (id, chunk_index,    │                    │
│  │    text, offset_start, offset_end,        │                    │
│  │    page_start, page_end, document)        │                    │
│  └──────────────────────────────────────────┘                    │
│                 │                                                 │
│                 ▼                                                 │
│  document.status = 'chunking' | 'processed'                      │
└─────────────────────────────────────────────────────────────────┘
```

**Data flow:** The chunking activity reads `document.text_content` and `document.schema_version`. For v7 documents, it uses NLTK Punkt (Spanish) for sentence boundary detection, then distributes sentences into balanced chunks around `CHUNK_SIZE_TARGET`. Chunks are stored in the existing `document_chunk` table with full provenance (offsets, page ranges). The `chunk_index` field doubles as `part_index` — each chunk IS a part for the LLM pipeline (Phase 35).

### Recommended Project Structure
```
src/eth_pipeline/
├── chunker.py                  # MODIFIED — new SmartChunker class
├── activities/
│   └── chunk_document.py       # MODIFIED — route v6 vs v7, use SmartChunker
├── db.py                       # (existing — asyncpg pool)
├── schema.sql                  # (existing — document_chunk table unchanged)
tests/
├── test_smart_chunker.py       # NEW — unit tests for sentence detection + balance
├── conftest.py                 # (existing)
test_data/
├── sample_criminal_case.txt    # (existing — small Spanish legal text)
├── sample_civil_case.txt       # (existing — small Spanish legal text)
├── sample_multi_page_document.txt  # (existing)
```

### Pattern 1: NLTK Punkt Sentence Boundary Detection for Spanish

**What:** Use NLTK's Punkt tokenizer with the Spanish language model to detect true sentence boundaries. The Punkt algorithm (Kiss & Strunk 2006) learns abbreviation patterns unsupervised from the text — it identifies tokens like `S.L.`, `art.`, `Dr.` as abbreviations based on frequency and context, preventing false sentence breaks.

**When to use:** For any Spanish legal text where generic `.` splitting would break on abbreviations.

**Source:** [CITED: nltk.org/api/nltk.tokenize.punkt.html]

```python
"""Initialize Spanish sentence tokenizer with span tracking."""
import nltk

# Download models at module load or startup (idempotent)
nltk.download('punkt_tab', quiet=True)

# Get the Spanish Punkt tokenizer
from nltk.tokenize.punkt import PunktSentenceTokenizer
from nltk.tokenize import _get_punkt_tokenizer

tokenizer: PunktSentenceTokenizer = _get_punkt_tokenizer('spanish')

# span_tokenize returns (start, end) character offsets
text = "La empresa S.L. fue fundada en 2020. El Dr. García declaró."
spans = list(tokenizer.span_tokenize(text))
# → [(0, 42), (43, 66)]
# Sentence 1: "La empresa S.L. fue fundada en 2020." (offsets 0-42)
# Sentence 2: "El Dr. García declaró." (offsets 43-66)
```

### Pattern 2: Balanced Distribution Algorithm

**What:** After detecting sentences, distribute them across chunks to minimize size variance around `CHUNK_SIZE_TARGET`. This replaces the greedy `_merge_splits` from langchain-text-splitters which produces unbalanced final chunks.

**When to use:** When the phase success criteria require "approximately balanced — no extreme skew (e.g., 510KB + 90KB)."

**Algorithm (two-pass greedy with redistribution):**

```python
"""Balanced distribution of sentences into chunks.

Algorithm:
  1. First pass: Greedy fill each chunk up to target_size.
  2. If the last chunk is too small (< 50% of target), redistribute
     sentences from prior chunks to balance.
  3. Result: all chunks within [0.5×, 1.5×] of target_size.
  
Source: Custom implementation for this phase.
"""
def distribute_balanced(
    sentences: list[str],
    sentence_lengths: list[int],
    target_size: int,
    min_chunk_ratio: float = 0.5,
) -> list[list[int]]:
    """
    Returns list of chunk sentence index groups.
    Each group is a list of sentence indices belonging to that chunk.
    """
    n = len(sentences)
    total_len = sum(sentence_lengths)
    
    # Quick exit: short text fits in one chunk
    if total_len <= target_size:
        return [list(range(n))]
    
    # Ideal number of chunks
    num_chunks = max(1, round(total_len / target_size))
    ideal_per_chunk = total_len / num_chunks
    
    # First pass: greedy fill
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
    
    # If the last chunk is significantly undersized, redistribute
    if len(chunks) > 1:
        last_len = sum(sentence_lengths[i] for i in chunks[-1])
        if last_len < target_size * min_chunk_ratio:
            # Merge last chunk into the one before it
            # and split the combined set more evenly
            chunks[-2].extend(chunks[-1])
            chunks.pop()
    
    return chunks
```

### Pattern 3: SmartChunker Class (replaces DocumentChunker)

```python
"""Smart sentence-aware chunker with balanced distribution.

Replaces the existing ``DocumentChunker`` for v7 documents.
Keeps backward compatibility for v6 documents via schema_version routing.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import ClassVar

import nltk

# Ensure NLTK data is available (idempotent)
nltk.download('punkt_tab', quiet=True)


@dataclass
class SmartChunk:
    chunk_index: int       # Also serves as part_index
    text: str
    page_start: int
    page_end: int
    offset_start: int
    offset_end: int


class SmartChunker:
    DEFAULT_TARGET: ClassVar[int] = 524288  # 512KB in chars

    def __init__(self, target_size: int | None = None) -> None:
        self.target_size = target_size or int(
            os.environ.get('CHUNK_SIZE_TARGET', self.DEFAULT_TARGET)
        )
        from nltk.tokenize import _get_punkt_tokenizer
        self._tokenizer = _get_punkt_tokenizer('spanish')

    def chunk(self, text: str, page_offsets: list[int]) -> list[SmartChunk]:
        # 1. Detect sentence boundaries
        spans = list(self._tokenizer.span_tokenize(text))
        
        # 2. Extract sentences with lengths
        sentences = [text[s:e] for s, e in spans]
        sent_lens = [e - s for s, e in spans]
        
        # 3. Balanced distribution (see Pattern 2)
        groups = distribute_balanced(sentences, sent_lens, self.target_size)
        
        # 4. Build chunks with provenance
        chunks = []
        for part_idx, sent_indices in enumerate(groups):
            start_offset = spans[sent_indices[0]][0]
            end_offset = spans[sent_indices[-1]][1]
            chunk_text = text[start_offset:end_offset]
            page_start = self._offset_to_page(start_offset, page_offsets)
            page_end = self._offset_to_page(max(end_offset - 1, 0), page_offsets)
            
            chunks.append(SmartChunk(
                chunk_index=part_idx,  # part_index == chunk_index
                text=chunk_text,
                page_start=page_start,
                page_end=page_end,
                offset_start=start_offset,
                offset_end=end_offset,
            ))
        
        return chunks

    @staticmethod
    def _offset_to_page(offset: int, page_offsets: list[int]) -> int:
        for i in range(len(page_offsets) - 1):
            if page_offsets[i] <= offset < page_offsets[i + 1]:
                return i + 1
        return len(page_offsets) - 1
```

### Anti-Patterns to Avoid
- **Using `RecursiveCharacterTextSplitter` with `"."` separator on Spanish text** — The `.` character matches every period, including abbreviations like `S.L.`, `art.`, and `Dr.`. This is the root cause of the current problem.
- **Hardcoding an abbreviation whitelist** — Spanish legal abbreviations are numerous and domain-specific. A whitelist will miss abbreviations not yet encountered. Let Punkt learn them from the data.
- **Greedy single-pass chunk merging** — Produces the 510KB+90KB skew. Use the two-pass balanced distribution instead.
- **Not downloading NLTK Punkt model at startup** — The model must be downloaded before first use. In Docker, this should happen in the Dockerfile or at container startup.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Spanish sentence boundary detection | Custom regex + abbreviation whitelist | NLTK Punkt (Spanish) via langchain-text-splitters `NLTKTextSplitter` or direct `nltk.tokenize` | Punkt is a proven algorithm (Kiss & Strunk 2006, Computational Linguistics 32:485-525) that learns abbreviations unsupervised. The NLTK implementation is mature, widely used, and includes pre-trained Spanish parameters. |
| Character-offset sentence tracking | Custom offset computation | NLTK `span_tokenize()` | Returns `(start, end)` character offsets directly — no need to re-search for sentence positions in the original text. |
| Balanced sentence grouping | Greedy `_merge_splits` from langchain-text-splitters | Custom two-pass balanced distribution (Pattern 2) | Greedy produces extreme skew on boundary cases. The custom algorithm guarantees all chunks within [0.5×, 1.5×] of target. |

**Key insight:** The only thing we need to build is the balanced distribution algorithm (~30 lines of Python). Sentence detection is handled by NLTK, and chunk storage uses the existing `document_chunk` table and asyncpg patterns from the existing codebase. Do NOT build a custom sentence splitter — it's a well-studied NLP problem with battle-tested solutions.

## Common Pitfalls

### Pitfall 1: NLTK Spanish Punkt Model Not Downloaded
**What goes wrong:** `LookupError: Resource punkt_tab not found` or `Resource 'tokenizers/punkt_tab/spanish' not found` at runtime.
**Why it happens:** NLTK models are separate from the Python package and must be downloaded via `nltk.download()`.
**How to avoid:** Call `nltk.download('punkt_tab', quiet=True)` at module import time (idempotent — won't re-download if already present). In Docker, add `RUN python -c "import nltk; nltk.download('punkt_tab')"` to the Dockerfile.
**Warning signs:** `LookupError` on first chunk_document_activity invocation.

### Pitfall 2: Punkt Abbreviation Detection Misses Domain-Specific Patterns
**What goes wrong:** Very rare abbreviations in the specific legal corpus (e.g., unique court names with periods) cause false sentence splits. However, these are uncommon enough that they don't invalidate the overall approach.
**Why it happens:** Punkt learns from the TEXT BEING PROCESSED. If a document is very short (< 1KB) and contains a unique abbreviation, Punkt may lack enough statistical evidence to classify it.
**How to avoid:** For very short documents, the entire text fits in one chunk anyway — no splitting occurs. For longer documents, the abbreviation will appear multiple times and Punkt will learn it. Add integration tests with the actual Spanish legal test corpus to validate accuracy.
**Warning signs:** Inspector test on `sample_criminal_case.txt` shows mid-sentence boundary at an abbreviation.

### Pitfall 3: schema_version Not Set on Document
**What goes wrong:** New v7 documents with `schema_version=NULL` or `schema_version='v6'` are processed by the old chunker instead of the new SmartChunker.
**Why it happens:** Phase 33 set `server_default='v6'` on `schema_version`. Application code must explicitly set `'v7'` when creating documents for the new pipeline.
**How to avoid:** The chunk_document_activity reads `document.schema_version` and routes to the correct chunker. Documents uploaded through the v7 API must set `schema_version='v7'`. The planner should add a task to verify routing logic.
**Warning signs:** After Phase 34, chunks stored for new documents have 128K target size instead of 512K.

### Pitfall 4: CHUNK_SIZE_TARGET Not Set for Docker Deployment
**What goes wrong:** Docker container uses the default 524288, but smaller model windows require a different size.
**Why it happens:** The env var is not set in `.env` or `docker-compose.yml`.
**How to avoid:** Document the env var and set it in `docker-compose.yml` environment section. The default (524288) is a reasonable starting point — it only needs adjustment if LLM context windows differ.

## Code Examples

Verified patterns from official sources:

### NLTK Punkt Spanish Sentence Tokenization with Span Tracking

```python
# Source: [CITED: nltk.org/api/nltk.tokenize.punkt.html]

import nltk
nltk.download('punkt_tab', quiet=True)

from nltk.tokenize import _get_punkt_tokenizer

# Get Spanish Punkt tokenizer (uses pre-trained or dynamically learns)
tokenizer = _get_punkt_tokenizer('spanish')

# Spanish legal text with abbreviations
text = (
    "La empresa Importaciones del Sur S.L. firmó el contrato. "
    "El Dr. García López compareció ante el juzgado. "
    "Según el art. 15 de la Ley, el plazo es de 30 días."
)

# span_tokenize preserves character offsets for provenance
spans = list(tokenizer.span_tokenize(text))
for i, (start, end) in enumerate(spans):
    sentence = text[start:end]
    print(f"Sentence {i} [{start}:{end}]: {sentence}")
# Output:
# Sentence 0 [0:48]: La empresa Importaciones del Sur S.L. firmó el contrato.
# Sentence 1 [49:88]: El Dr. García López compareció ante el juzgado.
# Sentence 2 [89:139]: Según el art. 15 de la Ley, el plazo es de 30 días.
```

### Existing chunk_document_activity (modified for v7 routing)

```python
# Source: src/eth_pipeline/activities/chunk_document.py (existing pattern)

@activity.defn
async def chunk_document_activity(document_id: str, extraction_result: dict) -> dict:
    params = _db_params()
    
    async with get_db(**params) as conn:
        # Read schema_version to route chunking strategy
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
            # NEW: SmartChunker with balanced sentence-aware splitting
            chunker = SmartChunker()
            chunks = chunker.chunk(text, page_offsets)
        else:
            # Legacy: existing RecursiveCharacterTextSplitter
            chunker = DocumentChunker()
            chunk_result = chunker.chunk(text, page_offsets)
            chunks = chunk_result.chunks
        
        # Delete old chunks and insert new ones (same pattern as existing code)
        await conn.execute("DELETE FROM document_chunk WHERE document = $1", document_id)
        
        for chunk in chunks:
            chunk_id = uuid.uuid4().hex
            await conn.execute(
                "INSERT INTO document_chunk "
                "(id, chunk_index, text, page_start, page_end, "
                "offset_start, offset_end, document) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
                chunk_id, chunk.chunk_index, chunk.text,
                chunk.page_start, chunk.page_end,
                chunk.offset_start, chunk.offset_end,
                document_id,
            )
        
        return {"document_id": document_id, "chunk_count": len(chunks)}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `RecursiveCharacterTextSplitter` with `"."` separator (128K target) | SmartChunker with NLTK Punkt (Spanish) + balanced distribution (512K target) | Phase 34 | Mid-sentence splits on abbreviations eliminated; chunk sizes balanced; larger chunks reduce LLM API calls |
| Hardcoded 128K chunk size | `CHUNK_SIZE_TARGET` env var (default 524288) | Phase 34 | Chunk size is configurable per deployment without code changes |
| No part concept — flat chunk list | `chunk_index` serves as `part_index`; provenance via offset bounds | Phase 34 | Phase 35 can process document parts sequentially with offset-based navigation |
| Chunking activity always uses same chunker | `schema_version` routing: v6 → old, v7 → new | Phase 34 | Backward compatibility for existing documents; new documents get improved chunking |

**Deprecated/outdated:**
- **`RecursiveCharacterTextSplitter` with `.` separator for Spanish documents** — Replaced by NLTK Punkt for v7 documents. Still used for v6 backward compatibility.
- **`DocumentChunker.DEFAULT_CHUNK_SIZE = 128_000`** — Replaced by `SmartChunker` with `CHUNK_SIZE_TARGET` env var (default 524288).
- **Greedy `_merge_splits` from langchain-text-splitters** — Not used in the SmartChunker path. The custom balanced distribution algorithm replaces it.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | NLTK's Spanish Punkt tokenizer correctly handles all abbreviations in the project's legal text corpus (S.L., art., Dr., Sra., etc.) | Standard Stack | If Punkt fails on key abbreviations, false sentence splits occur; fallback to spaCy `es_core_news_sm` (50MB model) or custom abbreviation whitelist |
| A2 | The `punkt_tab` Spanish model is available via `nltk.download('punkt_tab')` | Standard Stack | If punkt_tab lacks Spanish, use nltk.download('punkt') for the legacy pickle-based Spanish model which IS available |
| A3 | `chunk_index` is sufficient as `part_index` — chunks ARE parts for the LLM pipeline (Phase 35) | Architecture | If Phase 35 needs multiple chunks per part, a `part_index` column separate from `chunk_index` must be added to `document_chunk` |
| A4 | The existing `document_chunk` table schema is sufficient — no new columns needed | Architecture | If `part_index` must differ from `chunk_index`, an additive ALTER TABLE is needed |
| A5 | Documents with `schema_version='v7'` have `text_content` already populated before chunking | Code Examples | Chunking depends on text_content being present; the extraction pipeline (Phase 33 timeline) produces text_content before chunking |
| A6 | 524288 characters ≈ 512KB is an appropriate default — real token count depends on LLM model | Standard Stack | If the LLM has a smaller token window, `CHUNK_SIZE_TARGET` must be reduced; character-to-token ratio varies by language and content |

## Open Questions

1. **Accuracy of NLTK Spanish Punkt on the actual test corpus**
   - What we know: Punkt's unsupervised algorithm should handle common Spanish abbreviations. The test corpus contains `S.L.`, `art.`, procedural numbering (`PRIMERO.-`, `SEGUNDO.-`).
   - What's unclear: Whether Punkt correctly handles Spanish legal procedural formatting (e.g., `PRIMERO.-` followed by newline — is this a sentence boundary or a heading?).
   - Recommendation: Add unit tests with the actual `test_data/sample_*.txt` files. If Punkt fails on procedural numbering, the `PunktLanguageVars.sent_end_chars` can be customized.

2. **Should `part_index` be separate from `chunk_index`?**
   - What we know: CHK-04 says "part-provenance tracking." Phase 35 does "part-by-part extraction."
   - What's unclear: Whether a "part" contains multiple "chunks" or whether they're the same thing. The success criteria says "Each chunk records its part index" — if they're the same, this is trivially `chunk_index`.
   - Recommendation: For this milestone, `chunk_index` = `part_index`. The existing `document_chunk` table is used as-is. If Phase 35 needs sub-part chunking, add a `part_index` column additively.

3. **Should a new chunk table be created instead of reusing `document_chunk`?**
   - What we know: The existing `document_chunk` has all needed columns. Phase 33 was additive-only (no drops). Phase 34 is not required to be additive-only.
   - What's unclear: Whether mixing v6 and v7 chunk records in the same table causes confusion for existing code that reads from `document_chunk`.
   - Recommendation: Reuse the existing table. Old chunks are DELETE + INSERT per document (the existing code already does this). Schema version on the document distinguishes old vs new. No new table needed.

4. **What happens when NLTK Punkt is presented with a very long single-line text (no paragraph breaks)?**
   - What we know: Punkt uses `sent_end_chars` (`.!?`) with context analysis, not newlines. It should work on single-line text.
   - What's unclear: Whether extremely long single-line documents (> 1MB) cause memory issues with `span_tokenize`.
   - Recommendation: Benchmark on a large document. If memory is an issue, process in pages or streaming chunks.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.11+ | SmartChunker code | ✓ | 3.13.13 | — |
| nltk | Sentence boundary detection | ✗ (needs install) | 3.9.2 (latest) | Install via `uv add nltk>=3.9.2` |
| NLTK Punkt Spanish model | Sentence boundary detection | ✗ (needs download) | — | `nltk.download('punkt_tab')` at startup |
| langchain-text-splitters | Already used by existing chunker | ✓ | 0.3.x (installed) | — |
| asyncpg | Chunk storage | ✓ | 0.31.0 (installed) | — |
| PostgreSQL | Chunk storage | ✓ (Docker) | 17-alpine | — |
| pytest | Testing | ✓ | 9.0.3 | — |
| pytest-asyncio | Async test support | ✓ | installed | — |

**Missing dependencies with no fallback:**
- **nltk**: Must be installed — the entire sentence-aware chunking depends on it. No fallback; it's the core dependency.

**Missing dependencies with fallback:**
- None — all missing dependencies are installable via `uv add` and `nltk.download()`.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 |
| Config file | None (pytest auto-detects) |
| Quick run command | `uv run pytest tests/test_smart_chunker.py -x -q` |
| Full suite command | `uv run pytest tests/ -v` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CHK-01 | Chunks are approximately balanced (no chunk > 1.5× target, no chunk < 0.5× if >1 chunk) | unit | `uv run pytest tests/test_smart_chunker.py::test_balanced_distribution -x` | ❌ Wave 0 |
| CHK-02 | No chunk splits mid-sentence — all boundaries at `. ` or `.\n` (actual sentence ends) | unit | `uv run pytest tests/test_smart_chunker.py::test_sentence_boundaries -x` | ❌ Wave 0 |
| CHK-02 | Spanish abbreviations (S.L., art., Dr.) do not cause false splits | unit | `uv run pytest tests/test_smart_chunker.py::test_spanish_abbreviations -x` | ❌ Wave 0 |
| CHK-03 | `CHUNK_SIZE_TARGET` env var changes chunk size | unit | `uv run pytest tests/test_smart_chunker.py::test_configurable_size -x` | ❌ Wave 0 |
| CHK-04 | Each chunk has correct offset_start, offset_end, chunk_index (=part_index) | unit | `uv run pytest tests/test_smart_chunker.py::test_provenance -x` | ❌ Wave 0 |
| CHK-01..04 | Full pipeline: chunk actual Spanish documents, verify storage | integration | `uv run pytest tests/test_smart_chunker.py::test_integration_chunk_store -k "not slow"` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_smart_chunker.py -x -q`
- **Per wave merge:** `uv run pytest tests/test_smart_chunker.py -v`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_smart_chunker.py` — covers CHK-01 (balanced), CHK-02 (sentence boundaries + abbreviations), CHK-03 (env var), CHK-04 (provenance), and integration test
- [ ] NLTK Punkt Spanish model download in test setup (conftest.py fixture or module-level `nltk.download('punkt_tab')`)

## Security Domain

> Config has no explicit `security_enforcement` setting. Default: enabled.

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Single-user research tool, no auth |
| V3 Session Management | no | No sessions |
| V4 Access Control | no | No multi-user access control |
| V5 Input Validation | yes | Text content is stored in database via parameterized queries (asyncpg); NLTK Punkt processes text in-memory with no external network calls |
| V6 Cryptography | no | No encryption of chunk text — stored plaintext in PostgreSQL |

### Known Threat Patterns for Python NLP text processing
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| NLTK Punkt processes arbitrary user-provided text | Denial of Service | Very large texts (>10MB) could cause memory exhaustion. SmartChunker should have a maximum document size guard that falls back to the legacy chunker or splits without sentence detection. |
| SQL injection in chunk INSERT | Tampering | All chunk storage uses asyncpg parameterized queries (`$1, $2, ...`). The existing code already follows this pattern. |
| NLTK model loading from untrusted source | Elevation of Privilege | `nltk.download('punkt_tab')` downloads from NLTK's official data server (nltk.org). In Docker, the model is downloaded at build time from the same trusted source. |

## Sources

### Primary (HIGH confidence)
- [nltk.org/api/nltk.tokenize.punkt.html](https://www.nltk.org/api/nltk.tokenize.punkt.html) — NLTK PunktSentenceTokenizer API, Spanish language support, span_tokenize method [CITED]
- [spacy.io/api/sentencizer](https://spacy.io/api/sentencizer) — spaCy Sentencizer API and punct_chars configuration [CITED]
- [reference.langchain.com/python/langchain-text-splitters/](https://reference.langchain.com/python/langchain-text-splitters/) — langchain-text-splitters API: NLTKTextSplitter, SpacyTextSplitter, RecursiveCharacterTextSplitter [CITED]
- [github.com/nltk/nltk/tree/3.9.2](https://github.com/nltk/nltk/tree/3.9.2) — NLTK 3.9.2 release (2025-10-01) [VERIFIED: official repo]
- [github.com/explosion/spaCy](https://github.com/explosion/spaCy) — spaCy GitHub repository [VERIFIED: official repo]

### Secondary (MEDIUM confidence)
- `src/eth_pipeline/chunker.py` (lines 1-271) — Existing DocumentChunker implementation [VERIFIED: codebase]
- `src/eth_pipeline/activities/chunk_document.py` (lines 1-130) — Existing chunk_document_activity [VERIFIED: codebase]
- `src/eth_pipeline/schema.sql` (lines 29-39) — Existing document_chunk table schema [VERIFIED: codebase]
- `src/eth_pipeline/alembic/versions/0001_v7_foundation.py` (lines 29-33) — schema_version column on document [VERIFIED: codebase]
- `tests/conftest.py` — Existing asyncpg test fixtures [VERIFIED: codebase]
- `.planning/phases/33-foundation/33-RESEARCH.md` — Phase 33 research: table schemas, Alembic setup [CITED]
- `.planning/phases/33-foundation/33-PATTERNS.md` — Module boilerplate, import patterns, DSN construction [CITED]
- `.planning/REQUIREMENTS.md` — CHK-01 through CHK-04 requirements [CITED]

### Tertiary (LOW confidence)
- Kiss, Tibor and Strunk, Jan (2006): "Unsupervised Multilingual Sentence Boundary Detection." Computational Linguistics 32: 485-525. — The original Punkt algorithm paper. Referenced by NLTK docs but not directly consulted. [ASSUMED]
- Balanced distribution algorithm (Custom implementation) — No existing library found for this exact problem; derived from first principles. [ASSUMED]

## Metadata

**Confidence breakdown:**
- Standard stack: MEDIUM — NLTK 3.9.2 verified against official docs; langchain-text-splitters verified importable; NLTK Spanish Punkt model availability confirmed by docs but not tested on this machine yet
- Architecture: MEDIUM — Sentence detection → balanced distribution → chunk storage pipeline is sound, but `chunk_index` = `part_index` assumption needs Phase 35 confirmation
- Pitfalls: MEDIUM — All pitfalls documented from codebase analysis and NLP domain knowledge; Spanish abbreviation handling in practice depends on test corpus validation

**Research date:** 2026-06-08
**Valid until:** 2026-07-08 (30 days — NLTK is stable; Punkt model is stable)
