---
status: complete
completion_date: 2026-06-08
commit: 3805f10
---

## Summary

Fixed the llm-calls endpoint returning empty and added integration test coverage.

### Problem

Two bugs caused every `llm_call_log` INSERT to fail silently:

1. **Missing `chunk_index` column** in `llm_call_log` table DDL — the INSERT referenced it but the column didn't exist in schema.sql
2. **Timestamp type mismatch** — `record_llm_call_log` called `.isoformat()` on the datetime, producing a string, but asyncpg requires a Python `datetime` object for `TIMESTAMPTZ` columns

Both errors were caught by `except Exception` in the fire-and-forget recorder and logged at WARNING level — no records were ever written.

### Changes

- `llm_call_recorder.py`: Pass `datetime.now(timezone.utc)` directly (without `.isoformat()`)
- `schema.sql`: Added `chunk_index` to DDL + `ALTER TABLE ADD COLUMN IF NOT EXISTS` migration
- `helpers.ts`: Added `LlmCallLogListItem`, `LlmCallLogListResponse` interfaces and `listLlmCallLogs()` helper
- `e2e_pipeline.test.ts`: Added Test 3b asserting `total > 0` LLM call log entries

### Verification

Created a test document after fix: llm-calls endpoint returned 2 entries (extract_events + resolve_entities_with_search) with full prompt/response text, tokens, cost, and duration.
