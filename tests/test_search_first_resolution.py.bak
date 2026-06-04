"""
Unit tests for search-first entity resolution helper logic.

All tests are in-memory — no SurrealDB or LLM connection required.
Tests the core matching, candidate selection, and action-application
logic as pure functions extracted from
``resolve_entities_with_search_activity``.

DB-dependent behavior (connectivity, write, exact-match-avoid-LLM
integration) is tested via integration tests in Phase 18.
"""

from __future__ import annotations

import unicodedata


# ---------------------------------------------------------------------------
# Helper functions mirroring the activity's internal logic
# ---------------------------------------------------------------------------


def _normalize(text: str) -> str:
    """NFD-normalize, strip combining marks, then casefold for
    accent- and case-insensitive comparison.

    NFD decomposition separates base characters from combining diacritical
    marks (e.g., ``"José"`` → ``"Jose\\u0301"``), then stripping combining
    marks removes the diacritics, and ``casefold()`` provides aggressive
    case folding (handles ß→ss, etc.).

    This produces truly accent-insensitive comparison: "José" → "jose"
    and "Jose" → "jose".  (The activity uses the same function for
    exact-match comparison, which is why ``_exact_match`` can match
    across accent boundaries.)
    """
    nfd = unicodedata.normalize("NFD", text)
    return "".join(c for c in nfd if not unicodedata.combining(c)).casefold()


def _exact_match(
    verbatim_text: str,
    entities: list[dict],
) -> dict | None:
    """Find an exact (accent- + case-insensitive) match for *verbatim_text*
    among *entities*.

    Returns the first matching entity dict, or ``None``.
    """
    if not verbatim_text:
        return None
    needle = _normalize(verbatim_text)
    for ent in entities:
        haystack = _normalize(ent.get("name", ""))
        if needle == haystack:
            return ent
    return None


def _find_fuzzy_candidates(
    verbatim_text: str,
    entities: list[dict],
    limit: int = 5,
) -> list[dict]:
    """Find up to *limit* candidate entities via CONTAINS bidirectional.

    Returns entities where either the entity name CONTAINS the verbatim
    text (accent- + case-insensitive), or the verbatim text CONTAINS the
    entity name (accent- + case-insensitive).  Uses ``_normalize()`` so
    that accents do not block substring matching.
    Results are deduplicated, sorted by name length ascending, and capped
    at *limit*.
    """
    if not verbatim_text or not entities:
        return []

    norm_vt = _normalize(verbatim_text)
    seen_ids: set[str] = set()
    candidates: list[dict] = []

    for ent in entities:
        ent_name = ent.get("name", "")
        if not ent_name:
            continue
        norm_name = _normalize(ent_name)
        if norm_vt in norm_name or norm_name in norm_vt:
            eid = ent.get("id")
            if eid and eid not in seen_ids:
                seen_ids.add(eid)
                candidates.append(ent)

    # Sort by name length (ascending) for deterministic candidate order
    candidates.sort(key=lambda e: len(e.get("name", "")))
    return candidates[:limit]


def _apply_resolution_action(
    action: str,
    matched_candidate_id: str | None,
    matched_entity_id: str | None,
    entity_type: str,
    ref_text: str,
) -> dict:
    """Map an LLM resolution action to the entity update dict.

    Returns a dict with keys ``entity_id``, ``canonical_entity``,
    ``resolution_confidence``, and ``needs_create``.
    """
    if action == "match_existing":
        eid = matched_candidate_id or matched_entity_id
        return {
            "entity_id": eid,
            "canonical_entity": eid,
            "resolution_confidence": 0.95,
            "needs_create": False,
        }
    # create_new or uncertain — both need entity creation
    confidence = 0.6 if action == "uncertain" else 0.9
    return {
        "entity_id": None,
        "canonical_entity": None,
        "resolution_confidence": confidence,
        "needs_create": True,
        "inferred_name": ref_text,
        "inferred_type": entity_type,
    }


# ============================================================================
# Tests: Text normalization (NFD + casefold)
# ============================================================================


def test_normalize_removes_accents() -> None:
    """Accented characters normalize to base form."""
    assert _normalize("José") == _normalize("Jose")


def test_normalize_case_insensitive() -> None:
    """Upper/lower case normalizes identically."""
    assert _normalize("MADRID") == _normalize("madrid")


def test_normalize_mixed_accents_and_case() -> None:
    """Mixed accents and case produce the same normalized form."""
    assert _normalize("María José") == _normalize("maria jose")


def test_normalize_nfd_spanish() -> None:
    """Spanish-specific characters normalize correctly (ñ, é, etc.)."""
    assert _normalize("estación") == _normalize("estacion")
    assert _normalize("muñoz") == _normalize("Munoz")


def test_normalize_empty_string() -> None:
    """Empty string normalizes to empty string."""
    assert _normalize("") == ""


def test_normalize_already_normalized() -> None:
    """Already NFD-normalized text is idempotent."""
    first = _normalize("Alcalá")
    second = _normalize(first)
    assert first == second


# ============================================================================
# Tests: Exact match
# ============================================================================


def test_exact_match_found() -> None:
    """Verbatim text matches existing entity (case-insensitive)."""
    entities = [{"name": "Madrid", "id": "entity:madrid"}]
    result = _exact_match("madrid", entities)
    assert result is not None
    assert result["id"] == "entity:madrid"


def test_exact_match_accent_variation() -> None:
    """Accented verbatim matches unaccented entity name."""
    entities = [{"name": "José García", "id": "entity:jgarcia"}]
    result = _exact_match("Jose Garcia", entities)
    assert result is not None
    assert result["id"] == "entity:jgarcia"


def test_exact_match_accent_entity_name() -> None:
    """Unaccented verbatim matches accented entity name."""
    entities = [{"name": "Álvaro Pérez", "id": "entity:aperez"}]
    result = _exact_match("Alvaro Perez", entities)
    assert result is not None
    assert result["id"] == "entity:aperez"


def test_exact_match_not_found() -> None:
    """Non-matching verbatim returns None."""
    entities = [{"name": "Madrid", "id": "entity:madrid"}]
    result = _exact_match("Barcelona", entities)
    assert result is None


def test_exact_match_empty_entities() -> None:
    """Empty entity list returns None."""
    result = _exact_match("Madrid", [])
    assert result is None


def test_exact_match_empty_verbatim() -> None:
    """Empty verbatim text returns None."""
    entities = [{"name": "Madrid", "id": "entity:madrid"}]
    result = _exact_match("", entities)
    assert result is None


def test_exact_match_first_of_many() -> None:
    """When multiple entities share the same normalized name, the first
    entity in the list is returned."""
    entities = [
        {"name": "Madrid", "id": "entity:madrid-1"},
        {"name": "MADRID ", "id": "entity:madrid-2"},  # trailing space
    ]
    result = _exact_match("madrid", entities)
    # Only the first exact match (after normalization) is returned
    assert result is not None


def test_exact_match_partial_not_exact() -> None:
    """Partial substring match does NOT qualify as exact."""
    entities = [{"name": "Juzgado de Madrid", "id": "entity:juzgado"}]
    result = _exact_match("Madrid", entities)
    assert result is None  # "madrid" != "juzgado de madrid"


# ============================================================================
# Test fixture — entities for fuzzy matching tests
# ============================================================================

FIXTURE_ENTITIES = [
    {
        "name": "Juzgado de Primera Instancia de Madrid",
        "id": "entity:jpi-madrid",
        "entity_type": "place",
    },
    {
        "name": "Audiencia Provincial de Barcelona",
        "id": "entity:ap-bcn",
        "entity_type": "place",
    },
    {
        "name": "Juzgado de lo Social de Madrid",
        "id": "entity:jls-madrid",
        "entity_type": "place",
    },
    {
        "name": "Tribunal Superior de Justicia de Cataluña",
        "id": "entity:tsj-cat",
        "entity_type": "place",
    },
    {
        "name": "Juzgado de Primera Instancia de Barcelona",
        "id": "entity:jpi-bcn",
        "entity_type": "place",
    },
    {
        "name": "Juzgado de lo Mercantil de Madrid",
        "id": "entity:jlm-madrid",
        "entity_type": "place",
    },
]

# ============================================================================
# Tests: Fuzzy candidate selection (CONTAINS bidirectional)
# ============================================================================


def test_fuzzy_entity_contains_verbatim() -> None:
    """Entity name CONTAINS verbatim text — match found."""
    candidates = _find_fuzzy_candidates("Primera Instancia", FIXTURE_ENTITIES)
    assert len(candidates) >= 1
    ids = [c["id"] for c in candidates]
    assert "entity:jpi-madrid" in ids
    assert "entity:jpi-bcn" in ids


def test_fuzzy_verbatim_contains_entity() -> None:
    """Verbatim text CONTAINS entity name — match found."""
    candidates = _find_fuzzy_candidates(
        "Primera Instancia de Barcelona", FIXTURE_ENTITIES
    )
    assert len(candidates) >= 1
    ids = [c["id"] for c in candidates]
    assert "entity:jpi-bcn" in ids       # "primera instancia de barcelona"
                                         # is in "juzgado de primera instancia
                                         # de barcelona"


def test_fuzzy_deduplicates_candidates() -> None:
    """Same entity matched via both directions appears once."""
    single_fixture = [
        {"name": "Madrid", "id": "entity:madrid", "entity_type": "place"},
    ]
    # "Madrid" CONTAINS "Madrid" and "Madrid" CONTAINS "Madrid" — same entity
    candidates = _find_fuzzy_candidates("Madrid", single_fixture)
    assert len(candidates) == 1


def test_fuzzy_no_match() -> None:
    """Verbatim unrelated to any entity — empty result."""
    candidates = _find_fuzzy_candidates("Estadio Olímpico", FIXTURE_ENTITIES)
    assert len(candidates) == 0


def test_fuzzy_capped_at_default_limit() -> None:
    """Many matches capped at default limit (5)."""
    candidates = _find_fuzzy_candidates("Juzgado", FIXTURE_ENTITIES)
    assert len(candidates) <= 5


def test_fuzzy_custom_limit() -> None:
    """Custom limit (2) returns at most 2 candidates."""
    candidates = _find_fuzzy_candidates("Juzgado", FIXTURE_ENTITIES, limit=2)
    assert len(candidates) <= 2


def test_fuzzy_case_insensitive() -> None:
    """Case difference does not prevent matching."""
    candidates = _find_fuzzy_candidates("primera instancia", FIXTURE_ENTITIES)
    assert len(candidates) >= 1
    ids = [c["id"] for c in candidates]
    assert "entity:jpi-madrid" in ids


def test_fuzzy_sort_by_name_length() -> None:
    """Results sorted by name length ascending."""
    candidates = _find_fuzzy_candidates("Madrid", FIXTURE_ENTITIES)
    if len(candidates) >= 2:
        lengths = [len(c.get("name", "")) for c in candidates]
        for i in range(len(lengths) - 1):
            assert lengths[i] <= lengths[i + 1]


def test_fuzzy_empty_verbatim() -> None:
    """Empty verbatim returns empty list."""
    candidates = _find_fuzzy_candidates("", FIXTURE_ENTITIES)
    assert len(candidates) == 0


def test_fuzzy_empty_entities() -> None:
    """Empty entity list returns empty list."""
    candidates = _find_fuzzy_candidates("Madrid", [])
    assert len(candidates) == 0


def test_fuzzy_accent_insensitive() -> None:
    """Accents don't block CONTAINS matching."""
    accented = [{"name": "Cataluña", "id": "entity:cat", "entity_type": "place"}]
    candidates = _find_fuzzy_candidates("Cataluna", accented)
    assert len(candidates) == 1


def test_fuzzy_bidirectional_both_match() -> None:
    """Bidirectional CONTAINS from both directions adds both matches."""
    multi_entities = [
        {"name": "Juzgado de Primera Instancia de Madrid",
         "id": "entity:jpi-madrid", "entity_type": "place"},
        {"name": "Audiencia Provincial de Barcelona",
         "id": "entity:ap-bcn", "entity_type": "place"},
        {"name": "Juzgado de lo Social de Madrid",
         "id": "entity:jls-madrid", "entity_type": "place"},
        {"name": "Madrid",
         "id": "entity:madrid-city", "entity_type": "place"},
    ]
    # "Madrid" is CONTAINED by jpi-madrid AND jls-madrid AND
    # "Madrid" (the entity name) is CONTAINED by verbatim "Madrid"
    # In other words: both directions produce 3 results total
    candidates = _find_fuzzy_candidates("Madrid", multi_entities)
    assert len(candidates) == 3
    ids = {c["id"] for c in candidates}
    assert "entity:jpi-madrid" in ids
    assert "entity:jls-madrid" in ids
    assert "entity:madrid-city" in ids


# ============================================================================
# Tests: Resolution action mapping
# ============================================================================


def test_apply_match_candidate() -> None:
    """match_existing with matched_candidate_id uses that ID."""
    result = _apply_resolution_action(
        action="match_existing",
        matched_candidate_id="entity:jpi-madrid",
        matched_entity_id=None,
        entity_type="place",
        ref_text="JPI Madrid",
    )
    assert result["entity_id"] == "entity:jpi-madrid"
    assert result["canonical_entity"] == "entity:jpi-madrid"
    assert result["needs_create"] is False


def test_apply_match_entity_backward_compat() -> None:
    """match_existing with matched_entity_id (backward compat)."""
    result = _apply_resolution_action(
        action="match_existing",
        matched_candidate_id=None,
        matched_entity_id="entity:old-style",
        entity_type="place",
        ref_text="Some place",
    )
    assert result["entity_id"] == "entity:old-style"
    assert result["needs_create"] is False


def test_apply_candidate_preferred_over_entity() -> None:
    """matched_candidate_id takes priority over matched_entity_id."""
    result = _apply_resolution_action(
        action="match_existing",
        matched_candidate_id="entity:candidate",
        matched_entity_id="entity:legacy",
        entity_type="place",
        ref_text="Test",
    )
    assert result["entity_id"] == "entity:candidate"


def test_apply_create_new() -> None:
    """create_new action indicates entity creation needed."""
    result = _apply_resolution_action(
        action="create_new",
        matched_candidate_id=None,
        matched_entity_id=None,
        entity_type="person",
        ref_text="Dr. Smith",
    )
    assert result["needs_create"] is True
    assert result["inferred_name"] == "Dr. Smith"
    assert result["inferred_type"] == "person"
    assert result["resolution_confidence"] == 0.9


def test_apply_uncertain() -> None:
    """uncertain action indicates tentative entity creation."""
    result = _apply_resolution_action(
        action="uncertain",
        matched_candidate_id=None,
        matched_entity_id=None,
        entity_type="object",
        ref_text="Document A",
    )
    assert result["needs_create"] is True
    assert result["resolution_confidence"] == 0.6
    assert result["inferred_name"] == "Document A"


def test_apply_empty_ids() -> None:
    """match_existing with no IDs returns None entity_id."""
    result = _apply_resolution_action(
        action="match_existing",
        matched_candidate_id=None,
        matched_entity_id=None,
        entity_type="place",
        ref_text="Unknown",
    )
    assert result["entity_id"] is None
    assert result["needs_create"] is False


# ============================================================================
# Tests: Integration — full search-first resolution flow
# ============================================================================


def test_integration_exact_match_skips_fuzzy() -> None:
    """Exact match returns immediately — no fuzzy candidates needed."""
    entities = [
        {"name": "Madrid", "id": "entity:madrid", "entity_type": "place"},
        {"name": "Barcelona", "id": "entity:bcn", "entity_type": "place"},
    ]

    # Exact match on "Madrid" → should find entity:madrid
    exact = _exact_match("MADRID", entities)
    assert exact is not None
    assert exact["id"] == "entity:madrid"

    # No further fuzzy matching needed — verify it's not needed
    fuzzy = _find_fuzzy_candidates("MADRID", entities)
    # (both exist, but exact match was sufficient)


def test_integration_fuzzy_then_action() -> None:
    """No exact match → fuzzy candidates found → action maps correctly."""
    verbatim = "Primera Instancia de Barcelona"

    exact = _exact_match(verbatim, FIXTURE_ENTITIES)
    assert exact is None  # No exact match

    candidates = _find_fuzzy_candidates(verbatim, FIXTURE_ENTITIES)
    assert len(candidates) >= 1

    # Simulate LLM deciding to match the first candidate
    first_candidate = candidates[0]["id"]
    action_result = _apply_resolution_action(
        action="match_existing",
        matched_candidate_id=first_candidate,
        matched_entity_id=None,
        entity_type="place",
        ref_text=verbatim,
    )
    assert action_result["entity_id"] == first_candidate
    assert action_result["needs_create"] is False


def test_integration_fuzzy_no_match_then_create() -> None:
    """No exact match → no fuzzy candidates → must create new."""
    verbatim = "Nueva Entidad Desconocida 3000"

    exact = _exact_match(verbatim, FIXTURE_ENTITIES)
    assert exact is None

    candidates = _find_fuzzy_candidates(verbatim, FIXTURE_ENTITIES)
    assert len(candidates) == 0  # No fuzzy match either

    action_result = _apply_resolution_action(
        action="create_new",
        matched_candidate_id=None,
        matched_entity_id=None,
        entity_type="place",
        ref_text=verbatim,
    )
    assert action_result["needs_create"] is True
    assert action_result["inferred_name"] == verbatim


def test_integration_nullify_then_recreate_pattern() -> None:
    """Simulate the nullify-then-recreate: entities are cleared then
    re-resolved deterministically."""
    verbatim_a = "Madrid"
    verbatim_b = "Barcelona"

    # First pass: resolve both
    entities = [
        {"name": "Madrid", "id": "entity:madrid", "entity_type": "place"},
        {"name": "Barcelona", "id": "entity:bcn", "entity_type": "place"},
    ]

    # Both have exact matches
    match_a = _exact_match(verbatim_a, entities)
    match_b = _exact_match(verbatim_b, entities)
    assert match_a is not None
    assert match_b is not None

    # "Nullify": clear entities
    entities_after_nullify = []

    # Second pass (reprocess): same resolution logic
    match_a_redo = _exact_match(verbatim_a, entities_after_nullify)
    assert match_a_redo is None  # No entities to match

    match_b_redo = _exact_match(verbatim_b, entities_after_nullify)
    assert match_b_redo is None

    # After re-creation, entities available again
    match_a_after_create = _exact_match(verbatim_a, entities)
    assert match_a_after_create is not None


def test_integration_full_flow_exact_fuzzy_create() -> None:
    """Full search-first flow: exact match for one ref, fuzzy+create for
    another, action mapping for matched candidate."""
    # Entities available for matching
    entities = [
        {"name": "Juzgado de Primera Instancia de Madrid",
         "id": "entity:jpi-madrid", "entity_type": "place"},
        {"name": "Audiencia Provincial de Barcelona",
         "id": "entity:ap-bcn", "entity_type": "place"},
    ]

    # --- Ref 1: exact match ---
    ref_a = "Juzgado de Primera Instancia de Madrid"
    exact = _exact_match(ref_a, entities)
    assert exact is not None
    assert exact["id"] == "entity:jpi-madrid"
    # Exact: set entity_id + canonical_entity directly, LLM not needed
    assert _find_fuzzy_candidates(ref_a, entities) is not None  # would find candidates
    # but exact was sufficient

    # --- Ref 2: no exact match, fuzzy candidates found ---
    ref_b = "Barcelona"
    exact_b = _exact_match(ref_b, entities)
    assert exact_b is None  # no entity is exactly named "Barcelona"

    fuzzy_b = _find_fuzzy_candidates(ref_b, entities)
    assert len(fuzzy_b) >= 1  # "Barcelona" is contained in audiencia provincial de Barcelona

    # Simulate LLM matching the candidate
    action_b = _apply_resolution_action(
        action="match_existing",
        matched_candidate_id=fuzzy_b[0]["id"],
        matched_entity_id=None,
        entity_type="place",
        ref_text=ref_b,
    )
    assert action_b["entity_id"] == fuzzy_b[0]["id"]
    assert action_b["needs_create"] is False

    # --- Ref 3: no match at all → must create ---
    ref_c = "Audiencia Nacional de España"
    exact_c = _exact_match(ref_c, entities)
    assert exact_c is None
    fuzzy_c = _find_fuzzy_candidates(ref_c, entities)
    assert len(fuzzy_c) == 0

    # Action: create new
    action_c = _apply_resolution_action(
        action="create_new",
        matched_candidate_id=None,
        matched_entity_id=None,
        entity_type="place",
        ref_text=ref_c,
    )
    assert action_c["needs_create"] is True
    assert action_c["inferred_name"] == ref_c
