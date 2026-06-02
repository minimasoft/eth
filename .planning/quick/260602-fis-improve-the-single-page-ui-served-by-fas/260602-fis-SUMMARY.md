---
status: complete
quick_id: 260602-fis
date: 2026-06-02
tasks_completed: 2
---

# Quick Task 260602-fis: UI Improvements

## Summary

Improved the FastAPI single-page UI with 4 enhancements:

1. **Manual refresh buttons** in Documents, Entities, and References tab toolbars
2. **Always refresh on tab switch** — removed firstLoad flags, all tabs fetch fresh data via onTabClick
3. **New References view tab** — paginated table with verbatim_text, reference_type, event context, and document context, with search and type filtering
4. **Detailed document processing status** — error_message shown inline for failed documents, new status badge CSS classes for intermediate states (extracted, extracting_blob, extracting_text, chunking)

## Files Changed

- `src/eth_pipeline/api.py` — Added ReferenceListItem/ReferenceListResponse models, GET /references endpoint with pagination/search/type filtering
- `src/eth_pipeline/static/index.html` — All 4 UI improvements in single-page HTML/CSS/JS

## Verification

- API file parses without syntax errors
- New /references endpoint added with FETCH for nested event/document/entity data
- All 4 UI changes verified: refresh buttons, onTabClick, references tab, error_message display, new status CSS
