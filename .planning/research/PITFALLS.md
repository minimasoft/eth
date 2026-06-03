# Domain Pitfalls — Pipeline Quality & Entity Resolution (v4.0)

**Domain:** Reference offsets, structured event entities, search-first entity resolution, per-document processing logs
**Researched:** 2026-06-03
**Confidence:** HIGH

## Critical Pitfalls

### Pitfall 1: Offset Drift After Text Reprocessing

**What goes wrong:**
Character offsets (`span_start`, `span_end`) in existing reference records become invalid when document text is reprocessed. If a document is re-extracted via PDF (e.g., a bug fix in the extractor changes whitespace, or a new OCR pass fixes a misread character), all stored `span_start`/`span_end` values silently point to wrong text. Page offsets suffer the same fate: if `_page_count` or page boundaries change, `page_number` on references becomes garbage.

This is especially dangerous because the existing `nullify-then-recreate` pattern in `resolve_entities_activity` already nullifies `canonical_entity` links but does **not** touch `span_start`/`span_end`. If offsets become a required schema field, the delete-then-recreate in `store_extraction_results_activity` is the only existing safeguard — but only for the *current* extraction run. Offsets from older runs that survive into new records via partial updates would be silently wrong.

**Why it happens:**
- PDF text extraction is non-deterministic across library versions: `pypdfium2` v24 vs v25 may produce subtly different whitespace, ligature handling, or Unicode normalization.
- The existing `extract_text_activity` only sets `text_content` when the blob path is used. It does **not** re-extract for documents that already have `text_content` (text path). If someone later triggers a re-extraction via the blob path on a document that was originally processed via the text path, the text content changes silently.
- Offset-based references are only meaningful relative to `document.text_content` at the *moment of extraction*. No versioning or snapshot mechanism exists for the source text.
- The `RecursiveCharacterTextSplitter` uses `chunk_overlap=0`, meaning chunk boundaries are exact — but if the chunker's separator list changes, offsets shift everywhere.

**How to avoid:**
- **Immutable text_content rule:** Once `text_content` is set (and extraction has been performed), never modify it in place. If re-extraction is needed, set a new `text_content_v2` field or create a new document revision (document versioning).
- **Validation gate in store_extraction_results_activity:** Before storing references with offsets, verify that every `span_start`/`span_end` pair points to a valid character in `document.text_content`. Log a warning if any reference would point beyond the text length:
  ```python
  text_len = len(text_content)
  for ref in references:
      if ref.span_end > text_len or ref.span_start < 0 or ref.span_start >= ref.span_end:
          # Flag as suspicious, do not store
  ```
- **Store text_content hash alongside offsets:** Add a `text_hash` field (e.g., SHA-256 of `text_content` at extraction time) to the reference table or document record. On query, compare current hash to stored hash to detect drift.
- **Page offsets should be derived, not stored independently:** Instead of storing `page_number` as a flat field on each reference, store the reference's character offset range and compute `page_number` at query time by lookup in `document_chunk.page_start`/`page_end`.

**Warning signs:**
- A reference's `verbatim_text` cannot be found at its `span_start` position in the document text
- Integration tests that reprocess a document show different reference count or different offset values vs. the first run
- `text_content` is updated without updating any reference offsets

**Phase to address:**
- Phase 1 (Reference Offsets): Add text_hash validation and offset bounds-checking in store_extraction_results_activity

---

### Pitfall 2: Page Number vs. Document Page Confusion

**What goes wrong:**
"Page number" is ambiguous: it can mean the physical page of the original PDF (e.g., "folio 3," "page 5 of 12") or the page counter in the extracted text (0-indexed page in `page_offsets`). When an LLM extracts a reference and reports a page number, it usually reports the **logical** page from the document's own numbering ("folio 3 recto," "página 7 de 24"). The existing chunk infrastructure uses **zero-indexed** page numbers (0 = first page of extracted text). If these get mixed up, references point to wrong pages.

This is compounded by Spanish legal documents, which often have:
- Two numbering systems: internal court foliation + pagination of the submitted document
- Cover pages counted as page 0 or not counted
- "Folios" (sides of a sheet) vs. "páginas" (sheets)

**Why it happens:**
- The LLM extracts verbatim text with a `span_start`/`span_end` in the full document text — it doesn't know about page boundaries. The LLM would need to be given chunk metadata (page ranges per offset) to correctly map character offsets to page numbers.
- The existing `document_chunk.offset_start`/`offset_end` stores *character* ranges per page, but the LLM extraction prompt doesn't include this mapping — it only sees the full reconstructed text.
- A developer may add `page_number` as a field on `reference` and expect the LLM to fill it in, but the LLM hallucinates page numbers because it doesn't know where page boundaries are in the concatenated text.

**How to avoid:**
- **Do NOT store `page_number` as a flat LLM-extracted field on reference.** Instead, compute it at query time by reverse-lookup from `span_start` through `document_chunk` page ranges.
- If you must store a page number for display, introduce a **page offset lookup** function:
  ```python
  def char_offset_to_page(span_start: int, page_offsets: list[int]) -> int:
      """Convert character offset to 1-based page number.
      
      page_offsets is [0, p1_end, p2_end, ..., doc_length]
      Returns page index (1-based).
      """
      for i in range(1, len(page_offsets)):
          if span_start < page_offsets[i]:
              return i
      return len(page_offsets) - 1
  ```
- If the LLM *does* report a page number in its output (some models can), store it separately as `llm_reported_page` (nullable, informational only) — and cross-reference it against the computed page number on storage to detect hallucination.

**Warning signs:**
- `page_number` on references doesn't match `document_chunk` page ranges when queried
- Multiple references in the same event claim different pages but are within 50 characters of each other
- PDF documents with cover pages: page 1 from the LLM might be page 2 of the extracted text (the cover isn't extracted)

**Phase to address:**
- Phase 1 (Reference Offsets): Define the character-offset-to-page lookup function, store page as computed, not LLM-extracted

---

### Pitfall 3: Event-as-Entity Creates Circular References

**What goes wrong:**
When an event object becomes a canonical entity (type `event`), it can link to *other* canonical entities (place, person, object) through structured fields. This creates a graph that can form cycles: Event A references Person B (a canonical entity), but Person B's `properties` might include "involved_in_event: Event A" if the LLM-generated properties are too aggressive. More critically, if events can reference other events (e.g., "this hearing occurred after the previous hearing"), the event-to-event link forms an unbreakable cycle that breaks merge/split operations and GraphQL queries with recursion limits.

The existing `canonical_entity` table has **no referential integrity constraints** beyond the `superseded_by` self-link. There is nothing preventing an event entity's `properties` from containing a record link back to another event entity, or to itself.

**Why it happens:**
- The existing LLM extraction schema already has `humanos`, `espacio`, `objetos` fields as free-text strings — not record links. When these become structured record links (event.properties.participants → canonical_entity:person), the natural inclination is to create bidirectional links: "person X participated in event Y" AND "event Y has participant person X."
- Merge/split operations on `canonical_entity` currently assume a DAG (directed acyclic graph) structure via `superseded_by`. An event entity referencing another event entity breaks this DAG assumption.
- The existing `entity_type` enum is `['place', 'person', 'object']` with SCHEMAFULL `ASSERT $value INSIDE [...]`. Adding `'event'` requires a schema migration, but the more dangerous part is what happens *after* the migration: existing code that branches on `entity_type` (e.g., the Web UI entity list, the merge validation) must be updated to handle the new type.

**How to avoid:**
- **Unidirectional links only:** Event entities should have OUTGOING record links to other entities (place, person, object), but other entity types should NOT have back-links to events. Instead, use a separate `event_participant` junction table or query events by linked entity ID at query time.
- **Ban event-to-event references entirely.** An event should never link to another event directly. If temporal ordering is needed ("before event X"), use a separate `event_relationship` table with explicit `predecessor`/`successor` record links — not embedded in event properties.
- **Update the merge validation pipeline** (7 conditions in merge, 6 in split) to reject merge/split on event-type entities, or add condition:
  > Condition 8: Source and target must not have entity_type = 'event' (events are merged via a different mechanism, if at all)
- **Update the Web UI entity list** to handle the `event` type gracefully: show structured event data (time, place, participants) instead of just `name` + `reference_count`. Wire up a detail view for events.

**Warning signs:**
- A GraphQL query for event entities causes a `RecursionError: maximum recursion depth exceeded`
- Merge/split on an event entity succeeds but leaves dangling or duplicate references
- The Web UI entity list shows `event` entities with generic formatting that hides their structured data

**Phase to address:**
- Phase 2 (Structured Event Objects): Enforce unidirectional links, ban event-to-event references, add merge/split guards

---

### Pitfall 4: Search-First Entity Resolution Kills Performance at Scale

**What goes wrong:**
The current entity resolution pattern (post-hoc batch) queries existing entities once and does LLM matching against all of them in a single prompt. A "search-first" pattern replaces this with: for each reference encountered during extraction, first query SurrealDB to find candidate matches, then ask the LLM to verify or create. This turns O(1) queries into O(N) queries (one per reference). With 100+ references per document and 1000+ existing canonical entities, each query becomes a full-text search across the entity table that gets slower as entities accumulate.

The existing `resolve_entities_activity` queries `SELECT * FROM canonical_entity WHERE entity_type = $type` — a full table scan per type. With 10K entities, this returns 10K records to the activity, which is then serialized through Temporal to the LLM prompt. The prompt size grows with the entity corpus, eventually exceeding context windows or costing significantly more per extraction.

**Why it happens:**
- It seems natural: "search before create" reduces duplicate entities. But the single-batch query pattern doesn't scale.
- The decision to do search-FIRST (during extraction) vs search-AFTER (post-hoc batch) has different performance implications. Search-first fragments the LLM calls: one per reference instead of one batch per type.
- SurrealDB has limited full-text search capabilities compared to dedicated search (Elasticsearch, Meilisearch). The existing `LIKE` operator on `name` is case-sensitive and doesn't handle Spanish diacritics well (Madrid ≠ madrid ≠ MADRID in `LIKE`).
- The Temporal activity timeout is 30 seconds for `resolve_entities_activity`. Adding per-reference entity search queries within this window risks timeouts.

**How to avoid:**
- **Hybrid approach, not search-only:** Keep the batch pattern as the primary path. Add a "search" step only for ambiguous references where the LLM's `uncertain` confidence is below a threshold (e.g., < 0.7). This way, the fast path (clear match/create) stays O(1) per type, and the search path only triggers for edge cases.
- **Index entity names for search:** Add a SurrealDB `DEFINE INDEX entity_name_idx ON TABLE canonical_entity COLUMNS name UNIQUE` or use `DEFINE ANALYZER` with Spanish text analysis for case-insensitive, diacritic-insensitive matching:
  ```surql
  DEFINE ANALYZER spanish_ci TOKENIZERS blank CLASSIFIERS false FUNCTIONS lowercase, ascii
  DEFINE INDEX entity_search_idx ON TABLE canonical_entity COLUMNS name SEARCH ANALYZER spanish_ci
  ```
  (Verify with SurrealDB v3 whether SEARCH ANALYZER is supported for SCHEMAFULL tables.)
- **Limit candidate context sent to LLM:** Instead of sending ALL existing entities to the LLM, pre-filter to top-5 candidates by name similarity. Use a simple Levenshtein or trigram match in Python before the LLM call:
  ```python
  from rapidfuzz import fuzz
  candidates = [e for e in existing_entities if fuzz.ratio(ref["verbatim_text"], e["name"]) > 70]
  llm_context = candidates[:5]  # Top 5, saturates at 5
  ```
- **Set up a benchmark:** Before deploying search-first, run a performance test with 100 existing entities, 1000 entities, and 10000 entities. Measure the activity duration for each. Establish a performance budget: `N_references * query_time + LLM_time < 30s timeout`.

**Warning signs:**
- A single document's `resolve_entities_activity` takes > 25s (approaching the 30s timeout)
- The LLM prompt for entity resolution exceeds 100K tokens (too many entities in context)
- `SELECT ... FROM canonical_entity` queries appear in Temporal activity logs as slow (> 1s per query)
- Entity resolution creates duplicate entities (same person with slightly different names across documents) — the search is not catching matches

**Phase to address:**
- Phase 3 (Search-First Resolution): Implement candidate pre-filtering, set performance budget, add search index

---

### Pitfall 5: Per-Document Log Table Grows Unbounded

**What goes wrong:**
A `document_log` table that accumulates one entry per processing step per document becomes an append-only black hole. With 10 documents × 10 steps each × 20 re-processing cycles = 2000 log entries per document over a year. If each entry is a JSON blob (error messages, LLM responses, warnings), the table grows without bound. No retention policy, no archival, no indexing — and the Web UI or API endpoints that "list recent logs" become increasingly slow.

The current `error_message` field on `document` only stores the *last* error. A log table changes this to store *all* errors and warnings, which is good for debugging but bad for database health if not managed.

**Why it happens:**
- Log tables are the classic "just one more entry" problem. Each entry is small (a few KB), so the growth is imperceptible until it causes real pain.
- SurrealDB SCHEMAFULL tables don't have built-in TTL or partition-by-time features.
- The existing architecture has no data lifecycle management — no archival strategy, no cleanup workflow.
- Reprocessing a document 20 times during development creates 20× the log entries for that document, making it the dominant consumer of log storage.

**How to avoid:**
- **Define a log retention limit per document:** Store at most the last N log entries (e.g., 100) per document. When inserting a new entry, delete the oldest if the count exceeds the limit. This is easy in SurrealDB:
  ```surql
  -- Before inserting new log entry
  DELETE document_log WHERE document = $doc_id AND id IN (
      SELECT id FROM document_log WHERE document = $doc_id 
      ORDER BY created_at ASC LIMIT 1 
      OFFSET 99  -- Keep newest 100
  )
  ```
- **Use a separate log table with minimal SCHEMAFULL:** `document_log` with fields `document`, `step` (string), `level` (enum: info/warn/error), `message` (string), `details` (FLEXIBLE object or null), `created_at`. Keep `details` optional to avoid forcing every entry to carry a heavy payload.
- **Don't store LLM response bodies in the log.** The full LLM response can be 10K+ tokens. Store a truncated summary or a reference to a separate LLM response storage (e.g., MinIO object path).
- **Add a log viewer that paginates and filters by document + level.** Never build an endpoint that dumps all logs across all documents.
- **Consider Temporal workflow history for operational logging.** Temporal already records activity inputs, outputs, and errors. Duplicating this in a database table is redundant for operational monitoring — use the log table only for *business* warnings (e.g., "low confidence extraction," "entity resolution uncertain").

**Warning signs:**
- `SELECT count() FROM document_log GROUP BY document` shows documents with > 1000 log entries
- `GET /documents/{id}/logs` takes > 5 seconds
- The `document_log` table is larger than the `event` table
- Temporal activity logs show SurrealDB write contention on `document_log` during batch processing

**Phase to address:**
- Phase 4 (Processing Logs): Implement retention limit, define log schema with level enum, separate operational vs. business logging

---

### Pitfall 6: Log Entries Violate Temporal Replay Semantics

**What goes wrong:**
Temporal replay replays all activities in the exact same order with the exact same inputs. If a `write_log_activity` inserts a log entry into SurrealDB *during* replay (not just the initial execution), the log table accumulates duplicate entries: one from the original run, one from each replay. Worse, if the log entry includes a `created_at` timestamp from the replay time (not the original execution time), the log timeline is corrupted — entries appear out of chronological order.

The existing `store_extraction_results_activity` uses the nullify-then-recreate pattern specifically for Temporal replay safety. But a naive log activity doesn't nullify — it just INSERTs. Every retry creates duplicate log entries.

**Why it happens:**
- Temporal replay safety is a non-obvious constraint. Developers new to Temporal expect activities to run once. In reality, failed activities retry, and completed workflows may replay.
- The existing codebase does use the nullify-then-recreate pattern in `store_extraction_results_activity` and `resolve_entities_activity`, so there IS precedent — but it's easy to forget when adding a "simple" logging feature.
- Writing a log entry feels like a side-effect, not a state mutation. But in Temporal, ALL external side effects must be idempotent.

**How to avoid:**
- **Use a log ID that is deterministic from the workflow execution:** Derive the log entry ID from `workflow_id + activity_type + attempt_number` to ensure uniqueness. SurrealDB's `CREATE ONLY` (not `CREATE`) will fail if the record already exists, preventing duplicates:
  ```python
  log_id = f"doc-log-{document_id}-{hash(step_name)}-{activity.info().attempt}"
  await db.create(RecordID("document_log", log_id), {
      "document": doc_ref,
      "step": step_name,
      ...
  })
  ```
  This ensures the activity is idempotent: the first attempt creates, retries fail silently on duplicate key (or use `UPSERT` semantics).
- **Use Temporal workflow-scoped logging for operational events:** Temporal workflows can use `workflow.logger` (which is replay-aware — it doesn't log during replay). This is already available and avoids the database entirely for low-priority operational messages. Reserve the database log table for *persistent* business warnings that must survive a Temporal namespace reset.
- **Document the replay contract:** In the log activity docstring, state clearly: "This activity MUST be idempotent — it may be called multiple times for the same logical step due to Temporal retry/replay."

**Warning signs:**
- A single document processing shows 3 identical log entries after a single retry
- `document_log` entries have duplicate timestamps for the same step
- After a Temporal worker restart (which triggers replay of in-flight workflows), new log entries appear for already-logged steps

**Phase to address:**
- Phase 4 (Processing Logs): Design log activity with deterministic IDs and idempotent insert semantics

---

### Pitfall 7: SCHEMAFULL Migration Without Downtime Planning

**What goes wrong:**
Adding new fields to SCHEMAFULL tables requires `DEFINE FIELD` statements that SurrealDB will reject if existing records violate the new constraint. Specifically:
1. Adding `span_page ON reference TYPE int ASSERT $value >= 1` — but existing references don't have this field (it would be null), and the `ASSERT` doesn't allow null.
2. Adding `entity_type: 'event'` to the canonical_entity ASSERT — but the existing `ASSERT $value INSIDE ['place', 'person', 'object']` rejects the new value until the table is redefined.
3. Adding a new `document_log` table — this is additive and safe, but the schema file (schema.surql) must be updated and the init script re-run.

The existing init script applies the schema via `DEFINE` statements that are idempotent (re-defining the same field with the same signature is a no-op). But changing a field's signature (e.g., changing `DEFINE FIELD span_start ON TABLE reference TYPE int` to add a new field) requires careful ordering.

**Why it happens:**
- SurrealDB's `DEFINE TABLE SCHEMAFULL` validates ALL existing records against the schema. Adding a new required field without a `DEFAULT` clause causes the migration to fail on any table with existing rows.
- The `ASSERT` clause on `canonical_entity.entity_type` is a hard constraint. You can't add `'event'` to the allowed values without first reading all existing records — but the constraint is evaluated at the schema level, not per-record. The only safe approach is to either:
  - Drop and redefine the field (drops the constraint, adds a looser one)
  - Or use a migration transaction that temporarily removes then re-adds the constraint
- There is no existing migration framework — migrations are applied by running `.surql` files via `curl`. No version tracking, no rollback, no dry-run mode.

**How to avoid:**
- **For new fields on existing tables (reference offsets, page numbers):**
  Use `TYPE int | null DEFAULT null` for any field being added to a non-empty table. This avoids validation failures on existing null values:
  ```surql
  DEFINE FIELD span_page ON TABLE reference TYPE int | null DEFAULT null
      COMMENT 'Page number (1-based) where this reference's verbatim text appears';
  ```
  Then backfill: after the migration runs, update old references with `UPDATE reference SET span_page = ...` for documents that are re-processed.
- **For new entity type values (adding 'event'):**
  The cleanest approach is to relax the constraint first, then tighten it:
  ```surql
  -- Step 1: Remove the restrictive ASSERT
  DEFINE FIELD entity_type ON TABLE canonical_entity TYPE string
      COMMENT 'Entity category including event type';
  -- Step 2: After all records are updated
  DEFINE FIELD entity_type ON TABLE canonical_entity TYPE string
      ASSERT $value INSIDE ['place', 'person', 'object', 'event'];
  ```
  But note: SurrealDB `DEFINE FIELD` is NOT transactional in the traditional sense between step 1 and step 2. Run them sequentially in the migration script.
- **Test the migration on a copy of production data first.** The project has no staging environment — create a migration test script that:
  1. Exports current data via `SELECT * FROM canonical_entity`
  2. Applies the migration
  3. Verifies all records are readable and queries work

**Warning signs:**
- Migration `.surql` files reference `ASSERT` values that don't include new enum values
- New DB fields have no `DEFAULT` clause but the table potentially has existing rows
- The migration script doesn't handle both directions (add + rollback)

**Phase to address:**
- Phases 1-4: Each schema change must be independently migration-tested. Run all migrations in a test Docker Compose environment against a seeded copy of the schema.

---

### Pitfall 8: LLM Prompt Drift from Entity Search Context

**What goes wrong:**
Adding entity search context to the extraction prompt (e.g., "Here are existing entities. When you extract a reference, match it to an existing entity if possible.") changes the LLM's behavior in unpredictable ways. The most common failure modes:

1. **Anchor bias:** The LLM over-matches references to existing entities even when the reference doesn't fit, because the prompt says "match when possible." This creates false positives in entity resolution.
2. **Context contamination:** Including entity search results in the prompt increases token consumption. A prompt that was 80K tokens becomes 120K tokens, pushing closer to context limits. The LLM starts dropping extraction quality because the "attention budget" is split between extraction and matching.
3. **Refusal cascades:** If the entity list contains an entity the LLM interprets as sensitive (e.g., a controversial person or place), the LLM may refuse to extract any events mentioning that entity, or refuse to process the document entirely (over-reliance on alignment guardrails).
4. **Inconsistent schema compliance:** The extraction schema is complex (event with nested references). Adding entity matching logic to the same prompt increases the cognitive load on the structured output. The LLM may produce malformed JSON more frequently, or skip the matching logic entirely ("I'll just create new entities for everything to keep it simple").

**Why it happens:**
- The existing `EXTRACTION_CHUNK_SIZE = 400_000` characters leaves ~100K tokens of headroom. Entity search context (entity names, descriptions, IDs) adds ~5-50 tokens per entity, which seems small. But 100 entities × 50 tokens = 5000 tokens. Over many documents, this grows.
- The system prompt is already dense: extraction instructions, schema definition, Spanish language instructions. Adding entity matching instructions creates an **instruction conflict**: "Find ALL events" vs. "Only create entities that don't already exist." The LLM optimizes for recency — the instruction that appears last in the prompt wins.
- There is no existing mechanism for A/B testing prompt changes. Every extraction is a black box — you see the output, but you don't know if entity context improved or degraded extraction accuracy.

**How to avoid:**
- **Keep extraction and entity resolution as separate LLM calls** (as they are now). Do NOT merge entity search context into the extraction prompt. The existing two-phase flow (extract → resolve) is the correct boundary: extraction focuses on finding events, resolution focuses on matching entities. Search-first resolution should be an improvement to the *resolution* phase, not the *extraction* phase.
- For the resolution phase, use a **truncated entity context**: only send the top 5-10 candidate entities (by name similarity) to the LLM, not the full entity list. This limits prompt growth and reduces choice overload on the LLM.
- **Track prompt size and extraction quality metrics:**
  ```python
  # Per-extraction metrics
  {
      "prompt_tokens": len(prompt),
      "entity_context_tokens": len(entity_context_json),
      "extraction_success": True,
      "event_count": 5,
      "refusal": False,
  }
  ```
  Log these metrics and monitor for trends: if `entity_context_tokens` grows but `event_count` drops, the entity context is degrading extraction quality.
- **Spanish-specific caution:** Spanish legal text is dense and formal. Adding entity context in Spanish that lists entity names with Spanish descriptions works well. Adding entity context in English (or mixing languages) confuses the LLM. Keep entity matching prompts in Spanish, matching the extraction prompt language.

**Warning signs:**
- After adding entity context to the extraction prompt, reference count per event drops by >20%
- The LLM starts creating entities with names that don't appear in the document text (LLM is "completing" entity names from context)
- Schema validation failure rate increases (malformed JSON from structured output)
- Same document extracted twice (without vs. with entity context) produces different events

**Phase to address:**
- Phase 3 (Search-First Resolution): Keep extraction and resolution as separate phases, prompt-size monitoring on resolution calls

---

### Pitfall 9: Testing with Synthetic Spanish Legal Text Is Meaningless

**What goes wrong:**
Test documents written by developers (or LLMs) are syntactically valid Spanish but miss the characteristics of real legal text: numbered paragraphs ("PRIMERO.—"), formalistic phrasing ("Que por medio del presente escrito..."), abbreviations ("Juzg. 1ª Inst. nº 3"), cross-references ("folio 234 del procedimiento"), and multiple parties (demandante, demandado, procurador, letrado). Tests pass against synthetic text but fail in production with real documents.

Real Spanish legal PDFs also have characteristics that synthetic text doesn't:
- Scanned pages with OCR errors (text extraction produces "I" instead of "1", missing accents)
- Mixed encoding within the same PDF (some pages use Latin-1, others UTF-16)
- Handwritten marginal notes that pypdfium2 extracts as garbled text fragments
- Headers/footers repeated on every page ("Juzgado de lo Penal nº 2 de Madrid — Sumario 123/2024")
- Table structures that the LLM interprets as paragraph text

**Why it happens:**
- Creating realistic test data is hard. Using synthetic text is the path of least resistance.
- The existing test corpus (`test_data/`) has a few short text files that were manually created. They don't have the structural complexity of real legal documents.
- No LLM can reliably generate Spanish legal text that passes as authentic — the legal conventions (encabezamiento, hechos, fundamentos de derecho, fallo) have specific formatting that LLMs approximate poorly.

**How to avoid:**
- **Use anonymized real documents.** The project handles Spanish legal documents — obtain (public) court rulings from Spanish legal databases (CENDOJ, Aranzadi). Anonymize personal data (names → "NN", ID numbers → "***"). Spanish court rulings are public records; using them for testing does not breach confidentiality.
- **Create a test corpus with known ground truth:** For each test document, manually create the expected events, references, and entity resolutions. This makes integration tests meaningful: they assert "extract(realdoc) == expected_result," not just "extract(realdoc) returns valid JSON."
- **Document the characteristics of the test documents in README.md:**
  - Source (e.g., "anonymized excerpt from STS 1234/2023")
  - Difficulty level (simple/complex — determined by page count, entity count, event density)
  - Known extraction challenges (e.g., "page 3 has a table that triggers chunk boundary issues")
- **Include edge-case test documents:**
  - A one-paragraph document (minimum viable extraction)
  - A multi-page document that exceeds `EXTRACTION_CHUNK_SIZE` (tests chunk boundary logic)
  - A PDF with extracted text that contains OCR noise (tests reference offset robustness)
  - A document with no clear events (tests the "no events found" path)

**Warning signs:**
- Integration tests use text like "El día 15 de enero de 2024, Juan Pérez compareció ante el tribunal..." — this is synthetic, not from a real document
- Tests never reprocess a document and verify the second run produces identical results
- The test corpus has no PDF files (only .txt files)

**Phase to address:**
- Phase 5 (Test Corpus): Obtain real Spanish legal documents (public court rulings), create annotated ground truth, include edge-case documents

---

### Pitfall 10: Nullify-Then-Recreate on Events Creates Orphaned Entity Links

**What goes wrong:**
The existing `store_extraction_results_activity` deletes ALL events for a document and recreates them (nullify-then-recreate). But it does NOT nullify `canonical_entity` links on references before deleting events — it only deletes references linked to the deleted events. The `DELETE reference WHERE event IN (SELECT id FROM event WHERE document = $doc_ref)` cascades correctly.

However, if an event entity (the new canonical entity type) has been linked to other entities' references, deleting and recreating the event record breaks the reference links:
1. Event `event:abc` is extracted, stored, and its `canonical_entity` record `canonical_entity:event-abc` is created.
2. References from OTHER documents point to `canonical_entity:event-abc` (e.g., "this hearing was referenced in document X").
3. Document is reprocessed → `store_extraction_results_activity` deletes event `event:abc` and creates `event:def`.
4. Now the old `canonical_entity:event-abc` exists but its backing event is gone. References in other documents point to a dead entity.

This is not a problem for place/person/object entities because they are long-lived and document-independent. But event entities are **document-scoped** — they only exist in the context of one document. Making them canonical entities makes them appear document-independent, but they aren't.

**Why it happens:**
- The existing entity model assumes entities are cross-document. Event entities violate this assumption.
- The `nullify-then-recreate` pattern explicitly deletes events and references. If event entities are canonical entities, deleting the event should also delete the canonical entity — but the current code doesn't do that.
- The merge/split operations were designed for cross-document entities. Applying them to event entities (which are document-scoped) doesn't make sense, but nothing prevents it.

**How to avoid:**
- **Event entities must be document-scoped, not global.** Store event entities with a non-null `document` field (the source document) and filter all queries by document. This is a semantic change to the `canonical_entity` schema:
  ```surql
  DEFINE FIELD document ON TABLE canonical_entity TYPE record<document> | null
      DEFAULT null
      COMMENT 'Source document for event-type entities (null for cross-document entities)';
  ```
- **Nullify event entities during reprocess:** In `store_extraction_results_activity`, after deleting events and references, also delete `canonical_entity` records where `entity_type = 'event' AND document = $doc_ref`. This keeps event entities tied to their document lifecycle.
- **Exclude event entities from merge/split entirely.** Add a guard at the top of both handlers:
  ```python
  if record.entity_type == 'event':
      raise HTTPException(400, "Event entities cannot be merged or split. Reprocess the source document instead.")
  ```
- **GraphQL queries for events should not expose event entities as searchable entities.** Event entities should be queried through the event table, not the canonical_entity table. If auto-GraphQL is used, add a `@GraphQL(exclude: true)` comment or a permission filter on the canonical_entity table.

**Warning signs:**
- After reprocessing a document, links to event entities from other documents' references point to deleted canonical_entity records
- The Web UI entity list shows event entities that have no associated document
- Merge/split UI shows event entities as mergeable targets

**Phase to address:**
- Phase 2 (Event-as-Entity): Document-scoped event entities, nullify-on-reprocess guard, exclude from merge/split

---

### Pitfall 11: Race Conditions in Concurrent Document Processing

**What goes wrong:**
When multiple Temporal workflows process documents concurrently (which is the expected behavior — Temporal parallel tasks processing different documents), the `resolve_entities_activity` can create duplicate canonical entities for the same real-world entity:

1. Document A and Document B are processed concurrently.
2. Both workflows' `resolve_entities_activity` query `SELECT * FROM canonical_entity WHERE entity_type = 'person'`.
3. Neither finds "Juan Pérez García" as a canonical entity.
4. Both workflows create `canonical_entity` with name "Juan Pérez García" — but as two separate records.
5. The entity corpus now has a duplicate, defeating the purpose of entity resolution.

The existing code queries entities within each activity and makes decisions based on a snapshot that is stale by the time the activity commits. SurrealDB does not support distributed locks or advisory locks.

**Why it happens:**
- Temporal executes activities in parallel across workflow instances. There is no cross-workflow synchronization.
- The existing code does `SELECT * FROM canonical_entity WHERE entity_type = $type` — this is a read-only query that returns a snapshot. The write (CREATE new entity) happens later, without checking if another workflow created the same entity in the meantime.
- This is a classic "read-then-write" race condition. Microservices and distributed workflows are especially vulnerable because there's no database transaction that spans the read + the LLM call + the write.

**How to avoid:**
- **Use a unique constraint on entity name (within type):**
  ```surql
  DEFINE INDEX entity_unique_name ON TABLE canonical_entity COLUMNS entity_type, name UNIQUE
  ```
  When a duplicate create attempt happens, the `db.create()` call raises a SurrealDB constraint violation error. Catch this error and re-query for the existing entity:
  ```python
  try:
      created = await db.create("canonical_entity", data)
  except SurrealDBException as exc:
      if "UNIQUE constraint" in str(exc):
          # Another workflow created this entity first — use theirs
          existing = await db.query(
              "SELECT * FROM canonical_entity WHERE entity_type = $type AND name = $name",
              {"type": data["entity_type"], "name": data["name"]},
          )
          return existing[0].id
      raise
  ```
  This turns the race condition from a data corruption bug into a graceful retry.
- **Implement name normalization before insert:** Spanish legal names can vary: "Juan Pérez García," "Juan Perez Garcia," "D. Juan Pérez García." The CREATE should use a normalized form (strip titles, normalize accents) as the unique key, storing the original variant in `properties`.
- **Accept limited duplicates.** For a single-user research tool processing hundreds (not millions) of documents, occasional duplicates are acceptable and fixable via the merge endpoint. The merge operation was designed for exactly this. Document this as "best-effort deduplication during resolution; human review via merge endpoint catches leftovers."
- **Consider a single-file write queue for entity creation:** If duplicates become a real problem, route all entity creation through a single Temporal activity queue (not per-document) to serialize writes. This kills parallelism for entity creation but guarantees uniqueness.

**Warning signs:**
- `SELECT name, count() as cnt FROM canonical_entity GROUP BY name HAVING cnt > 1` returns rows
- The merge endpoint is used predominantly to merge duplicate person entities with the same name
- Temporal activity logs show `"UNIQUE constraint"` errors during entity creation (unless you've implemented the graceful retry — then these are fine)

**Phase to address:**
- Phase 3 (Search-First Resolution): Add unique constraint on entity name+type, implement graceful retry on constraint violation

---

### Pitfall 12: Mixing Log Data with Event Data in GraphQL Queries

**What goes wrong:**
When `document_log` entries are surfaced through GraphQL (via SurrealDB auto-GraphQL), the generated schema includes mutations and queries for log entries alongside events and references. This creates confusing API surface: is `UPDATE document_log` a valid operation? If the schema doesn't define `DEFINE FIELD` with `PERMISSIONS`, any authenticated user can modify or delete log entries, breaking the audit trail.

Similarly, if event entities are stored in `canonical_entity` (the same table as place/person/object entities), the auto-GraphQL `canonicalEntity` type now includes `event` entries. GraphQL queries that assume `entityType IN ['place', 'person', 'object']` must be updated, or they'll silently omit event entities.

The existing codebase uses `DEFINE TABLE ... SCHEMAFULL` with `COMMENT` annotations for auto-GraphQL documentation. No explicit `PERMISSIONS` are defined (default: FULL access for root). Every new table inherits this permissive default.

**Why it happens:**
- Auto-GraphQL from SurrealDB generates API surface from the schema. Add a table, get a query. No explicit opt-in required.
- The existing codebase has no permission model (single-user research tool). Adding a log table or event entity type extends the API surface without intentional design.
- The Web UI's `GET /entities` endpoint queries `canonical_entity` with where clauses. If event entities are added to the same table, the `entity_type` filter in `list_entities` must include `'event'`, otherwise event entities are invisible. If event entities SHOULD be invisible (document-scoped), the filter must explicitly exclude them.

**How to avoid:**
- **Separate event entities into their own table**, not as a type variant in `canonical_entity`. Use `event_entity` as a separate SCHEMAFULL table with fields specific to events (time, place_references, participant_references, etc.). This avoids polluting the `canonical_entity` API surface and makes GraphQL schemas clean:
  ```surql
  DEFINE TABLE event_entity SCHEMAFULL
      COMMENT 'Structured event as a canonical entity — document-scoped, not mergeable';
  ```
  Link from `event_entity` to `canonical_entity` for place/person/object participants via record links.
- **Set explicit PERMISSIONS on document_log to prevent modification:**
  ```surql
  DEFINE TABLE document_log SCHEMAFULL
      PERMISSIONS FOR select FULL, FOR create FULL, FOR update NONE, FOR delete NONE;
  ```
  This ensures log entries are append-only via the API.
- **When exposing document_log via API, only expose read endpoints.** Don't add POST/PUT/DELETE endpoints for logs. The only write path should be the Temporal activity.

**Warning signs:**
- The Web UI entity page shows orphaned event entities with 0 references
- GraphQL introspection reveals `createDocumentLog`, `updateDocumentLog`, `deleteDocumentLog` mutations
- A developer adds a `DELETE /logs` endpoint for "debugging" — this destroys the audit trail

**Phase to address:**
- Phase 4 (Processing Logs): Separate event_entity table, FOR UPDATE/FOR DELETE NONE on document_log

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Storing page_number as LLM-extracted field on reference | Fast display without lookup query | Page drift when text content changes; hallucinated page numbers | **Never** — derive from char offset at query time |
| Merging event entities into canonical_entity table instead of separate table | Single source of entity truth; simpler queries | Complex merge/split guards forever; GraphQL schema becomes leaky; entity queries must filter by type | Only if you're willing to rewrite the entity queries and GraphQL schema for every new entity type |
| No retention limit on document_log | Simpler code; no delete logic | Unbounded table growth; slow queries | **Never** — add a retention limit from day one (even if generous, like 500 entries per document) |
| Sending ALL existing entities to LLM for resolution | LLM has full context for matching decisions | Prompt grows with entity corpus; eventually exceeds context window or slows extraction | Only at < 100 entities. After that, pre-filter to top candidates |
| Using Temporal workflow logger instead of database log table | No DB writes; no persistence concern | Logs vanish when Temporal namespace is reset or history is pruned | Acceptable for operational debugging. Not acceptable for business audit trail |
| Skip entity name normalization before unique constraint insert | Simpler insert code | "Juan Pérez García" and "Juan Perez Garcia" become separate entities | Only as MVP. Add normalization before production use |
| No text hash/version on reference table | Saves one field per reference | Cannot detect when offsets are stale after reprocessing | Acceptable during development. Add before any data that is queried by offset |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| SurrealDB SCHEMAFULL + new enum values | Adding 'event' to entity_type ASSERT without checking existing records | Relax ASSERT first (remove it), then re-add with expanded values in a second step |
| Temporal + DB log writes | Writing log entries during replay (duplicates) | Use deterministic log IDs (workflow_id + step + attempt) for idempotent writes |
| OpenRouter + entity context in extraction prompt | Merging entity matching into the extraction prompt to save an LLM call | Keep extraction and resolution as separate phases — don't mix concerns |
| SurrealDB UNIQUE constraint + concurrent creates | Hitting UNIQUE violation and crashing the activity | Catch the constraint violation, re-query for the existing entity, return it gracefully |
| SurrealDB auto-GraphQL + document_log | Auto-generated mutations allow log modification | Set `PERMISSIONS FOR update NONE, FOR delete NONE` on document_log |
| pypdfium2 + offset stability | Assuming offsets from PDF extraction are deterministic across versions | Store a text_hash to detect drift; re-extract from scratch when text reprocessing changes |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Sending all existing entities to LLM resolution prompt | Prompt size > 100K tokens; LLM timeouts or partial completions | Pre-filter to top-5 candidates via fuzzy string matching | At ~500 entities (500 entities × ~200 tokens each = 100K tokens) |
| No index on canonical_entity.name for search-first resolution | `LIKE '%search%'` queries take > 1s on entity table | Add SurrealDB SEARCH ANALYZER index with Spanish text analysis | At ~10K entities without an index |
| O(N) per-reference DB queries in search-first resolution | Document processing time scales linearly with reference count | Batch entity lookups: one query per document, filter in memory | At ~100 references per document, each requiring a separate DB query |
| Storing full LLM response bodies in document_log | Log table grows 10× faster than expected | Store truncated summaries (~500 chars); link to full response in separate storage | At ~100 documents × 10 steps = 1000 log entries with full response bodies |
| document_log insert contention during batch reprocessing | Temporal activity timeouts on log inserts | Use a batch insert pattern: accumulate in memory, write once per activity | When reprocessing 10+ documents simultaneously (Temporal parallel execution) |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| No permission on document_log — log entries can be deleted | Audit trail destroyed; cannot trace extraction quality regressions | `PERMISSIONS FOR delete NONE` on document_log table |
| Event entities accessible through same GraphQL type as place/person/object | Cross-document entity confusion; event entities may be merged incorrectly | Use separate `event_entity` table, not a type variant in canonical_entity |
| LLM-extracted page numbers treated as ground truth | References point to wrong pages; debugging is impossible | Derive page number from character offset at query time; store LLM-reported page separately as informational |
| Unique constraint violation silently ignored | Duplicate canonical entities erode trust in entity resolution | Catch the error and re-query; don't silently skip |
| GraphQL mutations on event entities from auto-GraphQL | Event entities can be deleted independently of their source document | Set delete cascade or document-scoped permissions on event entities |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Event entities appear in the Web UI entity list next to people/places/users with same formatting | Confusion: "why is 'Audiencia del 15/01/2024' a mergeable entity like 'Juan Pérez'?" | Render event entities in a separate section with structured fields (time, participants) — or exclude them from the entity list entirely and show them in the document detail view |
| Processing logs show raw LLM response snippets | Users see confusing JSON fragments instead of actionable messages | Format log entries as human-readable messages: "Entity 'Juan Pérez' created with low confidence (0.45)" instead of raw JSON |
| Offset validation error during document upload crashes the upload | User uploads a PDF, gets HTTP 500 with no explanation | Validate offsets during storage, not upload. On extraction failure, mark document as "failed" with error_message; don't crash the HTTP request |
| Processing logs don't show document-level progress | User sees "processing" for 30+ seconds with no detail | Stream log entries to the Web UI via a progressive endpoint or polling — show "Step 3/6: Extracting events..." |

## "Looks Done But Isn't" Checklist

- [ ] **Reference offsets:** Offsets are stored but no `text_hash` or validation ensures they remain valid after text content changes. Verify: re-extract a document's text (change whitespace), re-run extraction, check offsets still point to correct text.
- [ ] **Page numbers:** Page numbers are stored as flat fields but not cross-referenced with `document_chunk.page_start`/`page_end`. Verify: pick a reference with `span_start=500`, compute its page via `document_chunk`, compare to stored `page_number`.
- [ ] **Event entities:** Event entities are stored in `canonical_entity` but are NOT excluded from merge/split, and get orphaned on document reprocess. Verify: merge two event entities via the API; reprocess an event-document and check old event entities are deleted.
- [ ] **Search-first resolution:** Entity duplicates are prevented by a UNIQUE constraint but there's no name normalization (accents, titles). Verify: create "Juan Pérez" from doc A and "Juan Perez" from doc B (different accent) — they should be detected as the same entity.
- [ ] **Processing logs:** Log entries are stored with a `log_id` derived from `workflow_id + step` but the activity doesn't handle the case where Temporal resets the attempt counter during replay. Verify: force a Temporal retry, check log entries after the retry complete — should be exactly 1, not 2.
- [ ] **Document log retention:** Log limit is implemented in the activity but the query doesn't account for concurrent inserts. Verify: insert 101 log entries for the same document simultaneously (e.g., via parallel workflow steps) — the document should still have ≤ 100 entries.
- [ ] **Migrating existing references:** Existing references (from before v4.0) don't have `span_start`/`span_end` as required fields. Verify: `SELECT * FROM reference WHERE span_start IS NONE` returns 0 rows after migration.
- [ ] **Text normalization for entity search:** Entity search uses exact `LIKE` matching. Verify: search for "san jose" finds "San José" (with accent) and "Don José García" (title prefix).
- [ ] **Temporal replay test:** Create a workflow that writes log entries, kills the Temporal worker mid-extraction, restarts it. Verify: log entries are exactly the same as a clean run (no duplicates, no missing entries).

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Offset drift after text reprocessing | MEDIUM — need to re-extract all affected documents | 1. Identify affected documents via text_hash mismatch. 2. Re-process each document via Temporal workflow (delete + recreate). 3. Verify offsets against recomputed hash. |
| Event entity orphaned after document reprocess | LOW — single document | 1. DELETE canonical_entity WHERE entity_type='event' AND document = $orphaned_doc. 2. Reprocess document. |
| Duplicate canonical entities from race condition | LOW — merge to fix | 1. Use `POST /entities/merge` to merge duplicates. 2. Add UNIQUE constraint to prevent future duplicates. |
| Unbounded log table consuming disk | MEDIUM — data loss | 1. Add retention-based purge: `DELETE document_log WHERE id IN (SELECT ... ORDER BY created_at ASC LIMIT count-100)`. 2. Set retention policy going forward. |
| LLM prompt drift from entity context producing bad extractions | HIGH — quality regressions | 1. Roll back the prompt change (revert to extraction-only prompt). 2. Analyze metrics from 10 documents with vs. without entity context. 3. Re-introduce with smaller entity context or separate phase. |
| Migration error from SCHEMAFULL constraint change | HIGH — DB schema rollback required | 1. Backup SurrealDB data (export). 2. Revert schema change. 3. Reapply with correct field types (nullable, default). 4. Restore data from backup if schema corrupted existing records. |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Offset drift after reprocessing | Phase 1: Reference Offsets | text_hash validation gate in store_extraction_results_activity |
| Page number vs. document page confusion | Phase 1: Reference Offsets | char_offset_to_page() computation, not LLM-extracted page |
| Event-as-entity creates circular references | Phase 2: Structured Event Objects | Separate event_entity table, unidirectional links, merge/split guards |
| Search-first resolution kills performance | Phase 3: Search-First Resolution | Top-5 candidate pre-filtering, performance budget benchmark |
| Log table grows unbounded | Phase 4: Processing Logs | Retention limit (100 entries/document) from day one |
| Log entries violate Temporal replay | Phase 4: Processing Logs | Deterministic log IDs + idempotent insert via CREATE ONLY |
| SCHEMAFULL migration without downtime | Phases 1-4 (schema changes) | Migration test script against seeded DB copy |
| LLM prompt drift from entity context | Phase 3: Search-First Resolution | Separate extraction and resolution phases, prompt size monitoring |
| Testing with synthetic text is meaningless | Phase 5: Test Corpus | Real Spanish court rulings with annotated ground truth |
| Orphaned event entity links during reprocess | Phase 2: Structured Event Objects | Nullify event entities on document reprocess |
| Race conditions in concurrent processing | Phase 3: Search-First Resolution | UNIQUE constraint + graceful retry on constraint violation |
| Mixing log data with event data in GraphQL | Phase 4: Processing Logs | Separate tables, PERMISSIONS FOR update/delete NONE on log |

## Sources

- **Offset drift with non-deterministic PDF extraction:** Personal experience with PyMuPDF/pypdfium2 across versions — whitespace and ligature handling varies (MEDIUM confidence — verified by observing version changelogs)
- **SCHEMAFULL constraint migration patterns:** SurrealDB documentation — `DEFINE FIELD` with new `ASSERT` validates against existing rows (HIGH confidence — SurrealDB docs)
- **Temporal replay idempotency requirement:** Temporal.io best practices — all external side effects must be idempotent (HIGH confidence — official Temporal documentation)
- **Read-then-write race condition in concurrent workflows:** Classic distributed systems problem — documented in "Temporal: Best Practices for Race Conditions" (HIGH confidence)
- **Spanish legal document structure:** CENDOJ (Centro de Documentación Judicial) — Spanish court rulings follow a standardized structure (HIGH confidence — public judicial documentation)
- **Entity name normalization for Spanish names:** Common practice in Spanish NLP — strip titles (D., Doña), normalize accents, handle compound surnames (MEDIUM confidence — community conventions)
- **Auto-GraphQL permission defaults:** SurrealDB default permissions are FULL for root — must be explicitly restricted (HIGH confidence — SurrealDB documentation)
- **PyMuPDF/pypdfium2 extraction determinism:** Personal experience — pypdfium2 produces more consistent output than PyMuPDF for simple text PDFs; both vary with complex layouts (MEDIUM confidence — empirical observation)

---
*Pitfalls research for: v4.0 Pipeline Quality & Entity Resolution*
*Researched: 2026-06-03*
