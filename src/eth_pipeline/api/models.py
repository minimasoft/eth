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


class EventV2ListItem(BaseModel):
    """A single v7 event entry in the paginated event list."""

    event_id: str
    """Unique identifier of the event."""

    title: str
    """Event title from the structured event object."""

    description: str
    """Event description / narrative text."""

    time_start: str | None = None
    """Earliest temporal bound as ISO-8601 datetime (may be null for open intervals)."""

    time_end: str | None = None
    """Latest temporal bound as ISO-8601 datetime (may be null for open intervals)."""

    time_precision: str | None = None
    """Precision label for the time window (hour, day, month, year)."""

    location_name: str | None = None
    """Primary location name from the first linked event_location row."""

    participant_count: int = 0
    """Number of participant rows linked to this event."""

    reference_count: int = 0
    """Number of reference rows linked to this event."""

    document_id: str | None = None
    """ID of the source document."""

    document_filename: str | None = None
    """Filename of the source document."""

    extraction_confidence: float = 1.0
    """LLM extraction confidence score."""

    created_at: str | None = None
    """ISO-8601 timestamp of event creation."""


class EventListV2Response(BaseModel):
    """Paginated response body for ``GET /api/v2/events``."""

    items: list[EventV2ListItem]
    """List of v7 event entries on the current page."""

    total: int
    """Total number of events matching the query."""

    page: int
    """Current page number (1-based)."""

    per_page: int
    """Number of items per page."""

    pages: int
    """Total number of pages available."""


class EventLocationDetail(BaseModel):
    """A location entry within an event detail response."""

    location_id: str
    """Unique identifier of the event_location row."""

    name: str
    """Location name."""

    location_type: str | None = None
    """Type of location (place, region, etc.)."""

    geom: str | None = None
    """EWKT geometry string for PostGIS display."""


class EventParticipantDetail(BaseModel):
    """A participant entry within an event detail response."""

    participant_id: str
    """Unique identifier of the event_participant_v2 row."""

    name: str
    """Participant name."""

    role: str = ""
    """Participant role (default empty string)."""

    confidence: float | None = None
    """LLM extraction confidence for this participant."""


class EventRefDetail(BaseModel):
    """A reference entry within an event detail response."""

    reference_id: str
    """Unique identifier of the event_ref row."""

    reference_type: str
    """Category of the reference (e.g., location, participant)."""

    verbatim_text: str
    """Verbatim text span from the source document."""

    span_start: int | None = None
    """Character offset (0-based) where the verbatim span begins."""

    span_end: int | None = None
    """Character offset (exclusive) where the verbatim span ends."""

    chunk_index: int | None = None
    """Index of the chunk this reference belongs to."""


class EventV2DetailResponse(BaseModel):
    """Response body for ``GET /api/v2/events/{event_id}``."""

    event_id: str
    """Unique identifier of the event."""

    title: str
    """Event title from the structured event object."""

    description: str
    """Event description / narrative text."""

    time_start: str | None = None
    """Earliest temporal bound as ISO-8601 datetime."""

    time_end: str | None = None
    """Latest temporal bound as ISO-8601 datetime."""

    time_precision: str | None = None
    """Precision label for the time window."""

    extraction_confidence: float = 1.0
    """LLM extraction confidence score."""

    document_id: str | None = None
    """ID of the source document."""

    document_filename: str | None = None
    """Filename of the source document."""

    locations: list[EventLocationDetail]
    """Linked location entries for this event."""

    participants: list[EventParticipantDetail]
    """Linked participant entries for this event."""

    references: list[EventRefDetail]
    """Linked reference entries for this event."""

    created_at: str | None = None
    """ISO-8601 timestamp of event creation."""

    updated_at: str | None = None
    """ISO-8601 timestamp of last event update."""


class ChunkTextResponse(BaseModel):
    """Response body for ``GET /api/v2/chunks/{document_id}/{part_index}``."""

    document_id: str
    """ID of the source document."""

    part_index: int
    """Zero-based chunk part index."""

    text: str
    """Full text content of the chunk."""

    offset_start: int
    """Character offset (0-based) where the chunk starts in the full document text."""

    offset_end: int
    """Character offset (exclusive) where the chunk ends in the full document text."""

    chunk_offset_start: int
    """Character offset within the chunk's text (for reference highlighting)."""

    chunk_offset_end: int
    """Character offset within the chunk's text (for reference highlighting)."""


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


class LlmCallLogListItem(BaseModel):
    """A single LLM call log entry in the paginated call log list."""

    id: str
    """Unique identifier of the LLM call log record."""

    document_id: str
    """ID of the document this LLM call belongs to."""

    prompt_text: str | None = None
    """Full LLM prompt text sent to the model."""

    response_text: str | None = None
    """Full LLM response text received from the model."""

    prompt_tokens: int | None = None
    """Number of prompt (input) tokens."""

    completion_tokens: int | None = None
    """Number of completion (output) tokens."""

    total_tokens: int | None = None
    """Total tokens (prompt + completion)."""

    cached_tokens: int | None = None
    """Tokens served from cache (when reported by provider)."""

    cost: float | None = None
    """Estimated monetary cost in USD (when reported by OpenRouter)."""

    duration_ms: int | None = None
    """Wall-clock HTTP request duration in milliseconds."""

    model: str | None = None
    """Model identifier as returned by OpenRouter."""

    activity_type: str | None = None
    """Activity type label (extract_events, resolve_entities, etc.)."""

    timestamp: str | None = None
    """ISO-8601 timestamp of when the LLM call was recorded."""


class LlmCallLogListResponse(BaseModel):
    """Paginated response body for GET /documents/{id}/llm-calls."""

    items: list[LlmCallLogListItem]
    """List of LLM call log entries on the current page."""

    total: int
    """Total number of LLM call log entries for this document."""

    page: int
    """Current page number (1-based)."""

    per_page: int
    """Number of items per page."""

    pages: int
    """Total number of pages available."""


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
    "EventsCleared",
    "ChunkTextResponse",
    "EventLocationDetail",
    "EventListV2Response",
    "EventParticipantDetail",
    "EventRefDetail",
    "EventV2DetailResponse",
    "EventV2ListItem",

    "LlmCallLogListItem",
    "LlmCallLogListResponse",
    "ProcessingLogListItem",
    "ProcessingLogListResponse",
]
