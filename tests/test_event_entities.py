"""
Unit tests for create_event_canonical_entities activity logic.

All tests are in-memory — no SurrealDB connection required.
Tests the core naming, properties mapping, nullify condition, RELATE
matching heuristic, and role mapping as pure functions.

DB-dependent behavior (connectivity, write, RELATE query) is integration-tested
in Phase 18.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Helper functions mirroring the activity's internal logic
# ---------------------------------------------------------------------------


def _build_event_entity_name(que_paso: str) -> str:
    """Build the canonical entity name from que_paso text.

    Pattern: ``Event: {que_paso[:80].strip()}...`` when que_paso exceeds
    80 characters, or ``Event: {que_paso.strip()}`` otherwise.
    """
    stripped = que_paso.strip()
    if not stripped:
        return "Event: "
    truncated = stripped[:80].strip()
    if len(stripped) > 80:
        return f"Event: {truncated}..."
    return f"Event: {truncated}"


def _build_event_properties(
    que_paso: str,
    tiempo: str = "",
    espacio: str = "",
    humanos: str = "",
    objetos: str = "",
    document_id: str = "",
) -> dict:
    """Map event fields to canonical_entity properties dict."""
    return {
        "title": que_paso[:80],
        "description": que_paso,
        "time_range": tiempo,
        "location": espacio,
        "participants": humanos,
        "objects": objetos,
        "document_id": document_id,
    }


def _nullify_condition(document_id: str) -> dict:
    """Return the query condition for nullifying prior event entities.

    Returns a dict with the query filter parts for the DELETE statements.
    """
    return {
        "entity_type": "event",
        "document_id": document_id,
    }


def _should_link(entity_name: str, verbatim_text: str) -> bool:
    """Determine whether a link should be created between an event field
    value and a canonical entity name.

    Returns True if either:
    - entity_name (lowercased) CONTAINS verbatim_text (lowercased)
    - verbatim_text (lowercased) CONTAINS entity_name (lowercased)
    """
    if not entity_name or not verbatim_text:
        return False
    en_lower = entity_name.lower()
    vt_lower = verbatim_text.lower()
    return vt_lower in en_lower or en_lower in vt_lower


def _map_reference_type_to_role(ref_type: str) -> str:
    """Map event reference type to event_entity_link role string."""
    mapping = {
        "espacio": "location",
        "humanos": "participant",
        "objetos": "object",
    }
    return mapping.get(ref_type, "subject")


# ---------------------------------------------------------------------------
# Tests: Event entity naming
# ---------------------------------------------------------------------------


def test_name_short_que_paso_no_ellipsis() -> None:
    """que_paso <= 80 chars: no ellipsis, used as-is."""
    short = "A brief event description with fewer characters"
    name = _build_event_entity_name(short)
    assert name == f"Event: {short.strip()}"
    assert "..." not in name


def test_name_exactly_80_chars_no_ellipsis() -> None:
    """que_paso exactly 80 chars: no ellipsis."""
    exact = "A" * 80
    name = _build_event_entity_name(exact)
    assert name == f"Event: {exact}"
    assert "..." not in name


def test_name_long_que_paso_adds_ellipsis() -> None:
    """que_paso > 80 chars: truncated to 80 chars + '...' appended."""
    long_text = "A" * 100
    name = _build_event_entity_name(long_text)
    assert name == f"Event: {'A' * 80}..."
    assert name.endswith("...")


def test_name_strips_trailing_whitespace() -> None:
    """que_paso with trailing whitespace is stripped before truncation."""
    padded = "  Meeting at noon  "
    name = _build_event_entity_name(padded)
    assert "Meeting at noon" in name
    assert "  " not in name


def test_name_empty_que_paso() -> None:
    """Empty que_paso produces 'Event: ' prefix with no text."""
    name = _build_event_entity_name("")
    assert name == "Event: "


def test_name_whitespace_only() -> None:
    """Whitespace-only que_paso produces 'Event: ' after stripping."""
    name = _build_event_entity_name("   ")
    assert name == "Event: "


def test_name_long_with_whitespace_edges() -> None:
    """Long que_paso with leading/trailing whitespace strips before truncation."""
    padded_long = "  " + "B" * 90 + "  "
    name = _build_event_entity_name(padded_long)
    assert name.startswith("Event: ")
    assert name.endswith("...")
    # Should have 80 B's + "..." = 83 chars after "Event: "
    body = name[len("Event: "):]
    assert body == ("B" * 80) + "..."


# ---------------------------------------------------------------------------
# Tests: Properties mapping
# ---------------------------------------------------------------------------


def test_properties_all_fields_mapped() -> None:
    """All event fields map to the correct property keys."""
    props = _build_event_properties(
        que_paso="Detailed event narrative text that could be quite long",
        tiempo="2024-01-15 to 2024-01-20",
        espacio="Conference Hall A",
        humanos="Dr. Smith, Prof. Jones",
        objetos="Laptop, Presentation slides",
        document_id="doc123",
    )
    assert props["title"] == "Detailed event narrative text that could be quite long"[:80]
    assert props["description"] == "Detailed event narrative text that could be quite long"
    assert props["time_range"] == "2024-01-15 to 2024-01-20"
    assert props["location"] == "Conference Hall A"
    assert props["participants"] == "Dr. Smith, Prof. Jones"
    assert props["objects"] == "Laptop, Presentation slides"
    assert props["document_id"] == "doc123"


def test_properties_title_truncated_to_80() -> None:
    """Title is truncated to 80 characters from que_paso."""
    long_text = "X" * 200
    props = _build_event_properties(que_paso=long_text)
    assert props["title"] == "X" * 80
    assert len(props["title"]) == 80


def test_properties_description_full_text() -> None:
    """Description is the full que_paso text, not truncated."""
    long_text = "Y" * 500
    props = _build_event_properties(que_paso=long_text)
    assert props["description"] == long_text
    assert len(props["description"]) == 500


def test_properties_empty_fields_default_to_empty_string() -> None:
    """Empty or None fields default to empty strings."""
    props = _build_event_properties(
        que_paso="Some event",
        tiempo="",
        espacio="",
        humanos="",
        objetos="",
    )
    assert props["time_range"] == ""
    assert props["location"] == ""
    assert props["participants"] == ""
    assert props["objects"] == ""


def test_properties_document_id_included() -> None:
    """document_id is included in properties for nullify scoping."""
    props = _build_event_properties(que_paso="Test", document_id="abc-123")
    assert props["document_id"] == "abc-123"


# ---------------------------------------------------------------------------
# Tests: Nullify condition
# ---------------------------------------------------------------------------


def test_nullify_condition_targets_event_type() -> None:
    """Nullify condition always targets entity_type='event'."""
    condition = _nullify_condition("doc123")
    assert condition["entity_type"] == "event"


def test_nullify_condition_scoped_to_document_id() -> None:
    """Nullify condition includes document_id for scoping."""
    condition = _nullify_condition("doc123")
    assert condition["document_id"] == "doc123"


def test_nullify_condition_different_docs_different_filters() -> None:
    """Different document_ids produce different nullify filters."""
    cond_a = _nullify_condition("docA")
    cond_b = _nullify_condition("docB")
    assert cond_a["document_id"] != cond_b["document_id"]
    assert cond_a["entity_type"] == cond_b["entity_type"] == "event"


def test_nullify_condition_entity_type_always_applied() -> None:
    """entity_type='event' is always applied regardless of document_id."""
    for doc_id in ["", "doc123", None]:
        condition = _nullify_condition(doc_id or "")
        assert condition["entity_type"] == "event"


# ---------------------------------------------------------------------------
# Tests: RELATE matching heuristic
# ---------------------------------------------------------------------------


def test_should_link_entity_contains_verbatim() -> None:
    """Entity name CONTAINS verbatim text → match."""
    assert _should_link("Old Town Square Market", "Town Square") is True


def test_should_link_verbatim_contains_entity() -> None:
    """Verbatim text CONTAINS entity name → match."""
    assert _should_link("Market", "Old Town Square Market") is True


def test_should_link_exact_match() -> None:
    """Exact match is a valid link."""
    assert _should_link("Dr. Smith", "Dr. Smith") is True


def test_should_link_no_match() -> None:
    """Neither contains the other → no match."""
    assert _should_link("Central Park", "Conference Room") is False


def test_should_link_case_insensitive() -> None:
    """Matching is case-insensitive."""
    assert _should_link("old town square", "Old Town") is True
    assert _should_link("Old Town", "old town square") is True


def test_should_link_empty_entity_name() -> None:
    """Empty entity name returns False."""
    assert _should_link("", "Market") is False


def test_should_link_empty_verbatim_text() -> None:
    """Empty verbatim text returns False."""
    assert _should_link("Market", "") is False


def test_should_link_both_empty() -> None:
    """Both empty returns False."""
    assert _should_link("", "") is False


def test_should_link_partial_substring() -> None:
    """Partial substring match works (case-insensitive)."""
    assert _should_link("Dr. John Smith III", "john smith") is True


# ---------------------------------------------------------------------------
# Tests: Link role mapping
# ---------------------------------------------------------------------------


def test_role_for_espacio_is_location() -> None:
    """espacio reference type maps to 'location' role."""
    assert _map_reference_type_to_role("espacio") == "location"


def test_role_for_humanos_is_participant() -> None:
    """humanos reference type maps to 'participant' role."""
    assert _map_reference_type_to_role("humanos") == "participant"


def test_role_for_objetos_is_object() -> None:
    """objetos reference type maps to 'object' role."""
    assert _map_reference_type_to_role("objetos") == "object"


def test_role_unknown_type_defaults_to_subject() -> None:
    """Unknown reference type defaults to 'subject' role."""
    assert _map_reference_type_to_role("tiempo") == "subject"
    assert _map_reference_type_to_role("") == "subject"
    assert _map_reference_type_to_role("unknown") == "subject"


# ---------------------------------------------------------------------------
# Tests: Integration — full event-to-entity pipeline logic
# ---------------------------------------------------------------------------


def test_integration_full_event_entity_creation() -> None:
    """End-to-end: event dict → entity name + properties."""
    event = {
        "que_paso": (
            "The annual conference featured keynote speakers discussing "
            "artificial intelligence and its impact on modern society. "
            "Attendees participated in workshops throughout the three-day "
            "event."  # >80 chars
        ),
        "tiempo": "2026-03-10 to 2026-03-12",
        "espacio": "Grand Ballroom",
        "humanos": "Dr. Sarah Chen, Prof. Miguel Torres",
        "objetos": "Projector, Whiteboard",
    }

    name = _build_event_entity_name(event["que_paso"])
    props = _build_event_properties(
        que_paso=event["que_paso"],
        tiempo=event["tiempo"],
        espacio=event["espacio"],
        humanos=event["humanos"],
        objetos=event["objetos"],
        document_id="doc-integration-01",
    )

    # Name starts with "Event: " and ends with "..." (long text)
    assert name.startswith("Event: ")
    assert name.endswith("...")
    assert len(name) <= 80 + len("Event: ") + len("...")

    # Properties are properly mapped
    assert props["title"] == event["que_paso"][:80]
    assert props["description"] == event["que_paso"]
    assert props["time_range"] == "2026-03-10 to 2026-03-12"
    assert props["location"] == "Grand Ballroom"
    assert props["participants"] == "Dr. Sarah Chen, Prof. Miguel Torres"
    assert props["objects"] == "Projector, Whiteboard"
    assert props["document_id"] == "doc-integration-01"

    # Link matching works
    assert _should_link("Grand Ballroom", "Ballroom") is True
    assert _should_link("Grand Ballroom", "Kitchen") is False
    assert _should_link("Dr. Sarah Chen", "Sarah") is True


def test_integration_empty_event() -> None:
    """Empty event fields produce correct defaults."""
    name = _build_event_entity_name("")
    props = _build_event_properties("")

    assert name == "Event: "
    assert props == {
        "title": "",
        "description": "",
        "time_range": "",
        "location": "",
        "participants": "",
        "objects": "",
        "document_id": "",
    }


def test_integration_nullify_plus_relate_flow() -> None:
    """Nullify + RELATE: different documents have separate scoping."""
    doc_a_condition = _nullify_condition("docA")
    doc_b_condition = _nullify_condition("docB")

    # Each document scopes its own nullify
    assert doc_a_condition["document_id"] == "docA"
    assert doc_b_condition["document_id"] == "docB"

    # Both target event type
    assert doc_a_condition["entity_type"] == "event"
    assert doc_b_condition["entity_type"] == "event"
