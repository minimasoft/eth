# Quick Plan 260604-mex: Fix 404 on /documents/{id}/logs API route

**Mode:** quick
**Slug:** fix-404-on-documents-id-logs-api-route-r
**Date:** 2026-06-04

## Tasks

### Task 1: Add missing route handler for GET /documents/{document_id}/logs

- **files:** `src/eth_pipeline/api/routes/documents.py`
- **action:** Add a `GET /documents/{document_id}/logs` route handler that queries the `document_event_log` table with pagination (50 per page) and returns `ProcessingLogListResponse`. Follow the existing pattern from other routes (check db availability, use RecordID, paginate with LIMIT/START, handle errors).
- **verify:** Route handler exists at `@router.get("/documents/{document_id}/logs")` with `response_model=ProcessingLogListResponse`. Existing imports cover all needed symbols. File passes `ruff check` and `pyright`.
- **done:** Route handler added and lint passes.
