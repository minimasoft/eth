---
phase: 38-cleanup
verified: 2026-06-11T06:00:00Z
status: gaps_found
score: 11/15 must-haves verified
overrides_applied: 0
gaps:
  - truth: "documents.py delete_document executes correct SQL against all surviving tables"
    status: failed
    reason: "7 of 10 SQL queries in delete_document are missing $1 parameter placeholders — asyncpg will raise InterfaceError at runtime"
    artifacts:
      - path: "src/eth_pipeline/api/routes/documents.py"
        issue: "7 queries missing $1 — lines 994, 1002, 1006, 1011, 1015, 1019, 1023"
    missing:
      - "Add $1 to each broken query: document_chunk WHERE document = $1, llm_usage WHERE document = $1, llm_call_log WHERE document = $1, event_ref WHERE document_id = $1, event_participant_v2 WHERE document_id = $1, event_location WHERE event_id IN (SELECT id FROM event_v2 WHERE document_id = $1), event_document WHERE document_id = $1"
  - truth: "DocumentProcessingV7Workflow can execute without NameError — get_document_chunks_activity and get_prior_events_activity are defined"
    status: failed
    reason: "Two v7 helper activities (get_document_chunks_activity, get_prior_events_activity) were collaterally deleted during Phase 38-03 cleanup. They were @activity.defn functions in workflows.py, NOT old activities. They are still called by DocumentProcessingV7Workflow.run() at lines 62-63 and 73-74. The workflow will crash at runtime with NameError."
    artifacts:
      - path: "src/eth_pipeline/workflows.py"
        issue: "Both functions deleted, lines 62-63 and 73-74 call undefined names"
    missing:
      - "Restore get_document_chunks_activity and get_prior_events_activity as @activity.defn functions in workflows.py (see commit f2158f8 for original definitions)"
  - truth: "test_migration.py passes with Phase 38 migration applied"
    status: failed
    reason: "test_migration_current expects alembic_version='0001' but it is now '0002' after migration was applied"
    artifacts:
      - path: "tests/test_migration.py"
        issue: "Line 37 asserts alembic_version == '0001', should be '0002'"
    missing:
      - "Update assertion to alembic_version == '0002'"
  - truth: "get_document endpoint does not query dropped tables"
    status: failed
    reason: "documents.py get_document endpoint (lines 388-400) still queries dropped tables 'reference' and 'event' for reference_count and entity_count. Wrapped in try/except so not a crash, but returns incorrect data."
    artifacts:
      - path: "src/eth_pipeline/api/routes/documents.py"
        issue: "Lines 388-400 query dropped tables reference and event. Also line 61 still documents the removed clear_document_events endpoint, and lines 63-66 list deleted /entities and /references routes."
    missing:
      - "Remove or replace old-table queries in get_document with event_v2-based counts, or remove reference_count/entity_count fields from DocumentStatus"
---

# Phase 38: Cleanup Verification Report

**Phase Goal:** All deprecated code from the old references/entities/events system is removed — tables dropped, routes deleted, activities removed, UI code cleaned
**Verified:** 2026-06-11T06:00:00Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Alembic migration 0002 drops 5 old tables in FK-safe order | ✓ VERIFIED | `alembic/versions/0002_cleanup_old_tables.py` drops event_participant → event_entity_link → reference → event → canonical_entity. All 5 tables confirmed GONE in PostgreSQL. |
| 2 | document_event_log survives migration | ✓ VERIFIED | Not in drop list. Confirmed PRESENT in PostgreSQL. |
| 3 | test_schema.py reflects post-cleanup state (old tables dropped, shared tables survive) | ✓ VERIFIED | `V6_TABLES` reduced to [document, document_chunk]; `DROPPED_TABLES` lists the 5 dropped tables; `test_old_tables_dropped` asserts NOT EXISTS; `test_shared_tables_survive` asserts EXISTS. All 5 tests PASS. |
| 4 | GET /entities, /references, old /events return 404 | ✓ VERIFIED | Route files deleted (entities.py, references.py, events.py). Router imports and include_router calls removed from api/__init__.py. Only documents_router and events_v2_router remain. |
| 5 | No old model types (Entity*, Reference*, Merge*, Split*, old Event*) importable from api.models | ✓ VERIFIED | All 14 old classes confirmed removed. v7 types (EventV2ListItem, DocumentListItem, etc.) still importable. EventsCleared persists in models.py/__all__ per 38-02 deviation. |
| 6 | api.py and api/__init__.py do not re-export deprecated symbols | ✓ VERIFIED | Both files checked — only v7/shared symbols in re-export chains. App starts without ImportError. |
| 7 | Old activity functions not importable | ✓ VERIFIED | Direct imports of extract_events_activity, resolve_entities_activity, etc. raise ImportError. All v7 activities importable. Files confirmed deleted from disk. |
| 8 | DocumentProcessingWorkflow class removed | ✓ VERIFIED | Only DocumentProcessingV7Workflow class exists in workflows.py. Direct import raises ImportError. |
| 9 | DocumentChunker class, ChunkResult, chunk_document() removed; SmartChunker retained | ✓ VERIFIED | chunker.py has only SmartChunker, SmartChunk, DocumentChunk, distribute_balanced. Direct imports of DocumentChunker raise ImportError. |
| 10 | _create_canonical_entity removed from _common.py | ✓ VERIFIED | _common.py has only _db_params, _extract_query_results, _get_blob_from_minio. No _create_canonical_entity or _normalize. |
| 11 | documents.py clear_document_events endpoint removed | ✓ VERIFIED | Endpoint not present in documents.py. EventsCleared import no longer in documents.py imports. |
| 12 | documents.py delete_document no longer has old-table orphan cleanup | ✓ VERIFIED | All canonical_entity/event_participant/event_entity_link/reference queries removed from delete_document. Returns DocumentDeleted without orphaned_entities_cleaned. |
| 13 | Entidades and Referencias tabs absent from nav bar; only 4 tabs remain | ✓ VERIFIED | Nav has Cargar, Documentos, Registros, Eventos — no tab-btn-entities, tab-btn-references. grep returns 0 matches. |
| 14 | No entity/reference JavaScript functions in index.html | ✓ VERIFIED | grep for fetchEntities, renderEntities, recycleEntities, fetchReferences, renderReferences, etc. returns 0 matches. |
| 15 | get_document_chunks_activity and get_prior_events_activity exist | ✗ FAILED | These v7 @activity.defn helpers were collaterally deleted in Phase 38-03 cleanup. DocumentProcessingV7Workflow references them at lines 62-63 and 73-74 but they no longer exist. |
| 16 | delete_document SQL queries have valid parameter placeholders | ✗ FAILED | 7 of 10 DELETE queries in delete_document are missing $1 parameter placeholders. |
| 17 | test_migration.py expects current alembic version | ✗ FAILED | Assertion expects '0001' but migration 0002 was applied. |
| 18 | get_document endpoint does not query dropped tables | ✗ FAILED | Lines 388-400 query dropped `reference` and `event` tables. Non-fatal (wrapped in try/except) but returns incorrect data. |

**Score:** 11/15 must-haves verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `alembic/versions/0002_cleanup_old_tables.py` | Drops 5 old tables in FK-safe order | ✓ VERIFIED | Lines 15-19: FK-safe order with no-op downgrade |
| `tests/test_schema.py` | Tests post-cleanup state | ✓ VERIFIED | 5 tests pass; DROPPED_TABLES list, old_tables_dropped, shared_tables_survive |
| `src/eth_pipeline/api/__init__.py` | Only documents_router + events_v2_router | ✓ VERIFIED | Lines 65-69: clean router section |
| `src/eth_pipeline/api/models.py` | Old types removed | ✓ VERIFIED | 14 old classes removed. EventsCleared still present (acknowledged deviation) |
| `src/eth_pipeline/api.py` | Clean re-exports | ✓ VERIFIED | Line 12-24: only v7/shared symbols |
| `src/eth_pipeline/activities/__init__.py` | Only v7+shared activities | ✓ VERIFIED | Lines 8-37: confirmed clean |
| `src/eth_pipeline/activities/_common.py` | _create_canonical_entity removed | ✓ VERIFIED | Only 3 helpers remain |
| `src/eth_pipeline/activities/chunk_document.py` | Only SmartChunker import | ✓ VERIFIED | Line 10: only SmartChunker imported |
| `src/eth_pipeline/workflows.py` | Only v7 workflow class | ⚠️ PARTIAL | DocumentProcessingWorkflow removed ✓ but get_document_chunks_activity and get_prior_events_activity also deleted ✗ |
| `src/eth_pipeline/chunker.py` | Only SmartChunker infra | ✓ VERIFIED | DocumentChunker/ChunkResult/chunk_document() all removed |
| `src/eth_pipeline/api/routes/documents.py` | No old-table refs, no clear_document_events | ✗ STALE_SQL | clear_document_events removed ✓, old-table cleanup removed ✓, BUT 7 queries missing $1 and get_document still queries dropped tables |
| `src/eth_pipeline/static/index.html` | ~500 lines entity/reference code removed | ✓ VERIFIED | Nav has 4 tabs, no entity/reference JS |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| alembic migration | PostgreSQL | op.drop_table() in FK-safe order | ✓ WIRED | Lines 15-19 confirmed |
| api/__init__.py | api/routes/ | app.include_router() | ✓ WIRED | Only documents + events_v2 |
| api/__init__.py | api/models.py | import block | ✓ WIRED | Clean re-exports confirmed |
| activities/__init__.py | chunk_document.py | import | ✓ WIRED | chunk_document_activity imported |
| workflows.py | activities/__init__.py | with workflow.unsafe.imports_passed_through() | ⚠️ PARTIAL | v7 activities imported OK, but helper activities (get_document_chunks_activity, get_prior_events_activity) missing |
| documents.py | api/models.py | DocumentDeleted import | ✓ WIRED | Clean import, no orphaned_entities_cleaned |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| documents.py delete_document | document_id | SQL DELETE calls | ✗ DISCONNECTED | 7 of 10 queries have broken SQL (missing $1) — will crash at runtime |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| App imports without error | `uv run python -c "from eth_pipeline.api import app"` | OK | ✓ PASS |
| v7 models importable | `from eth_pipeline.api.models import EventV2ListItem, DocumentListItem, DocumentDeleted` | OK | ✓ PASS |
| Old models not importable | `from eth_pipeline.api.models import EntityListItem` | ImportError | ✓ PASS |
| Old activities not importable | `from eth_pipeline.activities import extract_events_activity` | ImportError | ✓ PASS |
| v7 activities importable | `from eth_pipeline.activities import chunk_document_activity, extract_events_v7_activity` | OK | ✓ PASS |
| v7 workflow importable | `from eth_pipeline.workflows import DocumentProcessingV7Workflow` | OK | ✓ PASS |
| Old workflow not importable | `from eth_pipeline.workflows import DocumentProcessingWorkflow` | ImportError | ✓ PASS |
| DocumentChunker not importable | `from eth_pipeline.chunker import DocumentChunker` | ImportError | ✓ PASS |
| SmartChunker importable | `from eth_pipeline.chunker import SmartChunker, SmartChunk, DocumentChunk` | OK | ✓ PASS |
| DocumentDeleted simplified | `DocumentDeleted(document_id='test', document_deleted=True)` has no orphaned_entities_cleaned | OK | ✓ PASS |
| Old tables dropped | DB check: 5 tables confirmed GONE | OK | ✓ PASS |
| Retained tables survive | DB check: document, document_chunk, document_event_log, all v7 tables OK | OK | ✓ PASS |
| Schema tests pass | `uv run pytest tests/test_schema.py -v` | 5/5 PASS | ✓ PASS |
| Full test suite | `uv run pytest tests/ -v` (excluding env-dependent failures) | 1 expected regression (test_migration) | ✗ PARTIAL |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| CLN-01 | 38-01 | Drop old event/reference/entity tables | ✓ SATISFIED | 5 tables dropped, document_event_log retained per override. Schema tests verify. |
| CLN-02 | 38-02, 38-03, 38-04 | Remove old API routes, old activity functions, old UI code | ✗ BLOCKED | API routes ✓, old models ✓, activities ✓, UI ✓ — but two v7 helper activities deleted (collateral damage), broken SQL in delete_document, get_document still queries dropped tables |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/eth_pipeline/api/routes/documents.py` | 994 | Missing $1 placeholder in SQL query | 🛑 Blocker | `DELETE FROM document_chunk WHERE document = ` — asyncpg InterfaceError at runtime |
| `src/eth_pipeline/api/routes/documents.py` | 1002 | Missing $1 placeholder in SQL query | 🛑 Blocker | `DELETE FROM llm_usage WHERE document = ` |
| `src/eth_pipeline/api/routes/documents.py` | 1006 | Missing $1 placeholder in SQL query | 🛑 Blocker | `DELETE FROM llm_call_log WHERE document = ` |
| `src/eth_pipeline/api/routes/documents.py` | 1011 | Missing $1 placeholder in SQL query | 🛑 Blocker | `DELETE FROM event_ref WHERE event_id IN ... document_id = )` |
| `src/eth_pipeline/api/routes/documents.py` | 1015 | Missing $1 placeholder in SQL query | 🛑 Blocker | `DELETE FROM event_participant_v2 WHERE event_id IN ... document_id = )` |
| `src/eth_pipeline/api/routes/documents.py` | 1019 | Missing $1 placeholder in SQL query | 🛑 Blocker | `DELETE FROM event_location WHERE event_id IN ... document_id = )` |
| `src/eth_pipeline/api/routes/documents.py` | 1023 | Missing $1 placeholder in SQL query | 🛑 Blocker | `DELETE FROM event_document WHERE document_id = ` |
| `src/eth_pipeline/api/routes/documents.py` | 388-400 | Queries dropped tables `reference` and `event` | ⚠️ Warning | Non-fatal (try/except catches failure, returns 0) but returns incorrect data |
| `src/eth_pipeline/api/routes/documents.py` | 61-66 | root() endpoint documents deleted routes | ℹ️ Info | `/entities`, `/references`, `/documents/{id}/events` listed but deleted |
| `src/eth_pipeline/workflows.py` | 62-63, 73-74 | Calls undefined functions | 🛑 Blocker | `get_document_chunks_activity` and `get_prior_events_activity` deleted during cleanup |
| `tests/test_migration.py` | 37 | Assertion expects stale version | 🛑 Blocker | `assert version == "0001"` should be `"0002"` |
| `src/eth_pipeline/api/models.py` | 150-160 | EventsCleared model still present | ℹ️ Info | Acknowledged deviation — clear_document_events now removed so could be fully deleted |

### Gaps Summary

**3 BLOCKER issues found:**

1. **Collateral deletion of v7 helper activities (CRITICAL):** The `DocumentProcessingV7Workflow` calls `get_document_chunks_activity` (line 63) and `get_prior_events_activity` (line 74), but these were both deleted during the Phase 38-03 cleanup. These are NOT old activities — they are `@activity.defn` helper functions added in Phase 35 specifically for the v7 pipeline. The Temporal workflow will crash at runtime with `NameError`. **Fix:** Restore both functions in `workflows.py` from commit `f2158f8`.

2. **7 broken SQL queries in delete_document (HIGH):** The `delete_document` endpoint has 7 SQL queries with missing `$1` parameter placeholders. These will cause `asyncpg.exceptions.InterfaceError` at runtime. Only 3 of 10 queries have valid `$1`. **Fix:** Add `$1` parameter markers to each broken query.

3. **test_migration.py expects alembic_version='0001' (MEDIUM):** The assertion at line 37 needs updating to `'0002'` after Phase 38 migration was applied.

**1 WARNING issue found:**
- `get_document` endpoint still queries dropped `reference` and `event` tables (lines 388-400). Returns 0 values on failure due to try/except wrapper. Should be cleaned up with v7-based queries.

---

_Verified: 2026-06-11T06:00:00Z_
_Verifier: the agent (gsd-verifier)_
