---
phase: quick
plan: 260906-vct
type: execute
wave: 1
depends_on: []
files_modified:
  - src/eth_pipeline/static/index.html
  - src/eth_pipeline/static/providers.html
autonomous: true
requirements: []
must_haves:
  truths:
    - "When the passcode modal opens, the backdrop darkens the page at 60% black opacity (up from 40%) — a ~50% increase in darkening."
  artifacts:
    - "src/eth_pipeline/static/index.html — .passcode-backdrop background rgba(0,0,0,0.6)"
    - "src/eth_pipeline/static/providers.html — .passcode-backdrop background rgba(0,0,0,0.6)"
  key_links:
    - "promptPasscode() creates a div with class 'passcode-backdrop'; the CSS rule change is picked up automatically in both pages — no JS changes needed."
---

<objective>
Darken the passcode modal's background scrim by ~50% (from 40% to 60% black opacity) on both pages that use it.

Purpose: The passcode modal's backdrop currently does not visually separate the modal strongly enough from the page behind it.

Output: Updated `.passcode-backdrop` CSS in both static HTML files.
</objective>

<context>
The passcode modal is generated at runtime by `promptPasscode()` in two self-contained static pages. The backdrop styling lives purely in CSS — no JS changes are required.

Grep-verified: `.passcode-backdrop {` appears in exactly two files:
- `src/eth_pipeline/static/index.html` line 482-485 — current: `background: rgba(0,0,0,0.4);`
- `src/eth_pipeline/static/providers.html` line 426-429 — current: `background: rgba(0,0,0,0.4);`
</context>

<tasks>

<task type="auto">
  <name>Task: Increase passcode backdrop opacity from 0.4 to 0.6 in both static pages</name>
  <files>src/eth_pipeline/static/index.html, src/eth_pipeline/static/providers.html</files>
  <action>In both files, inside the `.passcode-backdrop` CSS rule, change the background value `rgba(0,0,0,0.4)` to `rgba(0,0,0,0.6)` (0.4 × 1.5 = 0.6 — the requested ~50% more darkening). Change nothing else in the rule: `position: fixed; inset: 0; z-index: 60; display: flex; align-items: center; justify-content: center;` stay as-is. Do not touch `.passcode-modal`, `.passcode-input`, or any JS. Do not add new CSS files — these pages keep their inline styles.</action>
  <verify>
    <automated>grep -A1 "\.passcode-backdrop {" src/eth_pipeline/static/index.html src/eth_pipeline/static/providers.html | grep -c "rgba(0,0,0,0.6)" | grep -qx "2" && ! grep -A1 "\.passcode-backdrop {" src/eth_pipeline/static/index.html src/eth_pipeline/static/providers.html | grep -q "rgba(0,0,0,0.4)"</automated>
  </verify>
  <done>`.passcode-backdrop` uses `background: rgba(0,0,0,0.6)` in both index.html and providers.html; no other styles changed.</done>
</task>

</tasks>

<verification>
- `grep -n "rgba(0,0,0,0.6)" src/eth_pipeline/static/index.html` → present in the `.passcode-backdrop` rule (line ~483).
- `grep -n "rgba(0,0,0,0.6)" src/eth_pipeline/static/providers.html` → present in the `.passcode-backdrop` rule (line ~427).
- No remaining `rgba(0,0,0,0.4)` inside a `.passcode-backdrop` rule.
- Visual check (optional, needs dev stack): `./run.sh`, open the UI, trigger the passcode prompt — the page behind should be noticeably darker than before.
</verification>

<success_criteria>
The passcode modal's backdrop darkens the background at 60% black opacity on both pages where it appears, with no other visual or behavioral changes.
</success_criteria>

<output>
When done, append a short summary to `.planning/quick/260906-vct-passcode-modal-should-darken-the-backgro/` and commit:
`git commit -m "fix(ui): darken passcode modal backdrop to 60% opacity"`
</output>
