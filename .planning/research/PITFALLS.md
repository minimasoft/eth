# Domain Pitfalls — Structured Event Data, References UI, Timeline/Map Views, Participant-Based Listing

**Domain:** Adding event-centric features (structured data model, reference-as-evidence UI, timeline/map visualization, participant-based queries) to an existing LLM document processing + entity resolution pipeline
**Researched:** 2026-06-04
**Confidence:** HIGH

**Context:** The existing system has a mature SCHEMAFULL SurrealDB schema (`event`, `reference`, `canonical_entity`, `document_chunk`, `llm_usage`, `document_event_log`, `event_entity_link`), Temporal workflows with nullify-then-recreate replay safety, automated entity resolution (search-first exact match → LLM grouping → DB dedup), a vanilla JS SPA with Upload/Documents/Entities/References/Logs tabs, paginated REST endpoints, and a GraphQL proxy. Adding structured event data, References tab, timeline/map visualizations, and participant-based event listing means extending — not replacing — every layer of this system.

---

## Critical Pitfalls

### Pitfall 1: Schema Bloat — Normalizing What Should Be JSON Properties

**What goes wrong:**
The `canonical_entity` table already has a `properties` field typed as `object | null FLEXIBLE` — an extensible JSON bag. When adding structured event data (date ranges, coordinates, participant roles, event categories), the natural instinct is to create new tables: `event_date`, `event_location`, `event_participant_role`, `event_category`. This produces 4–6 new SCHEMAFULL tables with their own CREATE/UPDATE/DELETE lifecycle, RELATE edges, and index definitions. Each new table requires: (a) DDL migration, (b) Temporal activity code for nullify-then-recreate, (c) REST endpoint(s), (d) UI rendering, (e) cascade delete participation. Worse: SurrealDB's auto-GraphQL generates separate types and queries for each table, making the GraphQL API surface explode.

**Why it happens:**
- Developers trained on relational databases instinctively normalize everything into tables
- "We'll need to query this independently" drives premature normalization
- The existing `event_entity_link` table (a graph edge table) sets a precedent — but that table exists because it represents *relationships between entities*, not *attributes of a single entity*
- SurrealDB's graph capabilities (`RELATE`, `SELECT →`) tempt developers to model everything as graph edges

**Consequences:**
- Pipeline activity complexity grows quadratically (each new table needs its own nullify-then-recreate code path)
- Cascade delete (`DELETE /documents/{id}`) must enumerate every new table in order — missing one leaves orphans
- The SPA must render types from N new tables — template duplication and inconsistency
- GraphQL API surface grows from ~7 types to ~15 types
- Existing entity merge/split operations break because they only handle `reference` → `canonical_entity` links, not links to new tables

**Prevention:**
- **Use `canonical_entity.properties` (FLEXIBLE JSON) for structured event metadata.** Add typed keys: `date_start`, `date_end`, `coordinates.lat`, `coordinates.lng`, `participants[]`, `event_category`, `document_section`. SurrealDB can index individual JSON keys:
  ```surql
  DEFINE INDEX idx_event_dates ON TABLE canonical_entity
      COLUMNS properties.date_start, properties.date_end
      COMMENT 'Index for timeline range queries on event entities';
  ```
- **Create ONE new table if you absolutely need indexed querying across all documents** (e.g., a `timeline_event` materialized view). If you creat zero new tables, you avoid all the cascade delete, migration, and pipeline complexity.
- **Rule of thumb:** If a field is queried *within* a single entity (timeline of one event, participants of one event), use `properties`. If it's queried *across all entities* (all events between date X and Y), add a materialized index or a single flat table — but only after verifying performance is actually a problem.
- **Ask before creating a new table:** "Does this need its own lifecycle (created independently, updated independently, deleted independently)?" If the answer is NO (the data only exists as part of an event), it belongs in `properties`.

**Warning signs:**
- A DDL migration file that adds more than 1 new `DEFINE TABLE` statement
- A cascade delete function that needs updating to add steps for new tables
- A GraphQL schema where the number of types triples
- A developer saying "we'll need to query this by itself later" without concrete use cases

**Phase to address:**
- Phase 1 (Schema Design): Decide properties vs. tables before any DDL is written. Write the schema with zero or one new table maximum.

---

### Pitfall 2: Breaking Existing Entity Resolution with Structural Changes

**What goes wrong:**
The entity resolution system (`resolve_entities_with_search_activity`) runs a specific sequence: (1) nullify prior `canonical_entity`/`entity_id` links on references, (2) exact-match references against existing entities, (3) batch remaining references to LLM for grouping, (4) DB-side dedup + link. Changing the event schema — adding new `canonical_entity` subtypes, changing reference field names, or adding new edge types — can silently break this pipeline: references fail to nullify properly, entity searches miss new types, merge/split logic creates dangling edges.

The `create_event_canonical_entities_activity` currently does a delete-then-recreate cycle that deletes `event_entity_link` edges and `canonical_entity` records where `entity_type = 'event'`. If you change what `entity_type = 'event'` means (adding subtypes), the delete step may miss records.

**Why it happens:**
- The existing resolution code hardcodes type mappings (`espacio → place`, `humanos → person`, `objetos → object`, `tiempo → skip`) — adding a new reference type or entity type requires updating these mappings in multiple places
- The `clear_document_events` endpoint and `DELETE /documents/{id}` cascade both hardcode delete order for event-type entities — adding new subtypes requires updating these
- Merge/split logic (`POST /entities/merge`, `POST /entities/{type}/{id}/split`) only handles `place/person/object` entity types — event entities aren't mergeable/splittable, which is intentional, but if you add subtypes of events, the split logic won't know which sub-types are safe to split
- The `_dedup_and_link` inner function normalizes entity names with NFD + casefold but doesn't account for event-specific name formats (e.g., `"Event: ..."` prefix added by `create_event_canonical_entities_activity`)

**Prevention:**
- **Don't add new `entity_type` enum values to `canonical_entity` without auditing ALL resolution code paths.** The existing enum is `['place', 'person', 'object', 'event']`. Adding `'event_category'` or `'timeline_point'` would need: resolution code updates, cascade delete updates, merge/split guard updates, and UI filter updates.
- **If events need categorization, add `properties.event_category` as a string** — queryable via SurrealDB JSON path without changing the entity_type enum.
- **Run the full integration test suite after ANY schema change:** create document → process → verify events + references + entities + event_entity_links → delete document → verify all records gone.
- **Add an assertion test:** After processing a document, check that `SELECT count() FROM canonical_entity WHERE entity_type = 'event' GROUP ALL` === `SELECT count() FROM event WHERE document = $doc GROUP ALL`.

**Warning signs:**
- A PR that modifies `_dedup_and_link`, merge/split routes, or cascade delete code without corresponding test updates
- Silent failures: entity resolution succeeds but leaves 0 links (watch `links_created` in activity return value)
- `clear_document_events` leaves orphaned `event_entity_link` records
- Merge/split endpoints return 200 but leave `event_entity_link` edges pointing to superseded entities

**Phase to address:**
- Phase 2 (Pipeline Extension): Every schema change must be paired with integration tests covering resolution, cascade delete, and merge/split.

---

### Pitfall 3: Timeline Queries — Unbounded Date Ranges and Missing Indexes

**What goes wrong:**
The existing schema stores event dates as free-form strings in `event.tiempo` and as `properties.time_range` on event-type canonical entities. There are zero date indexes. A timeline query ("show all events between 2018 and 2024") would require: (a) scanning every event record, (b) parsing free-form Spanish date strings like "el 15 de marzo de 2019" or "entre 2020 y 2022", (c) filtering in Python after loading all records. At 100 documents this works. At 10,000 documents with 50 events each (500K events), this is a full table scan followed by LLM-style date parsing — catastrophic.

Even with structured dates, if the query has no index, `SELECT * FROM canonical_entity WHERE properties.date_start >= '2018-01-01' AND properties.date_end <= '2024-12-31'` is still a full scan unless you create the JSON path index.

**Why it happens:**
- The LLM extraction schema (`EVENT_EXTRACTION_SCHEMA`) has `tiempo` as a free-form `string` — it produces unstructured dates
- The `create_event_canonical_entities_activity` stores the free-form `tiempo` string directly into `properties.time_range` — no parsing, no normalization
- Date parsing of Spanish legal text is hard ("a los quince días del mes de marzo del año dos mil diecinueve") — it's easier to defer it
- Developers assume "we'll add date parsing later" but the timeline UI arrives before the parser

**Prevention:**
- **Add structured date fields to the LLM extraction schema.** Extend `EVENT_EXTRACTION_SCHEMA` with optional structured fields:
  ```json
  "date_start": { "type": "string", "format": "date", "description": "Earliest date in ISO 8601 (YYYY-MM-DD), inferred from tiempo" },
  "date_end": { "type": "string", "format": "date", "description": "Latest date in ISO 8601, inferred from tiempo" },
  "date_precision": { "type": "string", "enum": ["exact", "year", "month", "decade", "unknown"], "description": "Precision of the date extraction" }
  ```
  The LLM is already doing structured extraction — adding date fields costs marginal tokens but avoids post-processing hell.
- **Store structured dates in `canonical_entity.properties.date_start`, `properties.date_end`, `properties.date_precision`** alongside the existing free-form `time_range`.
- **Create JSON path indexes immediately when the fields are added:**
  ```surql
  DEFINE INDEX idx_event_date_start ON TABLE canonical_entity
      COLUMNS properties.date_start
      COMMENT 'Index for timeline range queries — enables SELECT WHERE properties.date_start >= $from';
  ```
- **The timeline query MUST use the index.** Verify with `EXPLAIN SELECT` that the index is used. If the index isn't used, create a materialized flat table — but only after proving the JSON index doesn't work.
- **Gracefully degrade for events without structured dates.** Use `SELECT ... WHERE properties.date_start IS NOT NULL AND properties.date_start >= $from` — exclude events with `date_start = null` from timeline queries but still display them with a "no date" indicator.

**Warning signs:**
- Timeline endpoint takes >500ms for 50 documents
- `EXPLAIN SELECT` shows "Full scan" on the canonical_entity table
- The UI shows a loading spinner for >3 seconds on the timeline tab
- Developer says "we'll add indexes after the prototype works" — add them in the same PR

**Phase to address:**
- Phase 3 (Timeline View): Add structured date fields to LLM prompt + JSON schema, index them on canonical_entity.properties, then build the timeline query.

---

### Pitfall 4: Geocoding via External API — Slow, Rate-Limited, Expensive

**What goes wrong:**
When building a map visualization, the instinct is to geocode locations (extracted `espacio` fields or canonical entities of type `place`) via Google Maps / OpenStreetMap / Nominatim API. For Spanish legal documents with ~20 unique locations per document, 100 documents means 2,000 geocoding API calls. At 1 req/s (Nominatim limit), that's 33 minutes. With a commercial API at $0.005/request, that's $10 — and it's run on EVERY reprocess. Worse: rate-limited APIs return HTTP 429, and Temporal retries amplify the problem (exponential backoff → 3 attempts → 3× the API calls).

Spanish court locations are especially problematic: "Juzgado de Primera Instancia e Instrucción nº 2 de DIRECCION000" — geocoding APIs have never heard of "DIRECCION000" (it's an anonymized placeholder in published Spanish court decisions). The LLM that extracted the event knows what "DIRECCION000" represents from context — but the geocoding API doesn't.

**Why it happens:**
- "Just add a map" sounds simple until you realize you need lat/lng for every location
- The free-form `espacio` field contains human-readable location strings, not geocodable addresses
- Commercial APIs have rate limits that aren't obvious until you hit them
- Developers optimistically assume geocoding will "just work" for all locations

**Prevention:**
- **Do NOT run geocoding in the Temporal pipeline.** Geocoding is a UI concern, not a pipeline concern. The pipeline should extract and store location strings. The map view should use them as-is.
- **Curate coordinates manually in `canonical_entity.properties`.** For place-type entities, add `properties.lat` and `properties.lng` fields. These are set manually (or via a one-time admin script), NOT in the pipeline. The nullify-then-recreate cycle in `resolve_entities_activity` should preserve manually-curated coordinates — never overwrite `properties` from LLM output if `lat`/`lng` already exist.
  ```python
  # In _dedup_and_link or canonical entity creation:
  existing_props = existing_entity.get("properties", {}) or {}
  new_props = {**existing_props}  # Preserve curated data
  new_props["source_document_ids"] = existing_props.get("source_document_ids", []) + [document_id]
  # Only set lat/lng if NOT already set:
  if "lat" not in new_props:
      new_props["lat"] = None  # or omit
  if "lng" not in new_props:
      new_props["lng"] = None
  ```
- **If you must geocode, do it as a one-off batch job, not in the pipeline.** Use the Nominatim API with 1 req/s throttling, store results in `properties`, and never re-geocode the same entity. Add a `properties.geocoded_at` timestamp to track freshness.
- **The map view should gracefully handle entities without coordinates.** Show a "Sin coordenadas" placeholder. Don't crash. Don't try to geocode on-the-fly from the frontend.

**Warning signs:**
- A Temporal activity that makes HTTP calls to a geocoding API
- A UI that calls a geocoding API on every render
- Processing time grows linearly with document count (every document triggers geocoding)
- "Rate limit exceeded" errors in Temporal workflow logs

**Phase to address:**
- Phase 4 (Map View): Add `lat`/`lng` fields to canonical_entity.properties, build map rendering, accept that most entities won't have coordinates initially.

---

### Pitfall 5: LLM Prompt Regression — New Structured Output Breaking Old Extraction

**What goes wrong:**
The existing `EVENT_EXTRACTION_SCHEMA` is a strict JSON Schema with `additionalProperties: false` at every level. The LLM is currently tuned to produce events with the 5 existing fields (`que_paso`, `espacio`, `tiempo`, `humanos`, `objetos`) plus `references`. Adding new fields — `date_start`, `date_end`, `date_precision`, `event_category`, `participant_roles[]` — changes the schema that the LLM is constrained to produce. If the new schema is stricter (more `required` fields, more `enum` constraints), the LLM may: (a) refuse to produce valid output (constraint violation), (b) hallucinate values for new fields it doesn't have evidence for, or (c) degrade quality on the original 5 fields because the prompt is now longer and attention is diluted.

This is particularly dangerous because the schema has `additionalProperties: false` — adding a single new property means the LLM must produce it, or the response fails validation. This is NOT backward-compatible: old documents reprocessed with the new schema will get different (potentially worse) output.

**Why it happens:**
- The temptation to add "just one more field" to the schema is strong
- JSON Schema's `additionalProperties: false` is a strict guardrail — adding fields without changing it silently breaks
- LLM prompt engineering is empirical — you can't predict from first principles what adding a field will do to quality
- The chunked extraction pattern means each chunk's output affects subsequent chunks (prior events as context) — a bad extraction in chunk 1 poisons chunk 2+

**Prevention:**
- **Keep new fields OPTIONAL (not in `required`).** The current schema only requires `que_paso` and `references`. New fields should be optional with `"type": ["string", "null"]` or omitted entirely from `required`.
- **Test extraction quality on a benchmark set before merging the prompt change.** Run the current prompt and the new prompt on the same 5–10 representative documents. Compare: (a) event count, (b) que_paso quality (manual review), (c) reference quality (span accuracy, verbatim correctness). Flag any degradation.
- **Version the extraction schema.** Store `extraction_schema_version` in the document record or in `canonical_entity.properties`. This lets you track which schema produced which data without reprocessing. Example: `properties.schema_version = "v6.0"`.
- **If adding a new field is required for the feature but risks regression, add it to the entity resolution prompt instead.** The `ENTITY_RESOLUTION_SYSTEM_PROMPT` could be extended to infer structured dates from verbatim references, without changing the extraction prompt at all.
- **Don't add fields the LLM doesn't have evidence for.** If the LLM sees "el día 15" without a month or year, don't ask it for an ISO date — ask for whatever it CAN extract confidently.

**Warning signs:**
- "Extraction failed: JSON does not match schema" errors in Temporal logs after prompt change
- Event count drops by >20% on the same document after prompt change
- References become more vague ("el documento" instead of specific phrases) — the LLM is struggling to satisfy all constraints
- The LLM produces valid JSON but `date_start` values are clearly wrong or fabricated

**Phase to address:**
- Phase 1 (Schema + Prompt Design): Design the extended schema, test on benchmark documents, only merge if quality holds.

---

### Pitfall 6: Reference Explosion — UI Unusable When Every Chunk Produces 50+ References

**What goes wrong:**
The LLM is instructed to extract verbatim references for every event field. A single chunk can produce 5 events × 4 fields × 3 references per field = 60 references per chunk. A 20-chunk document produces 1,200 references. The existing `/references` endpoint fetches ALL references with `FETCH event, event.document, canonical_entity` — at 1,200 references, this is a massive response. The References tab renders every single reference in a table, with no grouping, no aggregation, no collapse.

The `store_extraction_results_activity` also stores every reference as a separate `INSERT` — at 1,200 per document, at 100 documents, that's 120,000 reference records. The `/references` endpoint paginates at 20 per page, so the user sees 6,000 pages of references.

**Why it happens:**
- The LLM prompt says "extract verbatim references for each event field" — there's no cap, no deduplication instruction
- Each chunk's extraction is independent — chunk 2 may extract references that overlap with chunk 1's references (same span, different chunk call)
- The `store_extraction_results_activity` doesn't deduplicate references before inserting
- The References tab was designed as a flat list for debugging, not for browsing 1,200+ references

**Prevention:**
- **Add an LLM-level cap.** In the extraction system prompt, instruct: "No extraigas más de 5 referencias textuales por campo de evento. Prioriza las referencias más específicas e informativas." (Extract at most 5 references per event field. Prioritize the most specific and informative.)
- **Deduplicate references before storing.** In `store_extraction_results_activity`, after collecting all references, de-duplicate by `(verbatim_text, reference_type, event_id)`. Two references with the same verbatim text supporting the same event field are the same reference.
- **Add pagination to the References tab FIRST, before populating it.** The existing References tab already has pagination — but it's at the `/references` endpoint level, not at the per-document level. Add a `document_id` filter parameter to `/references` so users can narrow down.
- **Group references by `canonical_entity` in the UI.** Instead of a flat list, show references grouped by the entity they resolve to. This collapses 50 references pointing to "Juzgado de Primera Instancia" into one expandable row.
- **Consider a "References by Event" view.** The References tab should default to showing events with their references inline, not a flat list of all references.

**Warning signs:**
- `/references` response time exceeds 500ms after processing 10 documents
- The References tab shows 500+ pages
- SurrealDB `FETCH event, event.document, canonical_entity` produces deeply nested responses that cause serialization errors
- Reference count per document grows linearly with document length (no cap applied)

**Phase to address:**
- Phase 2 (Pipeline Extension): Cap references in LLM prompt, add deduplication in `store_extraction_results_activity`.
- Phase 5 (References UI): Build the References tab with grouping, not flat listing.

---

### Pitfall 7: Temporal Replay Safety — New Records Not Included in Nullify-Then-Recreate

**What goes wrong:**
The system uses a nullify-then-recreate pattern across multiple activities: `store_extraction_results_activity` deletes events + references before recreating; `create_event_canonical_entities_activity` deletes `event_entity_link` edges and `canonical_entity` (event-type) records before recreating; `resolve_entities_with_search_activity` nullifies `canonical_entity`/`entity_id`/`resolution_confidence` on references before re-resolving. If you add new record types (e.g., `event_dates`, `event_locations`, timeline materialized rows) without including them in the nullify step, Temporal replay will accumulate duplicates: the original records from the first execution + new records from the replay = 2× the data.

This is especially dangerous for graph edges. If `create_event_canonical_entities_activity` creates 50 `event_entity_link` edges on first run and isn't nullified before the second run, there are now 100 edges — and queries like "find all entities linked to this event" return duplicates.

**Why it happens:**
- The nullify step is hardcoded for known tables — adding a new table means updating code in multiple places
- The cascade delete in `DELETE /documents/{id}` is a different code path from the nullify-then-recreate in activities — they must stay in sync
- Developers focused on the "happy path" (new records are created successfully) forget the "replay path" (old records must be deleted first)
- Temporal's replay is transparent — developers don't test with actual worker restarts during processing

**Prevention:**
- **For every new record type, identify ALL code paths that create it, and add a corresponding nullify step before creation.** This is a checklist, not optional:
  1. `store_extraction_results_activity` — if you add fields to `event` records, they go here; nullify is `DELETE event WHERE document = $doc`
  2. `create_event_canonical_entities_activity` — if you add new canonical entity sub-types, they go here; nullify is the existing `DELETE canonical_entity WHERE entity_type = 'event' AND properties.document_id = $doc`
  3. `resolve_entities_with_search_activity` — if you add new reference fields, they go here; nullify is the existing `UPDATE reference SET ... = null`
  4. Cascade delete (`DELETE /documents/{id}`) — enumerate every table and edge type
  5. Clear events (`DELETE /documents/{id}/events`) — same enumeration
- **Test replay explicitly.** Temporarily stop the Temporal worker mid-workflow, then restart it. Verify: (a) no duplicate records, (b) event count matches, (c) reference count matches, (d) `event_entity_link` count matches.
- **Add a workflow-level assert.** After `store_extraction_results_activity` completes, query `SELECT count() FROM event WHERE document = $doc` and assert it matches `len(result.events)` from the LLM. After resolution, query `SELECT count() FROM reference WHERE event.document = $doc AND canonical_entity IS NOT NULL` and assert it matches the activity return value.

**Warning signs:**
- After reprocessing a document, `event_entity_link` count is 2× the number of events × entities
- After a worker restart, the UI shows duplicate references
- "Duplicate key" errors in SurrealDB logs (if IDs aren't deterministic) or unexpected record counts (if IDs are deterministic but not nullified)
- Processing log shows multiple `create_event_entities` entries with increasing link counts

**Phase to address:**
- Phase 2 (Pipeline Extension): Every schema change must be paired with a nullify step in the correct activity — documented in the PR as "replay safety: [code path updated]."

---

### Pitfall 8: UI Pattern Inconsistency — New Tabs Using Different Pagination, Loading, or Filter Patterns

**What goes wrong:**
The existing SPA has established UI patterns across 4 tabs (Upload, Documents, Entities, References) + 1 detail view (Logs):
- **Pagination:** `deferredLoading()` helper, previous/next buttons, `page X of Y` display, URL params pattern (`?page=N&per_page=20&search=...`)
- **Loading states:** 200ms deferred loading spinner (`deferredLoading`), empty state with `<div class="placeholder-card">`
- **Filters:** Search input with 300ms debounce, clear button, status/type filter dropdowns
- **Tables:** `.documents-table` class with consistent styling, status badges, hover states
- **Data fetching:** `async fetchDocuments()` pattern, error handling with banner display, `loadingFlag` guard

Adding a new tab (Timeline) or a new detail view (Participant-based Event List) that uses a completely different pattern — e.g., `fetch('/api/timeline')` instead of URLSearchParams, inline spinners instead of `deferredLoading`, cards instead of tables — creates a disjointed UX. Users learn one pattern and expect it everywhere. Worse: the existing `switchTab()` function and `onTabClick()` handler must be extended for every new tab — if you forget to add the `onTabClick` handler or include the tab in `sections`, the tab silently breaks.

**Why it happens:**
- Timeline and map views are inherently "different" from table-based list views — the temptation to build them from scratch is strong
- Developers working on a new tab don't study the existing tab patterns first
- The SPA is vanilla JS — there are no shared React components enforcing consistency; every tab is a standalone set of functions
- The `deferredLoading` helper and `documents-pagination` CSS class are discoverable only by reading the full 2,277-line HTML file

**Prevention:**
- **Extract shared UI components into a single JS module.** Even without a framework, move `deferredLoading()`, `fetchPage()`, `renderPagination()`, `showBanner()` into a `ui-utils.js` file that all tabs import. This makes inconsistency harder (the shared code does the right thing).
- **New tabs MUST follow the existing tab patterns:**
  - Add tab button to `<nav>` with `data-tab="timeline"` attribute
  - Add `<section id="tab-timeline">` with `role="tabpanel"` and `class="tab-content"`
  - Register in `sections` object: `timeline: document.getElementById('tab-timeline')`
  - Add to `onTabClick` handler: `if (tabName === 'timeline') fetchTimeline();`
  - If the tab is conditionally enabled (like Logs which requires a document), use the `tab-disabled` CSS class
- **Timeline and map views don't need to use `<table>` but should use the same loading, error, and empty state patterns.** A timeline with a loading spinner that doesn't match the Documents tab's spinner is a bug, not a feature.
- **Copy-paste an existing tab's structure as a starting point.** Start with the Entities tab (it has search + type filter + pagination + detail panel) and adapt. Don't start from scratch.

**Warning signs:**
- A new tab that adds `<script>` at the bottom with its own `fetch()` pattern that looks nothing like `fetchDocuments()`
- A new view that uses `fetch('/api/timeline')` while all other views use `fetch('/timeline?' + params)`
- A new tab that shows/hides content with inline `style.display` instead of CSS classes like `active`
- A tab button that doesn't have `data-tab` attribute matching the section ID

**Phase to address:**
- Phase 3 (Timeline View) and Phase 4 (Map View): Before building, refactor shared UI utilities into a module. Then build new tabs using those utilities.

---

### Pitfall 9: Test Coverage Gaps — New Features Breaking Old Entity Resolution

**What goes wrong:**
The existing system has no test files in the `tests/` directory (the `glob` found nothing). Adding structured event data, new LLM prompt fields, or new schema columns without tests means every change is a regression risk. Specifically:
- Adding `date_start`/`date_end` to the LLM extraction schema changes the event structure → `store_extraction_results_activity` must handle the new fields → if it doesn't, events are stored without dates but the UI expects them → undefined behavior
- Adding new `properties` keys to canonical_entity records changes what `resolve_entities_with_search_activity` sees during dedup → if the dedup logic ignores new properties, it silently works but leaves data loss
- Adding a new tab to the SPA without testing means the tab might break when another tab's `switchTab` logic doesn't account for it

**Why it happens:**
- The pipeline is complex (7 SurrealDB tables, 8 Temporal activities, 5 REST endpoints, 5 UI tabs, GraphQL proxy) — testing every integration point requires significant test infrastructure
- "It works on my machine with one document" masks scale and edge-case issues
- The nullify-then-recreate pattern means every test must run a full workflow cycle — slow to write, slower to run
- SurrealDB + Temporal integration testing requires both services to be running

**Prevention:**
- **Write at minimum these integration tests (in priority order):**
  1. **Full pipeline cycle:** Create document → process → verify events, references, entities, event_entity_links, resolution results → clear events → verify all gone
  2. **Entity resolution with new fields:** Process a document with structured dates → verify `canonical_entity.properties.date_start` is set → merge two entities → verify merged entity has combined properties
  3. **Cascade delete:** Process document → delete document → verify zero records in ALL tables (event, reference, canonical_entity, document_chunk, document_event_log, llm_usage, event_entity_link)
  4. **Replay safety:** Process document → verify record count → trigger reprocessing → verify record count matches (no duplicates)
  5. **LLM prompt regression:** Run old prompt and new prompt on same text → verify event count doesn't drop >10% and reference quality doesn't degrade
- **For the UI:** Test that a new tab (a) appears in nav, (b) is clickable, (c) loads data, (d) shows pagination, (e) filters work, (f) empty state shows correctly.
- **Use the existing `test_data/` directory for test fixtures.** Create a small Spanish legal document (5–10 paragraphs) that extracts to 2–3 events with clear dates and locations. Use this as the golden test fixture.
- **Mock the LLM provider in tests, not SurrealDB.** The LLM is the slowest and most expensive part. Mock `OpenRouterProvider.extract_events()` to return a known event list. Test SurrealDB interactions against a real (local) SurrealDB instance.

**Warning signs:**
- A PR that changes the LLM schema with no new tests
- A PR that adds a new table with no integration test verifying cascade delete still works
- "I tested manually" — acceptable once, not acceptable for every PR

**Phase to address:**
- Phase 0 (Test Infrastructure): Build the test fixture, mock the LLM provider, write the full pipeline cycle test. Every subsequent phase adds tests for its feature.

---

### Pitfall 10: Data Migration — Schema Changes Requiring Backfill Instead of Being Backward-Compatible

**What goes wrong:**
Existing documents processed before the new structured event fields were added have `event.tiempo` as a free-form string but no `date_start`/`date_end` in `canonical_entity.properties`. The timeline query filters on `WHERE properties.date_start >= $from`. Old documents with `date_start = NULL` are silently excluded from the timeline — the user sees an empty timeline for documents they KNOW have temporal information.

Similarly, new `properties` fields (participant role, event category) added to the extraction schema won't exist on old canonical_entity records. If the UI tries to render `properties.participant_roles` without a null guard, it throws `TypeError` and the page breaks.

The worst case: adding a non-nullable field to the SCHEMAFULL `event` table. SurrealDB's `DEFINE FIELD new_field ON TABLE event TYPE string` with no `DEFAULT` silently fails for existing records that don't have the field — they can't be queried without a migration.

**Why it happens:**
- Developers add new fields and test with freshly processed documents — old documents are an afterthought
- The SCHEMAFULL constraint is invisible until you try to query old records
- "We'll write a migration script" is said but never done because it requires another Temporal workflow run on old documents
- The JSON properties approach (`FLEXIBLE`) eliminates some migration pain, but the JSON keys themselves can still be missing

**Prevention:**
- **ALL new fields must be nullable with DEFAULT null.** No exceptions. Even if the LLM always produces the field for new documents, old documents won't have it.
  ```surql
  DEFINE FIELD date_start ON TABLE event TYPE string | null
      DEFAULT null
      COMMENT 'Structured date start (ISO 8601). Null for documents processed before v6.0.';
  ```
- **All UI code that reads new fields must handle null/missing.** Every `properties.date_start` access should be `(props && props.date_start) || null` or equivalent. Use optional chaining everywhere.
- **Old documents can be reprocessed to gain new fields.** The existing "Delete Events" endpoint clears events and resets status to `pending`. Users can re-upload and reprocess. But this is a user action, not an automatic migration. Document it.
- **Add a `schema_version` field to `canonical_entity.properties`** so queries can distinguish old-formatted entities from new: `WHERE properties.schema_version >= 'v6.0' AND properties.date_start >= $from`.
- **For the timeline, show a "Sin fecha estructurada" badge for events with `date_start = null`.** Don't exclude them — aggregate them in a "Fecha desconocida" bucket. The user should see that the event exists but its date wasn't extracted in structured form.

**Warning signs:**
- A `DEFINE FIELD` without `| null` or without `DEFAULT null`
- UI code that accesses `props.date_start.toISOString()` without a null check
- A query that filters `WHERE properties.date_start >= $from` — this silently excludes null-date events; add `OR properties.date_start IS NULL`
- User reports: "The timeline shows 3 events but I know there are 15 in this document"

**Phase to address:**
- Phase 3 (Timeline View): Design the timeline query to handle null dates gracefully. Show the "unknown date" bucket prominently.

---

## Technical Debt Patterns

Shortcuts that seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Parse dates in the frontend from free-form `tiempo` strings | No LLM prompt change needed; no schema migration | Every user of the timeline API must replicate Spanish date parsing; inconsistent results across consumers | Only if you expose the parsed dates via a REST endpoint that all consumers use |
| Hardcode coordinates for known Spanish locations in a config file | No geocoding API needed; instant map rendering | Every new court location requires a code change; PR backlog for "add coordinates for Juzgado X" | Acceptable for an MVP with <20 locations; migrate to canonical_entity.properties before production |
| Skip deduplication in `store_extraction_results` (store all references as-is) | Simpler code; no O(n²) dedup check | Reference count grows linearly with document count; `/references` endpoint degrades; storage costs grow | Only for <50 documents total; add dedup at 50+ |
| Build timeline view as a separate page instead of a SPA tab | Can use React/MapLibre/Leaflet without integrating into vanilla JS SPA | Two codebases; two auth flows; inconsistent UX; users must switch between "the old UI" and "the new UI" | NEVER — the SPA is the UI; new views must be tabs |
| Add `event_category` as a new `entity_type` enum value instead of a `properties` key | Queryable via `WHERE entity_type = 'event_category'` | Every place that enumerates entity types breaks (merge, split, cascade, resolution, UI filters); adding 4 categories = 4 new enum values | NEVER — use `properties.event_category` |

---

## Integration Gotchas

Common mistakes when connecting to external services or extending existing systems.

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| LLM extraction schema (`EVENT_EXTRACTION_SCHEMA`) | Adding `date_start` as `required` in the JSON Schema | Make all new fields optional; the LLM should omit fields it can't confidently produce |
| `store_extraction_results_activity` | Only storing the 5 existing event fields; ignoring new structured fields from the LLM response | Map ALL fields from the LLM response into the SurrealDB `INSERT`, including new optional fields (they'll be `null` for old LLM responses — that's fine) |
| `create_event_canonical_entities_activity` | Overwriting curated coordinates on entity creation | Check if `lat`/`lng` already exist in `properties`; preserve them if set; only set defaults for new entities |
| `resolve_entities_with_search_activity` | Nullifying the `canonical_entity` link but not the `entity_id` link (or vice versa) | Always nullify BOTH: `SET canonical_entity = null, entity_id = null, resolution_confidence = null WHERE event.document = $doc_rid` |
| SurrealDB `FETCH` on references | Using `FETCH event, event.document, canonical_entity` on 1,000+ references — deeply nested response exceeds serialization limits | Paginate FIRST, then FETCH. Never FETCH on unbounded queries. Consider using separate queries for event/doc data instead of nested FETCH. |
| SPA tab registration | Adding a tab button in HTML but forgetting to add `tabName` to `sections` object or `onTabClick` handler | Checklist: (1) `<nav>` button with `data-tab`, (2) `<section>` with matching `id`, (3) `sections` object entry, (4) `onTabClick` handler, (5) fetch function, (6) render function |
| Cascade delete (`DELETE /documents/{id}`) | Adding a new table but not adding it to the cascade delete enumeration in `documents.py` | Delete order matters: edges first (event_entity_link), then referenced records (reference), then source records (event), then logs (document_event_log, llm_usage), then orphaned entities, then the document itself. ALWAYS add a test that does create → cascade delete → verify zero records in every table. |

---

## Performance Traps

Patterns that work at small scale but fail as usage grows.

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Timeline query scanning all `canonical_entity` records | `/timeline` endpoint takes 3+ seconds; SurrealDB CPU at 100% | JSON path index on `properties.date_start`, `properties.date_end`; LIMIT the result set to 500 events | ~500 events in the database |
| `FETCH event, event.document, canonical_entity` on paginated references | References endpoint times out; SurrealDB returns "response too large" errors | Separate queries: (1) paginate references, (2) batch-fetch related events and documents by ID | ~1,000 references per page fetch |
| Rendering 200+ map markers in a single Leaflet/MapLibre view | Browser tab freezes; map interaction laggy | Cluster markers (Supercluster or MapLibre's built-in clustering); paginate or lazy-load markers outside viewport | ~200 markers on screen |
| No date precision handling in timeline | Every date is rendered as a point on the timeline even when the LLM only knows the year | Store `date_precision` (exact/month/year/decade/unknown); render "year" events as spans, not points | High: even 50 events with mixed precision produce misleading visualizations |
| Polling the documents list every 5 seconds (`_docPollTimer`) while also polling a timeline query | 2× the database load; irrelevant polling (timeline doesn't change unless documents are being processed) | Only poll tabs where data is actively changing (documents during processing); timeline and map should be "load on tab switch" with a manual refresh button | ~5 concurrent users refreshing |
| Building the timeline view as a server-rendered HTML page | Every filter change reloads the entire page — slow, janky | Build the timeline as a client-side render in the SPA; fetch JSON from `/events/timeline` endpoint; re-render on filter change without page reload | First user with >10 documents |

---

## Security Mistakes

Domain-specific security issues beyond general web security.

| Mistake | Risk | Prevention |
|---------|------|------------|
| Exposing `canonical_entity.properties` via GraphQL with full read access | Any GraphQL client can query `properties` of all entities — including internal metadata like `document_id`, `schema_version`, cost tracking data | The GraphQL proxy forwards auth headers but doesn't filter fields — SurrealDB's auto-GraphQL exposes ALL fields. Consider a dedicated REST endpoint for timeline/map data that only returns the `properties` keys needed for rendering. |
| Embedding an API key in the frontend for map tiles (Mapbox, Google Maps) | The API key is visible in the SPA source; anyone can use it | Use a proxy endpoint: `/api/map-tile/{z}/{x}/{y}` that adds the API key server-side. Or use OpenStreetMap tiles (no API key needed). |
| No input validation on `/events/timeline` query parameters (`?from=2010-01-01&to=2025-01-01`) | SQL injection if directly interpolated into SurrealQL | Use parameterized queries: `SELECT * FROM canonical_entity WHERE properties.date_start >= $from AND properties.date_start <= $to`. Validate date format server-side before passing to SurrealDB. |
| Exposing document content through reference verbatim text | The References tab shows exact text spans — potentially sensitive legal content | This is by design (the References tab IS for viewing verbatim evidence). But ensure the References tab is behind the same access controls as the Documents tab. |

---

## UI/UX Pitfalls

Common user experience mistakes.

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Timeline showing only event entities with structured dates — silently hiding events without dates | User sees 5 events but knows 20 were extracted; loses trust in the tool | Show a "Fecha desconocida" summary bar above the timeline: "15 eventos sin fecha estructurada — procese de nuevo para extraer fechas" |
| Map view with 50 unclustered markers showing "Juzgado de Primera Instancia nº 1" as the label | Map is unreadable; labels overlap; user can't find anything | Cluster markers by proximity; on zoom, show individual markers with shortened labels ("Juzgado nº 1"); full name in tooltip |
| References tab that loads ALL references on tab switch without a loading state | 5+ second blank screen; user thinks the app crashed | Deferred loading spinner (200ms delay, then show); load first page immediately; fetch remaining pages on demand |
| No "back" button or breadcrumb when navigating from an entity detail panel back to the entity list | User gets stuck in detail view; refreshes page to escape | The existing entity detail panel has a "Volver" button — the References detail panel MUST do the same |
| Timeline and map views with different filter/search patterns than the Documents tab | User has to re-learn the UI for every tab; cognitive load | Consistent search bar + dropdown pattern across ALL tabs. If Documents tab has search + status filter, the Timeline tab should have search + date range filter with the SAME layout |

---

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical pieces.

- [ ] **Timeline view:** Often missing date precision rendering — verify events with `date_precision = 'year'` are shown as spans, not points
- [ ] **Map view:** Often missing coordinate backend — verify `properties.lat`/`properties.lng` fields exist, are indexed, and survive entity resolution without being overwritten
- [ ] **References tab:** Often missing grouping — verify references are grouped by `canonical_entity`, not shown as a flat list
- [ ] **Participant-based listing:** Often missing the reverse edge — verify `SELECT * FROM event WHERE id IN (SELECT event FROM event_entity_link WHERE entity = $person_entity)` works and has an index
- [ ] **Cascade delete:** Often missing new tables — verify `DELETE /documents/{id}` removes records from ALL tables, including any new tables added in this milestone
- [ ] **Replay safety:** Often missing nullify steps for new record types — verify that reprocessing a document produces the same record counts as the first run
- [ ] **Backward compatibility:** Often missing null handling — verify old documents (processed before the schema change) don't crash the new timeline/map/participant views
- [ ] **LLM prompt:** Often untested with old documents — verify that the new extraction schema produces the same `que_paso` quality on documents that worked well before
- [ ] **Empty states:** Often missing — verify every new tab shows a meaningful placeholder when there's no data (not a blank screen, not a JS error)
- [ ] **SPA tab registration:** Often incomplete — verify the new tab appears in ALL of: nav button, sections object, onTabClick handler, switchTab function

---

## Recovery Strategies

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Schema bloat (too many new tables) | MEDIUM | Consolidate into `properties` JSON; migrate data from old tables into JSON; drop old tables (one migration script + one Temporal reprocess run) |
| Broken entity resolution | HIGH | Revert the resolution change; manually fix linked references; run `resolve_entities_with_search_activity` on affected documents; add the missing nullify step |
| Timeline performance | MEDIUM | Add the missing JSON path index; add LIMIT to unbounded queries; if too late, create materialized `timeline_event` table populated by a one-time migration |
| Geocoding rate limit / cost explosion | LOW (if caught early), MEDIUM (if pipeline-dependent) | Remove geocoding from the pipeline; clear any existing rate-limit backoff; switch to manual coordinate curation in `properties` |
| LLM prompt regression | HIGH | Revert to the old prompt; run benchmark comparison; iterate on new prompt with smaller changes until quality holds; version the schema so old documents can stay on old prompt |
| Reference explosion | MEDIUM | Add the LLM cap; add dedup in `store_extraction_results`; run a cleanup query to deduplicate existing references by `(verbatim_text, reference_type, event)` |
| Temporal replay duplicates | HIGH | Write a cleanup activity that deduplicates by `(document_id, entity_type, record_hash)`; run it once; add nullify steps for the next deploy |
| UI pattern inconsistency | MEDIUM | Refactor the new tab to use shared utilities; extract `deferredLoading` and pagination into a module; migrate one tab at a time |
| Missing cascade delete for new table | LOW | Add the missing DELETE statement; run a one-time cleanup: `DELETE new_table WHERE event.document IN (SELECT id FROM document WHERE status = 'deleted')` |
| Missing null handling for old documents | LOW | Add null guards in the UI query; add `OR IS NULL` to timeline queries; no data migration needed (just code change) |

---

## Pitfall-to-Phase Mapping

How roadmap phases should address these pitfalls.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Schema bloat (P1) | Phase 1: Schema + Prompt Design | Count new `DEFINE TABLE` statements — must be ≤ 1. Reject PRs with >1 new table. |
| Entity resolution breakage (P2) | Phase 2: Pipeline Extension | Full pipeline cycle test passes. Merge/split test passes. Cascade delete test passes. |
| Timeline queries (P3) | Phase 3: Timeline View | `EXPLAIN SELECT` shows index usage. Timeline query <200ms at 500 events. |
| Geocoding in pipeline (P4) | Phase 4: Map View | No geocoding HTTP calls in Temporal activities. `properties.lat`/`lng` survive reprocessing. |
| LLM prompt regression (P5) | Phase 1: Schema + Prompt Design | Benchmark on 5 documents shows <10% event count change and comparable reference quality. |
| Reference explosion (P6) | Phase 2: Pipeline Extension + Phase 5: References UI | Documents with >100 text chunks produce <500 references. References tab loads <1s. |
| Temporal replay (P7) | Phase 2: Pipeline Extension | Worker restart test: reprocess document, verify record counts match first run. |
| UI inconsistency (P8) | Phase 3-5: All UI phases | New tabs use `deferredLoading`, `documents-pagination`, `placeholder-card` classes. |
| Test coverage (P9) | Phase 0: Test Infrastructure | At least 1 integration test per critical path exists before Phase 1 begins. |
| Data migration (P10) | Phase 1-3: Schema Design + Pipeline + Timeline | Old documents load in timeline with "Sin fecha" badge. No JS errors accessing new `properties` keys. |

---

## Sources

- **Primary:** Project source code — `src/eth_pipeline/schema.surql` (435 lines), `src/eth_pipeline/activities.py` (2341 lines), `src/eth_pipeline/workflows.py` (246 lines), `src/eth_pipeline/static/index.html` (2277 lines), `src/eth_pipeline/api/routes/` (documents.py 1235 lines, entities.py 813 lines, references.py 171 lines)
- **Schema evolution history:** `sql/event-migration.surql` (original migration), `sql/m002-s01-migration.surql` (canonical_entity foundation), `sql/m002-s02-migration.surql` (entity_type index)
- **Temporal patterns:** Nullify-then-recreate pattern documented in `resolve_entities_with_search_activity` (lines 716-728) and `create_event_canonical_entities_activity` (lines 1194-1198)
- **SPA patterns:** Tab navigation at lines 1142-1189, pagination at lines 1340-1530, deferred loading at lines 1128-1140
- **Cascade delete:** Full enumeration at lines 918-1119 of `documents.py` — 9-step cascade covering all 7+1 tables
- **SurrealDB indexing:** JSON path index pattern from SurrealDB 2.x/3.x docs (verified via existing `idx_event_entity_link_event` and `idx_entity_type` indexes)
- **Confidence:** HIGH — based on direct code inspection of the complete existing system, not speculation

---

*Pitfalls research for: Structured event data, References UI, timeline/map views, participant-based listing*
*Researched: 2026-06-04*
