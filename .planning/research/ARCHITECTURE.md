# Architecture Research — Blob & Chunk Pipeline Integration

**Domain:** Document ingestion processing pipeline (MinIO/S3 blob storage + PDF extraction + text chunking + internal multi-chunk document model)
**Researched:** 2026-05-31
**For milestone:** v2.0 Blob & Chunk Pipeline
**Mode:** Integration-points analysis of new components into existing Temporal/SurrealDB/FastAPI architecture
**Confidence:** HIGH (existing patterns and new library APIs verified)

---

## 1. Current Architecture Baseline

```
                    ┌─────────────────┐
                    │   User / API    │
                    │  (FastAPI port  │
                    │    8001)        │
                    └────────┬────────┘
                             │ POST /documents  (raw text)
                             │ POST /graphql
                             │ DELETE /documents/{id}/events
                             │ POST /entities/merge
                             ▼
┌──────────────────────────────────────────────────────┐
│                  Temporal Worker                       │
│  ┌────────────────────────────────────────────────┐   │
│  │         DocumentProcessingWorkflow               │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │   │
│  │  │ Status   │  │ Extract  │  │ Store        │  │   │
│  │  │ Update   │→│ Events  │→│ Results      │  │   │
│  │  └──────────┘  └──────────┘  └──────┬───────┘  │   │
│  │                                     ▼           │   │
│  │                              ┌──────────────┐  │   │
│  │                              │ Resolve      │  │   │
│  │                              │ Entities     │  │   │
│  │                              └──────────────┘  │   │
│  └────────────────────────────────────────────────┘   │
│                                                        │
│  Activities: extract_events, store_results,            │
│              resolve_entities, update_status            │
└──────────────────────┬─────────────────────────────────┘
                       │ WS RPC (ws://surrealdb:8000/rpc)
                       ▼
┌──────────────────────────────────────────────┐
│                 SurrealDB                      │
│  ┌──────────────────┐  ┌───────────────────┐ │
│  │    document       │  │      event         │ │
│  │ - text_content    │  │ - que_paso         │ │
│  │ - original_blob   │  │ - espacio          │ │
│  │   (base64 text)   │  │ - tiempo           │ │
│  │ - status          │  │ - humanos          │ │
│  │ - filename        │  │ - objetos          │ │
│  │ - mime_type       │  │ - document (link)  │ │
│  └──────────────────┘  └────────┬──────────┘ │
│                                 │ record<event>│
│  ┌──────────────────┐  ┌───────▼───────────┐ │
│  │ canonical_entity  │  │    reference       │ │
│  │ - name            │  │ - verbatim_text    │ │
│  │ - entity_type     │  │ - reference_type   │ │
│  │ - properties      │  │ - span_start/end   │ │
│  │ - superseded_by   │  │ - event (link)     │ │
│  └──────────────────┘  │ - canonical_entity  │ │
│                         └────────────────────┘ │
│                        auto-GraphQL on port 8000│
└──────────────────────────────────────────────────┘
```

### Current Data Flow (M001-M002)

```
POST /documents {text, filename}
    → SurrealDB create document {text_content, original_blob(b64), status=pending}
    → Temporal start workflow "doc-{id}"
        → update_status("processing")
        → extract_events(text)  [OpenRouter LLM]
        → store_extraction_results → SurrealDB events+references
        → resolve_entities(document_id, result)  [LLM per-type batching]
        → update_status("processed")
    → GET /documents/{id} → status visible via API
```

**Critical observation:** `original_blob` is currently stored as a base64-encoded string *inside SurrealDB*. The document `text_content` is accepted directly — no extraction step exists. The `original_blob` and `text_content` are the same text, just one is base64-encoded. There is no separation between "blob storage" and "text storage."

---

## 2. Target Architecture (v2.0 Blob & Chunk Pipeline)

```
                    ┌─────────────────┐
                    │   User / API    │
                    │  (FastAPI port  │
                    │    8001)        │
                    └────────┬────────┘
          ┌──────────────────┼──────────────────────┐
          │ POST /documents  │ POST /documents/upload│
          │ (existing,       │ (NEW — multipart)    │
          │  accepts text    │  accepts PDF/DOCX)   │
          │  unchanged)      │                      │
          └────────┬─────────┴──────────┬───────────┘
                   ▼                    ▼
        ┌─────────────────────────────────────┐
        │           Temporal Worker            │
        │  ┌──────────────────────────────┐   │
        │  │ DocumentProcessingWorkflow   │   │
        │  │ [existing steps + new]       │   │
        │  │                              │   │
        │  │ 1. update_status("processing")│   │
        │  │ 2. [NEW] store_blob(MINIO)   │   │
        │  │ 3. [NEW] extract_text(PDF)   │   │
        │  │ 4. [NEW] chunk_text(text)    │   │
        │  │ 5. store_chunks(SurrealDB)   │   │
        │  │ 6. extract_events(text)      │   │
        │  │    (from chunks — unchanged) │   │
        │  │ 7. store_results (unchanged) │   │
        │  │ 8. resolve_entities(unchanged)│   │
        │  │ 9. update_status("processed")│   │
        │  └──────────────────────────────┘   │
        │                                      │
        │  [NEW] ContentExtractionWorkflow     │
        │  (called by DocumentProcessing-     │
        │   Workflow for binary documents)    │
        └──────────────────┬───────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                   │
        ▼                  ▼                   ▼
┌───────────────┐  ┌──────────────┐  ┌──────────────┐
│    SurrealDB   │  │    MinIO     │  │   OpenRouter  │
│ (unchanged +  │  │ (NEW)        │  │ (unchanged)   │
│  new tables)  │  │ S3 API       │  │               │
│               │  │ port 9000    │  │               │
│ document:     │  │              │  │               │
│  - text_content│  │ Bucket:      │  │               │
│  - original_blob│  │ eth-documents│  │               │
│    → MINIO_PATH│  │  doc/{id}.pdf│  │               │
│  - status      │  │  doc/{id}.txt│  │               │
│  - filename    │  │              │  │               │
│  - mime_type   │  └──────────────┘  └──────────────┘
│               │
│ [NEW]         │
│ document_chunk│
│  - chunk_index │
│  - text       │
│  - page_start │
│  - page_end   │
│  - offset_start│
│  - offset_end │
│  - document   │
│    (record link)│
│               │
│ events +      │
│ references +  │
│ canonical_entity│
│ (unchanged)   │
└───────────────┘
```

### Data Flow (new pipeline — PDF document)

```
POST /documents/upload {file: document.pdf}
    → FastAPI stores to MinIO immediately
        → bucket: eth-documents, object: doc/{doc_id}.pdf
    → SurrealDB create document {
        text_content: null  (not yet extracted),
        original_blob: "minio://eth-documents/doc/{doc_id}.pdf"  (path ref),
        blob_stored: true,
        status: "pending"
      }
    → Temporal workflow "doc-{id}" starts
        → update_status("extracting_blob")
        → [NEW] store_blob_activity   (if not already stored by API)
            → MinIO get_object(doc/{doc_id}.pdf)
            → skip if already stored
        → [NEW] extract_text_activity
            → MinIO get_object(doc/{doc_id}.pdf)
            → PyMuPDF open(blob)
            → iterate pages, extract text per page
            → return {full_text, pages_text: {page: text}}
            → SurrealDB UPDATE document SET text_content = full_text
        → update_status("chunking")
        → [NEW] chunk_text_activity
            → RecursiveCharacterTextSplitter (max_chars=128000)
            → Map page provenance via character offsets
            → return list[DocumentChunk]
        → [NEW] store_chunks_activity
            → SurrealDB create document_chunk records
            → all in single batch
        → update_status("processing")  (resume existing flow)
        → extract_events(text=full_text)  [unchanged]
        → store_extraction_results  [unchanged]
        → resolve_entities  [unchanged]
        → update_status("processed")
```

---

## 3. Where Each New Component Integrates

### 3.1 MinIO Blob Storage

**Integration type:** New persistent service in Docker Compose + new Python dependency (`minio`)

| Integration Point | Existing Component | How It Connects |
|---|---|---|
| **API (`api.py`)** | `POST /documents` — base64 `original_blob` | NEW: `POST /documents/upload` accepts multipart, uploads to MinIO immediately (see section 5 for backward compat decision). MinIO client initialized in lifespan alongside SurrealDB + Temporal. |
| **Temporal activities** | `extract_events_activity` — gets text | NEW: `store_blob_activity` — uploads blob to MinIO. NEW: `extract_text_activity` — reads blob from MinIO, extracts text. MinIO client initialized per-activity (same pattern as SurrealDB `get_db()` — D012 pattern). |
| **SurrealDB schema** | `document.original_blob` — base64 string | **Repurposed:** `original_blob` becomes `"minio://{bucket}/{path}"` reference. New field: `blob_stored: bool`. The field TYPE stays `string` (no schema migration needed). |
| **Docker Compose** | N/A | New `minio` service + `minio_data` volume |
| **Verification / tests** | TypeScript integration tests | NEW: test helpers initialize MinIO client, upload fixture PDFs, verify blob round-trip |
| **GraphQL / queries** | `document.original_blob` | Unchanged — still returns `string`. Value is now a path ref instead of base64 text. |

**Critical constraint:** MinIO is synchronous-only (no native async SDK). In Temporal activities this is fine — activities run in a thread pool. In FastAPI lifespan / endpoints, wrap in `asyncio.to_thread()`.

### 3.2 Content Extraction Workflow (PDF First)

**Integration type:** New Temporal activities + optional sub-workflow

| Integration Point | Existing Component | How It Connects |
|---|---|---|
| **`DocumentProcessingWorkflow`** | Accepts `document_id, text` params | **Modified:** Accepts `document_id, text=None, mime_type=None`. If `mime_type` is binary (PDF/DOCX), text is extracted by new activities. If `text` is provided directly (backward compat), skip extraction. |
| **`extract_events_activity`** | Gets `text` param directly | **Unchanged** — still receives the full reconstructed text |
| **OCR / scanned PDF** | N/A | Deferred — PyMuPDF can do it but requires Tesseract on the container. First version: extractable PDFs only. Scanned PDFs → `status: "failed"` with message requesting OCR setup. |
| **Extensibility (DOCX, images)** | N/A | `ContentExtractor` protocol class mirrors `LLMProvider` pattern (decision D004 / D009). Add new extractor implementations without changing the workflow. |

**Extractor protocol design (recommended):**

```python
from abc import ABC, abstractmethod
import pymupdf

class ContentExtractor(ABC):
    """Abstract interface for binary document text extraction."""

    @abstractmethod
    def supports_mime(self, mime_type: str) -> bool:
        ...

    @abstractmethod
    def extract(self, blob: bytes) -> ContentExtractionResult:
        """Extract text and page metadata from binary blob."""
        ...

class PdfExtractor(ContentExtractor):
    def supports_mime(self, mime_type: str) -> bool:
        return mime_type in ("application/pdf",)

    def extract(self, blob: bytes) -> ContentExtractionResult:
        doc = pymupdf.open(stream=blob, filetype="pdf")
        pages: dict[int, PageExtraction] = {}
        full_text_parts: list[str] = []
        offset = 0
        for page_num, page in enumerate(doc, start=1):
            page_text = page.get_text("text")
            start_offset = offset
            end_offset = offset + len(page_text)
            pages[page_num] = PageExtraction(
                text=page_text,
                start_offset=start_offset,
                end_offset=end_offset,
            )
            full_text_parts.append(page_text)
            offset = end_offset
        return ContentExtractionResult(
            full_text="".join(full_text_parts),
            pages=pages,
        )
```

### 3.3 Multi-Chunk Document Model

**Integration type:** New `document_chunk` SurrealDB table + new `DocumentChunker` class

| Integration Point | Existing Component | How It Connects |
|---|---|---|
| **SurrealDB schema** | `document` table | NEW: `document_chunk` table (SCHEMAFULL) with `chunk_index`, `text`, `page_start`, `page_end`, `offset_start`, `offset_end`, `document` (record<document>). |
| **`document.text_content`** | Full text string | **Unchanged** — still stores the full text. Chunks are a secondary index, not a replacement. |
| **`extract_events_activity`** | Receives `text` | **Unchanged** — receives full reconstructed text from `document.text_content`. Chunks are transparent. |
| **GraphQL** | `query { document { text_content } }` | **Unchanged** — returns full text. NEW: `query { document { chunks { text, page_start, page_end } } }` for chunk-aware queries. |
| **Temporal chunks activity** | N/A | NEW: `chunk_text_activity` creates chunk list. `store_chunks_activity` persists to SurrealDB with idempotency (delete-then-recreate per-document, matching D012 pattern). |
| **Chunk re-extraction** | DELETE reprocess | When reprocessing, chunks are deleted + recreated alongside events. The `DELETE /documents/{id}/events` endpoint MUST also delete chunks (new SQL in the existing handler). |

**Document model evolution timeline:**

| Phase | `original_blob` | `text_content` | `document_chunk` table |
|---|---|---|---|
| **Before v2.0** (current) | base64 of submitted text | Submitted text | Doesn't exist |
| **v2.0 plain text** | `"minio://eth-documents/doc/{id}.txt"` | Submitted text | Chunks derived from text |
| **v2.0 PDF upload** | `"minio://eth-documents/doc/{id}.pdf"` | Extracted by PyMuPDF | Chunks derived from extracted text |
| **After v2.0** | MinIO path ref always | Text from extraction or direct | Always populated |

---

## 4. Critical Architecture Patterns

### Pattern 1: Activity Connection — Temporal Activities as Self-Contained Workers

The existing pattern (D012) is that Temporal activities connect to external services *at runtime* using environment variables, creating and closing their own connections. This is NOT about sharing the API's lifespan-managed connections.

**New activities follow the same pattern:**

```python
# workers.py — register new activities
worker = Worker(
    ...
    activities=[
        activities.extract_events_activity,      # existing
        activities.update_document_status_activity, # existing
        activities.store_extraction_results_activity, # existing
        activities.resolve_entities_activity,    # existing
        activities.store_blob_activity,          # NEW
        activities.extract_text_activity,        # NEW
        activities.chunk_text_activity,          # NEW
        activities.store_chunks_activity,        # NEW
    ],
)
```

**Connection management per activity:**

| Activity | Connects to | Connection Pattern | Replay-safe? |
|---|---|---|---|
| `store_blob_activity` | MinIO | Create `Minio()` client, use, drop | Yes (idempotent upload) |
| `extract_text_activity` | MinIO | Create `Minio()` client, use, drop | Yes (no side effects) |
| `chunk_text_activity` | None (pure function) | No connections needed | Yes (deterministic) |
| `store_chunks_activity` | SurrealDB | `get_db()` context manager | Yes (delete-then-recreate) |

### Pattern 2: Idempotency Strategy — Delete-Then-Recreate

Every activity that writes to SurrealDB follows the existing pattern (from `store_extraction_results_activity`):

1. **Delete** all existing records for this document (chunks, in this case)
2. **Create** fresh records from current result

```python
@activity.defn
async def store_chunks_activity(document_id: str, chunks: list[DocumentChunk]) -> dict:
    params = _db_params()
    doc_ref = f"document:{document_id}"
    
    async with get_db(**params) as db:
        # 1. Delete existing chunks for this document
        await db.query(
            "DELETE document_chunk WHERE document = $doc_ref",
            {"doc_ref": doc_ref},
        )
        # 2. Create all chunks
        for chunk in chunks:
            await db.create("document_chunk", {
                "chunk_index": chunk.chunk_index,
                "text": chunk.text,
                "page_start": chunk.page_start,
                "page_end": chunk.page_end,
                "offset_start": chunk.offset_start,
                "offset_end": chunk.offset_end,
                "document": doc_ref,
            })
```

### Pattern 3: Workflow Extensibility — Optional Extraction Branch

The `DocumentProcessingWorkflow` needs a conditional extraction path based on `mime_type`:

```
DocumentProcessingWorkflow.run(document_id, text=None, mime_type="text/plain")

if text is None:
    # Binary document path
    update_status("storing_blob")
    store_blob_activity(document_id)
    update_status("extracting_text")
    extraction = extract_text_activity(document_id)
    text = extraction.full_text
    # chunk and store
    chunks = chunk_text_activity(extraction)
    store_chunks_activity(document_id, chunks)
    update_document_status(document_id, "extracted")

# Shared path (unchanged)
update_document_status(document_id, "processing")
result = extract_events_activity(text)
store_extraction_results_activity(document_id, result)
resolve_entities_activity(document_id, result)
update_status("processed")
```

The **text= parameter is preserved** for backward compatibility — existing callers that submit raw text skip the extraction branch entirely.

### Pattern 4: MinIO Client Factory — Mirror of `get_db()`

Following the existing `db.py` pattern, create `storage.py`:

```python
# NEW: storage.py
import os
from minio import Minio

def _minio_params() -> dict:
    return {
        "endpoint": os.environ.get("MINIO_ENDPOINT", "minio:9000"),
        "access_key": os.environ.get("MINIO_ACCESS_KEY", "minioadmin"),
        "secret_key": os.environ.get("MINIO_SECRET_KEY", "minioadmin"),
        "secure": os.environ.get("MINIO_SECURE", "false").lower() == "true",
    }

def get_client(endpoint, access_key, secret_key, secure=False) -> Minio:
    return Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)
```

### Pattern 5: Content Extractor Registry — Plugin Architecture

Following the `LLMProvider` protocol pattern (D009, D011), create an extractor registry:

```python
# NEW: extractors.py
from abc import ABC, abstractmethod

class ExtractionResult:
    full_text: str
    pages: dict[int, PageExtraction]

class ContentExtractor(ABC):
    @abstractmethod
    def supports_mime(self, mime_type: str) -> bool: ...
    @abstractmethod
    def extract(self, blob: bytes) -> ExtractionResult: ...

class PdfExtractor(ContentExtractor):
    def supports_mime(self, mime_type: str) -> bool:
        return mime_type == "application/pdf"
    def extract(self, blob: bytes) -> ExtractionResult:
        import pymupdf
        ...

# Registry
EXTRACTORS: list[ContentExtractor] = [PdfExtractor()]

def get_extractor(mime_type: str) -> ContentExtractor:
    for ext in EXTRACTORS:
        if ext.supports_mime(mime_type):
            return ext
    raise UnsupportedFormatError(f"No extractor for {mime_type}")
```

---

## 5. Backward Compatibility and Data Migration

### Critical Decision: What Happens to Existing Documents?

**Option A: Full migration** — Backfill all existing `document` records:
- Extract base64 `original_blob`, decode, upload to MinIO
- Update `original_blob` to MinIO path
- Generate `document_chunk` records for each document

**Cost:** 15 existing documents → cheap. But if the user has many documents, this is a blocking concern.

**Option B: Lazy migration** — Existing documents remain as-is. New documents use MinIO + chunks. The `document_chunk` table and MinIO path are optional fields.

**Option C: Hybrid** — On first read/GET of an old document, trigger a migration on-the-fly. Only backfill documents that are actively queried.

**Recommendation: Option B (lazy migration).**
- The `original_blob` field stays TYPE `string` — old base64 data and new MinIO paths coexist
- Add a `blob_format` field (values: `"base64"` or `"minio"`) to distinguish
- Existing `GET /documents/{id}` continues to work unchanged
- NEW `GET /documents/{id}/chunks` returns empty for old docs (or triggers lazy migration)

### API Backward Compatibility

| Endpoint | v1 Behavior | v2 Behavior | Backward Compat |
|---|---|---|---|
| `POST /documents` | Accept `{text, filename}` | **Unchanged** — still accepts `{text, filename}` | ✅ Fully compatible |
| `POST /documents/upload` | N/A | NEW — multipart file upload returning `document_id` | N/A (new endpoint) |
| `GET /documents/{id}` | Returns `{text_content, original_blob(b64)}` | Returns `{text_content, original_blob(minio_path)}` | ⚠️ `original_blob` value format changed |
| `DELETE /documents/{id}/events` | Clears events, resets status | **Modified** — ALSO deletes `document_chunk` records | ✅ Extended but not broken |

**API breaking change mitigation:** `GET /documents/{id}` currently returns `original_blob` as base64 text. Since the API is consumed by TypeScript tests (and humans via curl), it's a private API — no external consumers to break. Still, note in changelog.

---

## 6. Modified vs New Components

### New Components

| Component | File | Type | Dependencies |
|---|---|---|---|
| MinIO Docker service | `docker-compose.yml` | Service | `minio/minio:latest` image |
| Blob storage module | `src/eth_pipeline/storage.py` | Python module | `minio` package |
| Content extractors | `src/eth_pipeline/extractors.py` | Python module | `pymupdf` package |
| Text chunker | `src/eth_pipeline/chunking.py` | Python module | `langchain-text-splitters` |
| `store_blob_activity` | `src/eth_pipeline/activities.py` | Activity (added) | `storage.py` |
| `extract_text_activity` | `src/eth_pipeline/activities.py` | Activity (added) | `extractors.py`, `storage.py` |
| `chunk_text_activity` | `src/eth_pipeline/activities.py` | Activity (added) | `chunking.py` |
| `store_chunks_activity` | `src/eth_pipeline/activities.py` | Activity (added) | SurrealDB `get_db()` |
| `POST /documents/upload` | `src/eth_pipeline/api.py` | Endpoint (added) | `storage.py` |
| Schema: `document_chunk` table | `src/eth_pipeline/schema.surql` | Schema (added) | N/A |
| MinIO bucket init script | `scripts/init_bucket.py` | Script | `minio` package |
| Integration tests (v2.0) | `tests/integration/pipeline_v2.test.ts` | Test suite | TypeScript |
| Verify script (v2.0) | `scripts/verify_v2_s01.py` | Verify script | stdlib |

### Modified Components

| Component | Change | Risk Level |
|---|---|---|
| `DocumentProcessingWorkflow` | Add conditional branch for binary docs | LOW — new branches, existing path untouched |
| `worker.py` | Register 4 new activities | LOW — additive change |
| `api.py` | Add `POST /documents/upload` | LOW — new endpoint |
| `api.py` lifepsan | Add MinIO client init | LOW — follows Temporal pattern |
| `DELETE /documents/{id}/events` | Also delete `document_chunk` records | LOW — one extra SQL query |
| `docker-compose.yml` | Add `minio` service, add to networks | LOW — standard service addition |
| `schema.surql` | Add `document_chunk` table definition | LOW — additive schema |
| `pyproject.toml` | Add `minio`, `pymupdf`, `langchain-text-splitters` deps | LOW — standard dependency add |
| `.env.example` | Add `MINIO_*` variables | LOW |

### Unchanged Components

| Component | Why Unchanged |
|---|---|
| `extract_events_activity` | Still receives full text (from document.text_content or reconstructed from chunks) |
| `store_extraction_results_activity` | Events + references — no chunk awareness needed |
| `resolve_entities_activity` | Entity resolution operates on events/references, not chunks |
| `GraphQL proxy` | No changes needed — new `document_chunk` table auto-exposed by SurrealDB GraphQL |
| `LLM provider` | Chunking is before LLM extraction — LLM never sees individual chunks |
| `Entity merge/split endpoints` | No relationship to chunks |
| Integration test helpers | New helpers for MinIO but existing helpers unchanged |

---

## 7. SurrealDB Schema Addition

```surql
-- ==========================================================================
-- Table: document_chunk
-- ==========================================================================
-- Internal: chunks are a secondary index on the document text, not a
-- replacement. This table is populated after text extraction and enables
-- chunk-aware queries (e.g., "which chunk contains this offset?").
-- Chunks are transparent to the user-facing API — GET /documents/{id}
-- still returns full text_content.
-- ==========================================================================

DEFINE TABLE document_chunk SCHEMAFULL
    COMMENT 'Text chunk derived from document text, with page provenance and offsets';

DEFINE FIELD chunk_index ON TABLE document_chunk TYPE int
    ASSERT $value >= 0
    COMMENT 'Zero-based index of this chunk within the document';

DEFINE FIELD text ON TABLE document_chunk TYPE string
    COMMENT 'Text content of this chunk';

DEFINE FIELD page_start ON TABLE document_chunk TYPE int
    ASSERT $value >= 1
    COMMENT 'First page number (1-based) that this chunk spans';

DEFINE FIELD page_end ON TABLE document_chunk TYPE int
    ASSERT $value >= 1 AND $value >= $value{page_start}
    COMMENT 'Last page number (1-based, inclusive) that this chunk spans';

DEFINE FIELD offset_start ON TABLE document_chunk TYPE int
    ASSERT $value >= 0
    COMMENT 'Character offset (0-based) where this chunk starts in document.text_content';

DEFINE FIELD offset_end ON TABLE document_chunk TYPE int
    ASSERT $value >= 0
    COMMENT 'Character offset (exclusive) where this chunk ends in document.text_content';

DEFINE FIELD document ON TABLE document_chunk TYPE record<document>
    COMMENT 'Link to the source document';
```

### Document table additions (to existing schema):

```surql
-- Add to existing document table
DEFINE FIELD blob_format ON TABLE document TYPE string
    ASSERT $value = 'base64' OR $value = 'minio' OR $value = 'none'
    DEFAULT 'base64'
    COMMENT 'Format of original_blob: base64 (legacy), minio (MinIO path ref), none (no blob)';

DEFINE FIELD chunk_count ON TABLE document TYPE int
    DEFAULT null
    COMMENT 'Number of chunks when chunked (null = not yet chunked)';
```

---

## 8. Workflow Evolution — Step-by-Step Transition

### Phase 1: Blob Storage (MinIO)
**Changes:** Docker service, `storage.py`, `store_blob_activity`, `POST /documents/upload`  
**What works:** Documents can be uploaded as files and stored in MinIO. `original_blob` gets MinIO path. Text still provided by user in `text_content`. No extraction yet.

### Phase 2: Text Extraction (PDF)
**Changes:** `extractors.py`, `PdfExtractor`, `extract_text_activity`, conditional workflow branch  
**What works:** PDF upload → PyMuPDF extraction → `text_content` populated automatically. Document enters existing pipeline with real extracted text.

### Phase 3: Smart Chunking
**Changes:** `chunking.py`, `DocumentChunker`, `chunk_text_activity`, `store_chunks_activity`, `document_chunk` schema  
**What works:** All documents (text and PDF) get chunk records. Chunks are visible via GraphQL but transparent to event extraction.

### Phase 4: Full Integration + Backfill
**Changes:** `DELETE /documents/{id}/events` extended, lazy migration for old docs  
**What works:** Everything integrated. Old documents get chunked on demand. Delete + reprocess includes chunk teardown/rebuild.

---

## 9. Error Handling Strategy

| Failure Mode | Where Caught | Recovery |
|---|---|---|
| MinIO unreachable | `store_blob_activity`, `extract_text_activity` | Temporal retry (existing policy) |
| Corrupt PDF (unreadable) | `PdfExtractor.extract()` | `ContentExtractionError` → workflow fails with descriptive message |
| Scanned PDF (no text layer) | `PdfExtractor.extract()` — PyMuPDF returns empty | Workflow fails with request for OCR setup; `status = "failed"` |
| Chunk too large (no break point) | `RecursiveCharacterTextSplitter` fallthrough to `[""]` | Hard split at `max_chars` — minimal quality degradation |
| SurrealDB chunk write failure | `store_chunks_activity` | Retry (existing Temporal policy). Replay-safe due to delete-then-recreate |
| Partial chunk write | `store_chunks_activity` — delete fails | Activity fails → workflow retries → full delete-then-recreate |

---

## 10. Anti-Patterns to Avoid

### Anti-Pattern 1: Storing Blobs in SurrealDB

**What people do:** Keep storing large binary blobs (PDFs, images) as base64 strings in `original_blob` in SurrealDB.

**Why it's wrong:** SurrealDB is a multi-model database optimized for queries and relationships, not blob storage. PDFs can be 10-100 MB each. Base64 encoding adds 33% overhead. Every GraphQL query on `document` that includes `original_blob` transfers the entire blob, even when only `text_content` is needed.

**Do this instead:** MinIO for blob storage. `original_blob` stores an S3 path reference (`"minio://bucket/doc/{id}.pdf"`). Add a `blob_format` field to distinguish old base64 from new MinIO paths.

### Anti-Pattern 2: Making Chunks Visible to Event Extraction

**What people do:** Modify `extract_events_activity` to accept chunked input, or process chunks in parallel.

**Why it's wrong:** Chunks are an internal implementation detail of the document model. They exist for provenance, storage optimization, and future RAG-style retrieval. The LLM extraction pipeline should receive the full document text, unchanged. Parallel chunk processing for event extraction is premature optimization.

**Do this instead:** Reconstruct the full text from chunks (or use `document.text_content` directly) and pass it to `extract_events_activity` identically to how it works today. The workflow gets `text` — it does not know about chunks.

### Anti-Pattern 3: Async MinIO Client Wrapper

**What people do:** Wrap `minio.Minio` in `asyncio` for "consistency" with the async FastAPI layer.

**Why it's wrong:** Temporal activities run in a thread pool — synchronous I/O is the expected pattern. In FastAPI endpoints, `asyncio.to_thread()` is appropriate for the rare case of synchronous MinIO calls from async handlers. A full async abstraction layer adds complexity with no benefit.

**Do this instead:** Use `minio.Minio` synchronously in Temporal activities. In FastAPI lifespan and upload endpoints, wrap MinIO calls in `asyncio.to_thread()` if needed. Keep it simple.

### Anti-Pattern 4: Global MinIO Client Singleton

**What people do:** Create one `Minio()` client at module level and share it across activities.

**Why it's wrong:** Temporal replay can re-execute activities from any point. A shared client introduces implicit state: connection pool state, credential refreshes, etc. This is the same reason SurrealDB connections are created per-activity (D012).

**Do this instead:** Create `Minio()` client instances per-activity call, using environment variables for config. The client creation is lightweight (no handshake — Lazy bucket/region resolution).

---

## 11. Scaling Considerations

| Scale | Blob Storage | Text Extraction | Chunking |
|---|---|---|---|
| **10-100 docs/day** | Single MinIO container | Single Temporal worker, sequential extraction | Single-threaded chunking is fine |
| **100-1000 docs/day** | MinIO with versioning | Temporal retry absorbs transient PDF failures | Main bottleneck is LLM extraction (OpenRouter API calls), not chunking |
| **1000+ docs/day** | MinIO cluster (distributed mode) | Parallel PDF extraction via Temporal activity worker scaling | Consider caching chunk results for identical documents |
| **Scaling ceiling** | MinIO scales to PB — no concern | PDF extraction is embarrassingly parallel (one-per-document workflow) | RecursiveCharacterTextSplitter is O(n) in text length |

**First bottleneck:** LLM extraction OpenRouter API calls (rate limits, cost). Chunking and MinIO are cheap by comparison.  
**Second bottleneck:** MinIO disk I/O on single-node Docker deployment. Mitigation: SSD-backed volume for `minio_data`.

---

## 12. Build Order Recommendation

Based on dependency structure:

```
Phase 1: MinIO Infrastructure + Blob Upload
  ├── docker-compose.yml (add minio service)
  ├── .env.example (add MINIO_* vars)
  ├── scripts/init_bucket.py (bucket creation)
  ├── src/eth_pipeline/storage.py (MinIO client factory)
  ├── activities.py: store_blob_activity
  ├── api.py: POST /documents/upload endpoint
  └── schema.surql: blob_format field on document
  └── Integration tests: file upload → MinIO stores blob

Phase 2: PDF Text Extraction
  ├── src/eth_pipeline/extractors.py (ContentExtractor protocol + PdfExtractor)
  ├── src/eth_pipeline/chunking.py (DocumentChunker + DocumentChunk model)
  ├── schema.surql: document_chunk table
  ├── activities.py: extract_text_activity
  ├── activities.py: chunk_text_activity
  ├── activities.py: store_chunks_activity
  ├── workflows.py: conditional extraction branch
  └── Integration tests: PDF upload → text extracted → chunks stored

Phase 3: Full Workflow Integration
  ├── workflows.py: integrate new branch into DocumentProcessingWorkflow
  ├── worker.py: register all new activities
  ├── api.py: extend DELETE /documents/{id}/events to clear chunks
  ├── Lazy migration for old base64 documents
  └── Full pipeline tests: upload → extract → chunk → LLM → events → resolve
```

**Key dependency:** Phase 1 must precede Phase 2 (MinIO must exist before extraction can read blobs). Phase 2 can be built and tested independently of the LLM pipeline (extract text → chunk → verify chunks).

---

## Sources

- **MinIO Python SDK v7.2.20**: PyPI — https://pypi.org/project/minio/ (HIGH confidence)
- **PyMuPDF v1.27.2**: PyPI — https://pypi.org/project/PyMuPDF/ (HIGH confidence)
- **langchain-text-splitters v1.1.2**: PyPI — https://pypi.org/project/langchain-text-splitters/ (HIGH confidence)
- **Existing codebase**: `src/eth_pipeline/` — activities.py, workflows.py, api.py, db.py, schema.surql (VERIFIED)
- **Existing patterns**: D012 (per-activity connections), D016 (per-type batching), D009 (protocol-based abstraction) — from `.gsd/DECISIONS.md` (VERIFIED)
- **MinIO Docker image**: Docker Hub — https://hub.docker.com/r/minio/minio (HIGH confidence)

---

*Architecture research for: eth-pipeline v2.0 Blob & Chunk Pipeline*
*Researched: 2026-05-31*
