# Phase 23: Entity Resolution Prompt & Batching Fix - Context

**Gathered:** 2026-06-04
**Status:** Ready for planning

<domain>
## Phase Boundary

Fix LLM context overflow in entity resolution by removing full document text from prompts, adding reference-only batching, and decoupling entity grouping (LLM) from DB dedup (code).

**Critical finding from codebase analysis:** The core implementation is already in place. All 5 requirements (RES-01 through RES-05) are already satisfied by the current codebase:
1. `_build_resolution_payload()` (llm.py:577) sends only `verbatim_text` and `reference_type` — no document_context
2. Both activities (`resolve_entities_activity`, `resolve_entities_with_search_activity`) never query or send full `text_content`
3. `_estimate_tokens()` (llm.py:627) and `batch_references()` (llm.py:632) already exist with `_BATCH_MAX_TOKENS = 240_000`
4. LLM groups references; code-side DB dedup handles matching (NFD+casefold exact → fuzzy CONTAINS → create new)
5. Both activities follow the same pattern

Phase 23 scope is verification-only — confirm all 5 requirements are met, run existing tests, and close the milestone.

</domain>

<decisions>
## Implementation Decisions

### Phase Scope
- Codebase already implements all Phase 23 requirements (RES-01 to RES-05)
- Phase scope narrowed to: formal verification + milestone completion
- No new code changes needed

### Verification Strategy
- Run existing integration tests to confirm no regressions
- Manually verify each requirement against codebase
- Create a verification checklist

</decisions>

<code_context>
## Existing Code Insights

### Key Files
- `src/eth_pipeline/llm.py:577` — `_build_resolution_payload()` — only sends verbatim_text + reference_type
- `src/eth_pipeline/llm.py:627` — `_estimate_tokens()` — crude len/4 token estimator
- `src/eth_pipeline/llm.py:632` — `batch_references()` — batch splitting at 240K tokens
- `src/eth_pipeline/llm.py:108` — `ENTITY_RESOLUTION_SCHEMA` — LLM groups refs into entities
- `src/eth_pipeline/activities.py:245` — `resolve_entities_activity()` — LLM grouping + code DB dedup
- `src/eth_pipeline/activities.py:607` — `resolve_entities_with_search_activity()` — same + exact-match pre-pass

### Established Patterns
- Lazy initialization pattern (verify modules exist and can be imported)
- Fire-and-forget ProcessingLogger for operations
- Deterministic SHA256 record IDs for Temporal replay safety

</code_context>

<specifics>
## Specific Ideas

No new code changes required. Phase is verification-only.

</specifics>

<deferred>
## Deferred Ideas

None — original Phase 23 requirements are already satisfied in codebase.

</deferred>
