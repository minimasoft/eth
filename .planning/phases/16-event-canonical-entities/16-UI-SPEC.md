# Phase 16: Event Canonical Entities - UI Design Contract

## Status: Locked

## Scope

Minimal UI change: add "Event" as an entity type in the existing entity list type filter dropdown. The entity list table, search, and pagination already work for all canonical entity types — no other UI changes needed.

## UI Changes

| Component | Change | File |
|-----------|--------|------|
| Entity type filter dropdown | Add `<option value="event">Event</option>` | `src/eth_pipeline/static/index.html:725` |

## Why No Other Changes

- **Entity list query** (`GET /entities`) already queries all `canonical_entity` types — `event` entities appear automatically
- **Type label** (`entityTypeLabel()`) just capitalizes the first letter — `"event"` → `"Event"` automatically
- **Entity list table** has columns for name, type, reference count — all work for event entities
- **Search** by name works for any entity type
- **Pagination** is type-agnostic
- **Merge/split** works on unified `canonical_entity` model — no event-specific conditions needed

## Visual Design

The Event type label follows the same pattern as existing entity types: capitalized string displayed in an `entity-type-label` span. No special color or badge needed — consistency with Place/Person/Object.

## Acceptance

1. Entity type filter dropdown shows "Event" as a selectable option
2. Selecting "Event" filter shows only event-type canonical entities
3. Event entities display with type "Event" in the entity list table
4. Event entities have the same row structure as other entities (name, type, reference count)
