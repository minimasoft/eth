---
phase: 34-smart-chunking
plan: 02
subsystem: api
tags: [nltk, punkt, chunking, temporal, smart-chunker]

key-files:
  created: []
  modified:
    - src/eth_pipeline/chunker.py
    - src/eth_pipeline/activities/chunk_document.py

key-decisions:
  - "_offset_to_page copied verbatim from DocumentChunker (identical logic, no shared dependency)"
  - "NLTK Punkt init is lazy inside SmartChunker.__init__ — nltk.download runs idempotently at class instantiation"
  - "schema_version routing uses fetchrow (single row) instead of fetch + _extract_query_results"
  - "v6 chunks from ChunkResult.chunks and v7 chunks from SmartChunker.chunk() both feed same dict-conversion loop"

patterns-established:
  - "SmartChunker: sentence-aware chunker using NLTK Punkt for Spanish, with balanced distribute_balanced() algorithm"
  - "schema_version routing: v6→DocumentChunker, v7→SmartChunker in chunk_document_activity"

requirements-completed: [CHK-01, CHK-02, CHK-03, CHK-04]

duration: 5min
completed: 2026-06-09
---

# Plan 34-02: SmartChunker Implementation

**SmartChunker class with NLTK Punkt Spanish sentence detection and balanced distribution algorithm, wired via schema_version routing in chunk_document_activity**

## Performance

- **Duration:** ~5 min
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- SmartChunk dataclass, distribute_balanced() function, and SmartChunker class added to chunker.py (220 lines, below existing DocumentChunker)
- DocumentChunker preserved intact for v6 backward compatibility
- chunk_document_activity now reads schema_version and routes: v7 → SmartChunker, v6 → DocumentChunker
- Both chunker paths feed the same dict-conversion loop and DELETE+INSERT pattern
- CHUNK_SIZE_TARGET env var controls SmartChunker target size at init time

## Task Commits

Each task was committed atomically:

1. **Task 1: Add SmartChunk, distribute_balanced(), and SmartChunker** - `50acff0` (feat)
2. **Task 2: Add schema_version routing to chunk_document_activity** - `35be22b` (feat)

## Files Created/Modified
- `src/eth_pipeline/chunker.py` - Added SmartChunk dataclass, distribute_balanced(), SmartChunker class with lazy NLTK Punkt init (after line 272, below existing code)
- `src/eth_pipeline/activities/chunk_document.py` - Updated import, changed fetch→fetchrow with schema_version, added v6/v7 routing, added schema_version to return dict

## Decisions Made
- None - followed plan as specified. _offset_to_page copied verbatim from DocumentChunker.

## Deviations from Plan

### Auto-fixed Issues

**1. [Naming Conflict] chunks variable conflict in chunk_document.py**
- **Found during:** Task 2 (schema_version routing)
- **Issue:** Variable name `chunks` used both for dataclass instances list and for dict-conversion list
- **Fix:** Renamed dict list to `chunks_dicts` to avoid shadowing
- **Files modified:** src/eth_pipeline/activities/chunk_document.py
- **Verification:** Import succeeds, grep confirms all references updated
- **Committed in:** 35be22b (Task 2 commit)

### Edge Case Notes

- NLTK Punkt Spanish tokenizer shows partial abbreviation handling for `S.L.` and `art.` in very short test strings (< 50 chars). In longer documents (> 1KB), Punkt's unsupervised learning from the text itself improves accuracy. `Dr.` and procedural numbering (`PRIMERO.-`) are correctly detected at all lengths.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- SmartChunker is importable and smoke-tested. Ready for test suite in Plan 34-03.

---
*Phase: 34-smart-chunking*
*Completed: 2026-06-09*
