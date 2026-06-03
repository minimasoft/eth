# Phase 17: Search-First Entity Resolution - Context

**Gathered:** 2026-06-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Replace the existing `resolve_entities_activity` with search-first entity resolution. Exact text matches skip the LLM entirely (~20-50% fewer LLM calls). Fuzzy matches search existing canonical entities, inject up to 5 candidates into the LLM prompt, and let the LLM decide.

**What this phase delivers:**
1. New `resolve_entities_with_search_activity` that replaces `resolve_entities_activity` in the workflow
2. Exact match (case-insensitive, accent-normalized) on name + type → auto-assign `entity_id`, skip LLM
3. Fuzzy/CONTAINS search → up to 5 candidates injected into LLM prompt
4. Updated `ENTITY_RESOLUTION_SCHEMA` and `ENTITY_RESOLUTION_SYSTEM_PROMPT` for candidate-aware resolution
5. New `entity_id` field on `reference` table (schema addition)
6. Nullify-then-recreate replay safety
7. Existing `resolve_entities_activity` kept but unused
8. Merge/split correction flow preserved

**NOT in scope:** Full-text search indexes (RSOL-07, deferred), event entity matching (handled in Phase 16), UI changes.

</domain>

<decisions>
## Implementation Decisions

### Search Strategy
- Exact match: case-insensitive, accent-normalized — `WHERE name = $verbatim_text COLLATE NOCASE`
- Fuzzy search: `CONTAINS` bidirectional — `name CONTAINS $verbatim_text OR verbatim_text CONTAINS name`
- Up to 5 candidates for non-exact matches
- Search all types except `event` (event entities handled in Phase 16)
- Global search scope (across all documents)

### LLM Integration
- Append `## Candidate Entities` section to system prompt with candidate details
- Extend `ENTITY_RESOLUTION_SCHEMA` with `matched_candidate_id` field
- Update `ENTITY_RESOLUTION_SYSTEM_PROMPT` to explain candidate matching

### entity_id Field
- New `entity_id` field on `reference` table: `DEFINE FIELD entity_id ON TABLE reference TYPE record<canonical_entity> | null DEFAULT null`
- Existing `canonical_entity` field kept for backward compatibility — both set for consistency
- No blocking migration — `entity_id` defaults to null

### Activity Changes
- New `resolve_entities_with_search_activity` replaces `resolve_entities_activity` in workflow
- Old activity kept registered but unused
- Nullify-then-recreate preserves `superseded_by` chains for manual merges

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/eth_pipeline/activities.py:resolve_entities_activity()` — Existing activity to refactor
- `src/eth_pipeline/llm.py:ENTITY_RESOLUTION_SCHEMA` — Schema to extend
- `src/eth_pipeline/llm.py:ENTITY_RESOLUTION_SYSTEM_PROMPT` — Prompt to update
- `src/eth_pipeline/llm.py:OpenRouterProvider.resolve_references()` — Existing LLM resolution method
- `src/eth_pipeline/schema.surql` — Reference table to extend with `entity_id` field
- `src/eth_pipeline/workflows.py` — Workflow to update
- `src/eth_pipeline/worker.py` — Worker registration

### Established Patterns
- **Activity pattern:** `@activity.defn`, `_db_params()`, `async with get_db()`, error dict returns
- **Nullify-then-recreate:** Query + nullify links → re-resolve from scratch
- **Type batching:** References grouped by mapped type (espacio→place, humanos→person, objetos→object)

### Integration Points
- `activities.py` — New activity, keep old one
- `llm.py` — Extend schema and prompt
- `schema.surql` — Add `entity_id` field on reference
- `workflows.py` — Replace old activity call with new one
- `worker.py` — Register new activity

</code_context>

<specifics>
## Specific Ideas

- The new activity should log candidate counts and LLM call savings for observability
- Exact match comparison should normalize Unicode accents (NFD decomposition)

</specifics>

<deferred>
## Deferred Ideas

- RSOL-07: Entity search with SurrealDB full-text indexes (SEARCH ANALYZER) for Spanish language — deferred to future v4.x
- Event entity matching in search-first resolution — Phase 16 creates event entities, they're matched by the existing RELATE mechanism, not search-first
- Embedding-based entity search — overkill at current scale

</deferred>
