---
status: complete
completion_date: 2026-06-08
commit: PLACEHOLDER
---

## Summary

Added an LLM call log integration test and fixed the root cause of the empty endpoint.

### Problem

The `/documents/{id}/llm-calls` endpoint always returned 0 entries because the `llm_call_log` table was missing the `chunk_index` column. The `record_llm_call_log()` INSERT statement references `chunk_index` at position $4, but the DDL in `schema.sql` never included it. The INSERT silently failed (caught by `except Exception` in the fire-and-forget recorder) — no records were ever written.

### Changes

1. **schema.sql** — Added `chunk_index INTEGER NOT NULL DEFAULT 0 CHECK (chunk_index >= 0)` to the `llm_call_log` CREATE TABLE. Added an `ALTER TABLE ADD COLUMN IF NOT EXISTS` migration for existing databases.

2. **helpers.ts** — Added `LlmCallLogListItem`, `LlmCallLogListResponse` interfaces and `listLlmCallLogs()` helper function.

3. **e2e_pipeline.test.ts** — Added Test 3b ("LLM call log — endpoint returns recorded calls") that asserts `total > 0` and logs activity types present.
