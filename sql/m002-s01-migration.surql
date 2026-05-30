-- ==========================================================================
-- SurrealDB SQL Migration: M002 S01 — Canonical Entity Schema Foundation
-- ==========================================================================
-- Run via: curl -X POST http://localhost:8000/sql \
--   -H "Authorization: Basic $(echo -n 'root:root' | base64)" \
--   -H "Surreal-Ns: eth" \
--   -H "Surreal-DB: pipeline" \
--   -d @sql/m002-s01-migration.surql

-- ==========================================================================
-- Table: canonical_entity
-- ==========================================================================
-- Represents a resolved canonical entity — a deduplicated, curated record
-- that multiple references and events can link to. Supports entity types:
-- place, person, object. The superseded_by field enables entity merging.
-- ==========================================================================

DEFINE TABLE canonical_entity SCHEMAFULL
    COMMENT 'Resolved canonical entity that references link to after entity resolution';

DEFINE FIELD entity_type ON TABLE canonical_entity TYPE string
    ASSERT $value INSIDE ['place', 'person', 'object']
    COMMENT 'Entity category: place (location/geography), person (individual/organization), object (physical/digital item)';

DEFINE FIELD name ON TABLE canonical_entity TYPE string
    COMMENT 'Display name or label for this canonical entity';

DEFINE FIELD properties ON TABLE canonical_entity TYPE object | null
    DEFAULT null
    COMMENT 'Arbitrary key-value metadata enriching this entity (optional, nullable)';

DEFINE FIELD superseded_by ON TABLE canonical_entity TYPE record<canonical_entity> | null
    DEFAULT null
    COMMENT 'When non-null, this entity has been merged into the target entity; queries should follow the chain';

DEFINE FIELD created_at ON TABLE canonical_entity TYPE datetime
    DEFAULT time::now() READONLY
    COMMENT 'Timestamp when the canonical entity record was created (immutable after creation)';

DEFINE FIELD updated_at ON TABLE canonical_entity TYPE datetime
    DEFAULT time::now()
    COMMENT 'Timestamp of the most recent update to this canonical entity record';

-- ==========================================================================
-- Update: reference table — typed canonical_entity link + resolution_confidence
-- ==========================================================================

DEFINE FIELD canonical_entity ON TABLE reference TYPE record<canonical_entity> | null
    COMMENT 'Link to the resolved canonical entity record (M002)';

DEFINE FIELD resolution_confidence ON TABLE reference TYPE number | null
    DEFAULT null
    ASSERT $value IS NONE OR ($value >= 0 AND $value <= 1)
    COMMENT 'Confidence score (0.0–1.0) for the canonical_entity resolution; null when not yet resolved';

-- Permissions are default (FULL for root) — no explicit DEFINE PERMISSIONS needed.
-- M002 S01 migration: creates the canonical_entity table with typed fields,
-- adds resolution_confidence to reference, and tightens canonical_entity to
-- record<canonical_entity>.
