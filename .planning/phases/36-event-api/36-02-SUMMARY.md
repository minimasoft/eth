---
phase: 36-event-api
plan: 02
subsystem: api
tags: [fastapi, asyncpg, pydantic, postgresql, events, v7]

# Dependency graph
requires:
  - phase: 36-01
    provides: Pydantic models (EventV2ListItem, EventV2DetailResponse, EventListV2Response, EventLocationDetail, EventParticipantDetail, EventRefDetail, ChunkTextResponse)
  - phase: 33-foundation
    provides: event_v2, event_location, event_participant_v2, event_ref PostgreSQL tables
provides:
  - GET /events v7 paginated event list with filter/search/sort
  - GET /events/{event_id} full event detail with resolved child records
affects: [37-event-ui]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "FastAPI router with last-registered-wins shadowing for API path migration"
    - "$N parameterized SQL with dynamic WHERE construction and sort-column whitelist"

key-files:
  created:
    - src/eth_pipeline/api/routes/events_v2.py
  modified:
    - src/eth_pipeline/api/__init__.py

key-decisions:
  - "Router registered AFTER events_router — FastAPI last-registered-wins shadows old /events path with v2 router"
  - "Sort column whitelist (time_start, time_end, created_at, title) prevents SQL injection in ORDER BY"
  - "Detail endpoint uses 4 separate asyncpg queries (event, locations, participants, references) — no N+1 loops"

patterns-established:
  - "events_v2.py follows exact events.py pattern for imports, router, dynamic WHERE, $N params, pagination math"
  - "Detail endpoint follows entities.py pattern for multi-query fetch + 404 guard + except HTTPException: raise"

requirements-completed: [API-01, API-02]

# Metrics
duration: 3 min
completed: 2026-06-09
---

# Phase 36 Plan 02: Events v2 Route + Registration Summary

**GET /events v7 paginated event list and GET /events/{event_id} detail endpoint with resolved child records on events_v2 table**

## Performance

- **Duration:** 3 min
- **Started:** 2026-06-09T19:57:04Z
- **Completed:** 2026-06-09T20:00:16Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- `events_v2.py` created with `list_events_v2` (API-01) — paginated v7 event list with dynamic WHERE, ILIKE search on title, document_id filter, sort-column whitelist, $N parameterized queries for SQL injection prevention
- `get_event_v2_detail` (API-02) — full event detail with 4 separate queries (event core + locations + participants + references), 404 handling, HTTPException guard
- Router registered in `api/__init__.py` AFTER `events_router` — FastAPI last-registered-wins shadows old `/events` path
- 7 new model names added to `api/__init__.py` re-exports

## Task Commits

Each task was committed atomically:

1. **Task 1: Create events_v2.py with API-01 paginated event list endpoint** - `1798219` (feat)
2. **Task 2: Add API-02 event detail endpoint + register router in api/__init__.py** - `7f2a87c` (feat)

## Files Created/Modified

- `src/eth_pipeline/api/routes/events_v2.py` — New route file with `list_events_v2` (API-01) and `get_event_v2_detail` (API-02), router tagged "Events V2"
- `src/eth_pipeline/api/__init__.py` — Added events_v2_router import and registration; added 7 model re-exports (ChunkTextResponse, EventListV2Response, EventLocationDetail, EventParticipantDetail, EventRefDetail, EventV2DetailResponse, EventV2ListItem)

## Decisions Made

- Router registered AFTER events_router (last-registered-wins shadows old `/events` path with v2 router) — per plan specification
- Sort column whitelist `{"time_start", "time_end", "created_at", "title"}` — non-whitelisted values default to "time_start"
- Detail endpoint runs 4 separate asyncpg queries (fetchrow for event, fetch for locations/participants/references) — no N+1 loops, follows entities.py detail pattern
- All user-supplied values use `$N` asyncpg parameterized placeholders — no string interpolation in WHERE values
- `except HTTPException: raise` guard present before generic `except Exception` for 502 — prevents the 404 from being swallowed

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## Known Stubs

None — both endpoints are fully implemented with parameterized SQL, error handling, and proper model mapping.

## Threat Flags

No new threat surface beyond what the plan's `<threat_model>` covers. All 5 threat mitigations (T-36-01 through T-36-04, T-36-SC) are implemented:
- T-36-01: Sort column whitelist `allowed_sorts` prevents injection in ORDER BY
- T-36-02: `$N` parameterized placeholders for all user values (ILIKE, document_id, event_id)
- T-36-03: `per_page: ge=1, le=100` hard cap prevents resource exhaustion
- T-36-04: Generic `HTTPException(502)` on DB errors — no SQL text, stack traces, or column names leak to response

## Next Phase Readiness

- GET /events and GET /events/{event_id} endpoints ready for Phase 37 Event UI
- Routes registered and importable — API server can serve these endpoints
- Ready for Plan 03 (chunk text endpoint) and Plan 04 (rename /events-old)

---

*Phase: 36-event-api*
*Completed: 2026-06-09*
