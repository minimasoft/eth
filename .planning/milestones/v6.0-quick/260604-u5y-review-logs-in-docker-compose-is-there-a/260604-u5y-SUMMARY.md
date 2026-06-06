---
phase: 260604-u5y
plan: 01
plan-name: Review docker compose logs — why entities remain after document deletion
status: complete
type: quick
completed: "2026-06-05"
duration: ~20m
tasks:
  completed: 3
  total: 3
tech-stack:
  added: []
  modified: []
key-files: []
decisions:
  - D-260604-u5y-01: Root cause is Step 2's graph traversal (reference → event → document) returning empty results when event.document = NONE, causing Step 8 orphan cleanup to never execute
  - D-260604-u5y-02: All 62 canonical_entity records are orphans — none are referenced by any remaining reference record
  - D-260604-u5y-03: 272 references remain with broken event links (all event.document = NONE) — cleanup_orphan_references.py can handle these but doesn't clean canonical_entity or event_entity_link orphans
requires: []
provides:
  - Root cause analysis of orphan entity accumulation
  - Specific code gaps with line numbers in documents.py delete cascade
  - Fix recommendations and one-time cleanup queries
affects:
  - docs: delete cascade orphan cleanup logic
  - scripts: cleanup_orphan_references.py missing entity cleanup
---

# Quick Task 260604-u5y: Orphan entity investigation

**One-liner:** Diagnosed why 62 canonical_entity records persist after deleting all documents — Step 2 of the delete cascade (`documents.py:1006-1016`) depends on a `reference → event → document` graph chain that is broken (all remaining references have `event.document = NONE`), causing the orphan cleanup in Step 8 to never execute. Two additional code gaps (`entity_id` field ignored, cleanup script incomplete) compound the problem.

## Record Inventory

| Table | Count |
|-------|-------|
| document | 0 |
| event | 0 |
| reference | 272 |
| canonical_entity | 62 |
| event_entity_link | 43 |

All 11 documents (10 pre-existing + 1 test document from prior quick task) were successfully deleted. Events were cascaded. But references, canonical entities, and event_entity_link records persist.

### canonical_entity by type

| entity_type | Count |
|-------------|-------|
| place | 47 |
| person | 6 |
| object | 9 |

## Orphan analysis

| Category | Count |
|----------|-------|
| Total canonical_entity records | 62 |
| Entities referenced by any reference (via canonical_entity or entity_id) | 0 |
| Total orphan entities (no reference links anywhere) | 62 |
| Orphan via event_entity_link only | 0 (all event_entity_link records have null in/out fields — see below) |

### Reference breakdown

| Category | Count |
|----------|-------|
| Total references | 272 |
| References with `event.document IS NOT NONE` | 0 |
| References with `event.document IS NONE` | 272 |
| References with both `canonical_entity` and `entity_id` = null | 208 |
| References with both `canonical_entity` and `entity_id` set to entity IDs | 64 |
| Entity IDs in references that match any existing canonical_entity | 0 (dangling references) |

### event_entity_link status

| Category | Count |
|----------|-------|
| Total event_entity_link records | 43 |
| Records with valid in/out fields | 0 (all fields = null, indicating broken edge links) |

### Docker logs summary

API logs show 11 successful DELETE operations, all with `0 orphaned entities cleaned`:
```
1b82ff7eeea44... test_doc 94c90fddfb... 0e939a0c92... 52393ad3170b...
3d569ce196... 5576b78fb2... 8c9f97708c0... bbd8e0bb6d9... b6882fcd13...
```
No errors in worker or SurrealDB logs during delete operations.

## Root Cause

The delete cascade at `documents.py:922-1133` has a single point of failure that causes orphan entities to never be checked or cleaned:

### Primary Gap: Broken graph traversal in Step 2 (line 1006-1011)

```python
affected_ce_query = await db.query(
    "SELECT VALUE canonical_entity FROM reference "
    "WHERE event.document = $doc_id "
    "AND canonical_entity IS NOT NONE "
    "AND canonical_entity IS NOT NULL",
    {"doc_id": doc_id_obj},
)
```

This query discovers which canonical entities to check for orphan status by traversing the graph: `reference → event → document`. When events have `document = NONE` (as all 272 remaining references do), this query returns **empty results**. With `affected_ce_rids = []`, Steps 7 and 8 are skipped entirely:

- **Step 7 (line 1049-1053):** Only deletes event-type canonical entities matched via `properties.document_id` — independent of Step 2, but only applies to entity_type='event'.
- **Step 8 (line 1055-1086):** The orphan check is guarded by `if affected_ce_rids:` — when empty, no entities are checked and `orphaned` stays 0.

**Why event.document is NONE:** The pipeline inserts events via `store_extraction_results_activity` (activities.py). Prior quick task (260604-taa) documented that this activity consistently fails with `RuntimeError`. Partial data may be committed where events exist without proper document links, or events were created in an earlier processing run that didn't set the document field.

### Secondary Gap 1: `entity_id` field ignored (line 1006-1010)

Step 2 only queries `reference.canonical_entity`, completely ignoring `reference.entity_id`. Phase 17's search-first resolution populates `entity_id` as the authoritative link for newly resolved entities (see schema.surql line 193-195). Any entity referenced only via `entity_id` is invisible to the orphan check. In our data, this gap is partially masked because references that set `entity_id` also set `canonical_entity` to the same value, but this is not guaranteed by the schema.

### Secondary Gap 2: Cleanup script incomplete

`scripts/cleanup_orphan_references.py` handles:
- **Type A:** References where `event` doesn't exist (272 count) ✅
- **Type B:** References where `event.document` doesn't exist (272 count — same records, double-counted) ✅

But does NOT handle:
- Orphan `canonical_entity` records ❌
- Orphan `event_entity_link` records ❌
- Orphan `event_participant` edges ❌

### Secondary Gap 3: event_entity_link cascade incomplete

Step 1b (line 996-1003) deletes `event_entity_link` edges for event-type canonical entities of the document. But after those edges are removed, the place/person/object entities that were linked via those edges are never checked for orphan status. The `event_entity_link.entity` field points to non-event canonical entities, but the cascade never traces back to check whether those entities now have zero remaining links.

## Fix Recommendations

### 1. [Primary] Use direct event-ID-based reference lookup instead of graph traversal

**File:** `src/eth_pipeline/api/routes/documents.py`, lines 1006-1016

Replace the graph-traversal approach with direct event-ID lookup and include both `canonical_entity` and `entity_id` fields:

```python
# --- Step 2: Collect affected canonical_entities from references ---
# Query references for events belonging to this document, then
# collect canonical_entity IDs from BOTH canonical_entity and entity_id fields
affected_ce_query = await db.query(
    "SELECT VALUE canonical_entity FROM reference "
    "WHERE event IN (SELECT id FROM event WHERE document = $doc_id) "
    "AND canonical_entity IS NOT NONE",
    {"doc_id": doc_id_obj},
)
affected_eid_query = await db.query(
    "SELECT VALUE entity_id FROM reference "
    "WHERE event IN (SELECT id FROM event WHERE document = $doc_id) "
    "AND entity_id IS NOT NONE",
    {"doc_id": doc_id_obj},
)
# Merge both result sets
affected_ce_rids = list(set(
    str(r) for r in (affected_ce_query or []) if r and isinstance(r, str)
) | set(
    str(r) for r in (affected_eid_query or []) if r and isinstance(r, str)
))
```

This bypasses the broken `event.document` graph traversal and uses direct `event.document = $doc_id` (a field-level comparison on the event table, not a graph traversal).

### 2. [Primary] Extend Step 8 orphan check to include both reference fields and event_entity_link

**File:** `src/eth_pipeline/api/routes/documents.py`, lines 1064-1068

```python
for ent_id in rids_to_check:
    # Check references via both canonical_entity AND entity_id fields
    count_result = await db.query(
        "SELECT count() AS total FROM reference "
        "WHERE canonical_entity = $entity_ref "
        "OR entity_id = $entity_ref "
        "GROUP ALL",
        {"entity_ref": RecordID("canonical_entity", ent_id)},
    )
```

### 3. [Secondary] Add event_entity_link orphan check after Step 8

After Step 8's orphan cleanup, also check entities that were linked via `event_entity_link`:

```python
# --- Step 8b: Delete orphaned canonical entities from event_entity_link ---
eel_orphan_result = await db.query(
    "SELECT VALUE entity FROM event_entity_link "
    "WHERE event IN (SELECT id FROM canonical_entity "
    "WHERE entity_type = 'event' AND properties.document_id = $doc_id)",
    {"doc_id": document_id},
)
for rid in (eel_orphan_result or []):
    # Check remaining references for entity
    # If zero, delete it
```

### 4. [Urgent] One-time cleanup for existing orphans

```bash
# Delete orphan canonical_entity records (not referenced by any reference table)
docker compose exec -T surrealdb /surreal sql --username root --password root --ns eth --db pipeline \
  "DELETE canonical_entity WHERE id NOT IN (SELECT canonical_entity FROM reference WHERE canonical_entity IS NOT NONE) AND id NOT IN (SELECT entity_id FROM reference WHERE entity_id IS NOT NONE)"

# Delete orphan references (dangling event links)
docker compose exec -T surrealdb /surreal sql --username root --password root --ns eth --db pipeline \
  "DELETE reference WHERE event NOT IN (SELECT id FROM event)"

# Delete orphan event_entity_link records (dangling edges)
docker compose exec -T surrealdb /surreal sql --username root --password root --ns eth --db pipeline \
  "DELETE event_entity_link WHERE event NOT IN (SELECT id FROM canonical_entity) OR entity NOT IN (SELECT id FROM canonical_entity)"
```

Or, equivalently via the existing script (references only):
```bash
docker compose run --rm integration-tests uv run python scripts/cleanup_orphan_references.py --execute
```

### 5. [Recommended] Extend cleanup script to include canonical_entity and event_entity_link orphans

**File:** `scripts/cleanup_orphan_references.py`

Add two new cleanup categories:
- **Type C:** Orphan canonical entities (no references via either field)
- **Type D:** Orphan event_entity_link edges (broken event or entity links)

## Deviation from Plan

**1. [Rule 3 - Blocking] `--hide` flag doesn't exist on SurrealDB CLI v3.1.2**

- **Found during:** Task 1, Step B
- **Issue:** The plan's queries used `--hide` flag which doesn't exist on this SurrealDB version. The correct flag is `--hide-welcome`, but SQL statements still produce a banner. Worked around by using `--json` mode and piping SQL via stdin with `docker compose exec -T`.
- **Fix:** Used `echo "QUERY" | docker compose exec -T surrealdb /surreal sql --username ... --json 2>&1 | grep '[[{''` to extract JSON results.
- **No files modified** — workaround applied inline.

## Verification

1. ✅ Docker logs captured — 11 successful DELETEs, all with `0 orphaned entities cleaned`
2. ✅ Record inventory complete — all 5 tables queried with numeric counts
3. ✅ Orphan analysis complete — 62/62 entities are orphans, 272/272 references have broken event.document links, 43/43 event_entity_link records have broken edges
4. ✅ Root cause traced to `documents.py:1006-1011` (Step 2 graph traversal dependency on `event.document`)
5. ✅ Fix recommendations provided — 4 concrete code-level fixes + 1 one-time cleanup
