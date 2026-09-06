---
phase: quick-260905-txn
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/eth_pipeline/static/index.html
autonomous: true
requirements: [QUICK-260905-txn]
estimate:
  tokens: 45000
  raw_tokens: 30000
  tasks: 2
  confidence: med
must_haves:
  truths:
    - Cronología timeline shows +/− zoom buttons at the top; clicking them re-renders at a new px/month scale clamped to [50, 400]
    - Default scale is 100px per month on first render
    - Horizontal scrolling moves ONLY the timeline canvas; the model (y-axis) label column stays visually fixed
    - Every month boundary is marked by a thin, low-intensity vertical divider line spanning the lanes
    - Zoom state persists across re-renders triggered by search/filter changes (module-level variable)
    - Event dots still open the detail modal on click; undated events section still renders below
  artifacts:
    - src/eth_pipeline/static/index.html (updated renderEventosTimeline, tl-* CSS, zoom toolbar)
  key_links:
    - zoom buttons → tlPxPerMonth clamp → renderEventosTimeline(eventosData) re-render
    - fetchAllEventos → eventosData cache → zoom re-render uses cached data without refetch
---

<objective>
Improve the Cronología timeline rendering in the Eventos tab: pixel-per-month scale (default 100, min 50, max 400), +/- zoom buttons at the top, horizontal scroll confined to the timeline area with model labels fixed, and thin subtle month divider lines.

Purpose: The current percentage-based flex rendering gives no zoom control and offers no month grid reference; with all events now fetched (prior quick task 260905-to0), users need to zoom into dense periods and orient by month.
Output: Updated `src/eth_pipeline/static/index.html` — single-file vanilla JS/CSS, no new dependencies.
</objective>

<execution_context>
@/home/u/src/eth/.opencode/gsd-core/workflows/execute-plan.md
@/home/u/src/eth/.opencode/gsd-core/templates/summary.md
</execution_context>

<context>
@src/eth_pipeline/static/index.html

Key locations (read once, all in this file):
- CSS `.tl-*` block: lines ~1153-1179 (`.tl-note`, `.tl-legend`, `.tl-row`, `.tl-lane-label` 240px fixed, `.tl-lane` flex:1, `.tl-dot`, `.tl-axis`)
- `renderEventosTimeline(data)`: lines ~2881-2958 — builds lanes keyed by model, positions dots as percentages `((t-min)/(max-min))*100`, renders min/max axis, undated section
- `fetchAllEventos()`: lines ~2766-2822 — fetches all pages, stores merged result in module-level `eventosData`, calls `renderEventosTimeline(merged)`
- `eventosViewMode` toggle handler: lines ~2966-2977 — re-calls `fetchEventos()` on mode switch
- Click delegation on `#eventos-timeline` (lines ~2960-2964) uses `[data-event-id]` closest — keep dot/event markup carrying `data-event-id`

Conventions: vanilla JS with `var`/`function` declarations in this section (not ES class), inline styles via string-built HTML, Spanish UI copy, `escapeHtml()` for all interpolated text, `modelPalette(modelKey(item))` for dot colors. Never run pytest/uv/npm ad-hoc on the host (AGENTS.md) — static HTML needs no Python tests; verify in browser.
</context>

<tasks>

<task type="auto">
  <name>Task 1: Restructure timeline CSS + DOM — fixed label column, scrollable canvas, zoom toolbar, month divider styles</name>
  <files>src/eth_pipeline/static/index.html</files>
  <action>
Rework the `/* ---- Timeline view ---- */` CSS block (~lines 1153-1179) to a two-column layout:

1. New structural classes (replace/extend `.tl-row` usage):
   - `.tl-toolbar`: flex row, holds the existing note text and the zoom controls; margin-bottom ~12px.
   - `.tl-zoom`: inline-flex group of two buttons (styled like `.view-toggle button`: bordered group, 14px font, cursor pointer, disabled state at scale limits — grayed `color:#cbd5e1; cursor:default`).
   - `.tl-body`: `display:flex` row wrapping label column + scroll area.
   - `.tl-labels-col`: `width:240px; flex-shrink:0` — hosts the per-lane label cells; each cell `height:40px; margin-bottom:10px; display:flex; align-items:center; justify-content:flex-end; gap:6px; padding-right:12px` (matches old `.tl-lane-label` metrics so labels align with lanes).
   - `.tl-scroll`: `flex:1; overflow-x:auto; overflow-y:hidden; min-width:0`.
   - `.tl-canvas`: `position:relative` block whose inline width is set in JS to `monthsSpan * pxPerMonth` px; hosts the lane rows and dividers.
   - `.tl-lane` keeps `position:relative; height:40px; margin-bottom:10px; background:#f8fafc; border:1px solid #e2e8f0; border-radius:6px` but drops `flex:1` (width is the canvas width).
2. `.tl-month-div`: `position:absolute; top:0; bottom:0; width:1px; background:#e8edf3; pointer-events:none` — thin and low-intensity (barely visible against `#f8fafc` lane background but distinguishable). z-index below `.tl-dot` hover (dots already get `z-index:2` on hover).
3. `.tl-dot` positioning stays `position:absolute; top:50%` — only the `left` value changes from % to px in Task 2.
4. Keep `.tl-undated` full-width BELOW `.tl-body` (undated events have no x position; do not put them inside the scroll canvas).
5. In `renderEventosTimeline`'s HTML-building section, restructure the emitted markup to: toolbar (note + `−`/`+` zoom buttons with ids `tl-zoom-out` / `tl-zoom-in`, using `&minus;` and `+` labels) → `.tl-body` ( `.tl-labels-col` with one label cell per lane, then `.tl-scroll` > `.tl-canvas` with one `.tl-lane` per lane) → axis → undated. Model chips and lane counts move into the label cells (same content as today's `.tl-lane-label`).

Per user requirement: ONLY the timeline area scrolls horizontally — the label column lives outside `.tl-scroll` so it stays fixed (this is the point of the two-column restructure; do not use a single scroll container with sticky labels).
  </action>
  <verify>
    <automated>rg -c 'tl-scroll|tl-canvas|tl-month-div|tl-labels-col|tl-zoom' src/eth_pipeline/static/index.html</automated>
  </verify>
  <done>New CSS classes exist with the fixed-label + scrollable-canvas layout; markup structure in renderEventosTimeline emits toolbar, label column, and scroll canvas.</done>
</task>

<task type="auto">
  <name>Task 2: Pixel-per-month positioning, zoom state + handlers, month boundary dividers</name>
  <files>src/eth_pipeline/static/index.html</files>
  <action>
In the Eventos timeline JS section (~line 2879+):

1. Module-level state next to `var eventosViewMode = 'table';`:
   - `var tlPxPerMonth = 100;` (default per user requirement)
   - `var TL_PX_PER_MONTH_MIN = 50; var TL_PX_PER_MONTH_MAX = 400;`
2. In `renderEventosTimeline(data)`, replace percentage positioning with pixel positioning:
   - After computing `min`/`max` epoch ms, compute `minMonthStart` = first day of `min`'s month (00:00) and `maxMonthEnd` = last ms of `max`'s month. `monthsSpan = Math.max(1, Math.round((maxMonthEnd - minMonthStart) / avg-month-ms))` — compute month count by iterating month starts (do NOT assume 30-day months; iterate: from `minMonthStart`, repeatedly advance to the 1st of the next month until past `maxMonthEnd`, counting steps).
   - Canvas width: `monthsSpan * tlPxPerMonth` px, set as inline style on `.tl-canvas`.
   - Dot x position uses a month-aware mapping (months have unequal lengths — never divide by a fixed 30-day month): walk month starts from `minMonthStart` once, building an array of `{startMs, px}` entries where each `px` accumulates `tlPxPerMonth` per month since `minMonthStart`. For a dot: find its month entry, then `left = entry.px + ((t - entry.startMs) / msInThatMonth) * tlPxPerMonth`. Clamp dots to `[0, canvasWidth]` (replaces the old 1.5/98.5 % clamps). Handle single-month spans (`min === max` in same month → all dots interpolate within one month, canvas = 1 month wide).
   - Month dividers: reuse the walked month-start array; for every month start AFTER the first, emit `<span class="tl-month-div" style="left:{px}px"></span>` inside `.tl-canvas` (so dividers span all lanes visually — canvas-level, not per-lane; pointer-events:none keeps dots clickable). First month start is the left edge (no divider needed).
   - Zoom handlers (delegated or direct listeners on `#tl-zoom-in` / `#tl-zoom-out`, wired after `tlEl.innerHTML` set — or use event delegation on `#eventos-timeline` alongside the existing click handler): clicking `+` multiplies `tlPxPerMonth` by 1.25, clicking `−` divides by 1.25, then clamps to `[TL_PX_PER_MONTH_MIN, TL_PX_PER_MONTH_MAX]` and rounds to an integer. After clamp, re-render from the cached dataset WITHOUT refetching: keep a reference to the last rendered data (e.g. store `lastTimelineData = data` at the top of `renderEventosTimeline`, or rely on existing module-level `eventosData` set by `fetchAllEventos`) and call `renderEventosTimeline(lastTimelineData)`. Disable `−` at 50 and `+` at 400 (set `disabled` attribute; CSS grays it).
   - Preserve horizontal scroll position across zoom re-renders and across search/filter-triggered re-renders: capture `document.querySelector('#eventos-timeline .tl-scroll').scrollLeft` before rebuilding, restore after. (Cheap UX win; state is the px/month variable, scroll restoration is best-effort.)
3. Persistence across re-renders: `tlPxPerMonth` is module-level so `fetchAllEventos()` → `renderEventosTimeline()` on search/filter changes keeps the chosen scale — no reset. Only a page reload resets it (acceptable).
4. Update the note text to mention zoom, e.g. append 'Usa + / − para acercar o alejar (50–400 px/mes).' — Spanish, matches existing copy style.
5. Keep: `data-event-id` on dots (click delegation opens detail modal), undated section, lane counts, modelChip labels, escapeHtml on all interpolated strings, axis row (min/max dates) — move it inside/aligned under `.tl-scroll` region so its endpoints visually match the canvas edges (e.g. place it inside `.tl-canvas` as an absolutely positioned bottom row, or keep it after `.tl-body` with `margin-left:240px` as today).
  </action>
  <verify>
    <automated>rg -c 'TL_PX_PER_MONTH|tlPxPerMonth' src/eth_pipeline/static/index.html && rg -n 'tl-month-div' src/eth_pipeline/static/index.html | wc -l</automated>
  </verify>
  <done>
- First render uses 100px/month; `+`/`−` step zoom and are disabled at the 400/50 clamps
- Dots positioned by pixel interpolation within their month, not percentages
- One thin divider per month boundary inside the canvas
- Zoom re-renders from cached data (no network request); scale survives search/filter re-renders
- Dot click still opens the event detail modal
  </done>
</task>

</tasks>

<verification>
Browser check (agent-browser skill) against the dev stack (`./run.sh` first, per AGENTS.md):
1. Eventos tab → Cronología: timeline renders at default scale, +/− buttons visible at top
2. Click + repeatedly: canvas widens, disabled at max (400px/month); click − down to min (50px/month), disabled there
3. Scroll horizontally: model labels on the left do NOT move; only lanes scroll
4. Month divider lines visible, thin and subtle, aligned with month starts
5. Change search/filter: zoom level retained; dots reposition; click a dot → detail modal opens
</verification>

<success_criteria>
All must_haves truths observable in the browser; single commit touching only `src/eth_pipeline/static/index.html`; no new dependencies; no changes to fetch logic beyond reusing cached data for zoom re-render.
</success_criteria>

<output>
Create `/home/u/src/eth/.planning/quick/260905-txn-improve-cronologia-timeline-rendering-zo/260905-txn-SUMMARY.md` when done
</output>
