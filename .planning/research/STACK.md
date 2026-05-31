# Technology Stack — Blob & Chunk Pipeline Additions

**Project:** eth-pipeline (Espacio Tiempo Humanos)
**Researched:** 2026-05-31
**Mode:** Ecosystem — New stack additions for MinIO/S3 blob storage, PDF text extraction, and smart text chunking

## Stack Additions Summary

| Area | Library | Version | Why This One |
|------|---------|---------|-------------|
| S3 Blob Storage | `minio` (minio-py) | >=7.2.20 | Native MinIO SDK, light deps, purpose-built |
| PDF Text Extraction | `PyMuPDF` | >=1.27.2 | 10-50x faster than pure-Python alternatives, page-level metadata |
| Text Chunking | `langchain-text-splitters` | >=1.1.2 | Battle-tested RecursiveCharacterTextSplitter, tiny footprint (35.9 kB) |
| MinIO Server (Docker) | `minio/minio` | latest | Official container, S3-compatible, includes Console UI |

---

## 1. MinIO / S3 Blob Storage

### Recommended: `minio` >= 7.2.20

**Purpose:** Upload PDF files, store source document blobs, retrieve for processing.

Install: `pip install minio`

**Why `minio` over `boto3`:**

| Criterion | `minio` 7.2.20 | `boto3` 1.43.18 |
|-----------|----------------|-----------------|
| Footprint | Pure SDK for MinIO (Python >=3.9) | Full AWS SDK + botocore + s3transfer (Python >=3.10) |
| Dependency tree | Minimal (1-2 transitive deps) | Heavy — pulls in urllib3, botocore, s3transfer, jmespath |
| API surface | `Minio.put_object()` / `Minio.get_object()` | `s3_client.put_object()` — need S3 credentials chain |
| Purpose-fit | Built by MinIO, Inc. for MinIO | General AWS SDK, designed for thousands of AWS services |
| Async support | `minio` has sync API only — use `asyncio.to_thread()` or wrap | `aioboto3` needed for async |

Since this project uses MinIO (not AWS S3) and the SDK is called from Temporal activities (sync is fine — Temporal runs activities in a thread pool), `minio` is the right choice. No AWS credential chain complexity, no bloated dependency tree.

**Integration pattern:**
```python
from minio import Minio

client = Minio(
    endpoint="minio:9000",
    access_key="minioadmin",
    secret_key="minioadmin",
    secure=False,  # local dev
)

# Upload
client.put_object("eth-documents", f"{doc_id}.pdf", file_stream, length=size)

# Download
response = client.get_object("eth-documents", f"{doc_id}.pdf")
content = response.read()
```

### Docker Image: `minio/minio:latest`

**Purpose:** S3-compatible object storage server for source document blobs.

**Why MinIO over filesystem:**
- Proper S3 API for future migration to cloud
- Built-in web Console UI (port 9001) for manual inspection
- Versioning support for document provenance
- No shared filesystem volume issues in Docker Compose

**Ports:** 9000 (S3 API), 9001 (Web Console)

---

## 2. PDF Text Extraction

### Recommended: `PyMuPDF` >= 1.27.2 (import as `pymupdf`)

**Purpose:** Extract text from PDF documents with page-level metadata for provenance tracking.

Install: `pip install pymupdf`

**Why `PyMuPDF` over alternatives:**

| Criterion | `PyMuPDF` 1.27.2 | `pypdf` 6.12.2 | `pdfminer.six` 20260107 |
|-----------|------------------|----------------|------------------------|
| Engine | C-based (MuPDF) | Pure Python | Pure Python |
| Speed | 10-50x faster | Baseline | ~2x slower than pypdf |
| Page metadata | `get_text("dict")` returns blocks/spans with bbox, font, size | `page.extract_text()` — text only | `LTPage` object — detailed but complex API |
| License | AGPL (or commercial) | BSD-3-Clause | MIT |
| Dependencies | Zero (ships MuPDF binary) | Zero | Zero |
| Python version | >=3.10 | >=3.9 | >=3.10 |

**Why `PyMuPDF` wins for this project:**

1. **Temporal activity performance** — PDF extraction runs inside a Temporal activity. At 10-50x the speed of pure-Python alternatives, `PyMuPDF` keeps activity duration low, which directly impacts pipeline throughput and retry economics.

2. **Page provenance** — `page.get_text("dict")` returns structured blocks with bounding boxes and page numbers. This is the foundation for "page-provenance" tracking in chunks. `pypdf`'s `extract_text()` gives page-level text but no position metadata.

3. **LLM pipeline fit** — `PyMuPDF4LLM` (companion package) provides native Markdown output with table extraction, available if needed later.

4. **Scanned PDF support** — Built-in Tesseract integration for OCR fallback on scanned documents.

**License note:** `PyMuPDF` is AGPL. This is fine for open-source / internal use. If this product ships as proprietary software, a commercial license from Artifex is required. If that's a blocker, fallback to `pypdf >= 6.12.2` (BSD-3-Clause, pure Python, `PdfReader("file.pdf").pages[i].extract_text()`).

**Usage pattern for this project:**
```python
import pymupdf

doc = pymupdf.open(blob_bytes)  # from MinIO get_object()
pages_text: dict[int, str] = {}
for page_num, page in enumerate(doc, start=1):
    pages_text[page_num] = page.get_text("text")

# For chunking with page metadata:
pages_blocks: dict[int, list[dict]] = {}
for page_num, page in enumerate(doc, start=1):
    blocks = page.get_text("dict")["blocks"]
    pages_blocks[page_num] = blocks
```

---

## 3. Text Chunking

### Recommended: `langchain-text-splitters` >= 1.1.2 + custom wrapper

**Purpose:** Split extracted text into ~128k-character chunks at punctuation boundaries, preserving page provenance and offset tracking.

Install: `pip install langchain-text-splitters`

**Why not build fully custom:**

The `RecursiveCharacterTextSplitter` from `langchain-text-splitters` implements exactly the algorithm needed:
1. Prioritized separator list (`["\n\n", "\n", ".", "!", "?", ";", " ", ""]`)
2. Tries to split at the highest-priority separator first
3. Falls back to lower-priority separators if chunks are still too large
4. Handles edge cases: empty text, very long words with no separators, overlap windows

This is non-trivial to get right. The package is 35.9 kB standalone — no full LangChain dependency.

**What the custom wrapper (`DocumentChunker`) adds:**

The chunker wraps `RecursiveCharacterTextSplitter` and adds:
1. **Page provenance mapping** — Given per-page text from PyMuPDF, tracks which pages each chunk spans
2. **Offset tracking** — `offset_start` and `offset_end` relative to the full document text
3. **Page boundary awareness** — Prefers to split at page boundaries when possible (aligns with document structure)

**Chunker interface:**
```python
class DocumentChunk(BaseModel):
    chunk_index: int           # 0-based
    text: str                  # chunk content
    page_start: int            # first page number (1-based)
    page_end: int              # last page number (1-based, inclusive)
    offset_start: int          # character offset from document start
    offset_end: int            # character offset from document start (exclusive)

class DocumentChunker:
    def __init__(self, max_chars: int = 128_000, overlap: int = 0):
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=max_chars,
            chunk_overlap=overlap,
            separators=["\n\n", "\n", ".", "!", "?", ";", " ", ""],
            length_function=len,
        )

    def chunk(self, full_text: str, page_offsets: dict[int, tuple[int, int]]) -> list[DocumentChunk]:
        """Split full_text into chunks, using page_offsets for provenance."""
        ...
```

**Why not `langchain` full package:**
- `langchain` v0.3+ pulls in 30+ dependencies (langchain-core, etc.)
- We only need the text splitter — `langchain-text-splitters` is the standalone extraction
- The chunker output model (`DocumentChunk`) is application-specific, not from any framework

---

## 4. Docker Compose — MinIO Service

### New service: `minio`

```yaml
minio:
  image: minio/minio:latest
  command: server /data --console-address ":9001"
  ports:
    - 9000:9000   # S3 API
    - 9001:9001   # Web Console
  volumes:
    - minio_data:/data
  environment:
    MINIO_ROOT_USER: ${MINIO_ROOT_USER:-minioadmin}
    MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD:-minioadmin}
  healthcheck:
    test: ["CMD", "mc", "ready", "local"]
    interval: 5s
    retries: 6
    start_period: 15s
    timeout: 5s
  restart: unless-stopped
  networks:
    - eth-pipeline

volumes:
  minio_data: null
```

The `mc ready local` healthcheck requires the MinIO Client (`mc`) to be available. Alternative: use `curl -f http://localhost:9000/minio/health/live`.

### New environment variables (`.env.example` additions):

```
# MinIO / S3 Blob Storage
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=eth-documents
MINIO_SECURE=false
```

**Bucket creation:** MinIO does not auto-create buckets. Add a `schema-init`-like init script that creates `eth-documents` bucket on startup, or add bucket creation as part of the first document upload activity.

---

## 5. What Does NOT Change

| Existing Component | Change Required | Rationale |
|-------------------|----------------|-----------|
| Temporal workflows | New activities only | Add `extract_text_activity`, `chunk_text_activity` — don't modify existing `extract_events_activity` |
| FastAPI (`api.py`) | New endpoint `POST /documents/upload` | Accepts multipart file upload instead of raw text. Existing `POST /documents` stays for backward compat |
| SurrealDB schema | New table `document_chunk` | Chunks stored as SurrealDB records linked to document. `original_blob` field repurposed to store MinIO object path |
| Temporal worker (`worker.py`) | Register new activities | Import new activities, add to worker |
| TypeScript tests | New test suite | Test upload + chunk flow alongside existing document flow |
| OpenRouter LLM layer | No change | `extract_events_activity` still receives full text (reconstructed from chunks) |

---

## 6. Key Design Decisions

### D001: MinIO SDK — Prefer `minio` over `boto3`
**Why:** Smaller dependency tree, simpler API, purpose-built for MinIO. The project uses MinIO, not AWS S3.

### D002: PDF extraction — Prefer `PyMuPDF` over `pypdf`
**Why:** 10-50x speed advantage critical for Temporal activity performance. Page-level metadata essential for provenance tracking. Zero native dependencies (ships MuPDF binary).

### D003: Chunking — Prefer `langchain-text-splitters` + custom wrapper
**Why:** RecursiveCharacterTextSplitter is battle-tested for punctuation-aware splitting. Wrapper adds page-provenance and offset tracking without reinventing the split logic.

### D004: Chunks as SurrealDB records, not separate storage
**Why:** Chunks are internal to the document model. Storing them as SurrealDB records linked to the document enables SQL queries across chunks, GraphQL access, and keeps the data model unified. The full text is reconstructed by concatenating chunks in `chunk_index` order.

### D005: No chunk-level Temporal workflow
**Why:** The current workflow processes one document at a time. Chunking is an internal implementation detail — the workflow receives `text` (reconstructed from chunks) identically to how it works today. No parallel chunk processing needed at this scale.

---

## Sources

- **minio-py v7.2.20**: PyPI — https://pypi.org/project/minio/ (HIGH confidence)
- **PyMuPDF v1.27.2.3**: PyPI — https://pypi.org/project/PyMuPDF/ (HIGH confidence)
- **pypdf v6.12.2**: PyPI — https://pypi.org/project/pypdf/ (HIGH confidence)
- **pdfminer.six 20260107**: PyPI — https://pypi.org/project/pdfminer.six/ (HIGH confidence)
- **langchain-text-splitters v1.1.2**: PyPI — https://pypi.org/project/langchain-text-splitters/ (HIGH confidence)
- **MinIO Docker image**: Docker Hub — https://hub.docker.com/r/minio/minio (HIGH confidence)
- **MinIO container docs**: https://min.io/docs/minio/container/index.html (MEDIUM confidence — documentation page, not release artifact)
