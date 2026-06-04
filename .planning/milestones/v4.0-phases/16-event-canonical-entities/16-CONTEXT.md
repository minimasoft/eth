# Phase 16: Event Canonical Entities - Context

**Gathered:** 2026-06-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Create canonical entities of type "event" from extracted events, with structured properties and RELATE graph edges to place/person/object entities. Integrates into the existing Temporal workflow after store_results, before entity resolution.

**What this phase delivers:**
1. New `create_event_canonical_entities_activity` — batch maps extracted events to `canonical_entity` records with `entity_type="event"`
2. Event entity properties: `time_range`, `location`, `participants`, `objects`, `que_paso`, `title`, `description`
3. RELATE graph edges (`event_entity_link` records) linking event entities to related place/person/object entities
4. Workflow integration — activity runs after `store_extraction_results_activity`, before `resolve_entities_activity`
5. Worker registration for new activity
6. Nullify-then-recreate replay safety

**NOT in scope:** LLM-powered relationship inference (EVNT-07 deferred), event-to-event relationships (deferred), Web UI changes (existing entity list already shows all types).

</domain>

<decisions>
## Implementation Decisions

### Event Entity Creation
- Single batch activity per document: `create_event_canonical_entities_activity(document_id, result)`
- Map extracted event fields directly: `que_paso` → `description`, first 80 chars → `title`, `espacio` → `location`, `tiempo` → `time_range`, `humanos` → `participants`, `objetos` → `objects`
- Nullify-then-recreate: nullify existing `canonical_entity` records where `entity_type='event'` AND properties contains the document_id, then recreate
- Entity naming: `"Event: {que_paso[:80]}..."`

### RELATE Graph Edge Linking
- Match by verbatim text: query `name LIKE $verbatim_text` on existing place/person/object entities
- Link threshold: if entity name or verbatim text fully contains the other, create a link
- Creates `event_entity_link` records with relationship_type, role, confidence

### Workflow Integration
- New activity runs after `store_extraction_results_activity`, before `resolve_entities_activity`
- Merge/split works automatically — existing endpoints accept `event` type (unified canonical_entity model)
- No blocking migration — existing documents get event entities on next reprocess
- Worker registration updated

### UI
- Existing entity list automatically shows event-type entities — no UI changes needed
- Entity type label for 'event' should be displayed as "Event" (same pattern as other types)

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/eth_pipeline/activities.py` — Template for new activity (follow existing patterns)
- `src/eth_pipeline/workflows.py` — Workflow orchestration (add new step after store_results)
- `src/eth_pipeline/worker.py` — Activity registration (add new activity)
- `src/eth_pipeline/schema.surql` — `event_entity_link` table already defined (Phase 13)
- `src/eth_pipeline/api.py` — Existing `EntityListItem` model, merge/split endpoints
- Existing `resolve_entities_activity` pattern — nullify-then-recreate

### Established Patterns
- **Activity pattern:** `@activity.defn`, `_db_params()`, `async with get_db()`, error dict returns
- **Nullify-then-recreate:** Query + UPDATE nullify + CREATE new records
- **Worker registration:** Add to activities list in worker.py

### Integration Points
- `activities.py` — Add new activity
- `workflows.py` — Add activity call between store_results and resolve_entities
- `worker.py` — Register new activity
- `api.py:EntityListItem.entity_type` — Comment shows "place/person/object", update to include "event"

</code_context>

<specifics>
## Specific Ideas

- Use `INSERT INTO canonical_entity ...` with bulk queries instead of individual `db.create()` calls for performance
- For RELATE edges, query canonical_entities by name + type, create links for matches

</specifics>

<deferred>
## Deferred Ideas

- EVNT-07: Event-to-event relationship table (sub_event, related_to, followed_by, caused_by) — deferred to future v4.x
- LLM-powered relationship inference — deferred, verbatim-text matching sufficient for prototype
- Web UI changes for event-specific display — deferred, entity list already shows all types
- Event-specific merge/split conditions — deferred, existing general conditions sufficient

</deferred>
