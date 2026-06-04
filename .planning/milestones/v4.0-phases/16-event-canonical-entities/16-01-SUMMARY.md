---
phase: 16-event-canonical-entities
plan: 01
subsystem: event-pipeline
tags:
  - canonical-entity
  - event-entity
  - graph-links
  - entity-linking
  - workflow-integration
dependency_graph:
  requires:
    - "Phase 13 (event_entity_link schema)"
    - "Phase 14 (reference offset fields)"
    - "Phase 7 (PDF extraction + chunking)"
  provides:
    - "canonical_entity records with entity_type='event'"
    - "event_entity_link graph edges to place/person/object entities"
  affects:
    - "activities.py — new activity"
    - "workflows.py — new workflow step (Step 7)"
    - "worker.py — new activity registration"
    - "static/index.html — new filter option"
    - "tests/test_event_entities.py — new test file"
tech-stack:
  added: []
  patterns:
    - "Nullify-then-recreate for replay-safe event entity creation"
    - "CONTAINS-based matching (both directions) for entity linking"
    - "Pure function extraction for unit-testable activity logic"
key-files:
  created:
    - "tests/test_event_entities.py"
  modified:
    - "src/eth_pipeline/activities.py"
    - "src/eth_pipeline/workflows.py"
    - "src/eth_pipeline/worker.py"
    - "src/eth_pipeline/static/index.html"
decisions: []
metrics:
  duration: "~20 minutes"
  completed_date: "2026-06-03"
---

# Phase 16 Plan 01: Event Canonical Entities Summary

Created canonical entities of type "event" from extracted events, with structured properties and RELATE graph edges to place/person/object entities, integrated into the Temporal workflow after store_results / before entity resolution.

**One-liner:** Event entities as first-class canonical_entity records with nullify-then-recreate replay safety, CONTAINS-based graph linking to place/person/object entities, and workflow integration between store_results and resolve_entities.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create `create_event_canonical_entities_activity` | `3b173c8` | `src/eth_pipeline/activities.py` |
| 2 | Integrate into workflow + worker | `4756d3e` | `src/eth_pipeline/workflows.py`, `src/eth_pipeline/worker.py` |
| 3 | Add Event option to entity type filter dropdown | `4ec1d3d` | `src/eth_pipeline/static/index.html` |
| 4 | Unit tests | `e3d0fbc` | `tests/test_event_entities.py` |

## Implementation Details

### Task 1 — Activity (activities.py)

New `@activity.defn` function `create_event_canonical_entities_activity(document_id, result) -> dict` following the same pattern as `resolve_entities_activity`:

- **Nullify step (per D-03):** Deletes existing `event_entity_link` records first (foreign-key order), then deletes `canonical_entity` records WHERE `entity_type = 'event' AND properties.document_id = $doc_id`
- **Event query:** `SELECT * FROM event WHERE document = $doc_ref` — same pattern as other activities
- **Per-event entity creation:** `CREATE canonical_entity CONTENT { name, entity_type: 'event', properties } RETURN id`
- **Entity naming:** `"Event: {que_paso[:80].strip()}..."` — first 80 chars, strip, append "..." if truncated
- **Properties dict:** `title` (que_paso[:80]), `description` (full que_paso), `time_range` (tiempo), `location` (espacio), `participants` (humanos), `objects` (objetos), `document_id`
- **RELATE edges (per D-05):** For each event text field (espacio→place/humanos→person/objetos→object), queries `canonical_entity` WHERE `name CONTAINS $value` AND `$value CONTAINS name` (both directions), creates `event_entity_link` records with `relationship_type: 'involves'`, role, and `confidence: 0.7`
- **Skip if no events:** Early return `{"events_processed": 0, "entities_created": 0, "links_created": 0}`
- **Error handling:** try/except for ConnectionError and Exception, ProcessingLogger log entries

### Task 2 — Workflow + Worker Integration

**workflows.py:**
- Added `create_event_canonical_entities_activity` to import block inside `workflow.unsafe.imports_passed_through()`
- Inserted new Step 7 between Step 6 (store_extraction_results) and Step 8 (resolve_entities)
- Fixed duplicate "Step 5" comment numbering and renumbered all subsequent steps
- Updated `run()` docstring to reflect new 11-step sequence

**worker.py:**
- Added `activities.create_event_canonical_entities_activity` to Worker activities list

### Task 3 — UI Dropdown

- Added `option value="event"` to entity-type-filter `<select>` after the Object option
- No other UI changes needed per UI-SPEC.md: entity list, type label, search, pagination all work for event entities automatically

### Task 4 — Unit Tests

- 32 tests in `tests/test_event_entities.py`, all pure in-memory (no SurrealDB)
- Helper functions: `_build_event_entity_name`, `_build_event_properties`, `_nullify_condition`, `_should_link`, `_map_reference_type_to_role`
- Test categories: naming (7 tests), properties mapping (5 tests), nullify condition (4 tests), RELATE matching (9 tests), role mapping (4 tests), integration (3 tests)

## Verification Results

| Check | Result |
|-------|--------|
| `grep -c "create_event_canonical_entities_activity" activities.py` | ✅ 5+ matches |
| `grep -c "create_event_canonical_entities_activity" workflows.py` | ✅ 3 matches (import + call + docstring) |
| `grep -c "create_event_canonical_entities_activity" worker.py` | ✅ 1 match |
| `grep -c 'value="event">Event' index.html` | ✅ 1 match |
| `pytest tests/test_event_entities.py -v -q` | ✅ 32 passed |
| `pytest tests/ -q` | ✅ 51 passed (no regressions) |

## Deviations from Plan

None — plan executed exactly as written.

## Success Criteria Fulfilled

1. ✅ `create_event_canonical_entities_activity` creates canonical_entity records with entity_type="event" and all 7 mapped properties
2. ✅ Reprocessing a document deletes old event entities scoped to document_id and recreates them (nullify-then-recreate)
3. ✅ RELATE graph edges created from event entities to matching place/person/object entities via verbatim text CONTAINS matching
4. ✅ New activity appears in workflow between store_results and resolve_entities, registered in worker
5. ✅ Entity type filter dropdown shows "Event" option
6. ✅ Existing tests pass with zero regressions (51 total)
7. ✅ All pure logic unit tests pass (32 tests, no DB required)

## Known Stubs

None.

## Threat Flags

None — all security-relevant surface was within the planned scope. Bound parameter queries per T-16-01, CONTAINS with bounded results per T-16-03.

## Key Decisions

- **Nullify via DELETE not UPDATE:** Prior event entities are deleted entirely (not marked superseded) because there is no event-entity-level merge use case yet. The DELETE includes cascade deletion of event_entity_link records.
- **CONTAINS both directions:** RELATE matching queries entity_name CONTAINS verbatim_text AND verbatim_text CONTAINS entity_name, then deduplicates. This handles both exact substring and wrapped matches.
- **Pure function extraction for testability:** Core logic (naming, properties, matching heuristic) extracted as pure functions in test file for isolated unit testing.

## Self-Check: PASSED

All files verified, all commits checked, all tests pass.
