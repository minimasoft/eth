# Technology Stack — v4.0 Pipeline Quality & Entity Resolution

**Project:** eth-pipeline (Espacio Tiempo Humanos)
**Researched:** 2026-06-03
**Mode:** Ecosystem — Reference offsets, structured event entities, search-first entity resolution, per-document processing logs
**Confidence:** HIGH

## Stack Additions Summary — v4.0

| Area | Recommendation | Version | Rationale |
|------|---------------|---------|-----------|
| Reference offset tracking | Existing `span_start`/`span_end` + new `page_number` field | — | `ExtractionResult.page_offsets` already available; compute page from offset range |
| Event canonical entity type | Add `"event"` to `entity_type` enum in `canonical_entity` | — | Existing unified entity model; no new table needed |
| SurrealDB entity search | `WHERE name CONTAINS ...` + SurrealQL `string::contains()` | SurrealDB >=3.0 | No external search infra needed; string functions are sufficient at this scale |
| SurrealDB full-text search (future) | `DEFINE ANALYZER` + `DEFINE INDEX ... FULLTEXT` | SurrealDB >=3.0 | BM25 scoring, multi-language support — defer until search volume requires it |
| Per-document processing log | New SurrealDB table `processing_log` + dedicated activity `write_processing_log_activity` | — | Keeps logs in same DB as data; Temporal replay-safe via idempotent DELETE+INSERT |
| Python structured logging | Stdlib `logging` with JSON-formatted log entries | Python >=3.10 | Already used; extend with structured dict messages, no new dependency needed |
| Temporal error accumulation | Warnings accumulated in activity result dicts + application-level log tables | Temporal Python SDK >=1.28 | `ApplicationError(BENIGN)` exists but is for errors, not warnings; return warnings in result |

---

## 1. Reference Offsets (Character + Page)

### Current State
The `reference` table and `EVENT_EXTRACTION_SCHEMA` already have `span_start` and `span_end` (character offsets, 0-based, exclusive end). `ExtractionResult.page_offsets` is already computed by `PdfExtractor` and available in the workflow.

### v4.0: Add `page_number` to references

**Schema change:** Add `page_number` field (integer, nullable, 1-based) to the `reference` table.

**Computation:** Given `page_offsets = [0, 523, 1047, ...]` and a reference with `span_start`/`span_end`, determine the page by binary search:

```python
def span_to_page(span_start: int, span_end: int, page_offsets: list[int]) -> int:
    """Return 1-based page number for a character span.

    Parameters
    ----------
    span_start: 0-based character offset where span begins.
    span_end: 0-based exclusive character offset where span ends.
    page_offsets: Cumulative offsets list, where page_offsets[i] is the
        character offset of page i (0-based page index).

    Returns
    -------
    int: 1-based page number (last page if span straddles a boundary).
    """
    for page_idx in range(len(page_offsets) - 1):
        if span_start < page_offsets[page_idx + 1]:
            return page_idx + 1
    return len(page_offsets) - 1  # fallback to last page
```

**Why not store page_number from the LLM:** The LLM already outputs `span_start`/`span_end`. Computing `page_number` from `page_offsets` is deterministic and avoids LLM hallucination risk. This is a pure post-processing step added to `store_extraction_results_activity`.

**LLM schema change:** No change needed to `EVENT_EXTRACTION_SCHEMA` — keep `span_start`/`span_end` as they are. The `page_number` is derived server-side.

### Sources

- Current `extractors.py` `ExtractionResult.page_offsets` — already computed (HIGH confidence)
- Current `llm.py` `EVENT_EXTRACTION_SCHEMA` — already has `span_start`/`span_end` (HIGH confidence)
- Current `activities.py` `store_extraction_results_activity` — creates references with `ss`/`se` from LLM output (HIGH confidence)

---

## 2. Structured Event Objects as Canonical Entities

### Current State
The `canonical_entity` table uses a unified model: `entity_type` enum (currently `place`, `person`, `object`, and `tiempo` which is skipped during resolution), `name` string, `properties` flexible JSON.

Events are stored as flat records in the `event` table with `que_paso`, `espacio`, `tiempo`, `humanos`, `objetos` as flat text fields.

### v4.0: Add `"event"` to `canonical_entity.entity_type` enum

**Schema change:** Add `"event"` to the `entity_type` enum on `canonical_entity`. The `properties` JSON stores structured event data:

```json
{
  "que_paso": "La parte demandada fue notificada",
  "time": "15 de enero de 2024",
  "place": "Juzgado de Primera Instancia",
  "participants": ["Juan Pérez", "María García"],
  "objects": ["notificación judicial"],
  "source_document": "document:abc123"
}
```

**Why this works:** The unified `canonical_entity` model already supports:
- `superseded_by` for soft-delete / merge (already in M002)
- `split_from` for provenance tracking (already in M002)
- `properties` flexible JSON for structured event fields
- Graph edges via `RELATE` to link events to place/person/object entities

**How to use RELATE for event–entity links:**

```surql
-- Link an event entity to the place it references
RELATE canonical_entity:event001->occurs_at->canonical_entity:place001
  SET confidence = 0.95, source_reference = reference:abc

-- Link an event entity to participants
RELATE canonical_entity:event001->involves->canonical_entity:person001
  SET role = "demandante", confidence = 0.9

-- Traverse: find all events for a person
SELECT ->involves<-canonical_entity FROM canonical_entity:person001
```

**Integration with resolution activity:** Modify `ENTITIY_RESOLUTION_SCHEMA` and `resolve_entities_activity` to handle the `"event"` entity type. Unlike skip-types (tiempo), events should be resolved via LLM just like place/person/object — but with a different prompt that extracts structured time/place/participants/objects fields.

### Sources

- Current `canonical_entity` schema: unified table with `entity_type` enum, `properties` JSON, `superseded_by` (HIGH confidence — code in `activities.py` and `PROJECT.md`)
- SurrealDB `RELATE` statement: https://surrealdb.com/docs/surrealql/statements/relate (HIGH confidence)

---

## 3. Search-First Entity Resolution

### Current State
`resolve_entities_activity` queries ALL existing canonical entities of a type and sends them all to the LLM for batch matching. This works now because entity counts are low, but doesn't scale and wastes LLM context on irrelevant entities.

### v4.0 Search-First: Query existing entities by name/type during extraction

**Core pattern:** Before `extract_events_activity` runs, query existing canonical entities and provide them as context to the LLM. The LLM then decides whether to match or create.

**SurrealDB query patterns for entity search:**

| Search Type | SurrealQL | Use Case | Performance |
|-------------|-----------|----------|-------------|
| Exact name match | `SELECT * FROM canonical_entity WHERE entity_type = $type AND name = $name` | Known entity | Indexed, fast |
| Case-insensitive | `SELECT * FROM canonical_entity WHERE entity_type = $type AND name ~* $name` | User input | Table scan |
| Contains match | `SELECT * FROM canonical_entity WHERE entity_type = $type AND name CONTAINS $keyword` | Partial name match | Table scan |
| String function | `SELECT * FROM canonical_entity WHERE entity_type = $type AND string::contains(name, $keyword)` | Explicit substring | Table scan |
| Full-text (indexed) | `SELECT * FROM canonical_entity WHERE name @@ "search term"` | Fuzzy/BM25 | Indexed, fast |

**Recommendation for v4.0:** Use `WHERE name CONTAINS $keyword` for the initial implementation. It's simple, readable, and sufficient at current scale. Add full-text search as a future optimization.

**Integration into extraction workflow:**

The current sequential flow is:
1. `extract_events_activity` → returns events with references
2. `store_extraction_results_activity` → persists events and references
3. `resolve_entities_activity` → resolves references against existing entities

For search-first, inject step 1a: query existing entities and pass them to the LLM as context:

```
Modified extract_events_activity flow:
1. Query existing canonical entities (all types or by type)
2. Build LLM prompt with existing entities as candidates
3. LLM extracts events AND links references to existing entities inline
4. Return events with pre-resolved canonical_entity links
```

**LLM prompt pattern for search-first extraction:**

```python
# In the system prompt for extract_events:
(
    "Además de extraer eventos, tu tarea incluye vincular cada referencia "
    "a entidades canónicas existentes cuando sea posible. "
    "Se te proporciona una lista de entidades existentes (lugares, personas, objetos, eventos).\n\n"
    "Para cada referencia en el evento:\n"
    "1. Si la referencia coincide claramente con una entidad existente, "
    "incluye el campo 'matched_entity_id' con el ID de esa entidad.\n"
    "2. Si no coincide con ninguna entidad existente, deja 'matched_entity_id' como null.\n"
    "3. Describe brevemente la referencia en 'reference_context' para ayudar "
    "a la resolución posterior.\n\n"
    "ENTIDADES EXISTENTES:\n"
    f"{json.dumps(existing_entities, ensure_ascii=False, indent=2)}"
)
```

**Schema change to `EVENT_EXTRACTION_SCHEMA`:**

```json
{
  "reference_type": {"type": "string", "enum": ["espacio", "tiempo", "humanos", "objetos"]},
  "verbatim_text": {"type": "string"},
  "span_start": {"type": "integer"},
  "span_end": {"type": "integer"},
  "matched_entity_id": {
    "type": "string",
    "description": "ID of matched canonical entity, or null if new"
  },
  "reference_context": {
    "type": "string",
    "description": "Brief context describing the reference (e.g. 'juzgado where the case was filed')"
  }
}
```

Add `matched_entity_id` as optional (not in `required` array) so existing extraction behavior is preserved when no entities exist yet.

### Sources

- SurrealDB `CONTAINS` operator: https://surrealdb.com/docs/surrealql/statements/select (HIGH confidence — documented in WHERE clause section)
- SurrealDB `string::contains()` function: https://surrealdb.com/docs/surrealql/functions/database-functions/string (MEDIUM confidence — docs blocked by SPA redirect, confirmed via Context7)
- SurrealDB full-text `DEFINE ANALYZER`: https://surrealdb.com/docs/surrealql/statements/define/analyzer (HIGH confidence — fetched successfully)
- SurrealDB full-text `@@` operator: documented in hybrid RAG examples on surrealdb.com (HIGH confidence)

---

## 4. Per-Document Processing Log

### Current State
Processing state is tracked via document status (`processing`, `extracting_blob`, `extracting_text`, `processed`, `failed`) and a single `error_message` field. There is no per-step audit trail or warning accumulation.

### v4.0: New `processing_log` Table

**Schema:**

```surql
DEFINE TABLE processing_log SCHEMAFULL;

DEFINE FIELD document ON processing_log TYPE record<document>;
DEFINE FIELD step ON processing_log TYPE string;
DEFINE FIELD level ON processing_log TYPE string
  ASSERT $value IN ["info", "warning", "error"];
DEFINE FIELD message ON processing_log TYPE string;
DEFINE FIELD details ON processing_log TYPE option<object>;
DEFINE FIELD created_at ON processing_log TYPE datetime
  DEFAULT time::now();

DEFINE INDEX log_document_idx ON processing_log FIELDS document;
```

**Activity pattern: `write_processing_log_activity`**

```python
@activity.defn
async def write_processing_log_activity(
    document_id: str,
    step: str,
    level: str,  # "info" | "warning" | "error"
    message: str,
    details: dict | None = None,
) -> dict:
```

**Replay-safe integration in workflow:**

```python
@workflow.run
async def run(self, document_id: str) -> dict:
    # Accumulate warnings in workflow memory
    warnings: list[str] = []

    async def log(step: str, level: str, msg: str, details: dict | None = None):
        """Fire-and-forget log write — non-blocking, non-fatal."""
        await workflow.execute_activity(
            write_processing_log_activity,
            args=[document_id, step, level, msg, details],
            start_to_close_timeout=timedelta(seconds=10),
        )
        if level == "warning":
            warnings.append(f"[{step}] {msg}")

    await log("ingest", "info", "Document processing started")

    # ... existing processing steps with log calls ...
    await log("extraction", "warning", "Low confidence on 3 event references",
              {"event_indices": [2, 5, 7]})

    # On reprocess: clear prior logs (idempotency)
    # This happens in a new activity that deletes logs for the document
    # before writing new ones.
```

**Alternative considered — in-document log JSON field:**
Appending log entries to a JSON array on the `document` record. **Chosen against** because:
- Temporal replay safety requires idempotent writes (DELETE+INSERT, not append)
- A separate table allows querying logs independently (e.g., "show all documents with warnings")
- Cleaner separation of concerns

### Sources

- SurrealDB `DEFINE FIELD` schema: https://surrealdb.com/docs/surrealql/statements/define/field (HIGH confidence)
- Temporal replay safety pattern: nullify-then-recreate already established in M002's `resolve_entities_activity` (HIGH confidence)

---

## 5. Temporal Error Accumulation (Non-Fatal Warnings)

### Current State
Activities raise exceptions (which cause retries and eventual failure) or return `{"error": ...}` dicts with no accumulation mechanism. The workflow's `except` block catches any exception and marks the document as `failed`.

### v4.0 Pattern: Return Warnings in Activity Results

**Core idea:** Activities return both their primary result AND a list of warnings. The workflow accumulates warnings across all activities.

```python
from dataclasses import dataclass, field

@dataclass
class ActivityWarning:
    step: str
    message: str
    details: dict | None = None

# Activity returns a typed dict with warnings
@activity.defn
async def extract_events_activity(document_id: str) -> dict:
    # ... extraction logic ...
    return {
        "events": [...],
        "warnings": [
            {"step": "llm_extraction", "message": "Skipped chunk 3: API timeout",
             "details": {"chunk_index": 3, "retry_attempt": 2}}
        ],
    }
```

**Workflow accumulation pattern:**

```python
@workflow.run
async def run(self, document_id: str) -> dict:
    all_warnings: list[dict] = []

    result = await workflow.execute_activity(
        extract_events_activity, ...,
    )
    all_warnings.extend(result.get("warnings", []))

    store_result = await workflow.execute_activity(
        store_extraction_results_activity, ...,
    )
    all_warnings.extend(store_result.get("warnings", []))

    # Persist all accumulated warnings at the end
    for w in all_warnings:
        await workflow.execute_activity(
            write_processing_log_activity,
            args=[document_id, w["step"], "warning", w["message"], w.get("details")],
            ...
        )

    return {
        "document_id": document_id,
        "event_count": len(events),
        "warning_count": len(all_warnings),
        "status": "processed",
    }
```

**When to use `ApplicationError` (Temporal native):**

The `ApplicationError` with `category=ApplicationErrorCategory.BENIGN` exists to suppress DEBUG-level logging and metrics for known-bad inputs. Use it ONLY when you intend to raise an error that the workflow catches and handles — NOT for accumulating warnings that shouldn't fail the workflow.

```python
# BAD: Don't raise errors for warnings
raise ApplicationError(
    "Low confidence on references",
    category=ApplicationErrorCategory.BENIGN,
)

# GOOD: Return warnings in results
return {"events": [...], "warnings": [...]}
```

**Why this pattern:** 
- Warnings don't trigger Temporal retry policies
- Warnings don't set document status to `failed`
- Warnings are persisted at the end of the workflow, not scattered across activities
- The pattern is simple, serializable, and Temporal-safe

### Sources

- `ApplicationErrorCategory.BENIGN` documentation: https://python.temporal.io/temporalio.exceptions.ApplicationErrorCategory.html (HIGH confidence)
- `ApplicationError` properties: https://python.temporal.io/temporalio.exceptions.ApplicationError.html (HIGH confidence)
- Temporal activity result types: any serializable dict (HIGH confidence — already in use)

---

## 6. JSON Schema Changes for v4.0

### Modified `EVENT_EXTRACTION_SCHEMA`

The current schema has flat string fields for `espacio`, `tiempo`, `humanos`, `objetos`. For v4.0, keep these as-is (they remain as human-readable summaries) but add the richer event entity extraction as a **separate schema path**.

**New: `STRUCTURED_EVENT_SCHEMA` for compound event entity creation**

```python
STRUCTURED_EVENT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "que_paso": {"type": "string"},
                    "espacio": {"type": "string"},
                    "tiempo": {"type": "string"},
                    "humanos": {"type": "string"},
                    "objetos": {"type": "string"},
                    "references": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "reference_type": {"type": "string", "enum": ["espacio", "tiempo", "humanos", "objetos"]},
                                "verbatim_text": {"type": "string"},
                                "span_start": {"type": "integer"},
                                "span_end": {"type": "integer"},
                                "matched_entity_id": {"type": "string"},
                                "reference_context": {"type": "string"},
                            },
                            "required": ["reference_type", "verbatim_text", "span_start", "span_end"],
                            "additionalProperties": False,
                        },
                    },
                    "event_entity": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "A descriptive name for this event"},
                            "time": {"type": "string", "description": "Structured temporal context"},
                            "place": {"type": "string", "description": "Structured spatial context"},
                            "participants": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "People or organizations involved",
                            },
                            "objects": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Objects or assets involved",
                            },
                        },
                        "required": ["name"],
                        "additionalProperties": False,
                    },
                },
                "required": ["que_paso", "references"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["events"],
    "additionalProperties": False,
}
```

---

## 7. What Does NOT Change

| Existing Component | Change Required | Rationale |
|-------------------|----------------|-----------|
| Temporal workflow sequence | New `write_processing_log_activity` calls inserted; `resolve_entities_activity` enhanced | Logging is additive; entity resolution adds search-first step before LLM call |
| FastAPI (`api.py`) | No change | Upload/document APIs unaffected |
| Temporal worker (`worker.py`) | Register `write_processing_log_activity` | New activity |
| TypeScript tests | New test suite for v4.0 features | Test log queries, event entities, offset page computation |
| OpenRouter LLM layer | Schema additions only | `EVENT_EXTRACTION_SCHEMA` gets optional fields; `ENTITY_RESOLUTION_SCHEMA` gets `event` type |
| SurrealDB schema | Add `page_number` to `reference`; add `"event"` to entity_type enum; create `processing_log` table | No destructive migrations |
| MinIO / blob storage | No change | Unrelated |
| PDF extraction | No change | Page offsets already computed |
| Text chunking | No change | Chunk transparency preserved |
| GraphQL | New queries for `processing_log` | Auto-GraphQL from schema COMMENT annotations |
| Canonical entity merge/split (`/entities/merge`, `/entities/{type}/{id}/split`) | No change | Event entities participate in same merge/split lifecycle |

---

## 8. Key Design Decisions

### D006: Compute `page_number` server-side, not from LLM
**Why:** `span_start`/`span_end` are already LLM outputs. Computing page number from `page_offsets` (which come from the PDF extractor) is deterministic and avoids LLM hallucination on page numbers.

### D007: Add `"event"` to existing `entity_type` enum, not a new table
**Why:** The unified `canonical_entity` model already supports flexible `properties` JSON, `superseded_by` soft-delete, and merge/split operations. A new table would duplicate all of this infrastructure. The `RELATE` statement provides the graph links between events and place/person/object entities.

### D008: Search-first as LLM context injection, not a separate query step
**Why:** Current architecture does batch LLM resolution AFTER extraction. Moving entity matching INTO extraction eliminates the two-pass pattern and reduces LLM calls. Existing entities are passed as context in the extraction prompt.

### D009: `processing_log` as SurrealDB table, not in-document JSON field
**Why:** Temporal replay safety requires idempotent writes, and `DELETE processing_log WHERE document = $doc` + re-insert is cleaner than trying to append to a JSON array. Separate table allows independent querying ("find all document processing warnings").

### D010: Warnings accumulated in activity result dicts, not via `ApplicationError(BENIGN)`
**Why:** `ApplicationError(BENIGN)` suppresses Temporal logging but still raises an exception, which triggers retry policies and workflow failure handling. Returning warnings in the result dict (e.g., `{"events": [...], "warnings": [...]}`) is non-fatal and lets the workflow accumulate warnings across multiple activities before persisting them.

---

## 9. Installation

No new external dependencies for v4.0:

```bash
# All v4.0 features use existing dependencies:
# - surrealdb (already installed)
# - temporalio (already installed)
# - httpx (already installed)
# - Python stdlib logging (built-in)
```

---

## Sources

- **SurrealDB DEFINE ANALYZER docs:** https://surrealdb.com/docs/surrealql/statements/define/analyzer (HIGH confidence — fetched successfully)
- **SurrealDB Geometry types (geospatial):** https://surrealdb.com/docs/surrealql/datamodel/geometries (HIGH confidence — fetched successfully)
- **SurrealDB CONTAINS operator:** https://surrealdb.com/docs/surrealql/statements/select (HIGH confidence — documented in WHERE clause section)
- **Temporal ApplicationErrorCategory.BENIGN:** https://python.temporal.io/temporalio.exceptions.ApplicationErrorCategory.html (HIGH confidence)
- **Temporal ApplicationError:** https://python.temporal.io/temporalio.exceptions.ApplicationError.html (HIGH confidence)
- **Current codebase patterns** — `llm.py`, `activities.py`, `workflows.py`, `extractors.py` (HIGH confidence — read from source)
- **SurrealDB RELATE statement:** https://surrealdb.com/docs/surrealql/statements/relate (HIGH confidence)
- **SurrealDB Python SDK v2.0.0:** https://surrealdb.com/docs/sdk/python (MEDIUM confidence — docs page confirms Python SDK exists)

---
*Stack research for: v4.0 Pipeline Quality & Entity Resolution*
*Researched: 2026-06-03*
