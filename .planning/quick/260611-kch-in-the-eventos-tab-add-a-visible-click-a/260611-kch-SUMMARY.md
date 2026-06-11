# Summary: 260611-kch

**Description:** Add visible click affordance to Eventos tab event list rows
**Status:** complete
**Commit:** d4c1c19

## Changes

- `src/eth_pipeline/static/index.html`: Added "→ Ver" affordance column to Eventos table

## Verification

- [x] Eventos table `<thead>` has new `<th class="col-actions" aria-label="Acción">` after Refs column
- [x] Each event row renders a "→ Ver" styled button in the last column (1 match in file)
- [x] Existing `tr.style.cursor = 'pointer'` and `tr.addEventListener('click', ...)` remain intact
- [x] `.col-actions` CSS class (width: 100px, text-align: center) already existed — no CSS changes needed
- [x] Styling matches existing blue (#2563eb) references-table affordance pattern
