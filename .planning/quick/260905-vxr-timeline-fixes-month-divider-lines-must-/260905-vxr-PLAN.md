---
phase: quick-260905-vxr
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/eth_pipeline/static/index.html
autonomous: true
requirements: []
must_haves:
  truths:
    - Month divider lines render underneath data dots (dots visibly on top where they overlap a divider)
    - Timeline axis shows month tick labels at an interval that adapts to tlPxPerMonth (50→6mo, 100→3mo, 200→2mo, 400→1mo, thresholds in between), and labels scroll with the content
    - Mouse wheel over the timeline scrolls it horizontally instead of the page
  artifacts:
    - src/eth_pipeline/static/index.html (tl CSS block + renderEventosTimeline + wheel listener)
  key_links:
    - .tl-dot z-index vs .tl-month-div z-index in the .tl-canvas stacking context
    - tick-interval lookup vs tlPxPerMonth after ×1.25/÷1.25 zoom steps (arbitrary intermediate values like 122, 153)
    - wheel listener attached to persistent #eventos-timeline (delegation) because .tl-scroll is recreated on every render
---

<objective>
Fix three Cronología (timeline) issues in src/eth_pipeline/static/index.html:
1. Month divider lines draw over data dots → draw under them.
2. Axis shows only first/last date → show month tick labels along the timeline, interval adapting to zoom (50px/mo→every 6 months, 100→3, 200→2, 400→1, with threshold lookup for intermediate zoom values).
3. Mouse wheel over the timeline scrolls it horizontally instead of scrolling the page.

Purpose: User-reported UX defects from quick task 260905-txn's timeline rendering.
Output: Patched index.html (CSS block ~lines 1153–1210, renderEventosTimeline ~lines 2899–3092), committed atomically.
</objective>

<context>
@src/eth_pipeline/static/index.html

Key code locations (read these ranges, do not re-read the whole file):
- CSS: lines 1153–1210 — .tl-scroll (1178), .tl-canvas (1179, has padding-bottom:28px axis zone), .tl-month-div (1184–1187, currently z-index:1), .tl-dot (1188–1194, no base z-index; hover sets z-index:2), .tl-axis (1195–1200, flex space-between min/max).
- JS: lines 2899–3092 — renderEventosTimeline: monthEntries walk (2950–2974), dotLeftPx (2976–2991), canvas/divider HTML (3007–3030), min/max axis HTML (3032–3035), scroll restore (3053–3055), zoom click handler with ×1.25 / ÷1.25 and clamp 50–400 (3070–3079).
- Persistent listeners pattern: #eventos-timeline click delegation at lines 3064–3079 — the wheel listener must follow the same delegation pattern because .tl-scroll is recreated on every innerHTML re-render.

Prior quick task context (260905-txn): tlPxPerMonth persists across re-renders; lastTimelineData caches the dataset for zoom re-renders; savedScrollLeft restores horizontal position after re-render.
</context>

<tasks>

<task type="auto">
  <name>Task 1: Draw month dividers under the data dots (stacking fix)</name>
  <files>src/eth_pipeline/static/index.html</files>
  <action>
In the .tl-month-div / .tl-dot CSS rules (~lines 1184–1194): give .tl-dot a base `z-index: 2` so dots always paint above the dividers (which keep z-index: 1). The dots live inside .tl-lane (position:relative, no z-index), so they participate in the same .tl-canvas stacking context as the canvas-level dividers — a base z-index:2 on .tl-dot is sufficient; no change to .tl-lane or .tl-month-div markup. Then remove the now-redundant `z-index: 2` from the `.tl-dot:hover` rule (keep the `transform: scale(1.4)` hover effect). Do NOT reorder DOM or move dividers into lanes — the CSS-only stacking change is the fix.
  </action>
  <verify>
    <automated>rg -n '^     \.tl-dot \{' -A 6 src/eth_pipeline/static/index.html | rg 'z-index: 2' && rg -n '\.tl-dot:hover' -A 1 src/eth_pipeline/static/index.html | rg -v 'z-index' && rg -n '\.tl-month-div' -A 3 src/eth_pipeline/static/index.html | rg 'z-index: 1'</automated>
  </verify>
  <done>.tl-dot has base z-index: 2; .tl-dot:hover no longer declares z-index; .tl-month-div unchanged at z-index: 1 — dots render above dividers where they overlap.</done>
</task>

<task type="auto">
  <name>Task 2: Month tick-label axis with zoom-adaptive interval</name>
  <files>src/eth_pipeline/static/index.html</files>
  <action>
Replace the min/max-only axis (JS lines 3032–3035) with per-month tick labels rendered inside .tl-canvas so they scroll with content:

1. CSS (.tl-axis rule ~lines 1195–1200): change from `display:flex; justify-content:space-between` to a plain absolute positioning wrapper (`position:absolute; left:0; right:0; bottom:0; height:18px;` keep font-size/color/tabular-nums). Add `.tl-axis span { position:absolute; bottom:0; white-space:nowrap; }` — horizontal position comes from an inline `left` style. Labels must not wrap or push layout.

2. JS inside renderEventosTimeline, after the monthEntries loop: compute the label interval from the current tlPxPerMonth with threshold lookup consistent with the user's mapping table (50→6, 100→3, 200→2, 400→1): px < 75 → every 6 months; px < 150 → every 3; px < 300 → every 2; else every 1. This handles arbitrary ×1.25 zoom values (62→6mo, 78/98/122→3mo, 153/191/239/298→2mo, 373/400→1mo).

3. Build tick HTML: for each monthEntries index i where i % interval === 0, emit `<span style="left:{entry.px}px">` containing a short month-year label formatted in Spanish, e.g. `new Date(entry.startMs).toLocaleDateString('es-ES', { month: 'short', year: 'numeric' })` (produces "ene 2025" style), passed through escapeHtml. Render the axis wrapper in the same place the old min/max axis was emitted (inside the canvas, after the divider loop), only when dated.length is truthy (same condition as today).

4. Edge clipping: the rightmost label may overflow the canvas width — that is acceptable (it is inside the scrollable canvas; .tl-scroll has overflow-x auto so the label extends the scroll area naturally or gets clipped at the very end). Do not add special right-edge repositioning logic.

5. Keep .tl-canvas `padding-bottom: 28px` as-is — the 18px axis wrapper fits in the existing axis zone that .tl-month-div's `bottom: 38px` already accounts for.

Do NOT change dotLeftPx, monthEntries construction, zoom handlers, or savedScrollLeft logic.
  </action>
  <verify>
    <automated>rg -n 'tlPxPerMonth < 75|tlPxPerMonth < 150|tlPxPerMonth < 300' src/eth_pipeline/static/index.html | wc -l | rg '^3$' && rg -n "toLocaleDateString\('es-ES'" src/eth_pipeline/static/index.html | wc -l | rg '^[1-9]' && rg -n 'justify-content: space-between' src/eth_pipeline/static/index.html | rg -v 'tl-axis' >/dev/null; rg -n '\.tl-axis \{' -A 5 src/eth_pipeline/static/index.html | rg -v 'space-between'</automated>
  </verify>
  <done>Axis renders one absolutely-positioned label per Nth month start (N from threshold lookup: <75→6, <150→3, <300→2, else 1), labels live inside .tl-canvas and scroll with content, Spanish month-year format, old flex min/max axis removed.</done>
</task>

<task type="auto">
  <name>Task 3: Mouse wheel scrolls the timeline horizontally</name>
  <files>src/eth_pipeline/static/index.html</files>
  <action>
Add a wheel listener on the persistent `#eventos-timeline` element (next to the existing click delegation listeners at ~lines 3064–3079) registered ONCE at init — do NOT attach inside renderEventosTimeline, because innerHTML re-renders recreate .tl-scroll and would leak/duplicate listeners. Registration must use `{ passive: false }` so preventDefault works.

Handler logic:
1. `var scroll = e.target.closest('.tl-scroll'); if (!scroll) return;` — only act when the wheel is over the timeline scroll area.
2. Pick the dominant axis: if `Math.abs(e.deltaY) >= Math.abs(e.deltaX)` use e.deltaY (vertical wheel → horizontal scroll), else use e.deltaX (trackpads already horizontal — honor natively).
3. `scroll.scrollLeft += delta;` then `e.preventDefault();` — stops the page from scrolling while the cursor is over the timeline.
4. Guard: only preventDefault/redirect when there is actually horizontal overflow (`scroll.scrollWidth > scroll.clientWidth`) so a short timeline doesn't hijack page scroll.

No changes to zoom buttons, render, or scroll restore.
  </action>
  <verify>
    <automated>rg -n "addEventListener\('wheel'" src/eth_pipeline/static/index.html | wc -l | rg '^1$' && rg -n "addEventListener\('wheel'" -A 2 src/eth_pipeline/static/index.html | rg 'passive: false'</automated>
  </verify>
  <done>Exactly one wheel listener, registered once on #eventos-timeline with passive:false; vertical wheel delta translates to .tl-scroll scrollLeft with preventDefault; trackpad deltaX honored; short timelines (no overflow) leave page scroll untouched.</done>
</task>

</tasks>

<verification>
All checks run against src/eth_pipeline/static/index.html:
1. `rg` gates from each task pass (stacking z-indexes, tick-interval thresholds, es-ES label formatting, single passive:false wheel listener).
2. Manual browser check (per AGENTS.md: `./run.sh`, open Eventos → Cronología):
   - Dots visibly paint on top of divider lines at month boundaries.
   - Axis shows month labels (e.g. "ene 2025"); zoom − until 50px/mo → labels every 6 months; default 100 → every 3; zoom + to ~200 → every 2; to 400 → every month. Labels track the content when scrolling horizontally.
   - Mouse wheel over the timeline scrolls it left/right without scrolling the page; wheel elsewhere still scrolls the page.
3. Zoom re-render (via +/− buttons) keeps labels correct at intermediate values (e.g. 122 px/mo → 3-month interval, 153 → 2-month).
</verification>

<success_criteria>
- Divider/dot stacking fixed with a CSS-only change (dots above dividers, hover still scales).
- Axis is a real month tick axis inside the scroll canvas, interval derived from tlPxPerMonth thresholds matching the 50→6 / 100→3 / 200→2 / 400→1 table and all intermediate zoom values.
- Wheel-over-timeline scrolls horizontally (passive:false, delegation-safe across re-renders, overflow-guarded).
- Single-file change to src/eth_pipeline/static/index.html, no behavioral regressions in zoom, scroll restore, or event detail clicks.
</success_criteria>

<output>
On completion, write SUMMARY and update STATE.md per quick-task workflow; commit docs+code atomically.
</output>
