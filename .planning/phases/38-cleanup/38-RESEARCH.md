# Phase 38: Cleanup — Research

**Researched:** 2026-06-10
**Domain:** Deprecated code removal — database tables, API routes, activity functions, UI components
**Confidence:** HIGH

## Summary

Phase 38 is the final v7.0 phase — a surgical cleanup that removes all code, tables, and UI components from the old `event`/`reference`/`canonical_entity`/`event_participant`/`event_entity_link` system. Per D056 and D059, old tables and code survived through all preceding phases as a safety net; now that the v7 pipeline (Phases 33–37) is verified operational, this safety net is no longer needed.

The cleanup spans four tiers: database (drop 5 tables via Alembic migration), API (delete 3 route modules, unregister from `api/__init__.py`), activities (remove 5 obsolete activity modules, clean up imports in `workflows.py` and `activities/__init__.py`), and UI (remove "Entidades" and "Referencias" tabs plus all associated JavaScript ~500 lines from `index.html`). Several test files reference the old system and must be updated or retired.

**Critical finding:** The `document_event_log` table is still actively used by the `ProcessingLogger` class in the new v7 system (both `DocumentProcessingV7Workflow` and `extract_events_v7_activity` call it). Despite appearing in the success criteria, **this table MUST NOT be dropped**. The planner should treat this as a documented override of criterion #1.

**Primary recommendation:** Execute cleanup in FK dependency order: drop `event_participant` → `event_entity_link` → `reference` → `event` → `canonical_entity`. Remove code in parallel waves: API routes + UI can be done independently of database migration, but activity deletions must wait until tests pass with routes deleted.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Drop old database tables | Database / Storage | — | Alembic migration runs against PostgreSQL |
| Remove old API routes | API / Backend | — | FastAPI router registration in `api/__init__.py` |
| Remove old activity functions | API / Backend | — | Python module deletion; Temporal worker imports them |
| Remove old UI tabs | Browser / Client | — | Vanilla JS SPA in `static/index.html` |
| Remove old model types | API / Backend | — | Pydantic models in `api/models.py` |
| Remove orphan cleanup scripts | — | — | Standalone scripts under `scripts/` |
| Update test files | API / Backend | — | Python test suite; references old activities and routes |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Alembic | 1.18.4 | Database migration to drop old tables | Already installed; project-standard migration tool [VERIFIED: Context7 docs] |
| FastAPI | (existing) | Route router; unregistering routes | Already installed; no new dependency needed |
| asyncpg | (existing) | Verify table existence post-drop | Already used by test fixtures |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | ≥8.0 | Run test suite post-cleanup | Verify no broken imports or failed tests after removals |
| pytest-asyncio | ≥0.21 | Async test fixtures for PostgreSQL | Existing test infrastructure |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Alembic migration | Raw SQL via `init_schema.py` | Alembic is the established pattern (Phase 33); raw SQL bypasses migration history |

**Installation:** No new packages needed. This is a pure removal phase.

**Version verification:** All packages already installed and verified in prior phases.

## Package Legitimacy Audit

> No new packages are installed in this phase. This is a pure removal operation — no external dependencies. Audit skipped.

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CLN-01 | Drop old event/reference/entity tables | Tables identified: `event_participant` (old), `event_entity_link`, `reference`, `event`, `canonical_entity`. FK dependency order documented. `document_event_log` MUST be retained (used by new `ProcessingLogger`). |
| CLN-02 | Remove old API routes, old activity functions, old UI code | Routes: `entities.py`, `references.py`, `events.py`. Activities: `extract_events.py`, `resolve_entities.py`, `store_extraction_results.py`, `resolve_entities_with_search.py`, `create_event_canonical_entities.py`. UI: "Entidades" + "Referencias" tabs. Also: orphan cleanup scripts, old model types, old workflow class. |

## Architecture Patterns

### System Architecture Diagram

```
BEFORE Phase 38 (current state after Phase 37):
┌──────────────────────────────────────────────────────┐
│                  FastAPI Application                  │
│  Routes: /documents, /entities, /references,         │
│          /events (OLD), /events (v2 shadows old)     │
│  Models: old (Entity*, Reference*, Event*) + v2       │
├──────────────────────────────────────────────────────┤
│                 PostgreSQL Database                   │
│  TABLES TO DROP: event_participant, event_entity_link │
│  → reference → event → canonical_entity               │
│  TABLES TO KEEP: document, document_chunk,             │
│  document_event_log, llm_usage, llm_call_log,          │
│  event_v2, event_location, event_participant_v2,       │
│  event_document, event_ref                            │
├──────────────────────────────────────────────────────┤
│                Temporal Activities                    │
│  OLD (to remove): extract_events_activity,            │
│  resolve_entities_activity, resolve_entities_with_    │
│  search_activity, store_extraction_results_activity,   │
│  create_event_canonical_entities_activity              │
│  NEW (keep): extract_events_v7_activity,              │
│  store_events_v7_activity, resolve_references_v7_     │
│  activity                                              │
└──────────────────────────────────────────────────────┘

AFTER Phase 38:
┌──────────────────────────────────────────────────────┐
│                  FastAPI Application                  │
│  Routes: /documents, /events (v2 only)                │
│  Models: v2 only (EventV2*, ChunkText*, etc.)         │
├──────────────────────────────────────────────────────┤
│                 PostgreSQL Database                   │
│  Only v7 tables remain + shared utility tables        │
├──────────────────────────────────────────────────────┤
│                Temporal Activities                    │
│  Only v7 activities + chunk_document (shared)         │
└──────────────────────────────────────────────────────┘
```

### Dependency Graph for Table Drops

```
event_participant ──FK──▶ event ──FK──▶ document (KEEP)
       │                     │
       ▼                     ▼
  canonical_entity ◀──FK── event
       ▲                     
       │                     
event_entity_link ──FK──┘    
       │                     
reference ──FK──▶ event     
       │                     
       └──FK──▶ canonical_entity

Drop order: event_participant → event_entity_link → reference → event → canonical_entity
```

### Recommended Project Structure (changes only)
```
src/eth_pipeline/
├── api/
│   ├── __init__.py              # EDIT: remove entities, references, events router registrations
│   ├── models.py                # EDIT: remove old model types (Entity*, Reference*, Event*, Merge*, Split*)
│   └── routes/
│       ├── entities.py          # DELETE
│       ├── references.py         # DELETE
│       ├── events.py             # DELETE
│       ├── events_v2.py          # KEEP
│       └── documents.py          # EDIT: remove references to canonical_entity/event_entity_link/event_participant
├── activities/
│   ├── __init__.py               # EDIT: remove old activity imports
│   ├── extract_events.py         # DELETE
│   ├── resolve_entities.py       # DELETE
│   ├── resolve_entities_with_search.py  # DELETE
│   ├── store_extraction_results.py      # DELETE
│   ├── create_event_canonical_entities.py # DELETE
│   ├── chunk_document.py         # EDIT: may need to keep or refactor (shared by both workflows)
│   ├── _common.py                # EDIT: remove _create_canonical_entity, _normalize if no longer used
│   └── extract_events_v7.py      # KEEP
│   └── store_events_v7.py        # KEEP
│   └── resolve_references_v7.py  # KEEP
├── chunker.py                    # EDIT: remove old DocumentChunker, keep DocumentChunk dataclass if still used
├── workflows.py                  # EDIT: remove DocumentProcessingWorkflow, remove old activity imports
├── schema.sql                    # EDIT: remove old table DDL, keep shared tables
└── static/
    └── index.html                # EDIT: remove ~500 lines of entity/reference JS + HTML
```

### Pattern 1: Backward-Incompatible Route Removal
**What:** Unregister FastAPI routes from `app.include_router()` in `api/__init__.py`, delete route module files, and remove their model imports.
**When to use:** When old API routes must be removed without affecting remaining routes.
**Example:**
```python
# api/__init__.py — BEFORE (lines 77-87)
from eth_pipeline.api.routes.documents import router as documents_router
from eth_pipeline.api.routes.entities import router as entities_router
from eth_pipeline.api.routes.references import router as references_router
from eth_pipeline.api.routes.events import router as events_router
from eth_pipeline.api.routes.events_v2 import router as events_v2_router

app.include_router(documents_router)
app.include_router(entities_router)
app.include_router(references_router)
app.include_router(events_router)
app.include_router(events_v2_router)

# AFTER
from eth_pipeline.api.routes.documents import router as documents_router
from eth_pipeline.api.routes.events_v2 import router as events_v2_router

app.include_router(documents_router)
app.include_router(events_v2_router)
```

### Pattern 2: Alembic Migration for Table Drops
**What:** Create a new Alembic migration revision that drops old tables in FK-safe order.
**When to use:** When tables must be removed from PostgreSQL via the established migration system.
**Example:**
```python
# alembic/versions/0002_cleanup_old_tables.py (new file)
"""Drop old v6 event/reference/entity tables (Phase 38 cleanup)

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-10
"""
from alembic import op

revision = '0002'
down_revision = '0001'

def upgrade():
    # Drop FK edges first, then the tables they reference
    op.drop_table('event_participant')      # FKs → event, canonical_entity
    op.drop_table('event_entity_link')      # FKs → canonical_entity
    op.drop_table('reference')               # FKs → event, canonical_entity
    op.drop_table('event')                   # FK → document, canonical_entity
    op.drop_table('canonical_entity')        # self-referential FK only

def downgrade():
    # No downgrade — tables contain deprecated data, not worth recreating
    pass
```

### Anti-Patterns to Avoid
- **Dropping parent before children:** Dropping `event` before `reference` will fail due to FK constraints. Always drop child tables first.
- **Forgetting model re-exports:** `api.py` at the top level re-exports symbols like `EntityListItem`, `EntityListResponse`, etc. from `api/__init__.py`. If the model classes are deleted but the re-exports remain, imports of those symbols will fail at module load time. The re-exports in `api/__init__.py` AND `api.py` must both be cleaned.
- **Partial UI removal:** Removing the nav button HTML but leaving the JavaScript references (fetchEntities, sections.entities, etc.) causes runtime errors. Both HTML and JS must be removed atomically.
- **Dropping `document_event_log`:** The `ProcessingLogger` class in `processing_log.py` writes to this table and both old AND new workflows use it. Dropping it would break processing log functionality for the v7 system.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Table drop migration | Raw SQL via `init_schema.py` | Alembic `op.drop_table()` | Alembic tracks migration history; raw SQL bypasses version tracking |
| Route removal | Commenting out code | Delete files + remove imports | Commented code is "deprecated code"; success criterion is NO deprecated code survives |
| FK-safe drop order | Manual trial-and-error | Documented dependency graph (this research) | Wrong order causes migration failure at runtime |

**Key insight:** This phase is deletion-only. Every line removed is a line that cannot regress. The "don't hand-roll" principle applies inversely here — do NOT try to "deprecate" or "comment out" code. Clean deletion with verified imports is the correct pattern.

## Runtime State Inventory

> Rename/refactor/migration phase — inventory required.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | Old tables in PostgreSQL: `event_participant`, `event_entity_link`, `reference`, `event`, `canonical_entity` with production data from prior pipeline runs | Data migration: Alembic `drop_table` in `upgrade()` — data loss is intentional (old pipeline output, superseded by v7) |
| Stored data | `document_chunk` table rows created by old `chunk_document_activity` — shared with new v7 system | None — table is retained. Old chunks MAY have been created without `page_start`/`page_end` provenance, but v7 system only needs `text` + `offset_start`/`offset_end` |
| Live service config | Temporal worker schedules old workflow `DocumentProcessingWorkflow` — may still be registered in Temporal server | Manual: after deploying Phase 38, terminate any running `DocumentProcessingWorkflow` executions and ensure only `DocumentProcessingV7Workflow` is registered |
| OS-registered state | None — no OS-level registrations reference the deprecated system | None |
| Secrets/env vars | None — no secrets reference old table/entity names | None |
| Build artifacts | `scripts/cleanup_orphan_entities.py`, `scripts/cleanup_orphan_references.py` — reference `canonical_entity` table | Delete both scripts |
| Test data | `tests/test_store_events_v7.py:157` inserts into old tables as part of v7 tests | Verify — may need to keep if it tests the NEW `event_participant_v2` etc. (filename suggests v7, but line 157 may reference old table) |
| Test data | `tests/test_v7_workflow.py:124-128` references old activity names `extract_events_activity`, `store_extraction_results_activity`, `resolve_entities_activity`, `resolve_entities_with_search_activity`, `create_event_canonical_entities_activity` | Update test to reference v7 activities or retire the test |

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3 | Alembic migration, activity deletion | ✓ | 3.13.13 | — |
| uv | Package management | ✓ | 0.11.18 | — |
| Alembic | Migration execution | ✓ | 1.18.4 | — |
| PostgreSQL | Target DB for table drops | ✓ | accepting connections | — |
| pytest | Post-cleanup test suite | ✓ | ≥8.0 | — |

**Missing dependencies with no fallback:** None — all runtime dependencies available.
**Missing dependencies with fallback:** None.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.0+ with pytest-asyncio |
| Config file | pyproject.toml (`[tool.pytest]`) |
| Quick run command | `uv run pytest tests/ -x --timeout=30 -q` |
| Full suite command | `uv run pytest tests/ -v` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CLN-01 | Old tables do not exist in database | integration | `uv run pytest tests/test_schema.py -x -k "test_all_expected_tables" -v` | ✅ `tests/test_schema.py` — needs update to remove old tables from expected list |
| CLN-02 | Old API routes return 404 | integration | `curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/entities` → expect 404 | ❌ Wave 0 — no automated route-404 test exists |
| CLN-02 | Old activity functions not importable | unit | `uv run python -c "from eth_pipeline.activities import extract_events_activity"` → expect ImportError | ❌ Wave 0 — no automated import-failure test exists |
| CLN-02 | Old UI tabs not in navigation | manual-only | Browser: Confirm "Entidades" and "Referencias" are absent from nav; "Subir", "Documentos", "Registros", "Eventos", "LLM Calls" are present | ❌ Wave 0 — no browser UI test exists |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_schema.py -x --timeout=30 -q` (verifies table state + basic import health)
- **Per wave merge:** `uv run pytest tests/ -x --timeout=60 -q` (full suite)
- **Phase gate:** Full suite green + manual UI verification before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_phase38_cleanup.py` — covers CLN-01 (table existence check) and CLN-02 (route 404 + import failure)
- [ ] Manual verification checklist for UI tab removal (CLN-02 success criterion #4)
- [ ] Framework install: already installed — no action needed

## Security Domain

> `security_enforcement` key absent from config — default to enabled.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | N/A — single-user research tool, no auth |
| V3 Session Management | no | N/A |
| V4 Access Control | no | N/A |
| V5 Input Validation | no | N/A — this is a deletion phase |
| V6 Cryptography | no | N/A |

### Known Threat Patterns for Cleanup Phase

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Stale API endpoints exposing old data after tables dropped | Denial of Service | Remove routes BEFORE dropping tables — avoids 500 errors for clients hitting old endpoints |
| Orphaned imports causing worker crashes | Denial of Service | Verify all imports resolve after deletions before restarting Temporal worker |
| Incomplete model cleanup leaving dead Pydantic schemas | Information Disclosure | Audit `api/models.py` and `api.py` re-exports for any remaining old model references |

## Common Pitfalls

### Pitfall 1: Dropping `document_event_log` table
**What goes wrong:** The `ProcessingLogger` class (`processing_log.py`) writes to `document_event_log` and is used by both the new v7 pipeline (`DocumentProcessingV7Workflow`, `extract_events_v7_activity`) and the old pipeline. Dropping this table breaks processing log functionality.
**Why it happens:** The success criteria lists `document_event_log` among tables to drop, but the criteria was written before all phases were executed and doesn't account for the shared nature of this table.
**How to avoid:** Document this as an override. The `document_event_log` table MUST be retained. The research explicitly flags this for the planner.
**Warning signs:** If `ProcessingLogger.log()` calls start failing with "relation does not exist" errors after migration.

### Pitfall 2: FK Violation When Dropping Tables in Wrong Order
**What goes wrong:** Dropping `event` before `reference` or `event_participant` fails with `ERROR: cannot drop table event because other objects depend on it`.
**Why it happens:** PostgreSQL enforces FK constraints; parent tables referenced by child tables cannot be dropped first.
**How to avoid:** Follow documented drop order: `event_participant` → `event_entity_link` → `reference` → `event` → `canonical_entity`.
**Warning signs:** Alembic migration fails at `drop_table` step.

### Pitfall 3: Stale Model Re-exports Breaking `api.py` Imports
**What goes wrong:** After deleting model classes from `api/models.py`, the re-exports in `api/__init__.py` (lines 12-43) and `api.py` (lines 12-34) still reference the deleted symbols, causing `ImportError` at application startup.
**Why it happens:** `api/__init__.py` has a large `from .api.models import (...)` block that re-exports ~30 symbols — many are old entity/reference models that must be removed. Missing even one causes a crash.
**How to avoid:** Make a complete audit of all imports before deleting model classes. Sync deletions in `api/models.py`, `api/__init__.py`, and `api.py` simultaneously.
**Warning signs:** Application fails to start with `ImportError: cannot import name 'EntityListItem' from 'eth_pipeline.api.models'`.

### Pitfall 4: Incomplete UI Cleanup
**What goes wrong:** Removing HTML for "Entidades"/"Referencias" tabs but leaving JavaScript functions that reference DOM elements from those tabs (e.g., `document.getElementById('entity-search')` returns `null`, then event listeners fail silently or throw errors).
**Why it happens:** The `index.html` file is monolithic (~2800 lines); the entity/reference code is interleaved with other tab code.
**How to avoid:** Delete in this order: (1) HTML sections for `#tab-entities` and `#tab-references`, (2) Nav buttons, (3) `sections` object references, (4) `onTabClick` references to `entities`/`references`, (5) All entity-specific JS (functions, event listeners, pagination, detail panel), (6) All reference-specific JS. Then test the remaining tabs (Subir, Documentos, Registros, Eventos) still work.
**Warning signs:** Console errors about `null` element references or `fetchEntities is not defined` when clicking on remaining tabs.

### Pitfall 5: Old Activities Still Imported in `workflows.py`
**What goes wrong:** Removing activity files without removing their imports in `workflows.py` causes `ImportError` when the Temporal worker starts.
**Why it happens:** `workflows.py` line 29-42 imports all activities in a `with workflow.unsafe.imports_passed_through()` block — every removed activity still has an import line here.
**How to avoid:** Remove activity files AND their imports in `workflows.py` AND their registrations in `activities/__init__.py` in the same commit. Also remove the old `DocumentProcessingWorkflow` class from `workflows.py` since it only calls old activities.
**Warning signs:** Temporal worker fails to start with import errors.

## Code Examples

### Alembic Migration: Drop Old Tables

```python
# Source: Alembic 1.18.4 official docs / existing 0001 migration pattern
# File: alembic/versions/0002_cleanup_old_tables.py (new)
"""Drop old v6 event/reference/entity tables (Phase 38 cleanup)

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-10
"""
from alembic import op

revision = '0002'
down_revision = '0001'

def upgrade():
    # Drop order respects FK dependencies (children before parents)
    op.drop_table('event_participant')      # FKs → event(id), canonical_entity(id)
    op.drop_table('event_entity_link')      # FKs → canonical_entity(id) × 2
    op.drop_table('reference')               # FKs → event(id), canonical_entity(id)
    op.drop_table('event')                   # FK → document(id), canonical_entity(id)
    op.drop_table('canonical_entity')        # Self-referential FK only

def downgrade():
    # No downgrade: these tables contain deprecated v6 pipeline data.
    # Recreating empty tables would serve no purpose.
    pass
```

### Route Cleanup: `api/__init__.py`

```python
# Source: Current codebase api/__init__.py lines 77-87
# BEFORE (remove these lines):
from eth_pipeline.api.routes.entities import router as entities_router
from eth_pipeline.api.routes.references import router as references_router
from eth_pipeline.api.routes.events import router as events_router

app.include_router(entities_router)
app.include_router(references_router)
app.include_router(events_router)

# AFTER (keep only):
from eth_pipeline.api.routes.documents import router as documents_router
from eth_pipeline.api.routes.events_v2 import router as events_v2_router

app.include_router(documents_router)
app.include_router(events_v2_router)
```

### Model Types to Remove from `api/models.py`

```python
# Source: api/models.py — these classes are tied to old system and MUST be removed:
#   EntityDetailReference (line ~240)
#   EntityDetailResponse (line ~250)
#   EntityListItem (line ~290)
#   EntityListResponse (line ~310)
#   EntityDeleted (line ~330)
#   MergeRequest, MergeResponse (lines ~350-380)
#   SplitPartition, SplitRequest, SplitResponse (lines ~390-450)
#   OrphanCleanupResponse (line ~470)
#   EventListItem (line ~500)  # OLD EventListItem — not EventV2ListItem
#   EventListResponse (line ~540)
#   EventsCleared (line ~590)
#   ReferenceListItem (line ~300)
#   ReferenceListResponse (line ~315)
#
# KEEP:
#   APIInfo, HealthResponse
#   DocumentInput, DocumentCreated, DocumentUploadCreated
#   DocumentStatus, DocumentListItem, DocumentListResponse
#   ProcessingLogListItem, ProcessingLogListResponse
#   ChunkTextResponse
#   EventV2ListItem, EventV2DetailResponse, EventListV2Response
#   EventLocationDetail, EventParticipantDetail, EventRefDetail
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `extract_events_activity` — whole-document LLM extraction | `extract_events_v7_activity` — per-chunk extraction with prior context | Phase 35 (v7 pipeline) | Old activity must be removed; new one already deployed |
| `resolve_entities_activity` — LLM grouping of references to entities | `resolve_references_v7_activity` — post-extraction character offset computation | Phase 35 (v7 pipeline) | Old activity removes; v7 resolves offsets, not entities |
| `store_extraction_results_activity` — inserts into `event` + `reference` tables | `store_events_v7_activity` — inserts into `event_v2` + `event_location` + `event_participant_v2` + `event_ref` | Phase 35 (v7 pipeline) | Old tables dropped, new tables already populated |
| `canonical_entity` — entity resolution and linking | v7 event model — inline participants, locations, references | Phase 35 (v7 pipeline) | Entity concept absorbed into event model; no separate entity table needed |
| "Entidades" + "Referencias" UI tabs | "Eventos" tab with inline participants, locations, references | Phase 37 (Event UI) | Old tabs removed; new Eventos tab serves all use cases |
| Old `GET /events` endpoint (queries `event` table) | New `GET /events` v2 (queries `event_v2` table, registered AFTER old route to shadow it) | Phase 36 (Event API) | Old route file deleted; v2 route already receives all traffic via FastAPI last-registered-wins |

**Deprecated/outdated:**
- `canonical_entity` table: Superseded by `event_location` + `event_participant_v2` + `event_ref` model where entities are embedded within events, not managed independently.
- `reference` table: Superseded by `event_ref` table — references are now event-scoped with chunk-traceable span offsets.
- `event_entity_link`: Superseded — no separate entity graph; relationships are captured within the v7 event structure.
- `event_participant` (old): Superseded by `event_participant_v2` — same role but FK to `event_v2` instead of `event`.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `document_event_log` is still used by the new v7 system and must not be dropped | Summary, Common Pitfalls | If the new system has its own logging mechanism and this table is truly unused, we leave dead code. LOW risk — confirmed via codebase grep. |
| A2 | `document_chunk` table rows created by old chunker are compatible with v7 system reads | Runtime State Inventory | If v7 system requires chunk metadata the old chunker didn't produce, existing documents may need re-chunking. MEDIUM risk — chunk_document_activity writes text + offsets which are the minimum required fields. |
| A3 | Temporal worker will not be running old `DocumentProcessingWorkflow` instances at deploy time | Runtime State Inventory | If old workflows are in-flight, dropping tables mid-execution corrupts state. Mitigation: stop Temporal worker, run migration, restart. |
| A4 | `chunk_document_activity` can be removed (only used by old `DocumentProcessingWorkflow`) | Architecture Patterns | If the new `DocumentProcessingV7Workflow` also calls `chunk_document_activity` (currently uses `get_document_chunks_activity` to read existing chunks), removal breaks v7 pipeline. MEDIUM risk — verified via workflow code analysis; v7 workflow reads chunks, doesn't create them. |
| A5 | Test `test_schema.py` currently lists old tables in expected table set | Validation Architecture | If the test was already updated in Phase 33-37 to exclude old tables, minimal changes needed. LOW risk — checked; test file references `canonical_entity` at line 24. |
| A6 | `_create_canonical_entity` in `activities/_common.py` is only used by old activities | Architecture Patterns | If any v7 activity imports it, removal breaks v7 pipeline. Verified: only used by `resolve_entities.py`, `resolve_entities_with_search.py`, `store_extraction_results.py`, `create_event_canonical_entities.py` — all old. |

## Open Questions (RESOLVED)

1. **`document_event_log` retention vs. removal**
   - What we know: The table is used by `ProcessingLogger` which is called by both old and new workflows. The success criteria lists it for removal.
   - What's unclear: Whether Phase 33-37 introduced a new logging mechanism rendering `document_event_log` truly unused.
   - Recommendation: Retain `document_event_log`. If it's genuinely unused, a separate audit phase can drop it later. Safer to keep than to break logging.

2. **`chunk_document_activity` — keep or remove? (RESOLVED)**
   - What we know: The old `DocumentProcessingWorkflow` calls `chunk_document_activity`; the new `DocumentProcessingV7Workflow` uses `get_document_chunks_activity` to READ existing chunks.
   - Resolution: KEEP `chunk_document_activity` — it is the chunking entry point that routes to `SmartChunker` for v7 documents. However, remove the `DocumentChunker` import and old-path branch (`else:` clause). After Plan 38-03, the activity only handles the `schema_version == 'v7'` path with `SmartChunker`. The `DocumentChunker` fallback is deleted because `DocumentProcessingWorkflow` (the only caller of the old path) is removed.
   - Verified by: codebase audit — `chunk_document.py` reads `schema_version` and branches; v7 workflow calls `get_document_chunks_activity` (reader), not `chunk_document_activity` (writer).

3. **`DocumentChunker` class in `chunker.py` — full removal or partial? (RESOLVED)**
   - What we know: `chunker.py` defines `DocumentChunk` dataclass, `ChunkResult` dataclass, `DocumentChunker` class, `chunk_document` convenience function, `SmartChunk` dataclass, `distribute_balanced` function, and `SmartChunker` class.
   - Resolution: REMOVE `DocumentChunker` class, `ChunkResult` dataclass, and `chunk_document` convenience function (all tied to the old chunking path). KEEP `DocumentChunk` dataclass (canonical data model, no dependency on old chunker), `SmartChunk` dataclass, `distribute_balanced` function, and `SmartChunker` class. After removal, `chunk_document_activity` only imports `SmartChunker` from `chunker.py`.
   - Verified by: grep of `chunker.py` — `DocumentChunker` is only used by the old `chunk_document_activity` branch and the `chunk_document()` convenience function, both of which are removed.

4. **`resolve_entities_with_search_activity` — remove in Phase 35 or Phase 38? (RESOLVED)**
   - What we know: D057 states PIP-06 (replace old activities) is in Phase 35, not Phase 38. But the activity might still be present in the codebase.
   - Resolution: REMOVE in Phase 38. Verified: `resolve_entities_with_search_activity` is still imported in `activities/__init__.py` (line 25-27) and `workflows.py` (line 37). The file `resolve_entities_with_search.py` still exists in the activities directory. Phase 35 added the v7 replacement activities but did not delete the old ones — that deletion is Phase 38's responsibility per D059.
   - Verified by: codebase audit — `activities/__init__.py` lines 25-27, `workflows.py` line 37, `resolve_entities_with_search.py` exists on disk.

5. **Which `event_location` table?**
   - What we know: The success criteria says "event_location (old)" but `schema.sql` has no old `event_location` table. The new `event_location` table was created in Phase 33 migration 0001 as part of the v7 schema.
   - What's unclear: The criteria phrasing — there may have been a rename from `event_location` to something else, or it's referring to the `location_point` JSONB column in the old `event` table.
   - Recommendation: No action needed. The new `event_location` (v7) table is retained. The old system used inline `location_point` JSONB which is dropped with the `event` table.

## Sources

### Primary (HIGH confidence)
- Codebase analysis: `src/eth_pipeline/` — full file audit of api/, activities/, models/, schema.sql, workflows.py, static/index.html
- `schema.sql` (lines 1-176) — full table definitions showing old vs. new schema
- `alembic/versions/0001_v7_foundation.py` — Phase 33 migration creating new v7 tables
- `tests/conftest.py` — test fixtures showing v7 table references

### Secondary (MEDIUM confidence)
- [CITED: alembic.sqlalchemy.org/en/latest/ops.html] — `op.drop_table()` official Alembic documentation, confirms standard drop pattern

### Tertiary (LOW confidence)
- WebSearch failed (BRAVE_API_KEY not set) — no external web sources available for cleanup best practices

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new dependencies needed; Alembic pattern verified via Context7
- Architecture: HIGH — full codebase audit completed; every file, route, activity, and UI element inventoried
- Pitfalls: HIGH — identified from direct code reading; FK dependency graph verified against actual schema

**Research date:** 2026-06-10
**Valid until:** 2026-07-10 (stable domain — cleanup patterns are well-established)
