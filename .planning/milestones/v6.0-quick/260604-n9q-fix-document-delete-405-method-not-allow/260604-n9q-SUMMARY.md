# Quick Task 260604-n9q Summary

**Description:** Fix document delete 405 Method Not Allowed error

**Date:** 2026-06-04

**Status:** complete

## Results

### Task 1: Restore delete_document endpoint ✅
Restored `DELETE /documents/{document_id}` route handler with full cascade delete logic from commit `f88e54d`. Includes proper cleanup of event_entity_link, document_chunk, reference, event, document_event_log, document, and orphaned canonical_entities.

### Task 2: Fix clear_document_events endpoint ✅
Reverted `DELETE /documents/{document_id}/events` to original behavior: clear document_chunk, reference, event, document_event_log, llm_usage, and reset document status to `pending`. No longer deletes the document record itself.

## Root Cause
Commit `7913676` (feat(19): token recording) accidentally deleted the `delete_document` function and repurposed `clear_document_events` to do full deletion — but the UI calls `DELETE /documents/{id}` (not `/events`), and the repurposed function had an undefined variable bug (`affected_ce_rids`).

## Files Changed
- `src/eth_pipeline/api/routes/documents.py` — +168 lines, -53 lines
