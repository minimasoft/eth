# Phase 29: LLM Call Log Schema — Pattern Map

**Mapped:** 2026-06-06
**Files analyzed:** 1 (modify `src/eth_pipeline/schema.sql`)
**Analogs found:** 3 / 3

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `src/eth_pipeline/schema.sql` *(append)* | schema | DDL | `llm_usage` table (lines 117-133) — same role | exact |
| `src/eth_pipeline/schema.sql` *(append)* | schema | DDL | `document_event_log` table (lines 107-115) — all-nullable log pattern | role-match |
| `src/eth_pipeline/schema.sql` *(append)* | schema | DDL | `CREATE INDEX IF NOT EXISTS` pattern (lines 135-148) — same role | exact |
| `scripts/init_schema.py` *(already exists)* | script | batch | Primary schema deployment mechanism (no changes needed) | reference |
| `docker-compose.yml` schema-init service (lines 79-94) *(already exists)* | config | batch | `docker compose run --rm schema-init` workflow (no changes needed) | reference |

## Pattern Assignments

### `src/eth_pipeline/schema.sql` — `llm_call_log` table definition (append)

**Analog:** `src/eth_pipeline/schema.sql` lines 117-133 (`llm_usage` table — primary analog)

**Core table pattern — `llm_usage` (lines 117-133):**
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
*Source: `src/eth_pipeline/schema.sql` lines 117-133*

**Key differences for `llm_call_log`:**
- All fields EXCEPT `id` (PK) and `document` (FK) are nullable `DEFAULT NULL` — do NOT copy `NOT NULL` constraints from `llm_usage`
- Add `prompt_text TEXT DEFAULT NULL` and `response_text TEXT DEFAULT NULL` — use `TEXT` (not `VARCHAR`) for arbitrarily large LLM outputs
- Use `activity_type TEXT DEFAULT NULL` instead of `step_name` (categories like `'extract_events'`, `'resolve_entities'`)
- Use `timestamp TIMESTAMPTZ DEFAULT NULL` instead of `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- No `DEFAULT` values, no `CHECK` constraints on content/metric fields

**All-nullable log table pattern — `document_event_log` (lines 107-115):**
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
*Source: `src/eth_pipeline/schema.sql` lines 107-115*
- Note: `document_event_log` has some `NOT NULL` + `DEFAULT` fields, but `llm_call_log` follows the **all-nullable** variant (no `NOT NULL` on any content field)

**FK `ON DELETE CASCADE` pattern — common across log tables:**
```
document TEXT NOT NULL REFERENCES document(id) ON DELETE CASCADE
```
Used at:
- `src/eth_pipeline/schema.sql` line 109 (`document_event_log`)
- `src/eth_pipeline/schema.sql` line 119 (`llm_usage`)
- `src/eth_pipeline/schema.sql` line 37 (`document_chunk`)
- `src/eth_pipeline/schema.sql` line 48 (`event`)

---

### `src/eth_pipeline/schema.sql` — Index definitions (append, after table)

**Analog:** `src/eth_pipeline/schema.sql` lines 135-148

**Index pattern (lines 147-148):**
```sql
CREATE INDEX IF NOT EXISTS idx_document_event_log_document ON document_event_log(document);
CREATE INDEX IF NOT EXISTS idx_llm_usage_document_created ON llm_usage(document, created_at);
```
*Source: `src/eth_pipeline/schema.sql` lines 147-148*

**Naming convention:** `idx_<table>_<column>` — e.g., `idx_llm_call_log_document`, `idx_llm_call_log_timestamp`

**Full index index in the file (lines 135-148) for reference:**
```sql
CREATE INDEX IF NOT EXISTS idx_document_chunk_document ON document_chunk(document);
CREATE INDEX IF NOT EXISTS idx_event_document ON event(document);
CREATE INDEX IF NOT EXISTS idx_reference_event ON reference(event);
CREATE INDEX IF NOT EXISTS idx_reference_canonical_entity ON reference(canonical_entity);
CREATE INDEX IF NOT EXISTS idx_reference_entity_id ON reference(entity_id);
CREATE INDEX IF NOT EXISTS idx_canonical_entity_type ON canonical_entity(entity_type);
CREATE INDEX IF NOT EXISTS idx_canonical_entity_name ON canonical_entity(name);
CREATE INDEX IF NOT EXISTS idx_canonical_entity_props_doc_id ON canonical_entity((properties->>'document_id'));
CREATE INDEX IF NOT EXISTS idx_event_entity_link_event ON event_entity_link(event);
CREATE INDEX IF NOT EXISTS idx_event_entity_link_entity ON event_entity_link(entity);
CREATE INDEX IF NOT EXISTS idx_event_participant_in ON event_participant(in_event);
CREATE INDEX IF NOT EXISTS idx_event_participant_out ON event_participant(out_entity);
CREATE INDEX IF NOT EXISTS idx_document_event_log_document ON document_event_log(document);
CREATE INDEX IF NOT EXISTS idx_llm_usage_document_created ON llm_usage(document, created_at);
```

### Deployment — Schema execution script (reference only, no changes)

**File:** `scripts/init_schema.py`

**Core pattern (lines 18-53):**
```python
async def apply_schema(schema_path: Path, dsn: str | None = None) -> None:
    import asyncpg
    dsn = dsn or DEFAULT_DSN
    sql = schema_path.read_text()

    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute("SELECT 1")
        statements = [s.strip() for s in sql.split(";") if s.strip()]

        for i, stmt in enumerate(statements, start=1):
            preview = stmt[:80].replace("\n", " ")
            print(f"  [{i}/{len(statements)}] {preview}...", end=" ", flush=True)
            try:
                await conn.execute(stmt)
                print("✅")
            except Exception as exc:
                print(f"❌ {exc}")
                sys.exit(1)
    finally:
        await conn.close()
```
*Important: The parser splits on `;` and has a known bug with apostrophes in SQL comments (see Pitfall 4 in RESEARCH.md). Avoid `'` in comments.*

### Deployment — Docker Compose schema-init service (reference only, no changes)

**File:** `docker-compose.yml` lines 79-94

```yaml
  schema-init:
    build: .
    command: uv run python scripts/init_schema.py
    env_file: .env
    environment:
      PGUSER: eth
      PGPASSWORD: eth
      PGHOST: postgres
      PGPORT: "5432"
      PGDATABASE: eth
    depends_on:
      postgres:
        condition: service_healthy
    restart: 'no'
    networks:
      - eth-pipeline
```

Run command: `docker compose run --rm schema-init`

## Shared Patterns

### 1. `CREATE TABLE IF NOT EXISTS` — All tables use this for idempotency

Source: Every table in `schema.sql` (lines 1, 19, 29, 41, 61, 80, 98, 107, 117)
Apply to: New `llm_call_log` table
Pattern: `CREATE TABLE IF NOT EXISTS <name> (...)` — safe for repeated schema-init runs

### 2. `CREATE INDEX IF NOT EXISTS` — All indexes use this for idempotency

Source: `schema.sql` lines 135-148
Apply to: New `llm_call_log` indexes
Pattern: `CREATE INDEX IF NOT EXISTS idx_llm_call_log_document ON llm_call_log(document);`

### 3. `TEXT PRIMARY KEY` — All PKs use TEXT (not SERIAL/UUID)

Source: Every table in `schema.sql` (lines 1, 19, 29, 41, 61, 80, 98, 107, 117)
Apply to: New `llm_call_log.id TEXT PRIMARY KEY`
Rationale: Deterministic SHA256 IDs generated at application layer (Phase 30)

### 4. `document TEXT NOT NULL REFERENCES document(id) ON DELETE CASCADE` — Log FK pattern

Source: `schema.sql` lines 109, 119
Apply to: New `llm_call_log.document` FK
Rationale: All log tables cascade-delete when parent document is removed

### 5. No trailing semicolons after closing `)` in multi-statement blocks

Source: `schema.sql` — each `CREATE TABLE` ends with `);` on its own line, then blank line, then next statement. No semicolons after the closing paren except the one terminating the CREATE TABLE statement.
Apply to: New DDL block follows same formatting

## No Analog Found

N/A — all patterns have close matches in the existing `schema.sql` file.

## Metadata

**Analog search scope:** `src/eth_pipeline/schema.sql`, `scripts/init_schema.py`, `docker-compose.yml`
**Files scanned:** 3
**Pattern extraction date:** 2026-06-06
