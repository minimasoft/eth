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

    provider_id: str | None = None
    """Optional llm_provider id to process this document (defaults to env default)."""

    llm_mode: str = "thinking"
    """LLM sampling mode for extraction: 'thinking' (default) or 'instruct'."""


class DocumentCreated(BaseModel):
    """Response body for a successful ``POST /documents`` (HTTP 201)."""

    document_id: str
    """Unique identifier for the created document."""

    status: str = "pending"
    """Initial lifecycle status of the document."""

    source_id: str | None = None
    """Source group this document belongs to (single-document uploads own theirs)."""


class DocumentUploadCreated(BaseModel):
    """Response body for a successful ``POST /documents/upload`` (HTTP 201)."""

    document_id: str
    """Unique identifier of the first created document row."""

    status: str = "pending"
    """Initial lifecycle status of the document rows."""

    document_ids: list[str] = []
    """All document rows created by the provider fan-out."""

    source_id: str | None = None
    """Shared source group id linking every fan-out sibling row."""


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

    provider_id: str | None = None
    """ID of the llm_provider used to process this document (None for legacy)."""

    provider_name: str | None = None
    """Display name of the provider used to process this document."""

    model: str | None = None
    """Model identifier used to process this document."""

    source_id: str | None = None
    """Source group shared by fan-out siblings of the same upload."""


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

    chunk_count: int = 0
    """Number of text chunks created from this document."""

    text_word_count: int = 0
    """Word count of the document's extracted text content."""

    event_count: int = 0
    """Total number of v7 events linked to this document."""

    reference_count: int = 0
    """Total number of verbatim references linked to this document via events."""

    entity_count: int = 0
    """Total number of distinct canonical entities linked to this document's references."""

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

    # Per-document LLM provider attribution
    provider_id: str | None = None
    """ID of the llm_provider used to process this document (None for legacy)."""

    provider_name: str | None = None
    """Display name of the provider used to process this document."""

    model: str | None = None
    """Model identifier used to process this document."""

    source_id: str | None = None
    """Source group shared by fan-out siblings of the same upload."""

    model_count: int = 1
    """Number of document rows (models) sharing this source group."""


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

    provider_id: str | None = None
    """ID of the llm_provider that extracted this event."""

    provider_name: str | None = None
    """Display name of the provider that extracted this event."""

    model: str | None = None
    """Model identifier that extracted this event."""

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

    lat: float | None = None
    """WGS84 latitude anchor for the map view (set by geocoding)."""

    lon: float | None = None
    """WGS84 longitude anchor for the map view (set by geocoding)."""


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

    provider_id: str | None = None
    """ID of the llm_provider that extracted this event."""

    provider_name: str | None = None
    """Display name of the provider that extracted this event."""

    model: str | None = None
    """Model identifier that extracted this event."""

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


class ModelColorItem(BaseModel):
    """A model string with its timeline palette index."""

    model: str
    """Model identifier as stored on event_v2 rows (e.g. 'glm-5.3-flash')."""

    color_index: int | None = None
    """Index into the fixed tableau20 palette (None when no provider/color is linked)."""


class ModelColorsResponse(BaseModel):
    """Response body for ``GET /events/colors``."""

    colors: list[ModelColorItem]
    """Distinct model strings seen on events, each with its DB color index."""


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


# =======================================================================
# LLM Provider models
# =======================================================================


class ProviderItem(BaseModel):
    """A single LLM provider (API key redacted)."""

    id: str
    name: str
    model: str
    base_url: str
    is_default: bool = False
    api_key_masked: str | None = None
    instruct_temperature: float | None = None
    """Instruct-mode sampling temperature override (None = module default)."""
    instruct_top_p: float | None = None
    """Instruct-mode top_p override (None = module default)."""
    instruct_top_k: int | None = None
    """Instruct-mode top_k override (None = module default)."""
    created_at: object | None = None


class ProviderItemList(BaseModel):
    """Response body for ``GET /api/providers``."""

    items: list[ProviderItem]


class ProviderCreate(BaseModel):
    """Request body for ``POST /api/providers``."""

    name: str
    model: str
    base_url: str | None = None
    api_key: str | None = None
    instruct_temperature: float | None = None
    """Optional instruct-mode sampling temperature (0–2; blank = module default)."""
    instruct_top_p: float | None = None
    """Optional instruct-mode top_p (0–1; blank = module default)."""
    instruct_top_k: int | None = None
    """Optional instruct-mode top_k (>= 1; blank = module default)."""


class ProviderTestResult(BaseModel):
    """Response body for ``POST /api/providers/{id}/test``."""

    ok: bool
    answer: str = ""
    normalized: str = ""
    expected: str = ""
    model: str = ""
    error: str | None = None
    provider_id: str = ""


# =======================================================================
# Cross-model comparison models
# =======================================================================


class ComparisonDocument(BaseModel):
    """A document row participating in a cross-model comparison."""

    document_id: str
    """Unique identifier of the document row."""

    filename: str
    """Original filename of the document."""

    status: str
    """Processing status of the document row."""

    provider_id: str | None = None
    """ID of the provider assigned to this row."""

    provider_name: str | None = None
    """Display name of the provider assigned to this row."""

    model: str | None = None
    """Model assigned to this row."""

    event_count: int = 0
    """Number of events extracted by this row's model."""


class ComparisonEvent(BaseModel):
    """An event entry in a cross-model comparison, with source footprint."""

    event_id: str
    """Unique identifier of the event."""

    document_id: str
    """Document row (model run) this event came from."""

    model: str | None = None
    """Model that extracted this event."""

    provider_name: str | None = None
    """Display name of the provider that extracted this event."""

    title: str
    """Event title."""

    description: str = ""
    """Event description."""

    time_start: str | None = None
    """Earliest temporal bound as ISO-8601 datetime."""

    time_end: str | None = None
    """Latest temporal bound as ISO-8601 datetime."""

    location_name: str | None = None
    """Primary location name."""

    participant_count: int = 0
    """Number of participants."""

    reference_count: int = 0
    """Number of verbatim references."""

    chunk_index: int | None = None
    """Primary source chunk this event was extracted from."""

    span_start: int | None = None
    """Document-absolute start of the event's reference footprint."""

    span_end: int | None = None
    """Document-absolute end of the event's reference footprint."""


class ComparisonResponse(BaseModel):
    """Response body for ``GET /comparisons/{source_id}``."""

    source_id: str
    """The compared source group."""

    filename: str | None = None
    """Filename of the underlying uploaded document."""

    documents: list[ComparisonDocument]
    """One entry per model run (document row) of this source."""

    events: list[ComparisonEvent]
    """All events across every model run of this source."""


# =======================================================================
# Map / geo models
# =======================================================================


class GeoEventItem(BaseModel):
    """A single geolocated event-location pair for the map view."""

    event_id: str
    """Unique identifier of the event."""

    title: str
    """Event title from the structured event object."""

    time_start: str | None = None
    """Earliest temporal bound as ISO-8601 datetime (may be null for open intervals)."""

    time_end: str | None = None
    """Latest temporal bound as ISO-8601 datetime (may be null for open intervals)."""

    time_precision: str | None = None
    """Precision label for the time window (hour, day, month, year)."""

    lat: float
    """WGS84 latitude of the location (always present — only geolocated rows are returned)."""

    lon: float
    """WGS84 longitude of the location (always present — only geolocated rows are returned)."""

    location_id: str
    """Unique identifier of the event_location row."""

    location_name: str
    """Location name as extracted from the document."""

    location_type: str | None = None
    """Type of location (place, region, etc.)."""

    document_id: str | None = None
    """ID of the source document."""

    document_filename: str | None = None
    """Filename of the source document."""


class GeoEventsResponse(BaseModel):
    """Response body for ``GET /geo/events``."""

    total: int
    """Number of items returned (already capped by the limit parameter)."""

    items: list[GeoEventItem]
    """List of geolocated event-location pairs."""


# Re-export all models for convenience
__all__ = [
    "APIInfo",
    "ComparisonDocument",
    "ComparisonEvent",
    "ComparisonResponse",
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
    "GeoEventItem",
    "GeoEventsResponse",

    "LlmCallLogListItem",
    "LlmCallLogListResponse",
    "ModelColorItem",
    "ModelColorsResponse",
    "ProcessingLogListItem",
    "ProcessingLogListResponse",

    "ProviderItem",
    "ProviderItemList",
    "ProviderCreate",
    "ProviderTestResult",
]
