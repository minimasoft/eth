---
status: complete
completion_date: 2026-06-04
commit: TBD
---

# Summary: Fix 404 on /documents/{id}/logs API route

**Quick Task:** 260604-mex
**Status:** Complete

## What was done

Restored the `GET /documents/{document_id}/logs` route handler that was accidentally deleted in commit `232413e` (feat(20): token aggregation endpoints). The handler was recovered verbatim from commit `7bfee64`.

- Added `get_document_logs` route back to `src/eth_pipeline/api/routes/documents.py`
- Queries `document_event_log` table with pagination (50 per page, newest first)
- Checks document existence first → returns 404 if doc not found
- All imports were already in place
