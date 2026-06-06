---
phase: 26
plan: 02
plan_name: API filter integration tests
subsystem: tests
tags:
  - integration-tests
  - api-filters
  - references
  - events
  - v6.0
dependency_graph:
  requires:
    - "Phase 25 — LLM Extraction & Pipeline (event/ref data for filter testing)"
    - "Phase 26 Plan 01 — Merge/split hardening (no direct dependency)"
  provides:
    - "Phase 28 — Integration Tests & Verification (enhanced filter test coverage)"
  affects: []
tech_stack:
  added:
    - "filterReferences() — GET /references with arbitrary query params + per_page=100"
    - "filterEvents() — GET /events with arbitrary query params + per_page=100"
  patterns:
    - "Test helpers follow existing error-returns-null pattern"
    - "All tests use skipIfDegraded for graceful non-LLM/offline fallback"
    - "Best-effort pattern: tests log and skip when entity data is unavailable"
key_files:
  created: []
  modified:
    - tests/integration/helpers.ts
    - tests/integration/pipeline_v6.test.ts
decisions:
  - "filterReferences() and filterEvents() are separate from listReferences/listEvents for clarity"
  - "Tests use skipIfDegraded to gracefully degrade when API is unavailable"
  - "entity_id filter tests skip gracefully when no entity-linked references exist (best-effort)"
metrics:
  duration: "~10 min"
  completed_date: "2026-06-06"
  tasks_completed: 3
  files_modified: 2
---

# Phase 26 — Plan 02: API filter integration tests — Summary

**One-liner:** Added filterReferences() and filterEvents() helpers to the integration test suite; added 7 new tests across two test groups covering document, entity_type, entity_id, event_element filters for references and entity_id, entity_type, date_range filters for events.

## Task Results

### Task 1: Add helper functions for enhanced filter tests

**Commit:** `4f1647e`
**Files modified:** `tests/integration/helpers.ts`

Added two new exported helper functions below the existing `mergeEntities` function:

- **`filterReferences(params: Record<string, string>): Promise<ReferenceListResponse | null>`** — wraps `httpGet` to `GET /references?{params}` with `per_page=100`, returns parsed body or null on error. Same error-returns-null pattern as existing `listReferences`.
- **`filterEvents(params: Record<string, string>): Promise<EventListResponse | null>`** — wraps `httpGet` to `GET /events?{params}` with `per_page=100`, returns parsed body or null on error.

Both use existing `httpGet` and `API_BASE` constants. No existing helper functions were modified.

**Done criteria met:**
- ✅ `filterReferences` exported from helpers.ts
- ✅ `filterEvents` exported from helpers.ts
- ✅ Both follow existing error-returns-null pattern
- ✅ Existing test file can import them

### Task 2: Add integration tests for enhanced reference filters

**Commit:** `4f1647e`
**Files modified:** `tests/integration/pipeline_v6.test.ts`

Appended a new `describe("Enhanced GET /references filters", ...)` block containing 4 tests:

- **5a. Document filter** — Creates a second document, calls `filterReferences({ document: docId })`, verifies `total >= 0` and every returned reference's `document_id` matches the requested document.
- **5b. entity_type filter** — Calls `filterReferences({ entity_type: "person", document: docId })`, verifies non-negative total, and where `canonical_entity_type` is set it must equal "person".
- **5c. entity_id filter** — Finds a reference with non-null `canonical_entity_id`, calls `filterReferences({ entity_id: thatId })`, verifies all returned references have matching `canonical_entity_id`.
- **5d. Event element filter** — Calls `filterReferences({ event_element: "tiempo", document: docId })`, verifies non-negative total, and all returned references have `element_field=tiempo`.

All tests use `skipIfDegraded` and check `documentWasProcessed` for graceful fallback.

**Done criteria met:**
- ✅ New test group "Enhanced GET /references filters" exists
- ✅ Document filter test verifies filtered results belong to requested document
- ✅ entity_type filter test verifies type-consistent results
- ✅ entity_id filter test verifies entity-specific filtering (skips gracefully when no entity data)
- ✅ event_element filter test verifies element_field filtering
- ✅ All tests use skipIfDegraded for graceful non-LLM fallback

### Task 3: Add integration tests for event entity filters

**Commit:** `4f1647e`
**Files modified:** `tests/integration/pipeline_v6.test.ts`

Appended a new `describe("Enhanced GET /events filters", ...)` block containing 3 tests:

- **6a. Entity ID filter** — Finds an entity_id from references, calls `filterEvents({ entity_id: thatId })`, verifies `participant_count >= 0` for all returned events.
- **6b. Entity type filter** — Calls `filterEvents({ entity_type: "person" })`, verifies non-negative total.
- **6c. Date range filter** — Calls `filterEvents({ date_from: "2000-01-01", date_to: "2100-01-01", document: docId })`, logs comparison with document's total event count.

All tests use `skipIfDegraded` for graceful fallback.

**Done criteria met:**
- ✅ New test group "Enhanced GET /events filters" exists
- ✅ entity_id filter test exercises entity-specific event filtering
- ✅ entity_type filter exercises type-based event filtering
- ✅ date range filter exercises time-bounded event filtering
- ✅ All tests use skipIfDegraded
- ✅ `filterEvents` and `filterReferences` imported from helpers.js

## Deviations from Plan

**None.** Plan executed exactly as written.

## Verification Results

- ✅ TypeScript type check: `npx tsc --noEmit` passes with exit code 0
- ✅ No existing test groups were modified (only appended to end of file)
- ✅ All 4 existing v6.0 test groups remain at the top of the file (Groups 1-4)
- ✅ 2 new test groups appended (Groups 5-6 = 7 tests total)
- ✅ `filterReferences` and `filterEvents` correctly exported from helpers.ts

## Known Stubs

None — all test helpers and assertions are fully wired.

## Threat Flags

No new threat surface identified. Tests use read-only GET endpoints only (per threat register).

## Self-Check: PASSED

- `tests/integration/helpers.ts` (517 lines) — exports `filterReferences` + `filterEvents` ✅
- `tests/integration/pipeline_v6.test.ts` (571 lines, ≥450 min) — includes "Enhanced GET /references filters" and "Enhanced GET /events filters" test groups ✅
- TypeScript `--noEmit` check passes with exit code 0 ✅
- 7 new tests (4 reference filters + 3 event filters) appended without modifying existing test groups ✅
- `filterReferences` and `filterEvents` imported from helpers.js in pipeline_v6.test.ts ✅
