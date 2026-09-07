---
status: complete
date: 2026-09-06
commits: [297473d, 9d741ba]
---

# Quick Task 260906-u3r: Timeline event navigation bugfix

## Outcome

Two fixes landed under this task id:

1. **2977473d → 297473d — logout re-nest** (completed by the first executor
   run before cancellation): `#logout-btn` wiring was nested inside
   `ensurePasscode()`'s success branch (from e4db2f5), so "Cerrar sesión" was
   dead for users with stored passcodes. Moved to script top level in the
   passcode section; guarded by
   `test_logout_wiring_top_level_not_nested_in_ensure_passcode`.

2. **9d741ba — timeline card click navigates via hash** (orchestrator-direct
   fix after the user rejected the split-view direction mid-execution):
   clicking a Línea de tiempo card now sets
   `location.hash = 's=eventos&event=<id>'` and nothing else — index.html's
   existing hashchange → applyHash machinery switches to the Eventos tab and
   opens the detail (fetch happens only after the address/tab changed).
   The 260906-t6c 50-50 split view (markup, CSS, reparenting state machine,
   selection highlight) was removed as superseded.

## Plan deviation (Rule 0/1)

The original plan preserved the t6c split view and verified it in a rebuilt
image. The user clarified the desired interaction is hash navigation to the
Eventos tab (`#s=eventos&event=<id>`), not an in-place split detail — the
split was a misreading of intent. Fix applied directly, plan superseded.

## Verification

- `./test.sh --unit`: 143 passed, 4 skipped (includes new guards:
  `test_timeline_card_click_navigates_via_hash`,
  `test_timeline_split_and_in_place_detail_removed`,
  `test_sync_hash_has_no_timeline_event_option`,
  `test_apply_hash_has_no_timeline_event_branch`;
  `test_linea_tiempo_js_contents` retargeted to the hash contract)
- `node --check` clean on linea-tiempo.js and the extracted inline app script
- Manual: click a card in Línea de tiempo → URL becomes
  `#s=eventos&event=<id>`, Eventos tab opens on the event detail; browser
  Back returns to the timeline

## Notes

- `#s=lineatiempo` deep links still work (applyHash → onTabClick); `event=`
  is now only meaningful for `#s=eventos`.
- The stale-image root cause found during planning (dev stack serving
  pre-t6c assets) still requires `./run.sh --build` to pick this change up.
