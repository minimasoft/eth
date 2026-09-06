---
phase: quick-260906-nap
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/eth_pipeline/alembic/versions/0006_model_colors.py
  - src/eth_pipeline/providers.py
  - src/eth_pipeline/api/routes/events_v2.py
  - src/eth_pipeline/api/models.py
  - src/eth_pipeline/static/index.html
  - src/eth_pipeline/static/linea-tiempo.js
  - tests/test_migration.py
  - tests/test_model_colors.py
  - tests/test_linea_tiempo.py
autonomous: true
requirements: [QUICK-260906-NAP]
estimate:
  tokens: 65000
  raw_tokens: 32000
  tasks: 3
  confidence: low
must_haves:
  truths:
    - A new tab "Línea de tiempo" exists next to the existing Eventos/Mapa tabs; the existing Cronología view is byte-untouched
    - The new view renders a vertical timeline (months top→bottom, old→new) with one column per model, colored from the tableau20 palette
    - Colors are stored in the DB, 1:1 with providers, assigned first-available in order, and freed when a provider is deleted
    - Existing providers get colors backfilled by migration 0006
    - Clicking an event rectangle opens the existing full-detail view
    - All new view JavaScript lives in static/linea-tiempo.js, not inline in index.html
  artifacts:
    - src/eth_pipeline/alembic/versions/0006_model_colors.py
    - src/eth_pipeline/static/linea-tiempo.js
    - tests/test_model_colors.py
    - tests/test_linea_tiempo.py
  key_links:
    - model_color.provider_id → llm_provider.id ON DELETE CASCADE (color freed on provider delete)
    - GET /events/colors joins event_v2 → llm_provider → model_color to serve model→color_index
    - linea-tiempo.js calls global showEventDetail(eventId) from index.html for click-through
---

<objective>
Add a NEW vertical timeline view as a separate "Línea de tiempo" tab: DB-backed model colors (migration 0006 + first-available assignment), a colors API endpoint, and a self-contained JS renderer with vertical months, model columns, and clickable 149×92 event rectangles — leaving the existing Cronología view completely untouched.

Purpose: the horizontal per-month-column timeline does not scale to many events per month; a vertical scroll with labeled columns and DB-stable model colors is readable at any density.
Output: migration 0006, colors endpoint, linea-tiempo.js, index.html tab wiring, tests.
</objective>

<execution_context>
@/home/u/src/eth/.opencode/gsd-core/workflows/execute-plan.md
@/home/u/src/eth/.opencode/gsd-core/templates/summary.md
</execution_context>

<context>
@AGENTS.md
@src/eth_pipeline/schema.sql
@src/eth_pipeline/alembic/versions/0005_llm_mode_instruct_params.py
@src/eth_pipeline/alembic/versions/0004_event_provenance_sources_geo.py
@src/eth_pipeline/providers.py
@src/eth_pipeline/api/routes/events_v2.py
@tests/test_migration.py

Key facts (already verified — do not re-derive):
- `event_v2` rows carry `model` (denormalized string) and nullable `provider_id` (FK → llm_provider, ON DELETE SET NULL — set by migration 0004).
- `llm_provider` (migration 0003): id, name, model, base_url, api_key, is_default, timestamps. Providers are deleted via `providers.py::delete_provider` (plain DELETE) — the default provider cannot be deleted. New providers are added in `providers.py::add_provider`.
- Alembic head is 0005. Migrations run in containers: `docker compose run --rm api uv run alembic <cmd>`. schema.sql is the pre-0001 baseline — do NOT add the new table there.
- Tabs: `index.html` has a hardcoded `sections` map (line ~1678), `switchTab(tabName)` (generic — hides/shows by section id), and `onTabClick` (~1719) which calls per-tab loaders. Nav buttons are `nav button[data-tab=...]` (lines ~1306-1311). The `<script>` for the app is inline in `<body>`; global function declarations (`fetchWithC`, `showEventDetail`, `escapeHtml`, `showBanner`, `truncateText`) are reachable from a classic external script loaded AFTER the inline script.
- Existing Cronología view: `renderEventosTimeline` (~2951) with CSS block starting at comment "Timeline view" (~1176) — DO NOT MODIFY any of it.
- Existing JS-structure regression test pattern: `tests/test_timeline_fetch_all.py` (static source assertions on index.html).
- Every read endpoint uses `@require_passcode("C")`; frontend fetches go through global `fetchWithC(url)`.
- UI language is Spanish with proper accents (e.g. "Cronología", "Documentos"). The user's request spells the tab "Linea de tiempo"; use "Línea de tiempo" for consistency with the accented existing UI.
</context>

<tasks>

<task type="auto">
  <name>Task 1: Migration 0006 — model_color table, backfill, and first-available color assignment service</name>
  <files>src/eth_pipeline/alembic/versions/0006_model_colors.py, src/eth_pipeline/providers.py, tests/test_migration.py, tests/test_model_colors.py</files>
  <action>
1. Create `src/eth_pipeline/alembic/versions/0006_model_colors.py` (revision '0006', down_revision '0005', same style as 0005):
   - `model_color` table: `id TEXT PRIMARY KEY`, `provider_id TEXT NOT NULL UNIQUE REFERENCES llm_provider(id) ON DELETE CASCADE`, `color_index SMALLINT NOT NULL CHECK (color_index >= 0 AND color_index <= 19)`, `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`. The UNIQUE constraint enforces the 1:1 relation; ON DELETE CASCADE means deleting a provider removes its color row, freeing the index.
   - `color_index` is an index into the fixed tableau20 palette (the RGB tuples live only as a JS constant in Task 3) — the DB stores the stable index, not the RGB value.
   - Backfill in `upgrade()`: INSERT one row per existing llm_provider, ordered by `created_at, id`, assigning `color_index = (row_number - 1) % 20` via a single SQL statement with `row_number() OVER (ORDER BY created_at, id)` and `gen_random_uuid()::text` for ids. This satisfies "a migration should assign colors to models without a color".
   - `downgrade()`: drop table.
   - Per AGENTS.md: do NOT add model_color to schema.sql.
2. In `src/eth_pipeline/providers.py`:
   - Add an async helper `assign_free_color(conn, provider_id) -> int | None`: picks the LOWEST color_index in 0..19 not present in model_color; if all 20 are taken, falls back to `(SELECT COUNT(*) % 20 FROM model_color)`; inserts the model_color row and returns the index. Call it from `add_provider` right after the provider INSERT succeeds (same transaction/conn if the function uses one; otherwise immediately after, tolerating failure without failing provider creation — log a warning if assignment fails).
   - `delete_provider` needs NO change (CASCADE frees the color) — add a one-line comment stating that so future readers don't "fix" it.
3. Update `tests/test_migration.py`: change the alembic_version assertions from "0005" to "0006" (both the current-migration test and the downgrade/re-upgrade test at lines ~37 and ~105).
4. Create `tests/test_model_colors.py` (integration, following test_migration.py fixture style):
   - After migration: model_color exists, every pre-existing llm_provider row has exactly one model_color row, color_index in 0..19, and backfill indices are distinct-and-ordered for the first N ≤ 20 providers.
   - Service test: add a provider via `providers.add_provider` (or direct INSERT + `assign_free_color`) → gets the lowest free index; delete the provider row → its color row is gone (CASCADE) and the freed index is the one reassigned next.
  </action>
  <verify>
    <automated>./test.sh tests/test_model_colors.py tests/test_migration.py</automated>
  </verify>
  <done>Migration 0006 creates+backfills model_color; alembic_version=0006 on fresh test DB; add_provider assigns lowest free index; provider delete frees it; all migration tests pass with 0006.</done>
</task>

<task type="auto">
  <name>Task 2: GET /events/colors endpoint — model→color_index map for the new view</name>
  <files>src/eth_pipeline/api/routes/events_v2.py, src/eth_pipeline/api/models.py, tests/test_model_colors.py</files>
  <action>
1. In `src/eth_pipeline/api/models.py` add (following existing response-model style):
   - `ModelColorItem { model: str, color_index: int | None }` and `ModelColorsResponse { colors: list[ModelColorItem] }`.
2. In `events_v2.py` add `@router.get("/events/colors", response_model=ModelColorsResponse)` with `@require_passcode("C")`, defined BEFORE the `/events/{event_id}` route (path matching: declare it above the detail route so "colors" is not captured as an event_id — FastAPI matches in declaration order).
   - Query: `SELECT DISTINCT ev.model, mc.color_index FROM event_v2 ev LEFT JOIN llm_provider lp ON lp.id = ev.provider_id LEFT JOIN model_color mc ON mc.provider_id = lp.id WHERE ev.model IS NOT NULL AND ev.model <> '' ORDER BY ev.model`. Models whose provider was deleted (provider_id NULL) come back with color_index NULL — the client falls back to a hash-palette color for those.
   - Guard with try/except → 502 like the sibling endpoints; log via logger.info.
3. Append an integration test to `tests/test_model_colors.py`: seed one event_v2 row for a colored provider → GET /events/colors returns that model with its index; a model string with no provider link → color_index null. Follow the client/auth pattern used by existing endpoint tests in tests/test_event_api.py (passcode C handling via the shared fixture helper).
  </action>
  <verify>
    <automated>./test.sh tests/test_model_colors.py tests/test_passcodes.py</automated>
  </verify>
  <done>GET /events/colors (passcode C) returns distinct model strings with their DB color_index, null for unlinked models; endpoint declared before /events/{event_id}; passcode tests still pass.</done>
</task>

<task type="auto">
  <name>Task 3: "Línea de tiempo" tab + external linea-tiempo.js vertical renderer</name>
  <files>src/eth_pipeline/static/index.html, src/eth_pipeline/static/linea-tiempo.js, tests/test_linea_tiempo.py</files>
  <action>
1. index.html wiring (smallest possible diff — do NOT touch the existing Cronología CSS/JS):
   - Nav: add `<button role="tab" aria-selected="false" aria-controls="tab-lineatiempo" id="tab-btn-lineatiempo" data-tab="lineatiempo">Línea de tiempo</button>` after the Mapa button (~line 1309).
   - Section: add `<section id="tab-lineatiempo" role="tabpanel" aria-labelledby="tab-btn-lineatiempo" class="tab-content">` containing a header "Línea de tiempo", a loading div, and an empty `<div id="lineatiempo-container"></div>`. Place it after the tab-mapa section.
   - `sections` map (~1678): add `lineatiempo: document.getElementById('tab-lineatiempo'),`.
   - `onTabClick` (~1719): add `if (tabName === 'lineatiempo' && window.renderLineaTiempo) window.renderLineaTiempo();` (renders on each tab entry; the renderer skips refetch if data is already loaded).
   - Before `</body>`, AFTER the inline script: `<script src="linea-tiempo.js"></script>`.
2. Create `src/eth_pipeline/static/linea-tiempo.js` — ALL new-view JS here, ES5-style consistent with index.html, using globals `fetchWithC`, `showEventDetail`, `escapeHtml`, `showBanner`. Contents:
   - `var TABLEAU20 = [[31,119,180],[174,199,232],[255,127,14],[255,187,120],[44,160,44],[152,223,138],[214,39,40],[255,152,150],[148,103,189],[197,176,213],[140,86,75],[196,156,148],[227,119,194],[247,182,210],[127,127,127],[199,199,199],[188,189,34],[219,219,141],[23,190,207],[158,218,229]];` — rgb strings built from these tuples.
   - Colors: on render, fetch `/events/colors` (via fetchWithC) + all events (paged `/events?per_page=100` loop reading `data.pages`, same accumulation pattern as the existing fetchAllEventos, passing current eventos search/filter is NOT needed — this tab has no filters; plain unfiltered fetch). Build map model→`rgb(...)`: DB color_index if present, else stable hash of the model string % 20 as fallback. Cache both; refetch only via a refresh button.
   - Model label: model name ONLY (the event_v2.model string, e.g. "glm-5.3-flash"); never render provider name. Lines/lanes are grouped by that model string.
   - Layout (vertical, old→new, top→bottom):
     - Bucket dated events by month (local Date; null time_start → "Sin fecha" section at the bottom, same pattern as the existing undated list, clickable).
     - Per month compute `n = max events of any single model in that month`; `monthHeight = max(1, n) * (92 + 4) + 4` — empty months take the single-event height (n floored to 1).
     - One header row on top styled like a table: model labels in their column, text in the model's color, with a small color swatch.
     - One column per model: column width = 149px + 16px gap (165px); each column keeps the light background guide from the current view (band with `#f8fafc` background + `#e8edf3` border, full timeline height).
     - Month divider lines: horizontal 1px lines across all columns at each month boundary + a month label in a LEFT gutter, format "Jan 2026" (3-letter English month abbreviated + 4-digit year; build from arrays so it is exactly `Jan 2026` style, not locale-dependent).
     - Centering: the columns block is horizontally centered; add an invisible right-side compensation element equal in width to the left label gutter (e.g. 90px) so the gutter does not shift the timeline off-center. Vertical scrolling is natural document/section scroll.
     - Event rectangles inside a month, per model column: sort events by time_start ascending; ideal y = dayFrac × (monthContentHeight − 92) where dayFrac = (day-of-month − 1)/(daysInMonth − 1) (1st at 0px, last day at bottom); then one downward collision pass enforcing ≥4px gap between same-column rectangles, clamped to the month bottom — aligns approximately to the day without wasting space (10 events spread through the month, not stacked at 0). Reasonable effort, no constraint solver.
     - Rectangle: exactly 149px × 92px, border-radius ~6px, 2px solid border in the model's color, background white, content = short description (item.title, falling back to a truncated description) centered both axes, overflow hidden with ellipsis (clip to what fits). `title` attribute = full date + description. Click → `showEventDetail(event_id)` (same behavior as current dots).
     - NO zoom controls, NO wheel hijack, NO px-per-month state.
   - Expose `window.renderLineaTiempo`.
   - All new CSS for this view goes in a `<style>` INSIDE linea-tiempo.js injected once (or a small class-prefixed block appended to document.head from JS) so index.html stays uncrowded — class prefix `lt2-` to avoid collisions with existing `.tl-*` classes.
3. Create `tests/test_linea_tiempo.py` (static source assertions, mirroring test_timeline_fetch_all.py):
   - index.html contains the nav button data-tab="lineatiempo", the sections map entry, and the script tag for linea-tiempo.js.
   - linea-tiempo.js exists, contains the TABLEAU20 tuples verbatim, `showEventDetail(`, and the 149/92 dimensions; index.html does NOT contain "TABLEAU20" (renderer stays out of the inline script).
   - index.html still contains `renderEventosTimeline` and its `tl-dot` CSS (existing view untouched guard).
4. Run `node --check src/eth_pipeline/static/linea-tiempo.js` for syntax; eyeball via `./run.sh` + browser at /ui (agent-browser skill optional) if the stack is up — not required for done.
  </action>
  <verify>
    <automated>node --check src/eth_pipeline/static/linea-tiempo.js && ./test.sh tests/test_linea_tiempo.py tests/test_timeline_fetch_all.py</automated>
  </verify>
  <done>New tab renders the vertical timeline from real data: model columns with model-only labels, tableau20 colors (DB-backed where available), vertical months with left "Jan 2026" labels, centered layout, 149×92 bordered rectangles with clipped centered descriptions, click opens detail; existing Cronología view untouched; all new JS in linea-tiempo.js.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| client→/events/colors | read endpoint behind passcode C, like all other reads |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-NAP-01 | Information disclosure | GET /events/colors | low | mitigate | `@require_passcode("C")` — same gate as sibling read endpoints; response exposes only model strings + palette indices, no keys/ids |
| T-NAP-02 | Denial of service | GET /events/colors | low | accept | DISTINCT over model strings joined to ≤ one row per provider — result set bounded by provider count; no pagination needed |
| T-NAP-03 | Tampering | model_color rows | medium | mitigate | color_index CHECK (0..19) + UNIQUE(provider_id) constrain values; writes only via migration backfill and `assign_free_color`; no client-writable path |
| T-NAP-SC | Tampering | npm/pip installs | high | mitigate | no new packages — alembic/asyncpg/fastapi already present; no supply-chain checkpoint needed |
</threat_model>

<verification>
- `./test.sh` full suite green (migration tests updated to 0006, new color + static-structure tests pass, existing suite unregressed — especially test_timeline_fetch_all.py guarding the old view).
- Fresh DB path: `schema-init` (schema.sql v6 baseline + alembic upgrade head) reaches 0006 with model_color populated.
- Dev stack: `./run.sh`, open /ui → "Línea de tiempo" tab shows the vertical timeline; clicking a rectangle opens the detail panel; deleting a provider in /ui/providers frees its color (verify via /events/colors).
</verification>

<success_criteria>
- Migration 0006 exists, is head, backfills colors for existing providers, and never touches schema.sql.
- model_color is 1:1 with llm_provider via UNIQUE FK ON DELETE CASCADE; add_provider assigns the lowest free index; deletion frees it.
- GET /events/colors serves model→color_index (null for provider-less models), passcode-gated, declared before /events/{event_id}.
- "Línea de tiempo" tab: vertical old→new months, model-only labels on top, per-model colored 149×92 rounded rectangles with clipped centered short descriptions, month lines with left "Jan 2026" labels, background guide preserved, no zoom, centered with right compensation, click-through to detail.
- Existing Cronología view and its code paths are unmodified.
- All renderer JS lives in static/linea-tiempo.js.
</success_criteria>

<output>
Create `.planning/quick/260906-nap-new-vertical-timeline-view-as-linea-de-t/260906-nap-SUMMARY.md` when done
</output>
