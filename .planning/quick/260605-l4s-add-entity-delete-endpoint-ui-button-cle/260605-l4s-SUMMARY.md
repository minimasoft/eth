---
status: complete
date: 2026-06-05
commits:
- HEAD
---

## Summary

### What was done

1. **Fixed column name bug** - All SQL queries in `entities.py` used `canonical_entity_id` but the actual column name is `canonical_entity`. Also fixed wrong join columns (`r.event_id` → `r.event`, `e.document_id` → `e.document`) and wrong `event_participant` column (`document_id` → subquery, `canonical_entity_id` → `out_entity`).

2. **Cleaned 181 orphan entities** - Entities that had zero references (due to the column name bug preventing proper linking) were deleted.

3. **Added `DELETE /entities/{entity_id}` endpoint** - Deletes a canonical entity, OR-effects references via FK SET NULL. Returns affected reference count.

4. **Added delete button in entities UI** - New "Acciones" column with a delete button per row. Uses event delegation to handle clicks with confirmation dialog.

### Files changed
- `src/eth_pipeline/api/routes/entities.py` - All SQL queries fixed + new delete endpoint
- `src/eth_pipeline/api/models.py` - Added `EntityDeleted` model
- `src/eth_pipeline/static/index.html` - Added delete column + button + handler
- `src/eth_pipeline/api/routes/documents.py` - Fixed `event_participant` column name

### Verification
- `GET /entities` returns 200 with correct counts
- 181 orphan entities cleaned up
- API container restarted with updated code
