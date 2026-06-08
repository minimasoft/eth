CREATE TABLE IF NOT EXISTS document (
    id TEXT PRIMARY KEY,
    original_blob TEXT NOT NULL DEFAULT '',
    text_content TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    filename TEXT NOT NULL DEFAULT '',
    mime_type TEXT NOT NULL DEFAULT '',
    blob_format TEXT,
    blob_path TEXT,
    _page_count INTEGER,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT valid_status CHECK (
        status IN ('pending','processing','extracted','extracting_blob','extracting_text','chunking','processed','failed')
    )
);

CREATE TABLE IF NOT EXISTS canonical_entity (
    id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL CHECK (entity_type IN ('place','person','object','event')),
    name TEXT NOT NULL DEFAULT '',
    properties JSONB,
    superseded_by TEXT REFERENCES canonical_entity(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS document_chunk (
    id TEXT PRIMARY KEY,
    chunk_index INTEGER NOT NULL CHECK (chunk_index >= 0),
    text TEXT NOT NULL DEFAULT '',
    page_start INTEGER CHECK (page_start >= 1),
    page_end INTEGER CHECK (page_end >= 1),
    offset_start INTEGER NOT NULL CHECK (offset_start >= 0),
    offset_end INTEGER NOT NULL CHECK (offset_end >= 0),
    document TEXT NOT NULL REFERENCES document(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS event (
    id TEXT PRIMARY KEY,
    que_paso TEXT NOT NULL DEFAULT '',
    espacio TEXT,
    tiempo TEXT,
    humanos TEXT,
    objetos TEXT,
    document TEXT NOT NULL REFERENCES document(id) ON DELETE CASCADE,
    extraction_confidence REAL NOT NULL DEFAULT 1.0 CHECK (extraction_confidence >= 0 AND extraction_confidence <= 1),
    -- Expected shape: {"start": "ISO datetime", "end": "ISO datetime", "precision": "day|month|year" | null}
    time_window JSONB,
    -- Expected shape: {"lat": float, "lon": float, "label": string | null}
    location_point JSONB,
    -- NOTE: entity_type='place' constraint for location_place_id is enforced at
    -- application level (store_extraction_results.py line 131-136, resolve_entities.py
    -- line 284-293). PostgreSQL CHECK constraints cannot reference other tables.
    location_place_id TEXT REFERENCES canonical_entity(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS reference (
    id TEXT PRIMARY KEY,
    reference_type TEXT NOT NULL CHECK (reference_type IN ('espacio','tiempo','humanos','objetos')),
    verbatim_text TEXT NOT NULL DEFAULT '',
    span_start INTEGER NOT NULL,
    span_end INTEGER NOT NULL,
    page_number INTEGER,
    page_offset_start INTEGER,
    page_offset_end INTEGER,
    element_field TEXT,
    reference_index INTEGER,
    event TEXT NOT NULL REFERENCES event(id) ON DELETE CASCADE,
    canonical_entity TEXT REFERENCES canonical_entity(id) ON DELETE SET NULL,
    entity_id TEXT REFERENCES canonical_entity(id) ON DELETE SET NULL,
    resolution_confidence REAL CHECK (resolution_confidence IS NULL OR (resolution_confidence >= 0 AND resolution_confidence <= 1)),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS event_entity_link (
    id TEXT PRIMARY KEY,
    event TEXT NOT NULL REFERENCES canonical_entity(id) ON DELETE CASCADE,
    entity TEXT NOT NULL REFERENCES canonical_entity(id) ON DELETE CASCADE,
    relationship_type TEXT NOT NULL DEFAULT '',
    role TEXT,
    confidence REAL CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- event_participant: Graph edge linking an event record directly to a participant
-- (person-type canonical_entity). IN→event, OUT→canonical_entity (person type).
-- Populated by pipeline activities (resolve_entities, store_extraction_results).
-- Distinguished from event_entity_link:
--   event_participant connects event records directly to person entities.
--   event_entity_link connects event-type canonical entities to any entity type
--   (place/person/object) via the RELATE pattern.
CREATE TABLE IF NOT EXISTS event_participant (
    id TEXT PRIMARY KEY,
    in_event TEXT NOT NULL REFERENCES event(id) ON DELETE CASCADE,
    out_entity TEXT NOT NULL REFERENCES canonical_entity(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT '',
    confidence REAL CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS document_event_log (
    id TEXT PRIMARY KEY,
    document TEXT NOT NULL REFERENCES document(id) ON DELETE CASCADE,
    step_name TEXT NOT NULL DEFAULT '',
    severity TEXT NOT NULL DEFAULT 'info' CHECK (severity IN ('info','warning','error')),
    message TEXT NOT NULL DEFAULT '',
    details JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

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

-- v6.1 Schema Evolution -- Phase 29: LLM Call Log
-- Additive DDL: new llm_call_log table for recording LLM prompt/response
-- pairs, token usage, cost, duration, and metadata per document.
-- All fields are nullable DEFAULT null for additive safety.

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
    chunk_index INTEGER NOT NULL DEFAULT 0 CHECK (chunk_index >= 0),
    document TEXT NOT NULL REFERENCES document(id) ON DELETE CASCADE,
    timestamp TIMESTAMPTZ DEFAULT NULL
);

CREATE INDEX IF NOT EXISTS idx_llm_call_log_document ON llm_call_log(document);
CREATE INDEX IF NOT EXISTS idx_llm_call_log_timestamp ON llm_call_log(timestamp);

-- v6.1 Migration: add chunk_index column (missing from initial DDL — INSERT fails without it)
ALTER TABLE llm_call_log ADD COLUMN IF NOT EXISTS chunk_index INTEGER NOT NULL DEFAULT 0 CHECK (chunk_index >= 0);
