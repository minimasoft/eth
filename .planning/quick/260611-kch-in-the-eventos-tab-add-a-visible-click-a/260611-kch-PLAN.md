---
id: 260611-kch
type: quick
description: In the Eventos tab, add a visible click affordance (button/arrow) to event list rows so users understand they are clickable
files_modified:
  - src/eth_pipeline/static/index.html
---

## Objective

Add a visible "→ Ver" affordance column to the Eventos table rows, replacing the current invisible `cursor: pointer` click handler with an explicit visual signal that rows are clickable.

**Purpose:** Users currently cannot tell the rows are interactive — there is no icon, button, or label indicating clickability. Adding an affordance column follows the same pattern already used in the references detail table (🔍 Ver button at line 2610).

**Output:**
- A new `<th>` column header in the Eventos table
- Each row rendered with a styled "→ Ver" button cell
- Consistent with the existing blue-button pattern from the references table (but without emoji, per project guidelines)

## Discovery Level

**Level 0 — Skip.** Pure internal work, established codebase patterns (same file, same table rendering style, same affordance pattern from references table at line 2610).

## Context

@/home/u/src/eth/src/eth_pipeline/static/index.html
- Line 1152-1162: Eventos table `<thead>` — current columns: ID, Tiempo, Título, Lugar, Particip., Refs — no affordance column
- Line 2398-2411: `renderEventos()` — creates rows with `cursor: pointer` + click handler but NO visible affordance
- Line 2610: Existing pattern in references table — `🔍 Ver` styled as inline-flex blue badge (inspiration, without emoji)
- Line 221-224: `.col-actions` CSS class (width:100px, text-align:center) — existing column style to reuse
- Line 526-528: `.documents-table tbody tr:hover { background: #f8fafc; }` — existing row hover state

## Tasks

<task type="auto">
  <name>Add visible "→ Ver" affordance column to Eventos table rows</name>
  <files>
    src/eth_pipeline/static/index.html
  </files>
  <action>
    Make two changes to the Eventos table in `index.html`:

    **1. Table header (line ~1159):** Add a new `<th>` after the "Refs" column for the affordance. Use:
    `<th class="col-actions" aria-label="Acción"></th>`
    — Empty header label (screen-reader-only via aria-label) keeps the table clean.

    **2. `renderEventos()` function (line ~2410):** Add a `<td class="col-actions">` cell at the end of each row's innerHTML with:
    ```
    '<span style="display:inline-flex;align-items:center;gap:4px;font-size:13px;font-weight:500;color:#2563eb;padding:2px 12px;border-radius:4px;border:1px solid #bfdbfe;background:#eff6ff;cursor:pointer">→ Ver</span>'
    ```
    — Uses the same blue color scheme and styling as the existing references-table affordance (line 2610), but with "→" arrow instead of 🔍 emoji, per the project's no-emoji-in-files guideline.
    — The `<span>` sits inside the `<td>` so clicking the span or the td area both trigger the existing `tr` click handler.

    Do NOT change the existing `tr.style.cursor = 'pointer'` and `tr.addEventListener('click', ...)` — keep those. The affordance is additive.

    Do NOT add any CSS — `.col-actions` already exists at line 221-224 with `width: 100px; text-align: center;` and the span's inline styles handle the button visual.
  </action>
  <verify>
    <automated>grep -c '→ Ver' src/eth_pipeline/static/index.html</automated>
  </verify>
  <done>
    - Eventos table `<thead>` has a new `<th class="col-actions">` after Refs column
    - Every rendered event row shows a visible "→ Ver" button in the last column
    - Button styling matches the existing blue (#2563eb) references-table affordance pattern
    - Row click handler still works (the affordance sits inside the clickable row)
  </done>
</task>

## Success Criteria

- Eventos table rows display a visible "→ Ver" affordance so users immediately understand they are clickable
- Styling is consistent with the existing references-table affordance (blue border, light blue background, rounded)
- No regressions: existing cursor:pointer, click handlers, and row hover states remain intact
