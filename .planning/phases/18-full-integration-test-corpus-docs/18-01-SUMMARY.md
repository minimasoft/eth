---
phase: 18
plan: 01
subsystem: integration-tests
tags:
  - test-fixtures
  - integration-tests
  - spanish-legal-documents
  - v4.0
---

# Phase 18 Plan 01: Test Fixtures + Integration Tests — Summary

Added Spanish legal document test fixtures and v4.0 integration tests for all new features.

## Tasks

| Task | Name | Files |
|------|------|-------|
| 1 | Add test fixtures | `test_data/sample_civil_case.txt`, `test_data/sample_multi_page_document.txt` |
| 2 | Create v4.0 integration tests | `tests/integration/pipeline_v4.test.ts` (834 lines, 6 describe blocks) |

## Test Fixtures

- `sample_civil_case.txt` (49 lines) — Contract breach dispute (Barcelona, 500 units MT-3000, €75k)
- `sample_multi_page_document.txt` (97 lines) — 3-page fraud investigation (Valencia, false bank guarantee, €120k) with page markers

## Integration Test Coverage

| Test Group | What It Verifies |
|------------|-----------------|
| Offset verification | page_number, page_offset_start/end populated correctly on references |
| Processing logs | GET /documents/{id}/logs returns entries with expected step_names and severities |
| Event entities | canonical_entity records with entity_type='event' exist after processing |
| Search-first resolution | entity_id populated on references (not null) |

## Python Test Results: 88/88 pass
