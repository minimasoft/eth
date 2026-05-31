-- ==========================================================================
-- Eth-Pipeline: SurrealDB Schema
-- ==========================================================================
-- This schema defines the data model for processing Spanish-language court documents,
-- extracting structured events, and storing verbatim text references.
--
-- All DEFINE TABLE and DEFINE FIELD statements carry COMMENT annotations
-- so that SurrealDB auto-GraphQL generates a self-documenting API.
-- ==========================================================================

-- --------------------------------------------------------------------------
-- Namespace and Database
-- --------------------------------------------------------------------------
-- These are idempotent: SurrealDB silently ignores re-creation of existing
-- namespaces and databases. The init script applies these, then selects the
-- namespace/database via HTTP headers (NS: eth, DB: pipeline).
-- --------------------------------------------------------------------------

DEFINE NAMESPACE eth COMMENT 'Top-level namespace for the document processing pipeline';
DEFINE DATABASE pipeline COMMENT 'Primary database holding documents, extracted events, and verbatim references';

-- ==========================================================================
-- Table: document
-- ==========================================================================
-- Stores uploaded (or ingested) source documents — Spanish-language court documents,
-- PDFs, markdown files, or plain text. Each document progresses through a
-- lifecycle: pending → extracted → processed → failed.
-- ==========================================================================

DEFINE TABLE document SCHEMAFULL
    COMMENT 'Source documents ingested into the pipeline (court documents, PDFs, markdown)';

DEFINE FIELD original_blob ON TABLE document TYPE string
    COMMENT 'Base64-encoded raw content of the uploaded source file';

DEFINE FIELD text_content ON TABLE document TYPE string
    COMMENT 'Plain-text representation extracted from the source file for LLM processing';

DEFINE FIELD status ON TABLE document TYPE string
    ASSERT $value = 'pending' OR $value = 'extracted' OR $value = 'processed' OR $value = 'failed'
    COMMENT 'Lifecycle status: pending=uploaded, extracted=events found, processed=fully handled, failed=processing error';

DEFINE FIELD filename ON TABLE document TYPE string
    COMMENT 'Original filename from ingestion (used for display and debugging)';

DEFINE FIELD mime_type ON TABLE document TYPE string
    COMMENT 'MIME type of the source file (e.g. text/plain, application/pdf, text/markdown)';

DEFINE FIELD error_message ON TABLE document TYPE string | null
    DEFAULT null
    COMMENT 'Human-readable error description when status is "failed" (null otherwise)';

DEFINE FIELD created_at ON TABLE document TYPE datetime
    DEFAULT time::now() READONLY
    COMMENT 'Timestamp when the document was first ingested (immutable after creation)';

DEFINE FIELD updated_at ON TABLE document TYPE datetime
    DEFAULT time::now()
    COMMENT 'Timestamp of the most recent update to this document record';

-- ==========================================================================
-- Table: event
-- ==========================================================================
-- Represents a single structured "event" extracted from a document by an LLM.
-- Each event answers the five Ws: qué pasó (what happened), espacio (where),
-- tiempo (when), humanos (who), objetos (what objects). The document field
-- links back to the source.
-- ==========================================================================

DEFINE TABLE event SCHEMAFULL
    COMMENT 'Structured event extracted from a source document via LLM analysis';

DEFINE FIELD que_paso ON TABLE event TYPE string
    COMMENT 'Core narrative: what happened (the primary event description)';

DEFINE FIELD espacio ON TABLE event TYPE string | null
    COMMENT 'Location or spatial context where the event occurred (optional)';

DEFINE FIELD tiempo ON TABLE event TYPE string | null
    COMMENT 'Temporal context: when the event occurred (optional, free-form date/time)';

DEFINE FIELD humanos ON TABLE event TYPE string | null
    COMMENT 'People or organizations involved in the event (optional)';

DEFINE FIELD objetos ON TABLE event TYPE string | null
    COMMENT 'Objects, assets, or physical items involved in the event (optional)';

DEFINE FIELD document ON TABLE event TYPE record<document>
    COMMENT 'Link to the source document from which this event was extracted';

DEFINE FIELD extraction_confidence ON TABLE event TYPE number
    ASSERT $value >= 0 AND $value <= 1
    COMMENT 'LLM confidence score for this extraction (0.0 = uncertain, 1.0 = certain)';

DEFINE FIELD created_at ON TABLE event TYPE datetime
    DEFAULT time::now() READONLY
    COMMENT 'Timestamp when the event record was created (immutable after insertion)';

-- ==========================================================================
-- Table: reference
-- ==========================================================================
-- Stores verbatim text spans extracted from the source document that support
-- a specific field of an event. Each reference carries a type tag
-- (espacio/tiempo/humanos/objetos) matching the event field it substantiates,
-- and records the exact character offsets within the source document so the
-- original context can be retrieved.
-- ==========================================================================

DEFINE TABLE reference SCHEMAFULL
    COMMENT 'Verbatim text span from a source document substantiating an event field';

DEFINE FIELD reference_type ON TABLE reference TYPE string
    ASSERT $value = 'espacio' OR $value = 'tiempo' OR $value = 'humanos' OR $value = 'objetos'
    COMMENT 'Which event field this reference supports: espacio (location), tiempo (time), humanos (people), objetos (objects)';

DEFINE FIELD verbatim_text ON TABLE reference TYPE string
    COMMENT 'Exact verbatim text as it appears in the source document';

DEFINE FIELD span_start ON TABLE reference TYPE int
    COMMENT 'Character offset (0-based) where the verbatim span begins in text_content';

DEFINE FIELD span_end ON TABLE reference TYPE int
    COMMENT 'Character offset (exclusive) where the verbatim span ends in text_content';

DEFINE FIELD event ON TABLE reference TYPE record<event>
    COMMENT 'Link to the event that this reference belongs to and substantiates';

DEFINE FIELD canonical_entity ON TABLE reference TYPE record<canonical_entity> | null
    COMMENT 'Link to the resolved canonical entity record (M002)';

DEFINE FIELD resolution_confidence ON TABLE reference TYPE number | null
    DEFAULT null
    ASSERT $value IS NONE OR ($value >= 0 AND $value <= 1)
    COMMENT 'Confidence score (0.0–1.0) for the canonical_entity resolution; null when not yet resolved';

-- ==========================================================================
-- Table: canonical_entity
-- ==========================================================================
-- Represents a resolved canonical entity — a deduplicated, curated record that
-- multiple references and events can link to. Supports entity types: place,
-- person, object. The superseded_by field enables entity merging: when two
-- entities are merged, the superseded record points to its replacement.
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
-- End of schema
-- ==========================================================================
