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

DEFINE FIELD text_content ON TABLE document TYPE string | null
    DEFAULT null
    COMMENT 'Plain-text representation extracted from the source file for LLM processing (null for unprocessed blob-stored documents)';

DEFINE FIELD status ON TABLE document TYPE string
    ASSERT $value = 'pending' OR $value = 'processing' OR $value = 'extracted' OR $value = 'extracting_blob' OR $value = 'extracting_text' OR $value = 'chunking' OR $value = 'processed' OR $value = 'failed'
    COMMENT 'Lifecycle status: pending=uploaded, processing=workflow started, extracted=events found, extracting_blob=reading binary blob, extracting_text=llm extracting events, chunking=splitting text into chunks, processed=fully handled, failed=processing error';

DEFINE FIELD filename ON TABLE document TYPE string
    COMMENT 'Original filename from ingestion (used for display and debugging)';

DEFINE FIELD mime_type ON TABLE document TYPE string
    COMMENT 'MIME type of the source file (e.g. text/plain, application/pdf, text/markdown)';

DEFINE FIELD blob_format ON TABLE document TYPE string | null
    DEFAULT null
    COMMENT 'Storage format of the original binary blob: "minio" (object-stored), null (inline base64 for legacy)';

DEFINE FIELD blob_path ON TABLE document TYPE string | null
    DEFAULT null
    COMMENT 'S3 object path within the eth-documents bucket when blob_format="minio" (e.g. doc/{id}.pdf); null for legacy inline-stored documents';

DEFINE FIELD _page_count ON TABLE document TYPE int | null
    DEFAULT null
    COMMENT 'Number of pages in the source document (set after text extraction or PDF parsing; null for unprocessed documents)';

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
-- Table: document_chunk
-- ==========================================================================
-- Stores text chunks extracted from a document, with page-level
-- provenance. Each chunk records its position in the chunk sequence, the
-- page range it covers (1-based), and the character offset range in the
-- full document text. Chunks are internal — the LLM extraction pipeline
-- always receives the full reconstructed text from document.text_content.
-- ==========================================================================

DEFINE TABLE document_chunk SCHEMAFULL
    COMMENT 'Text chunk from a document with page-level provenance (internal — LLM never sees individual chunks)';

DEFINE FIELD chunk_index ON TABLE document_chunk TYPE int
    ASSERT $value >= 0
    COMMENT 'Zero-based index of this chunk in the document chunk sequence';

DEFINE FIELD text ON TABLE document_chunk TYPE string
    COMMENT 'The chunk text content';

DEFINE FIELD page_start ON TABLE document_chunk TYPE int
    ASSERT $value >= 1
    COMMENT 'Page number (1-based) where this chunk begins in the source document';

DEFINE FIELD page_end ON TABLE document_chunk TYPE int
    ASSERT $value >= 1
    COMMENT 'Page number (1-based, inclusive) where this chunk ends in the source document';

DEFINE FIELD offset_start ON TABLE document_chunk TYPE int
    ASSERT $value >= 0
    COMMENT 'Character offset (0-based) where this chunk starts in the full document text_content';

DEFINE FIELD offset_end ON TABLE document_chunk TYPE int
    ASSERT $value >= 0
    COMMENT 'Character offset (exclusive) where this chunk ends in the full document text_content';

DEFINE FIELD document ON TABLE document_chunk TYPE record<document>
    COMMENT 'Link to the source document that this chunk belongs to';

DEFINE FIELD created_at ON TABLE document_chunk TYPE datetime
    DEFAULT time::now() READONLY
    COMMENT 'Timestamp when the chunk record was created (immutable after insertion)';

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
    DEFAULT null
    COMMENT 'Link to the resolved canonical entity record (M002)';

DEFINE FIELD resolution_confidence ON TABLE reference TYPE number | null
    DEFAULT null
    ASSERT $value IS NONE OR $value IS NULL OR ($value >= 0 AND $value <= 1)
    COMMENT 'Confidence score (0.0–1.0) for the canonical_entity resolution; NONE/null when not yet resolved';

DEFINE FIELD entity_id ON TABLE reference TYPE record<canonical_entity> | null
    DEFAULT null
    COMMENT 'Link to the pre-resolved canonical entity set by search-first resolution (Phase 17). Both entity_id and canonical_entity are set for consistency — entity_id is the authoritative link for search-first resolution, canonical_entity remains for backward compatibility with merge/split operations.';

DEFINE FIELD created_at ON TABLE reference TYPE datetime
    DEFAULT time::now() READONLY
    COMMENT 'Timestamp when the reference record was created (immutable after insertion)';

DEFINE FIELD updated_at ON TABLE reference TYPE datetime
    DEFAULT time::now()
    COMMENT 'Timestamp of the most recent update to this reference record';

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

DEFINE FIELD properties ON TABLE canonical_entity TYPE object | null FLEXIBLE
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

-- ====== v4.0 Schema Evolution ======
-- Phase 13: Schema Evolution — additive DDL for reference offsets,
-- processing logs, event entities, and RELATE graph edges.
-- All statements are idempotent on re-apply.
-- ======

-- -----------------------------------------------------------------------
-- 1. Reference offset fields (OFFS-01, OFFS-02, OFFS-04)
-- New nullable fields for page-level character offset tracking.
-- DEFAULT null preserves null safety for plain-text documents.
-- -----------------------------------------------------------------------

DEFINE FIELD page_number ON TABLE reference TYPE int | null
    DEFAULT null
    COMMENT '1-based page number where this reference appears (null for plain-text documents — Phase 14 sets this)';

DEFINE FIELD page_offset_start ON TABLE reference TYPE int | null
    DEFAULT null
    COMMENT 'Page-relative character offset (0-based) where the verbatim span begins on the page (null for plain-text documents)';

DEFINE FIELD page_offset_end ON TABLE reference TYPE int | null
    DEFAULT null
    COMMENT 'Page-relative character offset (exclusive) where the verbatim span ends on the page (null for plain-text documents)';

-- -----------------------------------------------------------------------
-- 2. Event entity_type enum extension (EVNT-01)
-- OVERWRITE required because entity_type is already defined with
-- ['place', 'person', 'object']. SurrealDB returns an error if you
-- DEFINE FIELD without OVERWRITE on an existing field.
-- -----------------------------------------------------------------------

DEFINE FIELD OVERWRITE entity_type ON TABLE canonical_entity TYPE string
    ASSERT $value INSIDE ['place', 'person', 'object', 'event']
    COMMENT 'Entity category: place, person, object, or event (event added in v4.0)';

-- -----------------------------------------------------------------------
-- 3. event_entity_link table (EVNT-05, D-11, D-12)
-- Explicit SCHEMAFULL table with record-link fields (not an embedded relation type).
-- Stores graph edges that link event-type canonical entities to
-- place/person/object canonical entities.
-- -----------------------------------------------------------------------

DEFINE TABLE event_entity_link SCHEMAFULL
    COMMENT 'Graph edge linking an event-type canonical entity to a place/person/object entity. Populated by Phase 16 (create_event_canonical_entities_activity). Use RELATE queries: event->event_entity_link->entity';

DEFINE FIELD OVERWRITE event ON TABLE event_entity_link TYPE record<canonical_entity>
    COMMENT 'The source event canonical entity (canonical_entity with entity_type="event")';

DEFINE FIELD entity ON TABLE event_entity_link TYPE record<canonical_entity>
    COMMENT 'The target canonical entity (place, person, or object type)';

DEFINE FIELD relationship_type ON TABLE event_entity_link TYPE string
    COMMENT 'Nature of the relationship: "involves", "located_at", "occurred_during", or free-form (prototype flexibility — documented but not ASSERT-constrained)';

DEFINE FIELD role ON TABLE event_entity_link TYPE string | null
    DEFAULT null
    COMMENT 'Role of the linked entity in the event context: "subject", "object", "location", or free-form (null when role is not applicable)';

DEFINE FIELD confidence ON TABLE event_entity_link TYPE number | null
    DEFAULT null
    ASSERT $value IS NONE OR ($value >= 0 AND $value <= 1)
    COMMENT 'Confidence score (0.0–1.0) for this relationship link; NONE/null when confidence is not assessed';

DEFINE FIELD notes ON TABLE event_entity_link TYPE string | null
    DEFAULT null
    COMMENT 'Human-readable notes about this relationship (optional)';

DEFINE FIELD created_at ON TABLE event_entity_link TYPE datetime
    DEFAULT time::now() READONLY
    COMMENT 'Timestamp when the event-entity link was created (immutable after creation)';

-- -----------------------------------------------------------------------
-- 4. document_event_log table (LOGS-01, D-03 through D-08)
-- Processing audit log for document workflows. Entries use deterministic
-- string IDs (SHA256 hash) for Temporal replay idempotency.
-- WARNING: This table is exposed via auto-GraphQL with MUTATIONS enabled.
-- Application code should INSERT/UPDATE via the REST API or Temporal
-- activities ONLY. Direct GraphQL mutations may bypass business logic.
-- -----------------------------------------------------------------------

DEFINE TABLE document_event_log SCHEMAFULL
    COMMENT 'Per-document processing audit log. Entries created by Temporal activities (Phase 15). Deterministic IDs for replay safety. ⚠ GraphQL mutations available but DISCOURAGED — writes should go through REST API or Temporal activities only';

DEFINE FIELD id ON TABLE document_event_log TYPE string
    COMMENT 'Deterministic record ID: crypto::sha256(document_id + step_name + sequence_number)[0:16] — enables delete-then-recreate on Temporal replays';

DEFINE FIELD document ON TABLE document_event_log TYPE record<document>
    COMMENT 'Link to the source document that this log entry belongs to';

DEFINE FIELD step_name ON TABLE document_event_log TYPE string
    COMMENT 'Processing step name: e.g. "extract_text", "chunk_document", "extract_events", "store_results", "resolve_entities" (free-form)';

DEFINE FIELD severity ON TABLE document_event_log TYPE string
    ASSERT $value INSIDE ['info', 'warning', 'error']
    COMMENT 'Severity level: info (normal operation), warning (non-fatal issue), error (processing failure)';

DEFINE FIELD message ON TABLE document_event_log TYPE string
    COMMENT 'Human-readable log message describing the event';

DEFINE FIELD details ON TABLE document_event_log TYPE object | null FLEXIBLE
    DEFAULT null
    COMMENT 'Arbitrary structured metadata attached to this log entry (FLEXIBLE — accepts any JSON object). Examples: { "llm_confidence": 0.85, "extraction_time_ms": 1234, "chunk_count": 5 }';

DEFINE FIELD created_at ON TABLE document_event_log TYPE datetime
    DEFAULT time::now() READONLY
    COMMENT 'Timestamp when the log entry was created (immutable after insertion)';

-- -----------------------------------------------------------------------
-- 5. Indexes (the agent's Discretion)
-- document_event_log: index on document field for efficient per-document queries
-- event_entity_link: index on event and entity for graph traversal performance
-- -----------------------------------------------------------------------

DEFINE INDEX idx_document_event_log_document ON TABLE document_event_log COLUMNS document
    COMMENT 'Index for efficient filtering of log entries by document (used by GET /documents/{id}/logs endpoint)';

DEFINE INDEX idx_event_entity_link_event ON TABLE event_entity_link COLUMNS event
    COMMENT 'Index for efficient graph traversal from event to linked entities';

DEFINE INDEX idx_event_entity_link_entity ON TABLE event_entity_link COLUMNS entity
    COMMENT 'Index for efficient reverse graph traversal from entity to linked events';

-- ==========================================================================
-- End of schema
-- ==========================================================================
