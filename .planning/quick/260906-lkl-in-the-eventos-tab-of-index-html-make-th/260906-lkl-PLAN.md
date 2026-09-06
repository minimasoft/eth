---
phase: quick
plan: 260906-lkl
type: execute
wave: 1
depends_on: []
files_modified:
  - src/eth_pipeline/static/index.html
autonomous: true
requirements: []
user_setup: []

estimate:
  tokens: 12000
  raw_tokens: 6000
  tasks: 1
  confidence: med

must_haves:
  truths:
    - Opening the Eventos tab on a fresh page load renders the Cronología timeline view, not the table
    - Clicking "Tabla" still switches to the table view and back, with active-button styling following the switch
    - Timeline fetch path (fetchEventos → fetchAllEventos) is used on initial load without any code duplication
  artifacts:
    - src/eth_pipeline/static/index.html (timeline default)
  key_links:
    - eventosViewMode initial value → fetchEventos branch (line ~2791) → renderEventosTimeline
    - data-mode="timeline" button → .active class at markup so UI matches state before first click
---

<objective>
Make the Cronología (timeline) view the default view when the Eventos tab loads, instead of the Tabla (table) view.

Purpose: Users primarily consume events as a timeline; requiring a click after every page load is friction.

Output: src/eth_pipeline/static/index.html with timeline as initial Eventos view.
</objective>

<execution_context>
@/home/u/src/eth/.opencode/gsd-core/workflows/execute-plan.md
@/home/u/src/eth/.opencode/gsd-core/templates/summary.md
</execution_context>

<context>
@src/eth_pipeline/static/index.html

Relevant facts (verified by planner):
- Line 1410-1411: view toggle markup — the `class="active"` is hardcoded on the `data-mode="table"` button.
- Line 2945: `var eventosViewMode = 'table';` — single state variable controlling which render path runs.
- Line 2791: `if (eventosViewMode === 'timeline') return fetchAllEventos();` and line 2817: `if (eventosViewMode === 'timeline') renderEventosTimeline(data);` — fetchEventos already fully supports the timeline path; no new code needed.
- renderEventosTimeline (line 2951) correctly hides the table container/pagination and shows the timeline element, including the empty state.
- There is NO localStorage/persistence for view mode anywhere (only the in-memory zoom scale `tlPxPerMonth`). Decision (planner discretion, per task brief "simplest correct behavior"): no persistence — timeline is the default on every fresh load; the existing toggle switches views per session. Do not add localStorage.
- No other write sites for `eventosViewMode` exist (grep confirmed: definition at 2945, assignment only in the toggle handler at 3157).
</context>

<tasks>

<task type="auto">
  <name>Task 1: Default Eventos tab to Cronología timeline view</name>
  <files>src/eth_pipeline/static/index.html</files>
  <action>
Two coordinated edits in src/eth_pipeline/static/index.html so the markup and the state variable agree with each other (mismatch would show the wrong active button on first paint):

1. Markup (lines 1410-1411): move the `active` class from the table button to the timeline button — `data-mode="table"` loses `class="active"`, `data-mode="timeline"` gains `class="active"`. Leave the toggle click handler (line 3152) untouched; it already manages classes from there.

2. State (line 2945): change `var eventosViewMode = 'table';` to initialize as `'timeline'`.

That is the entire change. fetchEventos() already branches to fetchAllEventos()/renderEventosTimeline() when the mode is timeline (lines 2791, 2817), and renderEventosTimeline hides the table container and handles the empty state. Do NOT add localStorage persistence, do NOT touch the toggle handler, do NOT duplicate rendering logic, and do NOT add comments.

Decision note: the task brief allowed either persistence-after-explicit-switch or simplest-correct; the planner chose simplest-correct (no persistence) because no view-persistence mechanism exists today and adding one would expand scope beyond the one-file tweak (per "decide" discretion in the task description).
  </action>
  <verify>
    <automated>cd /home/u/src/eth && ! grep -n 'data-mode="table" class="active"' src/eth_pipeline/static/index.html && grep -n 'data-mode="timeline" class="active"' src/eth_pipeline/static/index.html && grep -n "var eventosViewMode = 'timeline'" src/eth_pipeline/static/index.html && node -e "const s=require('fs').readFileSync('src/eth_pipeline/static/index.html','utf8'); const m=s.match(/<script>([\s\S]*?)<\/script>/); new Function(m[1]); console.log('script parses OK')"</automated>
  </verify>
  <done>
- The Cronología button carries the active class in markup and `eventosViewMode` initializes to 'timeline', so a fresh load of the Eventos tab fetches and renders the timeline (empty state included when no events).
- The Tabla button has no active class at load; clicking it still switches views with correct active styling via the existing handler.
- No persistence added; inline script still parses without syntax errors.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

None affected — client-side static markup/state default change; no new inputs, endpoints, or data flows.

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-QLK-01 | DoS | fetchAllEventos client-side fetch-all loop on initial load | low | accept | Existing behavior from 260905-to0 (paginated fetch-all with per_page=100); defaulting to it changes load timing, not volume; dataset size already accepted |
</threat_model>

<verification>
- Automated gate in Task 1 passes: active class on timeline button, no active class on table button, `eventosViewMode` initializes to timeline, inline script parses via `new Function`.
- Manual spot-check (optional, if dev stack is up): load index.html, open Eventos tab — Cronología renders first; click Tabla then Cronología — both switch correctly.
</verification>

<success_criteria>
Eventos tab shows the timeline view on every fresh page load without user interaction, while the existing table/timeline toggle remains fully functional.
</success_criteria>

<output>
Create .planning/quick/260906-lkl-in-the-eventos-tab-of-index-html-make-th/260906-lkl-SUMMARY.md when done
</output>
