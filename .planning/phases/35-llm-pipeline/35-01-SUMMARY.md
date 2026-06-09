---
phase: 35-llm-pipeline
plan: 01
subsystem: llm
tags: [openrouter, temporal, json-schema, v7, extraction, human-rights]

requires:
  - phase: 33-foundation
    provides: "v7 model definitions in models/v7_event.py (EventV2, EventLocation, EventParticipantV2, EventDocument, EventRef)"
  - phase: 34-smart-chunking
    provides: "document_chunk table with pre-chunked document text"
provides:
  - "EVENT_EXTRACTION_SCHEMA_V7 JSON Schema constant for LLM structured output"
  - "EVENT_EXTRACTION_V7_SYSTEM_PROMPT with human rights research framing"
  - "OpenRouterProvider._build_v7_payload() and extract_events_v7() methods"
  - "extract_events_v7_activity Temporal activity with refusal detection"
affects: [35-llm-pipeline-store, 35-llm-pipeline-workflow]

tech-stack:
  added: []
  patterns: ["HR system prompt framing for sensitive document extraction", "Refusal detection via RuntimeError catch with graceful degradation"]

key-files:
  created:
    - "src/eth_pipeline/activities/extract_events_v7.py"
    - "tests/test_extract_events_v7.py"
  modified:
    - "src/eth_pipeline/llm.py"

key-decisions:
  - "temperature=0.0 for v7 extraction (vs 0.7 for v6) to minimize output variation and cost on replays"
  - "Non-JSON LLM responses treated as refusals (degraded result) rather than crashing the activity"

patterns-established:
  - "V7 extraction uses HR system prompt framing to prevent safety filter refusals on sensitive documents"
  - "Refusal detection catches RuntimeError with 'refusal', 'empty content', or 'non-json' keywords"

requirements-completed: ["PIP-03", "PIP-05"]

duration: TBD
completed: 2026-06-09
---

# Phase 35 Plan 01: v7 Extraction Schema & Activity Summary

**New v7 extraction schema, HR system prompt, OpenRouterProvider v7 methods, and extract_events_v7_activity with refusal-detection graceful degradation.**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-06-09T09:11:00Z
- **Completed:** 2026-06-09T09:26:00Z
- **Tasks:** 3
- **Files modified:** 2 created, 1 modified

## Accomplishments
- EVENT_EXTRACTION_SCHEMA_V7 JSON Schema replacing old flat fields (que_paso, espacio, tiempo, humanos, objetos) with structured v7 model (title, description, time_start/end/precision, location.name/location_type, participants.name/role, references)
- EVENT_EXTRACTION_V7_SYSTEM_PROMPT framing extraction as legitimate academic research to prevent LLM safety filter refusals on human rights documents
- extract_events_v7_activity Temporal activity with refusal-detection graceful degradation and LLM usage/call log recording
- 5 passing unit tests + slow corpus test for HR prompt refusal verification

## Task Commits

1. **Task 1: v7 schema, HR prompt, provider methods** - `b60fd66` (feat)
2. **Task 2: extract_events_v7_activity with tests** - `a6124b9` (feat)
3. **Task 3: HR prompt refusal spike checkpoint** - User-approved, no modifications needed

## Files Created/Modified
- `src/eth_pipeline/llm.py` - Added EVENT_EXTRACTION_SCHEMA_V7, EVENT_EXTRACTION_V7_SYSTEM_PROMPT, _build_v7_payload, extract_events_v7
- `src/eth_pipeline/activities/extract_events_v7.py` - New Temporal activity with refusal handling and usage recording
- `tests/test_extract_events_v7.py` - 5 unit tests + 1 slow corpus test

## Decisions Made
- V7 extraction uses `temperature=0.0` (vs v6's 0.7) for deterministic replays and cost control
- RuntimeError with "non-json" keyword is caught as degraded result — non-JSON LLM output treated like a refusal

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## Next Phase Readiness
- Ready for Plan 35-02: store_events_v7_activity and resolve_references_v7_activity
- extract_events_v7_activity is importable and tested; ready to be wired into workflow

---
*Phase: 35-llm-pipeline*
*Completed: 2026-06-09*
