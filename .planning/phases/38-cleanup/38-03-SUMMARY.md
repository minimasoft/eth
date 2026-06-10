---
phase: 38-cleanup
plan: 03
subsystem: activities, workflows, api
tags: [cleanup, activities, workflows, chunker, api]

requires:
  - phase: 38-01
    provides: old v6 tables dropped
  - phase: 38-02
    provides: old API routes and models removed
provides:
  - Clean activity module with only v7+shared entries
  - Single DocumentProcessingV7Workflow for Temporal pipeline
  - Clean chunker with only SmartChunker infrastructure
  - Clean documents.py with no old-table references

tech-stack:
  added: []
  patterns: []

key-files:
  created: []
  modified:
    - src/eth_pipeline/activities/__init__.py
    - src/eth_pipeline/activities/_common.py
    - src/eth_pipeline/activities/chunk_document.py
    - src/eth_pipeline/api/routes/documents.py
    - src/eth_pipeline/chunker.py
    - src/eth_pipeline/worker.py
    - src/eth_pipeline/workflows.py
  deleted:
    - src/eth_pipeline/activities/extract_events.py
    - src/eth_pipeline/activities/resolve_entities.py
    - src/eth_pipeline/activities/resolve_entities_with_search.py
    - src/eth_pipeline/activities/store_extraction_results.py
    - src/eth_pipeline/activities/create_event_canonical_entities.py
    - scripts/cleanup_orphan_entities.py
    - scripts/cleanup_orphan_references.py

key-decisions:
  - "7 old files deleted, 7 files edited — no deprecated code survives"
  - "DocumentProcessingWorkflow fully removed; all new documents use DocumentProcessingV7Workflow"
  - "DocumentChunker, ChunkResult, chunk_document() removed; only SmartChunker remains"
  - "delete_document endpoint simplified to only clean surviving tables"
  - "clear_document_events endpoint removed entirely"

patterns-established: []

requirements-completed: ["CLN-02"]

duration: 15min
completed: 2026-06-10
---

# Phase 38-03: Old Activities and Workflows Cleanup Summary

**Deleted 7 old files, cleaned 7 edited files — deprecated activity, workflow, chunker, and API code fully removed**

## Performance

- **Duration:** 15 min
- **Tasks:** 3
- **Files modified:** 7
- **Files deleted:** 7

## Accomplishments
- Deleted 5 old v6 activity Python files (extract_events, resolve_entities, resolve_entities_with_search, store_extraction_results, create_event_canonical_entities)
- Deleted 2 orphan-cleanup scripts targeting dropped tables (cleanup_orphan_entities, cleanup_orphan_references)
- Cleaned activities/__init__.py — only v7+shared activity imports remain
- Removed _create_canonical_entity and _normalize from _common.py (inserted into dropped canonical_entity table)
- Cleaned chunk_document.py — only SmartChunker import (no DocumentChunker old-path)
- Removed DocumentProcessingWorkflow class (~200 lines) from workflows.py — only DocumentProcessingV7Workflow remains
- Removed DocumentChunker (~160 lines), ChunkResult, and chunk_document() from chunker.py — only SmartChunker/SmartChunk/DocumentChunk remain
- Cleaned documents.py delete_document — removed ~260 lines of old-table orphan cleanup, added v7 event table cleanup
- Removed clear_document_events endpoint (~110 lines, referenced dropped tables and deleted EventsCleared model)
- Removed old workflow/activity registrations from worker.py

## Verification Results
- All v7 activities importable: chunk_document_activity, extract_events_v7_activity, store_events_v7_activity, resolve_references_v7_activity
- V7 workflow importable: DocumentProcessingV7Workflow
- Chunker OK: SmartChunker, SmartChunk, DocumentChunk importable
- FastAPI app starts: documents.py cleaned successfully, DocumentDeleted with 2 args works
- Old symbols raise ImportError: DocumentChunker, DocumentProcessingWorkflow
- No remaining references to old activities in codebase

## Next Phase Readiness
- Phase 38 all plans complete — ready for verification
- Migration 0002 applied, old tables dropped (38-01)
- Old routes and models removed (38-02)
- Old UI tabs removed, event count added (38-04)
- All deprecated code fully purged