-- ==========================================================================
-- SurrealDB SQL Migration: event table creation
-- ==========================================================================
-- Run via: curl -X POST http://localhost:8000/sql -H "Authorization: Basic ..."
-- with Surreal-Ns:eth, Surreal-DB:pipeline

-- First ensure namespace and database exist
DEFINE NAMESPACE eth COMMENT 'Ethereum processing namespace';
DEFINE DATABASE pipeline COMMENT 'Ethereum document pipeline database';

-- Define the event table
DEFINE TABLE event SCHEMAFULL
    COMMENT 'Structured events extracted from documents via LLM extraction';

-- Define status field with lifecycle assertions
DEFINE FIELD status ON TABLE event TYPE string
    ASSERT value INSIDE ['pending', 'extracted', 'processed', 'failed']
    COMMENT 'Lifecycle status: pending=awaiting extraction, extracted=events found, processed=fully handled, failed=processing error';

-- Define reference_type field with allowed values assertion
DEFINE FIELD reference_type ON TABLE reference TYPE string
    ASSERT value INSIDE ['espacio', 'tiempo', 'humanos', 'objetos']
    COMMENT 'Which event field this reference supports: espacio (location), tiempo (time), humanos (people), objetos (objects)';

-- Additional fields for event content and provenance
DEFINE FIELD que_paso ON TABLE event TYPE string
    COMMENT 'Core narrative: what happened (the primary event description)';

DEFINE FIELD espacio ON TABLE event TYPE string
    COMMENT 'Location or spatial context where the event occurred';

DEFINE FIELD tiempo ON TABLE event TYPE string
    COMMENT 'Temporal context: when the event occurred (free-form date/time reference)';

DEFINE FIELD humanos ON TABLE event TYPE string
    COMMENT 'People or organizations involved in the event';

DEFINE FIELD objetos ON TABLE event TYPE string
    COMMENT 'Objects, assets, or items involved in the event';

-- References array linking verbatim text spans to event fields
DEFINE FIELD references ON TABLE event TYPE array
    COMMENT 'Array of reference objects linking verbatim text spans';

-- Define reference sub-object schema
DEFINE FIELD reference_type ON TABLE reference TYPE string
    ASSERT value INSIDE ['espacio', 'tiempo', 'humanos', 'objetos']
    COMMENT 'Which event field this reference supports';

DEFINE FIELD verbatim_text ON TABLE reference TYPE string
    COMMENT 'Exact verbatim text span from the source document';

DEFINE FIELD span_start ON TABLE reference TYPE number
    COMMENT 'Character offset (0-based) where the verbatim span begins';

DEFINE FIELD span_end ON TABLE reference TYPE number
    COMMENT 'Character offset (exclusive) where the verbatim span ends';

DEFINE FIELD document ON TABLE event TYPE record
    COMMENT 'Link to the source document from which this event was extracted';

-- Permissions
PERMISSIONS FULL ON TABLE event;
PERMISSIONS FULL ON TABLE reference;

-- Assertions for data integrity
ASSERT value INSIDE ['pending', 'extracted', 'processed', 'failed'] ON FIELD status OF event;
ASSERT value INSIDE ['espacio', 'tiempo', 'humanos', 'objetos'] ON FIELD reference_type OF reference;

COMMENT 'This schema defines the event extraction storage layer for the eth pipeline.
The event table holds structured data extracted by LLM from Spanish legal documents,
with status tracking (pending→extracted→processed→failed) and verbatim references
linking each event field to the original document text spans.';
