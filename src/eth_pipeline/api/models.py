from __future__ import annotations

from pydantic import BaseModel
# =======================================================================
# Pydantic models
# =======================================================================


class DocumentInput(BaseModel):
    """Request body for ``POST /documents``."""

    text: str
    """Plain-text content of the document to be processed."""

    filename: str
    """Original filename (used for display and debugging)."""

    mime_type: str | None = None
    """MIME type of the source (defaults to ``text/plain`` at creation)."""


class DocumentCreated(BaseModel):
    """Response body for a successful ``POST /documents`` (HTTP 201)."""

    document_id: str
    """Unique identifier for the created document."""

    status: str = "pending"
    """Initial lifecycle status of the document."""


class DocumentUploadCreated(BaseModel):
    """Response body for a successful ``POST /documents/upload`` (HTTP 201)."""

    document_id: str
    """Unique identifier for the created document."""

    status: str = "pending"
    """Initial lifecycle status of the document."""


class DocumentStatus(BaseModel):
    """Response body for ``GET /documents/{document_id}``."""

    document_id: str
    """Unique identifier of the document."""

    status: str
    """Current processing status (pending/processing/processed/failed)."""

    filename: str
    """Original filename submitted at creation time."""

    error_message: str | None = None
    """Human-readable error description when status is ``failed``."""

    created_at: str | None = None
    """ISO-8601 timestamp of document creation (if available)."""

    blob_format: str | None = None
    """Storage format: 'minio' (object-stored) or None (legacy inline)."""

    blob_path: str | None = None
    """S3 object path when blob_format='minio'; None for legacy inline-stored documents."""

    reference_count: int = 0
    """Total number of verbatim references linked to this document via events."""

    entity_count: int = 0
    """Total number of distinct canonical entities linked to this document's references."""

    chunk_count: int = 0
    """Number of text chunks created from this document."""

    text_word_count: int = 0
    """Word count of the document's extracted text content."""


class DocumentListItem(BaseModel):
    """A single document entry in the paginated document list."""

    document_id: str
    """Unique identifier of the document."""

    status: str
    """Current processing status (pending/processing/processed/failed)."""

    filename: str
    """Original filename submitted at creation time."""

    created_at: str | None = None
    """ISO-8601 timestamp of document creation (if available)."""

    error_message: str | None = None
    """Human-readable error description when status is ``failed``."""

    reference_count: int = 0
    """Total number of verbatim references linked to this document via events."""

    entity_count: int = 0
    """Total number of distinct canonical entities linked to this document's references."""

    chunk_count: int = 0
    """Number of text chunks created from this document."""

    text_word_count: int = 0
    """Word count of the document's extracted text content."""

    prompt_tokens: int = 0
    """Total prompt (input) tokens across all LLM calls for this document."""

    completion_tokens: int = 0
    """Total completion (output) tokens across all LLM calls."""

    total_tokens: int = 0
    """Total tokens (prompt + completion) across all LLM calls."""

    cached_tokens: int = 0
    """Total cached tokens across all LLM calls (0 when not reported)."""

    total_cost: float | None = None
    """Total monetary cost across all LLM calls (None when cost data absent)."""

    duration_ms: int = 0
    """Total wall-clock duration of all LLM calls for this document."""


class DocumentListResponse(BaseModel):
    """Paginated response body for ``GET /documents``."""

    items: list[DocumentListItem]
    """List of document entries on the current page."""

    total: int
    """Total number of documents matching the query."""

    page: int
    """Current page number (1-based)."""

    per_page: int
    """Number of items per page."""

    pages: int
    """Total number of pages available."""


class EventsCleared(BaseModel):
    """Response body for ``DELETE /documents/{document_id}/events``."""

    document_id: str
    """Unique identifier of the document whose events were cleared."""

    status: str = "pending"
    """The document status after clearing events."""

    events_cleared: bool = True
    """Whether any events were actually cleared."""


class DocumentDeleted(BaseModel):
    """Response body for ``DELETE /documents/{document_id}`` (full cascade)."""

    document_id: str
    """Unique identifier of the deleted document."""

    document_deleted: bool = True
    """Whether the document record was deleted."""

    orphaned_entities_cleaned: int = 0
    """Number of canonical_entities that were orphaned and removed."""


class DocumentTokenUsage(BaseModel):
    """Per-document token usage aggregation response."""

    has_data: bool = False
    """Whether this document has any llm_usage records."""

    prompt_tokens: int = 0
    """Total prompt (input) tokens across all LLM calls for this document."""

    completion_tokens: int = 0
    """Total completion (output) tokens across all LLM calls."""

    total_tokens: int = 0
    """Total tokens (prompt + completion) across all LLM calls."""

    cached_tokens: int = 0
    """Total cached tokens across all LLM calls (0 when not reported)."""

    total_cost: float | None = None
    """Total monetary cost across all LLM calls (None when cost data absent)."""

    duration_ms: int = 0
    """Total wall-clock duration of all LLM calls for this document."""


class HealthResponse(BaseModel):
    """Response body for ``GET /health``."""

    status: str = "ok"


class EntityDeleted(BaseModel):
    entity_id: str
    entity_deleted: bool = True
    references_affected: int = 0


class EntityListItem(BaseModel):
    """A single entity entry in the paginated entity list."""

    entity_id: str
    """Unique identifier (hex portion of the RecordID) of the canonical entity."""

    name: str
    """Display name of the entity."""

    entity_type: str
    """Type of the entity (place/person/object)."""

    reference_count: int = 0
    """Number of references pointing to this entity."""


class EntityDetailReference(BaseModel):
    """A reference entry within an entity detail response."""

    reference_id: str
    reference_type: str
    verbatim_text: str
    event_que_paso: str | None = None
    event_id: str | None = None
    document_filename: str | None = None
    document_id: str | None = None


class EntityDetailResponse(BaseModel):
    """Response body for ``GET /entities/{entity_id}``."""

    entity_id: str
    name: str
    entity_type: str
    reference_count: int = 0
    properties: dict | None = None
    references: list[EntityDetailReference]


class EntityListResponse(BaseModel):
    """Paginated response body for ``GET /entities``."""

    items: list[EntityListItem]
    """List of entity entries on the current page."""

    total: int
    """Total number of entities matching the query."""

    page: int
    """Current page number (1-based)."""

    per_page: int
    """Number of items per page."""

    pages: int
    """Total number of pages available."""

class ReferenceListItem(BaseModel):
    """A single reference entry in the paginated reference list."""

    reference_id: str
    """Unique identifier of the reference."""

    reference_type: str
    """Type of the reference (espacio/tiempo/humanos/objetos)."""

    verbatim_text: str
    """Verbatim text span from the source document."""

    span_start: int | None = None
    """Character offset (0-based) where the verbatim span begins."""

    span_end: int | None = None
    """Character offset (exclusive) where the verbatim span ends."""

    page_number: int | None = None
    """1-based page number where this reference appears."""

    element_field: str | None = None
    """Specific event element this reference substantiates (v6.0)."""

    reference_index: int | None = None
    """Zero-based ordering within element_field group (v6.0)."""

    resolution_confidence: float | None = None
    """Confidence score for canonical entity resolution."""

    event_que_paso: str | None = None
    """The que_paso (what happened) from the linked event."""

    event_id: str | None = None
    """Unique identifier of the linked event."""

    document_filename: str | None = None
    """Filename of the source document."""

    document_id: str | None = None
    """Unique identifier of the source document."""

    canonical_entity_name: str | None = None
    """Name of the resolved canonical entity, if any."""

    canonical_entity_id: str | None = None
    """ID of the resolved canonical entity, if any."""

    canonical_entity_type: str | None = None
    """Type of the resolved canonical entity, if any."""


class ReferenceListResponse(BaseModel):
    """Paginated response body for ``GET /references``."""

    items: list[ReferenceListItem]
    """List of reference entries on the current page."""

    total: int
    """Total number of references matching the query."""

    page: int
    """Current page number (1-based)."""

    per_page: int
    """Number of items per page."""

    pages: int
    """Total number of pages available."""


class EventListItem(BaseModel):
    """A single event entry in the paginated event list."""

    event_id: str
    """Unique identifier of the event."""

    que_paso: str
    """Core narrative: what happened."""

    espacio: str | None = None
    """Location context (free-form)."""

    tiempo: str | None = None
    """Temporal context (free-form)."""

    humanos: str | None = None
    """People involved (free-form)."""

    objetos: str | None = None
    """Objects involved (free-form)."""

    time_window: dict | None = None
    """Structured time {start, end} as ISO 8601 datetimes (v6.0)."""

    location_point: dict | None = None
    """Geolocation {lat, lon, label} for map display (v6.0)."""

    location_place_name: str | None = None
    """Name of the canonical place entity linked to this event."""

    participant_count: int = 0
    """Number of participant edges linked to this event."""

    reference_count: int = 0
    """Number of references linked to this event."""

    document_id: str | None = None
    """ID of the source document."""

    document_filename: str | None = None
    """Filename of the source document."""

    extraction_confidence: float = 1.0
    """LLM extraction confidence."""

    created_at: str | None = None
    """ISO-8601 timestamp of event creation."""


class EventListResponse(BaseModel):
    """Paginated response body for ``GET /events``."""

    items: list[EventListItem]
    """List of event entries on the current page."""

    total: int
    """Total number of events matching the query."""

    page: int
    """Current page number (1-based)."""

    per_page: int
    """Number of items per page."""

    pages: int
    """Total number of pages available."""


class ProcessingLogListItem(BaseModel):
    """A single log entry in the paginated log list."""

    id: str
    """Deterministic log entry ID (SHA256 hex digest, first 16 chars)."""

    document_id: str
    """ID of the document this log entry belongs to."""

    step_name: str
    """Processing step that created this entry."""

    severity: str
    """Severity level: info, warning, or error."""

    message: str
    """Human-readable log message."""

    details: dict | None = None
    """Optional structured metadata attached to this entry."""

    created_at: str | None = None
    """ISO-8601 timestamp of when the log entry was created."""


class ProcessingLogListResponse(BaseModel):
    """Paginated response body for GET /documents/{id}/logs."""

    items: list[ProcessingLogListItem]
    """List of log entries on the current page."""

    total: int
    """Total number of log entries for this document."""

    page: int
    """Current page number (1-based)."""

    per_page: int
    """Number of items per page (fixed at 50)."""

    pages: int
    """Total number of pages available."""


class MergeRequest(BaseModel):
    """Request body for ``POST /entities/merge``.

    Merges one canonical entity (source) into another (target) of the same
    type. All references pointing to the source are re-pointed to the
    target, and the source is soft-deleted via ``superseded_by``.
    """

    source_id: str
    """Record ID (hex portion) of the source canonical entity to absorb."""

    target_id: str
    """Record ID (hex portion) of the target canonical entity (survivor)."""


class MergeResponse(BaseModel):
    """Response body for ``POST /entities/merge``."""

    success: bool = True
    """Whether the merge completed successfully."""

    message: str
    """Human-readable summary of the merge operation."""

    source_id: str
    """Record ID of the source entity that was absorbed."""

    target_id: str
    """Record ID of the target entity (survivor)."""

    rewired_count: int
    """Number of references that were re-pointed from source to target."""


class SplitPartition(BaseModel):
    """A single partition of references to split off into a new canonical entity."""

    new_entity_name: str
    """Name for the new canonical entity that will receive these references."""

    reference_ids: list[str]
    """List of reference record IDs (hex portions) to move to the new entity."""


class SplitRequest(BaseModel):
    """Request body for ``POST /entities/{entity_type}/{entity_id}/split``.

    Partitions one or more groups of references from a source canonical entity
    into new separate canonical entities.  Each partition creates one new entity.
    """

    partitions: list[SplitPartition]
    """One or more partitions of references to split into new entities."""


class SplitResponse(BaseModel):
    """Response body for ``POST /entities/{entity_type}/{entity_id}/split``."""

    success: bool = True
    """Whether the split completed successfully."""

    message: str
    """Human-readable summary of the split operation."""

    entity_type: str
    """Type of the entities involved (place/person/object)."""

    original_entity_id: str
    """Record ID of the original entity that was split."""

    new_entities: list[dict]
    """List of ``{name, entity_id}`` for each created entity."""

    partition_count: int
    """Number of partitions (new entities created)."""

    total_references_moved: int
    """Total number of references moved to new entities."""


class APIInfo(BaseModel):
    """Response body for ``GET /``."""

    name: str
    version: str
    description: str
    endpoints: dict[str, str]


# Re-export all models for convenience
__all__ = [
    "APIInfo",
    "DocumentCreated",
    "DocumentDeleted",
    "DocumentInput",
    "DocumentListItem",
    "DocumentListResponse",
    "DocumentStatus",
    "DocumentUploadCreated",
    "EntityDeleted",
    "EntityDetailReference",
    "EntityDetailResponse",
    "EntityListItem",
    "EntityListResponse",
    "EventListItem",
    "EventListResponse",
    "EventsCleared",

    "MergeRequest",
    "MergeResponse",
    "ProcessingLogListItem",
    "ProcessingLogListResponse",
    "ReferenceListItem",
    "ReferenceListResponse",
    "SplitPartition",
    "SplitRequest",
    "SplitResponse",
]
