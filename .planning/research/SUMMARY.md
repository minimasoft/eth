# Project Research Summary

**Project:** eth-pipeline — v5.0 LLM Cost & Usage Tracking
**Domain:** Token/cost observability for document extraction pipeline
**Researched:** 2026-06-04
**Confidence:** HIGH (stack, features, pitfalls); MEDIUM (architecture — conflict resolved below)

## Executive Summary

This project adds per-LLM-call token and cost tracking to an existing document extraction pipeline powered by OpenRouter and Temporal workflows. The pipeline processes documents through extraction chunks and entity resolution steps, each making independent LLM API calls — currently invisible in terms of cost. The research confirms this is a well-understood domain with standard patterns: capture `usage` from the OpenAI-compatible response body, store in a dedicated table, aggregate at query time, and display in the existing vanilla-JS SPA.

**The recommended approach** diverges from the initial "reuse existing log infrastructure" assumption. A critical finding from the pitfalls research — the 100-entry cap on `document_event_log` — makes a separate `llm_usage` table mandatory. Token data must use deterministic record IDs with UPSERT semantics to survive Temporal replay without double-counting, and must be included in the existing nullify-then-recreate cycle for reprocessing safety. The result is a replay-safe, append-only audit trail of every LLM call the pipeline makes.

**The key risk** is Temporal replay double-counting (Pitfall #1, CRITICAL severity). Every activity retry, worker restart, or workflow replay must produce identical token records — which requires careful design of deterministic ID derivation, UPSERT persistence, and inclusion in the delete cycle. The secondary risk is the 100-entry ProcessingLogger cap silently dropping token data if shoehorned into the existing infrastructure. Both risks have clear mitigations documented in the pitfalls research.

## Key Findings

### Recommended Stack

**Core finding:** Zero new dependencies. All token/cost data is extracted from the OpenRouter API response body using existing packages (httpx, surrealdb, temporalio) and stdlib (`time.monotonic()`). The vanilla JS SPA needs only `Intl.NumberFormat` and `toFixed()`.

**Core technologies:**
- **SurrealDB `llm_usage` table** (new): Schemaful table with `PERMISSIONS FOR update NONE, FOR delete NONE` — append-only audit trail of every LLM call
- **OpenRouter `response.usage` dict**: Source of `prompt_tokens`, `completion_tokens`, `total_tokens`, `cached_tokens`, and optional `cost`
- **`time.monotonic()` from stdlib**: Wall-clock round-trip timing for each LLM call (labeled as such, not "inference time")
- **SurrealQL `math::sum()`**: Per-document aggregation — identical pattern to existing reference/entity count queries

**See:** [STACK.md](./STACK.md) for full schema definition, field-by-field extraction logic, and UI formatting helpers.

### Expected Features

**Must have (table stakes):**
- **T1: Per-LLM-call token accounting** — capture `prompt_tokens`, `completion_tokens`, `total_tokens`, `cached_tokens`, `cost` from every OpenRouter response
- **T2: Per-document token aggregation** — sum token/cost across all LLM calls for a document (extraction chunks + entity resolution)
- **T3: Processing time per LLM call** — `time.monotonic()` round-trip timing alongside token data
- **T4: Storage in a dedicated table** — NOT in `document_event_log` (100-entry cap is the deal-breaker)

**Should have (differentiators):**
- **D1: Token/cost in document list** — single aggregated column (e.g., "1,234 / 567 | $0.02") rather than separate columns
- **D2: Cache-hit indicator** — show cached tokens separately (e.g., "500/1,234/567" meaning 500 cached + 1,234 input + 567 output)
- **D3: LLM-call filter in Logs tab** — `?llm_only=true` filter on `GET /documents/{id}/logs`
- **D4: Retry/error tracking** — `attempt_number` and `retry_of` in token records

**Defer (v2+):**
- Real-time streaming token display (non-streaming pipeline)
- Cost charts/graphs (vanilla JS SPA limitation)
- Token usage budgets/threshold alerts (single-user tool)
- Prompt/response content storage (too large, stored elsewhere)

**Anti-features (explicitly warned against by research):**
- Do NOT push token data into `document_event_log.details` (100-entry cap swallows it — Pitfall #4)
- Do NOT create a new table when a separate approach is needed — actually CREATE the separate `llm_usage` table (the architecture researcher's anti-pattern #2 is overridden by the critical pitfall finding)
- Do NOT compute cost from model pricing lookups when `usage.cost` is available from OpenRouter
- Do NOT add 4 new columns to the document table (layout over-crowding — Pitfall #5)

**See:** [FEATURES.md](./FEATURES.md) for full feature breakdown, MVP prioritization, and test patterns.

### Architecture Approach

The architecture is a clean extension of the existing pipeline: the `OpenRouterProvider` returns usage metadata alongside parsed content, the Temporal activity writes it to a dedicated `llm_usage` table via deterministic-ID UPSERT, and the API aggregates it at query time for the SPA.

**NOTE: Conflict resolved.** The architecture researcher (ARCHITECTURE.md) and features researcher (FEATURES.md) recommended storing token data in the existing `document_event_log.details` field. The pitfalls researcher discovered the 100-entry cap on this table (Pitfall #4), which would silently drop token data for documents with many chunks. **The separate `llm_usage` table is mandatory**, not an anti-pattern.

**Major components:**
1. **OpenRouterProvider** (in `llm.py`) — Extract `usage` dict from response, return alongside parsed content. No DB writes from this layer.
2. **Temporal activities** (`extract_events_activity`, etc.) — Call provider, unpack usage, call `record_llm_usage()`. Include token records in nullify-then-recreate cycle.
3. **`llm_usage` table** (SurrealDB) — Schemaful, append-only via PERMISSIONS. Deterministic IDs (SHA256 of `document_id:step_name:chunk_index`) + UPSERT for replay safety.
4. **API endpoints** — `GET /documents/{id}/tokens` (per-doc aggregation), batched token data in `GET /documents` list to avoid N+1
5. **Web UI** (vanilla JS SPA) — Token summary in logs panel/detail view, single aggregated column in document table

**Data flow:**
```
LLM Response → OpenRouterProvider._parse_choice()
  ├── parsed_content → activity (existing flow)
  └── usage_metadata → ProcessingLogger.log() or record_llm_usage()
                                              ↓
                                       llm_usage table
                                              ↓
                              API: GET /documents/{id}/tokens
                              API: GET /documents (batch query)
```

**Key patterns:**
- **Deterministic replay-safe logging** (existing SHA256 + UPSERT pattern)
- **Graceful degradation** for missing API fields (`.get()` with defaults)
- **Context-manager timing** to handle `asyncio.CancelledError` cleanly

**See:** [ARCHITECTURE.md](./ARCHITECTURE.md) for data flow diagrams, component boundaries, and scalability considerations.

### Critical Pitfalls

**Top 5 by severity:**

1. **CRITICAL: Temporal replay double-counts tokens (Pitfall #1)** — Activity retries and workflow replays can inflate token totals unless deterministic ID + UPSERT is used and token records are included in the nullify-then-recreate delete cycle. **Mitigation:** Record inside provider, persist via deterministic-ID UPSERT in activity.

2. **HIGH: ProcessingLogger 100-entry cap swallows token data (Pitfall #4)** — The existing `document_event_log` has a hard cap of 100 entries per document. Token data pushed into `details` would be silently dropped for documents with many chunks. **Mitigation:** Use a separate `llm_usage` table with no cap and its own write path.

3. **HIGH: OpenRouter cache hits report 0 tokens (Pitfall #2)** — Cache HIT responses can zero out `prompt_tokens` or omit `usage` entirely. Crash on missing `usage` = pipeline failure. **Mitigation:** Null-safe parsing, store raw usage JSON for future recalculation.

4. **HIGH: Chunked extraction produces multiple records requiring aggregation (Pitfall #3)** — 5-20+ LLM calls per document across extraction chunks + entity resolution types. Missing a record type in aggregation = incomplete totals. **Mitigation:** `step_name` discriminator + `chunk_index` on each record; aggregate at query time with a documented helper function.

5. **MEDIUM: UI token columns overwhelm document table layout (Pitfall #5)** — Adding 3-4 token columns to an already-wide table ruins mobile UX. **Mitigation:** Show token data in logs panel/detail view, not as new columns. Single aggregated column if table-adjacent is unavoidable.

**See:** [PITFALLS.md](./PITFALLS.md) for all 15 pitfalls with warning signs, phase mappings, and the "Looks Done But Isn't" checklist.

## Implications for Roadmap

Based on the combined research, I recommend **5 phases** with the following structure:

### Phase 1: Token Recording & Schema (Foundation)
**Rationale:** Everything depends on capturing token data from OpenRouter responses and storing it safely. The `llm_usage` table must exist before anything else works.
**Delivers:** Token/cost data captured for every LLM call and persisted to SurrealDB with replay safety.
**Features addressed:** T1 (per-LLM-call accounting), T3 (processing time)
**Pitfalls avoided:** #1 (replay double-count via deterministic ID + UPSERT), #2 (cache hit via null-safe parsing), #3 (chunked records via step_name + chunk_index), #4 (log cap via separate table), #9 (async cancellation via context manager), #12 (schema perms), #14 (model storage)
**Key deliverables:**
- `llm_usage` table definition in `schema.surql` (SCHEMAFULL, PERMISSIONS FOR update/delete NONE)
- `_usage` extraction in `OpenRouterProvider._parse_choice()` return dict
- `record_llm_usage()` helper with deterministic ID (SHA256 of `document_id:step_name:chunk_index`) + UPSERT
- Context manager for `time.monotonic()` timing
- Token record deletion in nullify-then-recreate cycle
- Include `llm_usage` in `DELETE /documents/{id}` and `DELETE /documents/{id}/events` cascade
- **Research flag:** Needs `/gsd-plan-phase --research-phase 1` — the Temporal replay safety design requires careful verification of deterministic ID collision boundaries and UPSERT semantics in the existing activity patterns.

### Phase 2: API Aggregation Endpoints
**Rationale:** Once token data is in the database, it needs to be queryable. This phase adds the REST endpoints for per-document token aggregation and list-level batch queries.
**Delivers:** Token totals usable by the frontend and API consumers.
**Features addressed:** T2 (per-document aggregation), D4 (retry tracking — attempt_number, retry_of)
**Pitfalls avoided:** #3 (multi-record aggregation via query-time SUM), #8 (legacy document handling via coalesce + has_data), #13 (N+1 via batch query or document-record storage)
**Key deliverables:**
- `GET /documents/{id}/tokens` endpoint (per-doc aggregation, null-coalesced)
- Batch token query in `GET /documents` list endpoint (`WHERE document INSIDE $docs GROUP ALL`) to avoid N+1
- `has_data: bool` flag for legacy pre-v5.0 documents
- 404 handling for documents with no token records
- Attempt number recording in token records
- **Research flag:** Standard patterns — no deeper research needed.

### Phase 3: UI Token Display
**Rationale:** Token data must be visible to users. This phase adds it to the existing vanilla-JS SPA without over-crowding the layout.
**Delivers:** Token/cost visibility in the document detail view and LLM-call filter in the Logs tab.
**Features addressed:** D1 (token/cost in document list), D2 (cache-hit indicator), D3 (LLM-call filter)
**Pitfalls avoided:** #5 (table overcrowding via logs panel display), #8 (legacy display via graceful fallback), #15 (meaningless numbers via tooltips + step grouping)
**Key deliverables:**
- Token summary section in `logs-doc-info` panel (not new columns)
- Single aggregated token column in document table (e.g., "1,234 / 567 | $0.02")
- `formatTokenCount()` and `formatCost()` JS helpers
- Step-grouped token breakdown in logs detail view (extraction chunks vs. entity resolution)
- Tooltips on all token numbers
- Cache-hit visual indicator (e.g., "500/1,234/567" format)
- `?llm_only=true` filter on Logs tab with "Ver LLM" button
- Green/yellow/red cost badges
- "Sin datos de tokens (documento anterior a v5.0)" for legacy docs
- **Research flag:** Standard UI patterns — no deeper research needed if following the existing SPA patterns.

### Phase 4: Cost Estimation & Retry Accounting
**Rationale:** Cost data from OpenRouter's `usage.cost` field is optional and not always present. This phase adds fallback cost estimation from model pricing and comprehensive retry tracking.
**Delivers:** Estimated cost for calls where `usage.cost` is absent; visibility into retry overhead.
**Features addressed:** D4 (retry tracking — full), Pitfall #10 (cost estimation), Pitfall #11 (test brittleness)
**Pitfalls avoided:** #7 (retry ambiguity via attempt_number + retry_of), #10 (cost via configurable pricing), #11 (brittle tests via structural assertions)
**Key deliverables:**
- Configurable model pricing dict (input/output/cached per-1M rates)
- `estimate_cost()` function for fallback when `usage.cost` is absent
- `cost_usd_estimated` and `cost_source` fields on `llm_usage` records
- "Coste estimado" labels in UI when cost is estimated
- `retry_of` field on token records linking retries to original attempts
- Documented accounting policy: "totals include retry overhead"
- Structural test assertions in Python verification scripts (not hardcoded numerical values)
- Replay-safety e2e test (process twice without DELETE, verify identical totals)
- **Research flag:** Needs `/gsd-plan-phase --research-phase 4` — OpenRouter pricing is model-dependent and changes over time; the estimation strategy needs validation against the user's actual OpenRouter billing data.

### Phase 5: Pricing Sync (Optional)
**Rationale:** Keeping model pricing up to date is a maintenance task, not a launch requirement. Phase 4's configurable pricing dict works immediately.
**Delivers:** Automated pricing updates from OpenRouter's model list API.
**Features addressed:** Pricing freshness
**Pitfalls avoided:** #10 (stale cost estimates via periodic sync)
**Key deliverables:**
- `scripts/sync_pricing.py` — optional script fetching pricing from `https://openrouter.ai/api/v1/models`
- Pricing cache update mechanism
- **Research flag:** Can skip research entirely if the sync script is deferred to a future milestone.

### Phase Ordering Rationale

- **Phase 1 first** because everything depends on capturing and storing token data safely. The schema must exist, the extraction must work, and the replay-safety mechanism must be correct before any other phase has meaning.
- **Phase 2 second** because the API layer is the bridge between storage and UI. Without aggregation endpoints, the UI has nothing to display.
- **Phase 3 third** because the UI is the consumer of the API endpoints from Phase 2. These two phases could partially overlap (build the UI alongside the API contract).
- **Phase 4 fourth** because cost estimation and retry tracking are enhancements on top of the core token tracking. The basic token data pipeline works without cost estimation — it just shows null-cost where `usage.cost` is absent.
- **Phase 5 deferred** because pricing sync is a maintenance automation task. The configurable pricing dict from Phase 4 works immediately with manual updates.

### Research Flags

| Phase | Needs Research? | Reason |
|-------|----------------|--------|
| Phase 1: Token Recording | **YES** | Temporal replay safety design requires verification of: deterministic ID collision boundaries with existing SHA256 pattern, UPSERT semantics in SurrealDB Temporal context, integration with existing nullify-then-recreate cycle |
| Phase 2: API Aggregation | No | Standard REST endpoint patterns, existing codebase patterns to follow |
| Phase 3: UI Display | No | Standard vanilla JS SPA patterns, existing table/logs patterns to follow |
| Phase 4: Cost & Retry | **YES** | OpenRouter pricing model validation needed — `usage.cost` field availability, model pricing change frequency, retry behavior with actual OpenRouter responses |
| Phase 5: Pricing Sync | No | Optional maintenance script; standard HTTP + file write pattern |

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | **HIGH** | OpenRouter `response.usage` shape confirmed via TypeScript types in `llms-full.txt`. SurrealDB schema patterns verified against existing codebase. Zero new dependencies. |
| Features | **HIGH** | Feature taxonomy directly from OpenRouter API capabilities and existing pipeline architecture. MVP recommendation follows standard observability patterns. |
| Architecture | **MEDIUM** | The architecture researcher recommended using `document_event_log.details` for storage, which the pitfalls researcher showed is broken (100-entry cap). The recommended architecture (separate `llm_usage` table) resolves this but needs implementation verification during Phase 1. |
| Pitfalls | **HIGH** | 15 pitfalls identified with severity ratings, mitigations, and phase mappings. All derived from codebase analysis and Temporal/OpenRouter domain knowledge. Primary source: actual codebase behavior. |

**Overall confidence:** HIGH — the core approach is well-understood, the conflicts have been resolved with clear rationale, and the pitfalls research provides robust guardrails. The only uncertainty is around OpenRouter's `usage.cost` field availability (captured as a gap below).

### Gaps to Address

- **OpenRouter `usage.cost` field availability:** STACK.md says `cost?: number` is optional in the response type. PITFALLS.md says OpenRouter does not return per-call cost at all. These may reflect different versions of the API. **Resolution:** Capture `usage.cost` when present; fall back to model-pricing estimation when absent. Phase 1 stores `cost_source` to distinguish. Phase 4 validates against actual billing data.

- **Deterministic ID collision with existing SHA256 pattern:** The `ProcessingLogger` already uses SHA256 for log entry IDs. The `llm_usage` table needs its own ID namespace. **Resolution:** Prefix the hash with `"llm:"` or use a separate hash domain (`document_id:step_name:chunk_index` is naturally distinct from the log entry hash composition).

- **`time.monotonic()` precision sufficiency:** The round-trip time for a typical LLM call is 5-30 seconds, so `time.monotonic()` at millisecond precision is more than adequate. This is not a real gap — just noting that sub-millisecond precision is neither needed nor achievable over HTTP.

- **Model pricing change frequency:** Phase 4's configurable pricing dict works for initial launch. The frequency of OpenRouter pricing changes determines whether Phase 5 (sync script) becomes valuable. **Resolution:** Start with manual config; add sync script if pricing changes more than quarterly.

## Sources

### Primary (HIGH confidence)
- **STACK.md research**: OpenRouter TypeScript `ResponseUsage` type (llms-full.txt lines 18870-18920), current `llm.py`, current `schema.surql`, current `static/index.html`
- **FEATURES.md research**: OpenRouter Usage Accounting docs, OpenRouter Prompt Caching guide, existing codebase
- **ARCHITECTURE.md research**: Existing codebase (`llm.py`, `processing_log.py`, `schema.surql`), OpenRouter usage docs
- **PITFALLS.md research**: Codebase analysis (`llm.py`, `activities.py`, `processing_log.py`, `schema.surql`, `api/models.py`, `api/routes/documents.py`, `static/index.html`), OpenRouter chat completions format

### Secondary (MEDIUM confidence)
- OpenRouter model list API at `/api/v1/models` — referenced for pricing sync (Phase 5) but not verified at time of research
- `httpx` event hooks — alternative timing approach (Pitfall #6) — available but not currently imported

### Tertiary (LOW confidence)
- None — all research findings were cross-referenced against actual codebase behavior or official OpenRouter documentation

---

*Research completed: 2026-06-04*
*Ready for roadmap: yes*
