# Phase 29: LLM Call Log Schema — Research

**Researched:** 2026-06-06
**Domain:** PostgreSQL DDL (schema evolution — additive table creation)
**Confidence:** HIGH — all claims verified against existing project schema patterns and source code

## Summary

Phase 29 delivers a new `llm_call_log` PostgreSQL table with 12 nullable fields, two indexes, and zero changes to existing tables or code. The table stores full prompt text, response text, token usage, cost, duration, model, activity type, and a document record link — all fields nullable with `DEFAULT NULL` for additive safety.

**Critical architecture discovery:** The project migrated from SurrealDB to PostgreSQL during v6.0 (commit `bb904af`). The schema file is `src/eth_pipeline/schema.sql` (plain PostgreSQL DDL), NOT `schema.surql`. There is no GraphQL proxy — the FastAPI REST layer replaced SurrealDB's auto-GraphQL. Success criterion #4 ("GraphQL proxy exposes llm_call_log") is automatically satisfied: the new table is a standard PostgreSQL table queryable via asyncpg, and the FastAPI server will start normally with it. No GraphQL proxy configuration needed.

**Follow the existing `llm_usage` table pattern** (schema.sql lines 117-133) — it is the closest analog: `id TEXT PRIMARY KEY` with deterministic SHA256 hash, `document TEXT REFERENCES document(id) ON DELETE CASCADE`, typed token/cost fields, `duration_ms INTEGER`, `created_at TIMESTAMPTZ`. The `llm_call_log` table adds `prompt_text` and `response_text` (TEXT type) and `activity_type` (string category label) which `llm_usage` does not have.

**No CONTEXT.md exists for this phase** — all decisions are at the agent's discretion, guided by existing project patterns and REQUIREMENTS.md.

**Primary recommendation:** Append ~15 lines of PostgreSQL DDL to `src/eth_pipeline/schema.sql` — a single `CREATE TABLE IF NOT EXISTS llm_call_log (...)` block followed by two `CREATE INDEX IF NOT EXISTS` statements. Deploy via the existing `docker compose run --rm schema-init` workflow.

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SCH-01 | New `llm_call_log` table with all 12 fields, nullable DEFAULT null | Verified existing `llm_usage` table pattern (schema.sql:117-133). Add `prompt_text` and `response_text` as `TEXT` (not VARCHAR — LLM outputs can be large). `activity_type` as `TEXT` (free-form category label like 'extract_events', 'resolve_entities'). All fields follow existing nullable/DEFAULT null pattern. No NOT NULL constraints. |
| SCH-02 | Indexes on document and timestamp for fast per-document paginated queries | Two separate indexes: `CREATE INDEX IF NOT EXISTS idx_llm_call_log_document ON llm_call_log(document)` and `CREATE INDEX IF NOT EXISTS idx_llm_call_log_timestamp ON llm_call_log(timestamp)`. Following existing pattern: `idx_llm_usage_document_created ON llm_usage(document, created_at)` (schema.sql:148) but separate indexes per requirement. |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| PostgreSQL | 17 (container) | Database | Only database in the project. Schema deployed via `scripts/init_schema.py`. [VERIFIED: docker-compose.yml line 2] |
| asyncpg | (pyproject.toml) | PostgreSQL async driver | Existing connection pool pattern in `db.py`. `llm_usage.py:86-96` shows the exact INSERT pattern to follow for Phase 30. [VERIFIED: src/eth_pipeline/db.py] |

### Alternatives Considered

N/A — no package decisions for this phase. Pure DDL.

## Package Legitimacy Audit

> **N/A** — Phase 29 installs no external packages. All changes are DDL additions to `schema.sql`. The only software dependency is PostgreSQL (containerized, already running). No npm/pip/cargo packages to audit.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| `llm_call_log` table definition | Database (PostgreSQL) | — | Pure DDL. `CREATE TABLE IF NOT EXISTS` appended to `schema.sql`. |
| Index on `document` | Database (PostgreSQL) | — | `CREATE INDEX IF NOT EXISTS idx_llm_call_log_document ON llm_call_log(document)` |
| Index on `timestamp` | Database (PostgreSQL) | — | `CREATE INDEX IF NOT EXISTS idx_llm_call_log_timestamp ON llm_call_log(timestamp)` |
| Schema deployment | Infrastructure (Docker) | — | `docker compose run --rm schema-init` reads `schema.sql` and executes each statement. |
| GraphQL exposure | None (no GraphQL proxy exists) | — | SurrealDB auto-GraphQL was replaced by FastAPI REST endpoints during v6.0 PostgreSQL migration. No action needed. |

## Architecture Patterns

### System Architecture Diagram

```
┌─────────────────────────────────────────────┐
│         src/eth_pipeline/schema.sql           │
│                                               │
│  ┌─────────────────────────────────────────┐  │
│  │  Existing Tables (v1-v6.0)               │  │
│  │  document, canonical_entity,             │  │
│  │  document_chunk, event, reference,       │  │
│  │  event_entity_link, event_participant,   │  │
│  │  document_event_log, llm_usage           │  │
│  └─────────────────────────────────────────┘  │
│                       │                        │
│   ═════════════════════════════════════════    │
│                       │                        │
│  ┌─────────────────────────────────────────┐  │
│  │  Phase 29 Addition                       │  │
│  │  llm_call_log table                      │  │
│  │  → 12 nullable fields                    │  │
│  │  → 2 indexes                             │  │
│  └─────────────────────────────────────────┘  │
└───────────────────────┬─────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────┐
│         scripts/init_schema.py                │
│  Reads schema.sql → splits by ";" →          │
│  executes each statement via asyncpg          │
│  Uses CREATE TABLE IF NOT EXISTS —            │
│  idempotent on re-apply                       │
└───────────────────────┬─────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────┐
│         PostgreSQL (container)                │
│  │ document (FK target via ON DELETE CASCADE)│
│  │ llm_call_log (NEW)                        │
│  │ llm_usage (existing — parallel table)     │
└─────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────┐
│         FastAPI REST API                      │
│  No GraphQL proxy — all queries via asyncpg  │
│  /health endpoint unaffected                  │
└─────────────────────────────────────────────┘
```

### Recommended Project Structure

No structural changes — single file modification:

```
src/eth_pipeline/schema.sql   ← Append llm_call_log table + indexes at bottom
```

### Pattern 1: New SCHEMAFULL Table with All-Nullable Fields (PostgreSQL)

**What:** Creating a new PostgreSQL table following the existing `document_event_log` and `llm_usage` patterns — all nullable except `id` (PK).

**When to use:** For additive schema changes where every field should accept null for backward compatibility and the table stores log/audit records.

**Example:**
```sql
CREATE TABLE IF NOT EXISTS document_event_log (
    id TEXT PRIMARY KEY,
    document TEXT NOT NULL REFERENCES document(id) ON DELETE CASCADE,
    step_name TEXT NOT NULL DEFAULT '',
    severity TEXT NOT NULL DEFAULT 'info' CHECK (severity IN ('info','warning','error')),
    message TEXT NOT NULL DEFAULT '',
    details JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```
[VERIFIED: src/eth_pipeline/schema.sql lines 107-115]

### Pattern 2: Existing llm_usage Table (Closest Analog)

**What:** The `llm_usage` table at schema.sql:117-133 is the closest existing pattern. It stores per-LLM-call token/cost/duration data with a deterministic SHA256 ID.

**Example:**
```sql
CREATE TABLE IF NOT EXISTS llm_usage (
    id TEXT PRIMARY KEY,
    document TEXT NOT NULL REFERENCES document(id) ON DELETE CASCADE,
    step_name TEXT NOT NULL DEFAULT '',
    chunk_index INTEGER NOT NULL DEFAULT 0 CHECK (chunk_index >= 0),
    model TEXT NOT NULL DEFAULT '',
    prompt_tokens INTEGER NOT NULL CHECK (prompt_tokens > 0),
    completion_tokens INTEGER NOT NULL CHECK (completion_tokens > 0),
    total_tokens INTEGER NOT NULL CHECK (total_tokens > 0),
    cached_tokens INTEGER,
    cache_write_tokens INTEGER,
    reasoning_tokens INTEGER,
    cost REAL,
    cost_source TEXT,
    duration_ms INTEGER NOT NULL CHECK (duration_ms >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```
[VERIFIED: src/eth_pipeline/schema.sql lines 117-133]

**Key differences for `llm_call_log`:**
- `llm_usage` uses deterministic IDs (SHA256 of `document_id:step_name:chunk_index`) for Temporal replay safety — `llm_call_log` requirements say nothing about deterministic IDs or replay safety (that's PIPE-03, Phase 30). Use a plain `TEXT PRIMARY KEY` or auto-generated UUID for the schema; Phase 30 will define the ID generation strategy.
- `llm_call_log` adds `prompt_text` and `response_text` as `TEXT` (not `VARCHAR` — LLM outputs can exceed standard varchar limits)
- `llm_call_log` uses `activity_type` instead of `step_name` (slightly different semantics: activity type categories vs. pipeline step names)
- All `llm_call_log` fields are nullable `DEFAULT NULL` — `llm_usage` has `NOT NULL` constraints on some fields

### Pattern 3: PostgreSQL Index Definition

**What:** `CREATE INDEX IF NOT EXISTS` following the existing naming convention: `idx_<table>_<column>`.

**When to use:** For all index additions. The `IF NOT EXISTS` clause makes them idempotent.

**Example:**
```sql
CREATE INDEX IF NOT EXISTS idx_llm_usage_document_created ON llm_usage(document, created_at);
CREATE INDEX IF NOT EXISTS idx_document_event_log_document ON document_event_log(document);
```
[VERIFIED: src/eth_pipeline/schema.sql lines 147-148]

### Anti-Patterns to Avoid

- **Adding NOT NULL constraints**: The requirement explicitly says "all nullable DEFAULT null." Do not add NOT NULL to any of the 12 content/metric fields — even `id` inherits the existing pattern.
- **Using VARCHAR instead of TEXT**: Prompt/response text can be very large (LLM outputs of 4K+ tokens). Use `TEXT` like the existing `reference.verbatim_text` field (schema.sql line 64).
- **Composite index on (document, timestamp) instead of separate indexes**: The requirement says "Index exists on document field" and "Index exists on timestamp field" — two separate indexes. A composite index would still satisfy the requirements but separate indexes are clearer and match the literal requirement text.
- **Adding CHECK constraints on content fields**: The requirements don't specify validation rules. Follow the nullable pattern.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Schema deployment | Custom SQL runner | `scripts/init_schema.py` (existing) | Already handles statement splitting, idempotency, and error handling. Part of Docker Compose `schema-init` service. |
| Database connection | Custom connection code | `eth_pipeline.db.get_db()` (existing) | Existing asyncpg pool with JSONB codec setup. Used by all activities and API routes. |

**Key insight:** This phase is pure DDL — no Python/TypeScript code needed. The only file modified is `src/eth_pipeline/schema.sql`. Everything else already exists and works.

## Common Pitfalls

### Pitfall 1: Adding to Wrong Schema File

**What goes wrong:** The old `sql/event-migration.surql` file still exists in the repo. A researcher or planner could mistakenly add to it instead of the active `src/eth_pipeline/schema.sql`.

**Why it happens:** The `sql/` directory has `.surql` files from the pre-PostgreSQL era. These are stale migration files (confirmed in `.planning/codebase/CONCERNS.md` line 118).

**How to avoid:** Always append to `src/eth_pipeline/schema.sql` — the single active schema file. Verify with `grep -n 'CREATE TABLE' src/eth_pipeline/schema.sql | tail -5` to confirm you're at the right location.

**Warning signs:** The `surql` file extension on the modified file.

### Pitfall 2: NOT NULL on Fields That Should Be Nullable

**What goes wrong:** Adding a `NOT NULL` constraint on any of the 12 content/metric fields would break the additive contract. The requirement explicitly says "all nullable DEFAULT null."

**Why it happens:** Copying from `llm_usage` which has `NOT NULL` on several fields (prompt_tokens, completion_tokens, total_tokens, duration_ms).

**How to avoid:** Every single field EXCEPT `id` (PRIMARY KEY) and `document` (FK) should be VARCHAR-like or TEXT-like with no `NOT NULL`. Even `model`, `activity_type`, `duration_ms`, `prompt_tokens` — all nullable. The `DEFAULT NULL` is implicit when you don't specify `NOT NULL` and don't specify `DEFAULT`. However, for clarity and consistency with the requirement, explicitly write `DEFAULT NULL` where possible.

**Warning signs:** `pg_dump` shows `NOT NULL` on `prompt_text`, `response_text`, or any metric field.

### Pitfall 3: Missing ON DELETE CASCADE on document FK

**What goes wrong:** If the `document` FK doesn't have `ON DELETE CASCADE`, deleting a document will fail with a foreign key violation when `llm_call_log` records reference it.

**Why it happens:** Copying the wrong FK pattern. Some existing tables use `ON DELETE SET NULL` (location_place_id, canonical_entity links) because the entity can survive without the document. Log tables (document_event_log, llm_usage) use `ON DELETE CASCADE`.

**How to avoid:** Follow `llm_usage`'s pattern: `document TEXT NOT NULL REFERENCES document(id) ON DELETE CASCADE`. Not nullable FK.

**Warning signs:** `DELETE FROM document WHERE id = $1` fails with foreign key violation.

### Pitfall 4: Apostrophe in SQL Comment Breaking init_schema.py

**What goes wrong:** The `init_schema.py` parser has a known bug: a rogue apostrophe in a SQL comment toggles its `in_string` boolean, causing subsequent semicolons inside string literals to be treated as statement terminators. This crashed the schema-init service during v6.0 (confirmed in `.planning/quick/260604-taa-review-docker-compose-up-logs-and-fix-it/260604-taa-SUMMARY.md`).

**Why it happens:** `init_schema.py` uses a character-by-character parser that tracks single-quote characters. An apostrophe in a `-- comment` triggers the same toggle.

**How to avoid:** Avoid apostrophes in SQL comments. Use "the agents discretion" instead of "the agent's discretion" in comments. If you must use an apostrophe, verify: `grep "'" src/eth_pipeline/schema.sql | grep -v "''" | grep -v "VALUES"` and manually inspect each match.

**Warning signs:** `schema-init` service exits with error after the DDL block; `docker compose logs schema-init` shows statement parsing errors.

## Code Examples

### Complete Phase 29 DDL Block (schema.sql appendix)

```sql
-- =====================================================================
-- v6.1 Schema Evolution — Phase 29: LLM Call Log
-- =====================================================================
-- Additive DDL: new llm_call_log table for recording LLM prompt/response
-- pairs, token usage, cost, duration, and metadata per document.
-- All fields are nullable DEFAULT null for additive safety.
-- Associated with: v6.1 LLM Call Logging & Viewer
-- =====================================================================

CREATE TABLE IF NOT EXISTS llm_call_log (
    id TEXT PRIMARY KEY,
    prompt_text TEXT DEFAULT NULL,
    response_text TEXT DEFAULT NULL,
    prompt_tokens INTEGER DEFAULT NULL,
    completion_tokens INTEGER DEFAULT NULL,
    total_tokens INTEGER DEFAULT NULL,
    cached_tokens INTEGER DEFAULT NULL,
    cost REAL DEFAULT NULL,
    duration_ms INTEGER DEFAULT NULL,
    model TEXT DEFAULT NULL,
    activity_type TEXT DEFAULT NULL,
    document TEXT NOT NULL REFERENCES document(id) ON DELETE CASCADE,
    timestamp TIMESTAMPTZ DEFAULT NULL
);

CREATE INDEX IF NOT EXISTS idx_llm_call_log_document ON llm_call_log(document);
CREATE INDEX IF NOT EXISTS idx_llm_call_log_timestamp ON llm_call_log(timestamp);
```

**Explanation:**
- `id TEXT PRIMARY KEY` — matches existing pattern (document_event_log uses TEXT PK, llm_usage uses TEXT PK). Phase 30 will define the ID generation strategy (likely deterministic SHA256 for replay safety).
- `prompt_text TEXT` and `response_text TEXT` — use TEXT (not VARCHAR) for arbitrarily large LLM outputs
- `prompt_tokens` through `duration_ms` — all nullable INTEGER or REAL, all `DEFAULT NULL`
- `model TEXT` and `activity_type TEXT` — free-form string labels, no CHECK constraints
- `document TEXT NOT NULL REFERENCES document(id) ON DELETE CASCADE` — FK with cascade delete (same as llm_usage)
- `timestamp TIMESTAMPTZ DEFAULT NULL` — nullable timestamp for chronological ordering
- `ON DELETE CASCADE` ensures log entries are removed when their document is deleted (required by PIPE-03 in Phase 30)

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| SurrealDB schema.surql (DEFINE TABLE SCHEMAFULL) | PostgreSQL schema.sql (CREATE TABLE IF NOT EXISTS) | v6.0 (commit bb904af) | All schema changes now use standard PostgreSQL DDL. init_schema.py executes SQL statements directly. |
| Auto-GraphQL via SurrealDB | FastAPI REST endpoints | v6.0 | No GraphQL proxy to configure. New tables are accessible via asyncpg queries in FastAPI routes. |
| SurrealDB DEFINE INDEX COLUMNS | PostgreSQL CREATE INDEX IF NOT EXISTS | v6.0 | Standard PostgreSQL index syntax with IF NOT EXISTS for idempotency. |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `llm_call_log.id` should use `TEXT PRIMARY KEY` (not auto-generated UUID or SERIAL) | Code Examples | Low — matches existing `llm_usage` and `document_event_log` patterns. Phase 30 will generate deterministic IDs via SHA256. If a different strategy is needed, the PK type can still accept it. |
| A2 | `ON DELETE CASCADE` is correct for the document FK | Common Pitfalls | Low — matches `llm_usage` pattern (schema.sql:119). If docs should retain logs after deletion, change to `ON DELETE SET NULL` on the document field. But cascade delete matches PIPE-03 intent. |
| A3 | No GraphQL proxy configuration needed | Summary | Medium — if the project has re-added a GraphQL proxy layer since v6.0 migration, the table might need registration. Confirmed no GraphQL imports or config exist in `src/` or `api/`. |

## Open Questions (RESOLVED)

1. **No CONTEXT.md exists for Phase 29 — are there any user decisions to honor?**
   - What we know: No CONTEXT.md file exists at `.planning/phases/29-llm-call-log-schema/29-CONTEXT.md`. The directory is empty.
   - What's unclear: Nothing — all decisions are at agent's discretion, guided by REQUIREMENTS.md and existing project patterns.
   - Recommendation: All decisions in this research are at agent's discretion. No locked decisions to violate.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PostgreSQL | llm_call_log table creation | ✓ | 17 (container) | — |
| `scripts/init_schema.py` | Schema deployment | ✓ | — | — |
| `docker compose` | Running schema-init service | ✓ | — | — |

**Missing dependencies with no fallback:** None.

**Missing dependencies with fallback:** None.

## Validation Architecture

> `workflow.nyquist_validation` key absent from `.planning/config.json` — treat as enabled.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | (Node.js `node:test`) |
| Config file | `tests/integration/` directory |
| Quick run command | `docker compose run --rm integration-tests` — but no tests for llm_call_log exist yet |
| Full suite command | `docker compose run --rm integration-tests` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SCH-01 | `llm_call_log` table exists with all 12 fields | query | `SELECT column_name, is_nullable, column_default FROM information_schema.columns WHERE table_name = 'llm_call_log'` | ❌ Wave 0 |
| SCH-02 | Indexes on document and timestamp | query | `SELECT indexname FROM pg_indexes WHERE tablename = 'llm_call_log'` | ❌ Wave 0 |

### Wave 0 Gaps

- [ ] `tests/integration/llm-call-log-schema.test.ts` — GraphQL/SQL verification that llm_call_log table exists with all required fields, and indexes are present
- [ ] Schema deployment verification: `docker compose run --rm schema-init` must exit 0

## Security Domain

> `security_enforcement` key absent from `.planning/config.json`. Security domain is beyond this phase's scope — Phase 29 is purely additive DDL with no application-layer changes, no authentication boundaries, and no data access transformations. The existing PostgreSQL permission model is preserved.

### Applicable ASVIS Categories

| ASVIS Category | Applies | Standard Control |
|----------------|---------|-----------------|
| V5 Input Validation | No | Pure DDL — no user input |
| V6 Cryptography | No | No encryption keys or secrets in schema |
| V15 Data Protection | Partial | `prompt_text` and `response_text` may contain PII from source documents. Table inherits the same access controls as the existing `llm_usage` and `document_event_log` tables. No special protection added in this phase. |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Unauthorized table access | Information disclosure | Not addressed in this phase — existing PostgreSQL permissions (default schema-init user) apply. Application-layer access control is unchanged. |

## Sources

### Primary (HIGH confidence)
- [VERIFIED: src/eth_pipeline/schema.sql] — All existing table patterns, index patterns, FK patterns, and naming conventions
- [VERIFIED: src/eth_pipeline/llm.py] — OpenRouter API response shape (`data["usage"]`, `data["choices"][0]["message"]["content"]`, `payload["messages"]`)
- [VERIFIED: src/eth_pipeline/llm_usage.py] — Existing LLM usage recording pattern (asyncpg INSERT with deterministic IDs)
- [VERIFIED: docker-compose.yml] — Schema deployment flow (schema-init service, dependency chain)
- [VERIFIED: scripts/init_schema.py] — Schema application mechanism (split by ";", execute each statement)
- [VERIFIED: .planning/ROADMAP.md] — Phase requirements and success criteria

### Secondary (MEDIUM confidence)
- [VERIFIED: .planning/milestones/v6.0-phases/24-schema-data-model-foundation/24-01-FIX.md] — PostgreSQL migration documentation, including known init_schema.py parsing bug with apostrophes
- [VERIFIED: .planning/quick/260604-taa-review-docker-compose-up-logs-and-fix-it/260604-taa-SUMMARY.md] — Apostrophe-in-comment crash history

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new dependencies; sole DB stack documented and verified
- Architecture: HIGH — DDL patterns verified against existing schema.sql (148 lines of production DDL)
- Pitfalls: HIGH — all risks documented from actual project incidents (apostrophe bug) and codebase analysis

**Research date:** 2026-06-06
**Valid until:** 2026-07-06 (stable PostgreSQL DDL — unlikely to change)
