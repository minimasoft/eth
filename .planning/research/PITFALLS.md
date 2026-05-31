# Domain Pitfalls — Blob & Chunk Pipeline

**Domain:** Document blob storage, PDF text extraction, smart text chunking
**Researched:** 2026-05-31

## Critical Pitfalls

### Pitfall 1: Chunk Visibility Leak — Making Chunks Visible to Event Extraction

**What goes wrong:** Someone modifies `extract_events_activity` to accept chunked input (list of chunks instead of full text), or adds parallel-per-chunk LLM extraction.

**Why it happens:** It seems intuitive — "if the document is chunked, extract events per chunk for parallelism." The developer thinks they're being clever.

**Consequences:**
- Chunk boundary artifacts: events split across chunks lose context (a sentence ending in chunk N, its city reference starting in chunk N+1)
- 10-100x more LLM calls (one per chunk instead of one per document)
- Stitching complexity: events from chunk A might duplicate events from chunk B at the boundary
- Temporal workflow complexity: managing fan-out/fan-in for chunk parallelism
- Breaks Temporal replay: chunk parallelism introduces non-determinism risks

**Prevention:**
- Architectural rule: **chunks are a secondary index on document text, never an input to LLM extraction**
- Reconstruct full text from `document.text_content` before passing to `extract_events_activity`
- The workflow IF statement checks `text is None` (binary) vs `text is provided` (direct) — not chunk-based

**Detection:** If you see `extract_events_activity` accepting `list[dict]` instead of `str`, or `for chunk in chunks:` in the workflow, flag it immediately.

### Pitfall 2: Blob in SurrealDB Perpetuation

**What goes wrong:** The team keeps storing binary blobs as base64 strings in SurrealDB even after MinIO is available, because "it works" and "we can do both."

**Why it happens:** The existing `original_blob` field stores base64 text. Adding MinIO means either migrating or supporting both. Supporting both is less work initially.

**Consequences:**
- SurrealDB fills up with binary data (base64 = +33% overhead)
- GraphQL queries on `document` that include `original_blob` transfer entire PDF payloads
- No versioning or object lifecycle management (MinIO features)
- Performance degradation as blob storage grows

**Prevention:**
- Make `blob_format` a mandatory field in the API (`POST /documents/upload` always sets `blob_format = "minio"`)
- Always upload blob to MinIO before writing SurrealDB document record
- For old documents, migrate on access (lazy migration) but stop accepting new base64 blobs

**Detection:** Check `SELECT count() FROM document WHERE blob_format = 'base64'` — if growing, the API is accepting base64 alongside MinIO.

### Pitfall 3: PyMuPDF AGPL Licensing Surprise

**What goes wrong:** The project ships as proprietary software and the legal team discovers PyMuPDF is AGPL-licensed, requiring either open-sourcing the whole product or buying a commercial license from Artifex.

**Why it happens:** PyMuPDF appears as a standard PyPI package — its license isn't visible during development. AGPL is more restrictive than Apache 2.0 (the project's current license).

**Consequences:**
- Legal blockers before release
- Last-minute switch to `pypdf` (BSD-3, 10-50x slower) requiring re-verification
- Schedule impact if commercial license negotiation is needed

**Prevention:**
- Make `pypdf` the primary fallback: `try: import pymupdf; except ImportError: import ... as pypdf_adapter`
- Document the license constraint in `pyproject.toml` classifiers and a comment in `extractors.py`
- Add a deployment option `USE_PYPDF=true` env var that forces the BSD-licensed code path

**Detection:** Before any release that includes PyMuPDF, verify license compatibility with the target distribution model. Run `pip show pymupdf` and check License field.

### Pitfall 4: DELETE + Reprocess Leaves Orphaned Chunks

**What goes wrong:** The existing `DELETE /documents/{id}/events` endpoint clears events and references but does NOT delete `document_chunk` records. When the document is reprocessed, chunks from the previous run plus chunks from the new run coexist.

**Why it happens:** The existing endpoint was written before chunks existed. Adding a new endpoint for chunk management is easy to forget during implementation.

**Consequences:**
- Duplicate chunk records (same `chunk_index` but different `created_at`)
- Inconsistent data: `document_chunk` shows N chunks, but `text_content` was reprocessed to different text
- Temporal replay safety violated — replay creates new chunks without clearing old ones

**Prevention:**
- `DELETE /documents/{id}/events` MUST also delete `document_chunk WHERE document = $doc_ref`
- Same principle for `store_chunks_activity`: delete-then-recreate pattern
- Verification test: reprocess a document, verify `document_chunk` count equals new chunk count, not old + new

**Detection:** `SELECT count() as cnt, document FROM document_chunk GROUP BY document WHERE cnt > expected` — requires knowing expected chunk count per document.

## Moderate Pitfalls

### Pitfall 1: Mixed Document Storage Formats in the Same Query

**What goes wrong:** A query or activity assumes `original_blob` contains base64 text (legacy documents), reads it, and fails because it's now a MinIO path string.

**Where it happens:** `resolve_entities_activity` currently reads `text_content` (not `original_blob`), so this doesn't affect existing code. But NEW code that reads `original_blob` (e.g., a bulk-export script) must handle both formats.

**Prevention:** Always check `blob_format` before reading `original_blob`. Provide a helper function:

```python
async def get_blob_path(db, document_id: str) -> tuple[str, bytes] | None:
    """Return (blob_format, raw_bytes) for a document's original blob."""
    result = await db.query("SELECT original_blob, blob_format FROM document WHERE id = $id", ...)
    record = result[0]
    fmt = record.get("blob_format", "base64")
    blob_raw = record["original_blob"]
    if fmt == "minio":
        path = blob_raw  # "minio://bucket/doc/id.pdf"
        # parse and fetch from MinIO
    else:
        return "base64", base64.b64decode(blob_raw)
```

### Pitfall 2: MinIO Port Conflict on Docker Host

**What goes wrong:** Port 9000 is already in use on the developer's machine (common for other S3-compatible services, Jenkins, etc.).

**Consequences:** Docker Compose fails to start MinIO on `localhost:9000`. Developer wastes time debugging infrastructure instead of building.

**Prevention:** Document the port mapping in `docker-compose.yml` with a comment about conflict: "Change 9000:9000 to 9002:9000 if port 9000 conflicts." Add `MINIO_PORT` env var.

### Pitfall 3: Chunk Size Mismatch with LLM Token Limits

**What goes wrong:** The chunker targets ~128k *characters*, but LLM context windows are measured in *tokens* (~4 chars = 1 token for English, ~2 chars = 1 token for Spanish). A 128k-character chunk might be 64k tokens — exceeding some model limits.

**Consequences:** If someone later tries to feed chunks directly to an LLM (against the chunk-transparency rule), they hit token limits.

**Prevention:** Document the character-to-token distinction. The 128k-char limit is chosen because:
- A GPT-4o-mini 128k-token window can hold ~250k characters (~2 chars/token for Spanish)
- A full 128k-char chunk is well within most model limits
- If fine-tuning chunk size later, use tokens (via `tiktoken`), not characters

## Minor Pitfalls

### Pitfall 1: MinIO Bucket Not Created on Startup

**What happens:** MinIO container starts but the `eth-documents` bucket doesn't exist. First `put_object` call fails with `S3Error: The specified bucket does not exist`.

**Prevention:** Write `scripts/init_bucket.py` that creates the bucket on startup (same pattern as `init_schema.py` for SurrealDB). Run it as a Docker Compose init container that depends on `minio` being healthy.

### Pitfall 2: `page.get_text("text")` Returns Empty for Some PDFs

**What happens:** Some PDFs (created by certain scanners or generators) have text stored in unexpected ways. `page.get_text()` returns empty string. The document is silently processed without content.

**Prevention:** In `extract_text_activity`, check if `full_text` is empty after extraction. If so, log the error and update `status = "failed"` with message: "PDF has no extractable text layer — may be a scanned document."

### Pitfall 3: Unicode Encoding Issues with Spanish Text

**What happens:** Spanish legal text uses accented characters (é, í, ó, ú, ñ), quotation marks («»), and special punctuation. Chunking splits at `.` but Spanish journalism sometimes uses `;` as sentence separators.

**Prevention:** Ensure `RecursiveCharacterTextSplitter` separator list includes `\n\n`, `\n`, `.`, `!`, `?`, `;` in that order. All are UTF-8-safe. PyMuPDF extracts text as UTF-8 by default.

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|---|---|---|
| Phase 1: MinIO setup | Port conflicts with host | Document port conflict resolution in Compose comments |
| Phase 1: Blob upload | Storing blob in MinIO AND in SurrealDB (double storage) | API endpoint uploads to MinIO first, stores path ref only |
| Phase 2: PDF extraction | AGPL license surprise | Document license constraint, provide `pypdf` fallback |
| Phase 2: Chunking | Chunk transparency rule violated | Code review gate: "does this make chunks visible to LLM?" |
| Phase 3: Workflow integration | DELETE reprocess misses chunks | Integration test verifies chunk count after reprocess cycle |
| Phase 3: Lazy migration | Legacy base64 reads from old code crash | `get_blob_path()` helper handles both formats defensively |

## Sources

- **AGPL licensing**: PyMuPDF README — https://github.com/pymupdf/PyMuPDF (HIGH confidence — official repository)
- **MinIO bucket creation**: MinIO documentation — buckets are NOT auto-created (MEDIUM confidence — minio-py example code shows explicit `bucket_exists()` + `make_bucket()`)
- **Chunk transparency**: Architecture decision derived from existing D012/D016 patterns and LLM pipeline design (HIGH confidence — applies existing patterns)
- **DELETE + reprocess safety**: Existing `store_extraction_results_activity` delete-then-recreate pattern verified in codebase (HIGH confidence — VERIFIED in source)
