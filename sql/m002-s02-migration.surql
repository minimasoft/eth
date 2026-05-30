-- ==========================================================================
-- SurrealDB SQL Migration: M002 S02 — Entity Resolution Index
-- ==========================================================================
-- Run via: curl -X POST http://localhost:8000/sql \
--   -H "Authorization: Basic $(echo -n 'root:root' | base64)" \
--   -H "Surreal-Ns: eth" \
--   -H "Surreal-DB: pipeline" \
--   -d @sql/m002-s02-migration.surql

-- ==========================================================================
-- Index: canonical_entity.entity_type
-- ==========================================================================
-- Speeds up the entity-resolution query:
--   SELECT * FROM canonical_entity WHERE entity_type = $type
-- which is executed per reference-type batch in resolve_entities_activity.
-- ==========================================================================

DEFINE INDEX entity_type_idx ON TABLE canonical_entity COLUMNS entity_type
    COMMENT 'Index for efficient filtering of canonical entities by type (place/person/object) during LLM-based resolution batching';
