---
phase: 31-llm-call-api-endpoint
reviewed: 2026-06-08T15:30:00Z
depth: deep
files_reviewed: 2
files_reviewed_list:
  - src/eth_pipeline/api/models.py
  - src/eth_pipeline/api/routes/documents.py
findings:
  critical: 0
  warning: 0
  info: 1
  total: 1
status: clean
---

# Phase 31: LLM Call API Endpoint — Code Review Report

**Reviewed:** 2026-06-08T15:30:00Z
**Depth:** deep
**Files Reviewed:** 2
**Status:** clean

## Summary

Reviewed the `GET /documents/{document_id}/llm-calls` endpoint implementation and its corresponding Pydantic response models (`LlmCallLogListItem`, `LlmCallLogListResponse`). The implementation faithfully follows the `get_document_logs` template pattern and implements all 9 CONTEXT.md decisions (D-01 through D-09). All queries use parameterized SQL (`$1`, `$2`, `$3`) — no injection vectors. Error handling is consistent with existing endpoints. No bugs, security vulnerabilities, or logic errors found.

### Cross-check against plan success criteria

| # | Criterion | Status |
|---|-----------|--------|
| 1 | `LlmCallLogListItem` and `LlmCallLogListResponse` models with 13 fields + envelope | ✅ |
| 2 | `GET /documents/{document_id}/llm-calls` endpoint defined | ✅ |
| 3 | Models import successfully | ✅ |
| 4 | All 9 D-NN decisions implemented | ✅ |
| 5 | Missing document returns 404 | ✅ |
| 6 | Empty document returns `pages=1`, not 404 | ✅ |
| 7 | Results ordered by timestamp ASC | ✅ |
| 8 | per_page capped at 100 via Query validator | ✅ |
| 9 | DB errors return 502 with "Failed to query database." | ✅ |

### Cross-check against CONTEXT.md decisions

| Decision | Implementation | Status |
|----------|---------------|--------|
| D-01: Include full prompt_text and response_text | `LlmCallLogListItem.prompt_text` / `.response_text` mapped from DB row | ✅ |
| D-02: Sort by timestamp ASC | `ORDER BY timestamp ASC` at line 625 | ✅ |
| D-03: Default per_page=20 | `Query(20, ge=1, le=100)` at line 566 | ✅ |
| D-04: Max per_page=100 | `Query(..., le=100)` at line 566 | ✅ |
| D-05: No extra filter params | Signature has only `document_id`, `page`, `per_page` | ✅ |
| D-06: Missing doc → 404 | Lines 587-592 raise `HTTPException(404)` | ✅ |
| D-07: DB error → 502 | All three try/except blocks raise `HTTPException(502)` | ✅ |
| D-08: Empty → `pages=1` | Line 615: `pages = 1` when `total == 0` | ✅ |
| D-09: per_page capped at 100 | Same as D-04 via Query validator | ✅ |

## Findings

No critical or warning issues were found. The implementation is correct, secure, and follows established patterns.

### Info

#### IN-01: Root API info endpoint missing `/documents/{document_id}/llm-calls` entry

**File:** `src/eth_pipeline/api/routes/documents.py:56`
**Issue:** The root API info endpoint (lines 48-68) returns an `endpoints` dict that documents available API paths. The new `/documents/{document_id}/llm-calls` endpoint is not listed. The existing `/documents/{document_id}/tokens` endpoint is also absent from this list, indicating this documentation gap is a pre-existing pattern, but the new endpoint should be added for discoverability.

**Fix:** Add an entry to the `endpoints` dict in the `root()` function (around line 66, before `"/entities"`):

```python
"/documents/{document_id}/llm-calls": "Get LLM call log entries for a document (GET)",
```

## Verdict

**clean** — No blocking issues, no warnings. One minor info-level documentation gap. The implementation is complete, correct, and production-ready from a correctness and security standpoint.

---

_Reviewed: 2026-06-08T15:30:00Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: deep_
