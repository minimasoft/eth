# Audit: Single Source of Truth for Chunk Sizing (260905-jsy)

Date: 2026-09-05

## 1. Single-chunker check

`grep -rn "SmartChunker" src/`

**Result: PASS.** Exactly one construction site:
- `src/eth_pipeline/activities/chunk_document.py:40` → `SmartChunker()` constructed bare,
  no explicit `target_size`, so it honors `CHUNK_SIZE_TARGET` env at init
  (chunker.py:148-151). No other construction with a literal `target_size` exists.
  All other matches are definitions/docstrings inside `chunker.py` itself.

## 2. No second chunk-size constant

`grep -rniE "chunk.?size|target.?size" src/ | grep -v "CHUNK_SIZE_TARGET"`

**Result: PASS.** Only `chunker.py` `target_size` parameter plumbing (function
params, `self.target_size`, `distribute_balanced` internal use) and prose
docstrings. No numeric literal (400_000, 512_000, 128_000, …) used as a chunk
size anywhere. The dead duplicate `EXTRACTION_CHUNK_SIZE = 400_000` was deleted
from `llm.py` in Task 1 (commit ffc74e8). (Only stale `.pyc` bytecode files
matched — not source; regenerated on next run.)

## 3. Env plumb-through check

`grep -n "CHUNK_SIZE_TARGET" docker-compose.yml`

**Result: PASS.** Both services declare it:
- Line 125 (api service): `CHUNK_SIZE_TARGET: ${CHUNK_SIZE_TARGET:-262144}`
- Line 156 (worker service): `CHUNK_SIZE_TARGET: ${CHUNK_SIZE_TARGET:-262144}`

The **worker** (line 156) is the container that actually chunks
(`chunk_document_activity` runs there) — confirmed present, so no silent
fallback to a stale baked-in default.

## 4. Consumer check

**Result: PASS.** `extract_events_v7.py` and `workflows.py` contain no
chunk-size computation (grep for `chunk_size|target_size|CHUNK_SIZE` returns
nothing in either file). They iterate `document_chunk` table rows produced by
the chunker — the env-driven default flows: docker-compose worker env →
`SmartChunker()` init → `document_chunk` rows → per-chunk `extract_events_v7`
LLM calls.

## 5. Full unit suite

`./test.sh --unit -q` — **PASS** (see SUMMARY for counts).

## Conclusion

`CHUNK_SIZE_TARGET` is the single chunk-size control: code default 262144
(`SmartChunker.DEFAULT_TARGET`), docker-compose default 262144 in both
services, `.env`/`.env.example`/README document 262144. No hardcoded
duplicates remain in `src/`. No fixes required by the audit.
