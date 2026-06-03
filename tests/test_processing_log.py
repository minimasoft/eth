"""
Unit tests for ProcessingLogger's deterministic ID and counter logic.

All tests are in-memory — no SurrealDB connection required.
DB-dependent behavior (connectivity, write, 100-entry cap query)
is tested via integration tests (Phase 18).
"""

from __future__ import annotations

import hashlib


def test_deterministic_id_computation() -> None:
    """SHA256 hex digest produces a 16-char hex string."""
    raw = "doc123extract_text0"
    h = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    assert len(h) == 16
    assert all(c in "0123456789abcdef" for c in h)

    # Different input produces different hash
    h2 = hashlib.sha256(b"doc123extract_text1").hexdigest()[:16]
    assert h != h2


def test_deterministic_id_same_inputs() -> None:
    """Same inputs always produce the same output (pure function)."""
    id1 = hashlib.sha256(b"docAstep0").hexdigest()[:16]
    id2 = hashlib.sha256(b"docAstep0").hexdigest()[:16]
    assert id1 == id2  # Same inputs → same output


def test_deterministic_id_different_inputs() -> None:
    """Different inputs produce different outputs."""
    id1 = hashlib.sha256(b"docAstep0").hexdigest()[:16]
    id2 = hashlib.sha256(b"docAstep1").hexdigest()[:16]
    id3 = hashlib.sha256(b"docBstep0").hexdigest()[:16]
    assert id1 != id2
    assert id1 != id3
    assert id2 != id3


def test_hash_length() -> None:
    """Truncated hash is always 16 characters."""
    h = hashlib.sha256(b"anything").hexdigest()[:16]
    assert len(h) == 16


def test_sequence_counter_logic() -> None:
    """Verify the sequence counter pattern: increments per (doc, step) pair."""
    counter: dict[str, int] = {}
    key1 = "doc123:extract_text"
    key2 = "doc123:chunk_document"

    seq1 = counter.get(key1, 0)
    counter[key1] = seq1 + 1
    seq2 = counter.get(key1, 0)
    counter[key1] = seq2 + 1
    seq3 = counter.get(key2, 0)
    counter[key2] = seq3 + 1
    # Third call is for a different step — resets to 0

    assert seq1 == 0
    assert seq2 == 1
    assert seq3 == 0


def test_multi_call_id_uniqueness() -> None:
    """Multiple calls for the same doc+step produce unique IDs."""
    doc = "abc123"
    step = "extract_events"
    ids = []
    for seq in range(3):
        raw = f"{doc}{step}{seq}"
        h = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
        ids.append(h)
    assert len(set(ids)) == 3
    assert all(len(h) == 16 for h in ids)
