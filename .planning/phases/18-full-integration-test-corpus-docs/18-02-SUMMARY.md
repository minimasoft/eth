---
phase: 18-full-integration-test-corpus-docs
plan: 02
subsystem: docs
tags: [readme, documentation, v4.0, architecture, audit-trail, processing-logs]

requires:
  - phase: 13-schema-evolution
    provides: v4.0 schema DDL (reference offsets fields, document_event_log table, event entity_type)
  - phase: 14-reference-offset-computation
    provides: deterministic page/character offset computation in store_extraction_results_activity
  - phase: 15-per-document-processing-logs
    provides: append-only audit log entries per document processing run
  - phase: 16-event-canonical-entities
    provides: event-type canonical entities with RELATE graph edges
  - phase: 17-search-first-entity-resolution
    provides: search-first entity resolution with exact/fuzzy match, LLM call reduction
provides:
  - Updated README.md with v4.0 feature documentation covering all 5 v4.0 subsystems
  - Full pipeline documentation: blob → text → chunks → events → references → canonical entities
  - Processing Logs endpoint documentation with severity/activity tables
  - 6-layer Audit Trail documentation with traceability guarantees
affects: [future phases needing README references or onboarding docs]

tech-stack:
  added: []
  patterns: []
key-files:
  modified:
    - README.md — Updated from 417 to 595 lines with v4.0 feature docs, architecture diagram, audit trail

key-decisions:
  - "" — Structured the v4.0 Features section as subsections with forward links to the full Processing Logs and Audit Trail sections to avoid duplication
  - "" — Used GitHub-compatible TOC anchors (collapsed-dash format for Architecture & Data Flow heading)

requirements-completed: [TEST-04, TEST-05]

duration: 2min
completed: 2026-06-03
---

# Phase 18: Full Integration + Test Corpus + Docs — Plan 02 Summary

**Updated README.md (417→595 lines) with v4.0 architecture diagram, data flow, feature docs, processing logs, and 6-layer audit trail documentation**

## Performance

- **Duration:** 2 min
- **Completed:** 2026-06-03
- **Tasks:** 2
- **Files modified:** 1

## Accomplishments

- Updated architecture mermaid diagram to show MinIO blob storage, chunk pipeline, offset computation, search-first resolution, and processing logs
- Expanded data flow from 4 to 6 steps: Ingest → Extract Text → Chunk → Extract Events → Resolve → Query
- Added v4.0 Features section with 4 subsections: Reference Offsets, Processing Logs, Event Canonical Entities, Search-First Entity Resolution
- Added full Processing Logs section with endpoint docs, example response, severity levels table, logged activities table, and replay safety documentation
- Added Audit Trail section documenting all 6 layers (Blob → Text → Chunks → Events → References → Canonical Entities) with storage, recording activity, and traceability guidance for each
- Added 3 new entries to the Table of Contents
- Added `/documents/{document_id}/logs` to the API endpoints list
- Updated Key Patterns with search-first resolution and deterministic offsets patterns; updated audit trail pattern to include v4.0 steps

## Task Commits

1. **Task 1: Update architecture diagram and add v4.0 Features section** — `5aa8cd6`
2. **Task 2: Add Processing Logs section and audit trail documentation** — `5aa8cd6`

**Plan metadata:** `5aa8cd6` (docs(18): update README with v4.0 features and audit trail)

## Files Created/Modified

- `README.md` — Updated from 417 to 595 lines: mermaid diagram, data flow, v4.0 features, processing logs, audit trail, ToC, endpoints list

## Decisions Made

- Structured v4.0 Features section as brief subsections with forward links to the full Processing Logs and Audit Trail sections, avoiding content duplication
- Used collapsed-dash anchor (`#architecture-data-flow`) for the Architecture & Data Flow TOC link to match GitHub's anchor generation

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None.

## Next Phase Readiness

- README.md now serves as a single source of truth for understanding the complete pipeline from blob ingest to GraphQL query
- All v4.0 enhancements (reference offsets, processing logs, event entities, search-first resolution) are documented
- No further README updates expected in this phase

## Self-Check: PASSED

- [x] SUMMARY.md exists
- [x] Commit 5aa8cd6 exists
- [x] README.md > 500 lines (595 lines)

---

*Phase: 18-full-integration-test-corpus-docs*
*Completed: 2026-06-03*
