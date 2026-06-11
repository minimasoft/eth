---
status: completed
---

# Quick Task 260611-hxu: Sort eventos by time ascending, nulls at end

## Changes Made

- `src/eth_pipeline/static/index.html`:
  - Changed API sort order from `desc` to `asc` in `fetchEventos()` (line 2341)
  - Added client-side sort in `renderEventos()` that sorts by `time_start` ascending with nulls at end (lines 2391-2396)

## Result

Events in the "Eventos" tab now display oldest first (time ascending). Events with a null/undefined `time_start` are pushed to the very end of the list.
