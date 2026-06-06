---
phase: 27-references-ui
plan: 01
type: execute
subsystem: backend
tags: [api, model, references, context-excerpt, page-offset]
dependency_graph:
  requires: []
  provides: [27-02]
  affects: [reference-list-response]
tech-stack:
  added: []
  patterns:
    - "Computed context_excerpt from document text_content using span start/end offsets"
    - "Context excerpt truncation with 80-char padding before/after verbatim span"
key-files:
  modified:
    - src/eth_pipeline/api/models.py
    - src/eth_pipeline/api/routes/references.py
decisions:
  - "Context excerpt uses 80 chars before and 80 chars after the verbatim span"
  - "Excerpt is null when document text_content is unavailable (graceful fallback)"
  - "Context excerpt prefixes/suffixes with '...' when truncated"
metrics:
  duration: ~5 min
  completed_date: 2026-06-06
---

# Phase 27 Plan 01: Backend - ReferenceListItem Model & Context Excerpt Computation

**One-liner:** Added `page_offset_start`, `page_offset_end`, and computed `context_excerpt` fields to the `ReferenceListItem` model and `list_references` query for the References tab's Contexto and Página/Offset columns.

## Tasks Completed

### Task 1: Add page_offset_start, page_offset_end, context_excerpt to ReferenceListItem model

- Added three optional fields to `ReferenceListItem` after `page_number`:
  - `page_offset_start: int | None = None`
  - `page_offset_end: int | None = None`
  - `context_excerpt: str | None = None`
- Each field has a docstring comment documenting its purpose

### Task 2: Compute context_excerpt and map page_offset fields in list_references query

- Added `d.text_content AS doc_text_content` to the data SQL SELECT
- Added context_excerpt computation in the record loop: extracts ~80 chars before/after the verbatim span from the document's text_content, with "..." ellipsis markers at truncation boundaries
- Mapped `page_offset_start`, `page_offset_end`, and `context_excerpt` to the `ReferenceListItem` constructor

## Verification

- **Model schema check PASSED**: `page_offset_start`, `page_offset_end`, `context_excerpt` all present in JSON schema with correct types
- **Import check PASSED**: `list_references` imports cleanly
- All 3 new fields verified in `ReferenceListItem.model_json_schema()`

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check: PASSED

All verification criteria met. Model serializes correctly with new fields.
