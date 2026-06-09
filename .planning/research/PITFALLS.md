# Domain Pitfalls — v7.0 Event-Centric Rewrite (PostgreSQL, Smart Chunking, Event Object Model)

**Domain:** Stripping and rebuilding the references/entities/events system with a unified event object model, PostgreSQL schema, smart document chunking (512KB), and clickable reference UI, while preserving a working document ingestion/extraction pipeline

**Researched:** 2026-06-08
**Confidence:** HIGH (existing codebase analysis + domain patterns)

**Context:** The system has already migrated from SurrealDB to PostgreSQL (schema.sql is PostgreSQL DDL). The current v6.x pipeline works end-to-end: document → chunk → LLM extract → store events + references + entities → resolve entities → link participants. v7.0 strips the old references/events/entities system and rebuilds with:
- A unified event object model (references embedded directly in event objects instead of separate tables)
- Smart document chunking targeting 512KB balanced splits
- New PostgreSQL relational schema with N-N relations for events/locations/participants
- Event list + detail UI with clickable reference navigation
- LLM prompts tuned with human rights context

**Critical constraint:** The pipeline must stay working during the migration. No long downtime. Existing documents must be readable during and after the rewrite.

---

## Critical Pitfalls

### Pitfall 1: Replacing in Flight — Dropping Old Tables Before New Schema Is Validated

**What goes wrong:**
The current `event`, `reference`, `canonical_entity`, `event_entity_link`, and `event_participant` tables are live. The v7.0 rewrite wants to strip the "old" system. The natural instinct is to `DROP TABLE` the old references/entities tables and `CREATE TABLE` the new unified event schema. If the new schema has a bug (missing index, wrong foreign key, wrong data type for the LLM output), the pipeline breaks for ALL documents — old and new. The Temporal worker starts failing on every workflow. The UI shows empty pages. Recovery requires restoring from backup or manually recreating old tables from scratch.

**Why it happens:**
- "We're replacing it, so the old stuff is dead" — developer optimism about the new schema being correct on first try
- The `CREATE TABLE` DDL is applied by `init_schema.py` which runs once at startup — there's no rolling migration framework
- The DELETE cascade in `store_extraction_results_activity` hardcodes table names — when the old tables vanish, the activity crashes
- Existing integration tests process a document and check for specific table rows — after the schema changes, test assertions fail or silently pass with wrong data

**Prevention:**
- **NEVER drop old tables during v7.0 implementation.** The old schema stays live throughout the rewrite. The new unified schema is built as NEW tables (`event_v2`, `reference_embedded`, etc.) alongside the old tables. The old pipeline continues writing to old tables. The new pipeline writes to new tables. Cutover is a single flag flip: update the workflow activity to write to new tables instead of old ones.
- **Implement a feature flag:** `USE_V2_EVENT_SCHEMA` environment variable. When `false` (default during development), `store_extraction_results_activity` writes to old tables. When `true`, it writes to new tables. This lets you deploy the new schema, run both schemas in parallel, compare results, and flip the switch only when validated.
- **Old table cleanup is the LAST step, not the first.** Only drop old tables after: (a) new schema has processed 10+ real documents, (b) integration tests pass with new schema, (c) rollback plan exists, (d) all old data is migrated or archived.
- **Migration SQL must be additive-only.** `CREATE TABLE IF NOT EXISTS`, `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`. No destructive DDL until the very end.

**Warning signs:**
- A SQL migration file containing `DROP TABLE`, `DROP COLUMN`, or `DROP INDEX`
- A PR that removes code from `store_extraction_results_activity` without adding new storage code
- Integration tests being rewritten instead of extended (new tests for new schema, old tests stay passing)
- Developer says "we'll clean up the old stuff in the same PR"

**Phase to address:**
- Phase 1 (Foundation): Build new tables alongside old ones. Add `USE_V2_EVENT_SCHEMA` flag. Verify both schemas coexist.
- Phase 8 (Cleanup): Drop old tables only after new system is validated with real documents.

---

### Pitfall 2: Smart Chunking at 512KB — Balanced Splits Splitting Mid-Sentence, Breaking LLM Coherence

**What goes wrong:**
The current chunker (`DocumentChunker` in `chunker.py`) uses a simple `RecursiveCharacterTextSplitter` with 128K character target and zero overlap. v7.0 targets `512KB` chunks with "balanced splits." The risk: the recursive splitter uses `["\n\n", "\n", ". ", " ", ""]` as separators. At 512KB, paragraphs are large and the splitter often falls through to word-boundary (`" "`) or character-level (`""`) splitting. This produces chunks that:
- Split in the middle of a sentence: `"...el juez determinó que el acu"` + `"sado debía comparecer..."` — the LLM sees fragments
- Break in the middle of a Spanish legal phrase: `"...conforme a lo dispuesto en el artícu"` + `"lo 14 de la Constitución..."` — the LLM can't resolve the reference
- Produce unbalanced chunks: one chunk is 512KB, the next is 12KB (the tail end after a heading), wasting prompt capacity

**Why it happens:**
- The `RecursiveCharacterTextSplitter` uses greedy splitting — it packs as much text as possible up to `chunk_size`, then moves on. It has no concept of "balance" across chunks
- The default separator fallthrough (`""`) breaks at character boundaries — the worst possible split for an LLM
- At 128K (current size), falling through to word-boundary is rare. At 512KB, paragraph-length text in Spanish legal documents means the splitter hits `"\n\n"` less often per chunk (paragraphs are shorter than 512KB but the splitter still needs to find N separators to fill the chunk)
- Spanish legal text uses long compound sentences with many commas and semicolons — the `. ` separator doesn't occur as frequently as in English prose

**Prevention:**
- **Do NOT use `RecursiveCharacterTextSplitter` for 512KB balanced splits.** It fundamentally can't produce balanced chunks. Instead:
  1. **Two-pass chunking:** First pass identifies natural break points (sentence boundaries, paragraph boundaries, section headings). Second pass groups these breakpoints into roughly equal-sized chunks. This guarantees no mid-sentence splits and balanced sizes.
  2. **Or use sentence-aware splitting:** Detect sentence boundaries with regex (`[.!?]\s+[A-Z¿¡]`) before chunking. Build chunks by accumulating sentences until the next sentence would exceed the target, then start a new chunk.
- **Implement a `max_overrun` parameter:** If a single sentence exceeds 512KB (rare for legal text but possible for a single court order paragraph), split at the first natural break within the sentence (semicolon, comma-separated clause). Never split mid-word.
- **Add chunk quality metrics:** After chunking, measure: (a) size variance across chunks (target: stddev < 20% of mean), (b) number of sentence fragments (target: 0), (c) number of chunks that end mid-paragraph (target: 0). Fail the chunking activity if quality is below threshold.
- **Target 512KB binary chunks (text encoded as bytes), not characters.** Spanish text with tildes and ñ characters is multi-byte — 512KB != 512K characters. The LLM's context window is measured in tokens, which roughly correspond to word-syllable units. A safe rule: target 384K characters for 512KB binary, providing headroom for Unicode expansion.
- **Validate with actual documents.** Test on the existing test corpus (Spanish legal documents). Log chunk sizes, sentence fragments, and split points. Verify no chunk is below 100KB or above 600KB.

**Phase to address:**
- Phase 2 (Smart Chunking): Build the new chunker with quality metrics. The existing chunker stays as fallback. Integration tests must verify zero sentence fragments.

---

### Pitfall 3: Part-by-Part LLM Processing with Accumulated Context — Context Window Bloat and Hallucination Cascade

**What goes wrong:**
The current `extract_events_activity` already processes long documents in chunks: for each chunk, it passes `prior_events=all_events` (the accumulated list of previously extracted events) as context for the next chunk. At 512KB chunks with ~20 chunks per document (assuming a 10MB legal document), chunk 20 receives prior events from chunks 1–19. If each chunk produces ~10 events, that's 190 prior events passed as context — potentially thousands of tokens of serialized JSON. The LLM prompt for chunk 20 is: [512KB chunk text] + [190 prior events as JSON] = most of the context window is consumed by prior events, not the actual text to analyze.

This produces:
1. **Hallucination cascade:** Chunk 5 sees prior events from chunks 1–4. Chunk 10 sees events from chunks 1–9. By chunk 15, the LLM starts "finding" events in its current chunk that are suspiciously similar to prior events — it's pattern-matching against the accumulated list rather than extracting from the text. Events start duplicating.
2. **Context window overflow:** At 128K context (standard models), 512KB of text doesn't fit. Even at 200K context (Claude 3.5 Sonnet), 512KB of raw text + accumulated prior events + system prompt exceeds the limit. The LLM provider truncates the prompt silently.
3. **Duplicate event explosion:** The LLM sees similar events in prior context and creates new but nearly identical events in the current chunk. By the end of the document, you have 3–5 duplicates of the same event with slightly different verbatim references.

**Why it happens:**
- The current code in `extract_events_activity.py` passes `prior_events` as a naive list — no deduplication, no summarization, no limit on size
- The `EXTRACTION_CHUNK_SIZE` is currently ~128K but the chunker produces 128K chunks; text + prior events + system prompt can exceed the model's context window
- At 512KB chunks, the problem is 4× worse — bigger chunks, more prior events, tighter context window pressure
- The LLM is not instructed to avoid duplicating events it already sees in prior context — there's no anti-duplication instruction in the system prompt

**Prevention:**
- **Stop passing raw prior events as context.** This is the most impactful single change. Instead of passing the full list of prior events:
  1. **Pass a summary instead:** After each batch of chunks, ask the LLM to produce a 1-paragraph summary of extracted events. Pass only this summary (not the full event list) to subsequent chunks. This caps the "prior context" at ~500 tokens regardless of document length.
  2. **Or use a hybrid: pass only event IDs + short descriptions** (2–5 words each). This is <50 tokens even for 100 prior events.
- **Add an anti-duplication instruction to the system prompt:** "NO extraigas eventos que ya aparecen en el contexto previo. Si un evento ya fue extraído en un fragmento anterior, NO lo extraigas de nuevo en este fragmento. Revisa cuidadosamente la lista de eventos previos antes de extraer nuevos eventos."
- **Post-processing deduplication:** After all chunks are processed, run a deduplication step that groups similar events by `que_paso` text (using semantic similarity: cosine distance on embeddings or simple TF-IDF + threshold). Merge duplicates: combine references, keep the most complete `que_paso`.
- **Cap the prior events list at 10 most recent events.** Research (Anthropic, 2024) suggests that LLMs use recent history most effectively. Passing the full 190-event list is worse than passing the last 10 — the LLM ignores the middle.
- **Monitor chunk extraction quality:** Log the number of events per chunk. If chunk N+1 produces significantly fewer events than chunk N (e.g., 10 events vs. 2 events), the prior context may be overwhelming the current chunk's signal. Flag for review.

**Phase to address:**
- Phase 3 (LLM Pipeline): Implement summary-based context passing, anti-duplication instruction, post-processing dedup. Test on 10+ real documents.

---

### Pitfall 4: References Embedded in Event Objects — Losing Referential Integrity

**What goes wrong:**
Currently, references are a separate PostgreSQL table (`reference`) with foreign keys to `event` and `canonical_entity`. v7.0 wants references embedded directly in event objects as JSON (e.g., `event.references` as a JSONB array). This means:
- References can no longer be independently queried: `SELECT * FROM reference WHERE canonical_entity = $1` becomes `SELECT id FROM event WHERE references @> '[{"canonical_entity": $1}]'` — a JSON containment query that requires a GIN index and is 10–100× slower than a direct FK lookup
- Entity resolution (which finds references, groups them, links them to canonical entities) must now parse JSON from every event record instead of querying a flat table
- Cascade deletion becomes complex: you can't `DELETE FROM reference WHERE event = $1` (there's no separate table). You must `UPDATE event SET references = '[]'::jsonb WHERE document = $1` or delete the event entirely
- Merge/split of canonical entities requires: (a) find all event records where any reference in `references` has `canonical_entity = $old_id`, (b) update the JSON to replace with `$new_id`. This is `UPDATE event SET references = (SELECT jsonb_agg(CASE WHEN ref->>'canonical_entity' = $1 THEN jsonb_set(ref, '{canonical_entity}', to_jsonb($2)) ELSE ref END) FROM jsonb_array_elements(references) AS ref) WHERE references @> '[{"canonical_entity": $1}]'` — an unreadable, unmaintainable query

**Why it happens:**
- "Embedded references feel more natural for the LLM to produce" — the LLM output is a JSON structure where references are children of each event. Storing them as-is avoids parsing/splitting.
- "It's simpler for the UI" — the event detail view needs references alongside event data. Embedding avoids a JOIN.
- The existing schema ALREADY stores references as a separate table with a well-designed foreign key structure. The embed-vs-reference debate is between "store what the LLM produces" and "store what's queryable."

**Prevention:**
- **Do NOT embed references in event JSONB if any of these conditions exist:**
  1. References need independent querying (by document, by canonical entity, by reference_type, by verbatim text span) — they do (entity resolution, References tab, merge/split)
  2. References are resolved to canonical entities that can be merged/split — they are (entity resolution + merge/split already work)
  3. References need to be bulk-updated (e.g., during entity merge: rewrite all references from old canonical entity to new one) — this is a core operation
- **Instead, keep the separate `reference` table but restructure the relationship:**
  - Add `event_id` FK to the reference table (already exists)
  - Add a `reference_order` column to maintain array ordering within an event
  - Remove the old `event_entity_link` table and `canonical_entity` table's reference to events (they're being stripped)
  - The `reference` table IS the embedded references — it's just not stored as a JSON blob
- **If you MUST embed:** Create a PostgreSQL function to handle the complex JSON update:
  ```sql
  CREATE OR REPLACE FUNCTION update_reference_canonical_entity(
      old_ce_id TEXT, new_ce_id TEXT
  ) RETURNS INTEGER AS $$
  DECLARE
      updated INTEGER;
  BEGIN
      UPDATE event SET references = (
          SELECT jsonb_agg(
              CASE WHEN ref->>'canonical_entity' = old_ce_id
              THEN jsonb_set(ref, '{canonical_entity}', to_jsonb(new_ce_id))
              ELSE ref END
          )
          FROM jsonb_array_elements(references) AS ref
      )
      WHERE references @> format('[{"canonical_entity": %s}]', to_jsonb(old_ce_id))::jsonb;
      GET DIAGNOSTICS updated = ROW_COUNT;
      RETURN updated;
  END;
  $$ LANGUAGE plpgsql;
  ```
  Add a GIN index on `event.references`: `CREATE INDEX idx_event_references ON event USING GIN (references);`
- **The litmus test:** Write the entity merge query using embedded references. If it looks like the monstrosity above, keep the separate table.

**Phase to address:**
- Phase 1 (Foundation): Decide table vs. JSONB for references. If keeping table (recommended), evolve the reference table schema rather than removing it. If embedding, add GIN index and helper function before any data is written.

---

### Pitfall 5: N-N Relations for Events/Participants/Locations — Over-Normalization vs. Query Performance

**What goes wrong:**
The v7.0 schema needs to model: an event has many participants (N-N), an event has one location (1-N, a location can appear in many events), an event has many references (1-N). The natural relational instinct is to create:
- `event_participant` junction table (already exists)
- `event_location` junction table (even though the current schema stores location as `location_point` JSONB + `location_place_id` FK on the event table)
- `participant_role` enum table
- `location` table with address fields, coordinates, metadata

This produces 4–5 tables for what is essentially: event → [people, place, text spans]. Each new table requires CRUD operations in the pipeline, cascade delete handling, merge/split handling, and API endpoint support. The current schema already has `event_participant` with a role + confidence — adding `location` as a separate table instead of JSONB on the event adds minimal query benefit (how often do you query "find all events at this exact lat/lon"? — almost never; you query "find events near this point" which is a spatial query on coordinates, not an FK lookup).

**Why it happens:**
- "We're moving to PostgreSQL, so let's normalize properly" — relational database best practices are applied without considering query patterns
- The existing `event_participant` table sets a precedent for normalization — developers extend this pattern to locations
- Future-proofing: "What if we need to add metadata to location-event links?" (e.g., "was the location confirmed by geocoding?") — the answer is `event.location_point` JSONB, not a new table
- The system is Spanish legal documents — a location is typically a court name + city, not a precise address that needs its own lifecycle

**Prevention:**
- **Keep `event.location_point` as JSONB** (already the case in schema.sql). Do NOT create an `event_location` table. The spatial index on `location_point` (MTREE DIMENSION 2) provides efficient spatial queries without a separate table.
- **Keep `event.location_place_id` as a nullable FK** to `canonical_entity` WHERE `entity_type = 'place'`. This is already in schema.sql. This FK satisfies the rare query "find all events tied to this canonical place entity."
- **Keep `event_participant` as-is** (already well-designed with `in_event`, `out_entity`, `role`, `confidence`). Do NOT split participants into a `person` table. `canonical_entity` WHERE `entity_type = 'person'` IS the person table.
- **Rule of thumb for N-N tables in this domain:** Create a junction table ONLY when the relationship has metadata that can't fit in a JSONB field. `event_participant` has `role` and `confidence` — the existing table is appropriate. `event_location` would have... nothing except the link itself — use `event.location_place_id` FK.
- **Verify with a checklist before creating ANY junction table:**
  - [ ] Does the relationship have attributes beyond the link itself? (Yes → table; No → FK)
  - [ ] Will we query this relationship independently of events? (Yes → table; No → FK or JSONB)
  - [ ] Will this entity need its own merge/split lifecycle? (Yes → separate table + canonical_entity link; No → JSONB or FK)

**Phase to address:**
- Phase 1 (Foundation): Finalize the relational model. The current schema is close to correct. Add `event_participant` indexes if missing. Keep `location_point` as JSONB. Do NOT add new junction tables.

---

### Pitfall 6: Clickable Reference Text Highlighting — Offsets Drift During Document Reprocessing

**What goes wrong:**
The current references store `span_start` and `span_end` character offsets into the original document text. The clickable reference UI needs to highlight these spans in the rendered document view. When a document is reprocessed (e.g., the user re-uploads a new version of the same PDF with minor corrections), the text changes slightly — a page break moves, a typo is fixed. Now the stored `span_start`/`span_end` offsets point to wrong locations. The highlight appears at the wrong position or highlights garbled text. If the document was re-OCR'd and the text changed significantly, offsets may point past the end of the string.

The existing `reference` table stores offsets without a `document_version` or `text_hash` field — there's no way to detect that the document has changed since the references were extracted.

**Why it happens:**
- Offsets are computed once during extraction and stored as static integers — they're never validated against the document text
- The system uses `compute_reference_offsets()` in `store_extraction_results.py` which maps global character offsets to page-level offsets — but this mapping is done once and never re-verified
- There's no mechanism to flag "stale offsets" when a document is reprocessed — the new extraction creates new references with new offsets, but if the document text hasn't changed, the old references (from old extraction) remain with their correct offsets; it's the CHANGE in document text that's the problem
- The UI renders document text by fetching `document.text_content` — but if this differs from the text that was chunked during extraction (because the blob was re-extracted), the offsets don't match

**Prevention:**
- **Store a `text_content_hash` field on the `event` or `reference` table** — a SHA256 of the document text at extraction time. Before rendering a reference highlight, verify the current document text hash matches the hash stored with the reference. If not, show a warning: "Esta referencia corresponde a una versión anterior del documento."
- **Validate offsets at render time.** When the UI requests a document with highlights, the API should:
  1. Load the document text
  2. For each reference with `span_start`/`span_end`:
     - Verify `span_start < len(text) and span_end <= len(text)`
     - Verify `text[span_start:span_end]` actually matches `reference.verbatim_text` (or a close fuzzy match for minor OCR changes)
     - If validation fails, return the reference with `offset_valid: false` instead of crashing or rendering wrong highlights
- **Use fuzzy text matching as fallback.** If exact offset match fails, search for `reference.verbatim_text` in the document text using fuzzy matching (Levenshtein distance < 20% of text length). If found, return the discovered offsets with `offset_fuzzy: true`.
- **Store the chunk context too.** For each reference, store `chunk_text_snippet` (200 chars of surrounding text at extraction time). This helps the fuzzy matcher locate the reference even if the document has minor edits.
- **In the UI, render invalid offsets gracefully.** Don't crash. Show the reference text with a "ubicación no disponible" badge. Allow the user to manually locate it by searching.

**Phase to address:**
- Phase 4 (Event UI): Add offset validation + fuzzy fallback to the API. Add `text_content_hash` to the pipeline storage. Build the highlight renderer with error handling.

---

### Pitfall 7: Human Rights Context in Prompts — Safety Filter Triggering Halts Extraction Mid-Document

**What goes wrong:**
The system processes Spanish legal documents about human rights violations. These documents contain: torture descriptions, forced disappearances, political violence, sexual violence, death threats. The LLM's built-in safety classifiers (OpenRouter moderation, Claude content filters, GPT safety systems) flag this content as "harmful" and block the response. When this happens mid-extraction:
- The LLM returns a refusal message instead of structured JSON: "I'm sorry, I cannot process this request as it contains harmful content"
- The JSON Schema validation in `llm.py` fails because the response is not valid JSON
- The activity returns `{"error": "LLM response is not valid JSON"}` — the workflow fails
- The entire document must be reprocessed, consuming more tokens and potentially hitting the filter again
- For chunked extraction, one chunk triggers the filter but the other chunks would have been fine — the whole extraction is wasted

Spanish civil war/Carlos Soublette-era documents are especially vulnerable: the LLM sees "tortura," "ejecución," "desaparición forzada" and the safety classifier fires even though these are historical legal records, not hate speech or incitement to violence.

**Why it happens:**
- LLM safety classifiers are trained on English-language "harmful content" datasets — they have poor precision for Spanish legal text about historical human rights violations
- The current system prompt (`EXTRACTION_SYSTEM_PROMPT`) doesn't address this — it's purely functional ("Extrae eventos de documentos legales...")
- OpenRouter passes through the provider's default safety settings — no opt-out
- The JSON Schema `additionalProperties: false` makes any non-JSON response a hard failure — there's no graceful degradation for safety filter responses

**Prevention:**
- **Add human rights context to the system prompt.** Instruct the LLM that these documents are legal/historical records and the context is professional research, not harmful speech:
  ```text
  "Este documento es un registro legal/histórico de un caso de derechos humanos. 
  Estás analizando este documento para fines académicos/de investigación. 
  El contenido puede describir violencia o abusos — esto es un registro factual, 
  no incitación al odio ni contenido dañino. Es tu deber profesional extraer 
  los eventos con precisión. NO rechaces extraer eventos por motivos de seguridad 
  — este es un análisis legal legítimo."
  ```
- **Opt out of safety moderation explicitly.** For OpenRouter, set `X-OpenRouter-Moderation: off` in headers. For Claude, use the system message prefix `[SAFETY: this is a legal document analysis task]`. For GPT, use the `system` role level instructions.
- **Handle filter-triggered responses gracefully.** In `extract_events.py`, detect refusal patterns ("I cannot", "I'm sorry", "harmful content", "I apologize" — with Spanish translations like "no puedo", "lo siento", "contenido dañino"). When detected:
  1. Log the chunk index and the triggering text
  2. Return the chunk's events as empty (don't fail the whole document)
  3. Record a processing log entry: "Safety filter triggered on chunk 5 — continuing with remaining chunks"
  4. The workflow continues with subsequent chunks
- **Add a per-chunk retry with simplified prompt.** If chunk extraction fails due to filter, retry with a minimized prompt (no system message, just "Extrae eventos de este texto legal: [text]") — the shorter prompt is less likely to trigger classifiers.
- **Pre-scan documents for trigger words.** Before sending to the LLM, scan the document text for high-risk patterns ("tortura", "violación", "asesinato", "cadáver", etc.). Log these as warnings. If >10 trigger words are found, wrap the document in additional safety context.
- **Test with actual documents.** Run the full pipeline on the test corpus before deploying the prompt change. Verify zero refusals for all documents.

**Phase to address:**
- Phase 3 (LLM Pipeline): Update system prompt with human rights context, add refusal detection + graceful degradation, add OpenRouter header override.

---

### Pitfall 8: Removing Old References/Entities/Events System — Orphan Cleanup Creates Transient Data Inconsistency

**What goes wrong:**
The old system has accumulated data across multiple tables:
- `reference` (contains FK to `event` and `canonical_entity`)
- `event` (contains FK to `document`)
- `canonical_entity` (contains FK to itself via `superseded_by`, FK from `reference.canonical_entity` and `reference.entity_id`)
- `event_entity_link` (FK to `canonical_entity` on both sides)
- `event_participant` (FK to `event` and `canonical_entity`)

When v7.0 removes or restructures these, the migration must handle existing data. The tempting approach: "just drop the tables and reprocess everything." But:
- Existing documents are linked to entities that might be referenced in entity merge/split operations — dropping `canonical_entity` loses merge/split provenance
- The `superseded_by` FK on `canonical_entity` points to other canonical entities — dropping the table while `superseded_by` values exist causes FK violations
- Deleting all old events, references, and entities to reprocess means the UI shows empty pages for the duration of the reprocess — users see "no data" for minutes or hours
- If reprocessing fails mid-way, some documents are in the new format and some are in the old format — the application must handle both formats simultaneously

**Why it happens:**
- "We're rebuilding from scratch, so start fresh" — developers underestimate the cost of reprocessing every document
- The cascade delete on `DELETE /documents/{id}` already handles all related tables — but this is designed for single-document deletion, not bulk
- `canonical_entity` records can be shared across documents (via entity resolution) — deleting all canonical entities for all documents loses cross-document entity links
- The merge/split provenance (`superseded_by`, `split_from`) is stored on `canonical_entity` — dropping the table loses this history permanently

**Prevention:**
- **Implement a phased cleanup, NOT a single DROP operation:**
  1. **Phase A — Freeze old tables:** Stop writing to old tables (the feature flag in Pitfall 1 now directs all writes to new tables). Old tables become read-only.
  2. **Phase B — Migrate select data:** If entity merge/split history is valuable, migrate `canonical_entity` records (merged/split ones) to a `entity_history` JSONB field or a new `entity_audit` table. Don't migrate every event — just the canonical entities that have been manually merged or split.
  3. **Phase C — Archive old tables:** `ALTER TABLE reference RENAME TO reference_archive_20260608`. They stay in the database but out of the active schema. Queries target new tables.
  4. **Phase D — Drop old tables:** Only after 2 weeks of no issues. By then, the archive tables are confirmed unused.
- **Do NOT bulk-reprocess.** The new schema should be backward-compatible for READ operations. Old data (unmigrated) shows as "processed with legacy schema" with a note: "Reprocess this document to view in the new event format." This avoids a multi-hour reprocess job.
- **The `core_cleanup` activity must handle partial state.** If some documents are in old format and some are in new format, the API should detect the document's schema version and serve appropriate responses. A `schema_version` field on the `document` table tracks this.
- **Graceful degradation for entity merge/split:** If old `canonical_entity` records are archived, the merge/split endpoints return a clear error: "Esta entidad fue creada con el esquema anterior. No se puede modificar."

**Phase to address:**
- Phase 7 (Cleanup): Phased migration with read-backward-compatibility. Archive, don't delete. No bulk reprocess.

---

### Pitfall 9: Clickable Reference UI — Modal State Management and Text Highlighting Accuracy

**What goes wrong:**
The event detail UI needs to show:
1. An event list (paginated table)
2. Clicking an event opens a detail panel showing event data + references
3. Each reference shows verbatim text + "Ver en documento" button
4. Clicking this button opens the document viewer, scrolls to the reference's location, and highlights the text span
5. The user can close the highlight and return to the event list

With vanilla JS (no React, no state management library), managing these modal states is error-prone:
- Opening event detail while a reference highlight is active must close the highlight
- Navigating to another page in the event list while a detail panel is open must either close it or persist the panel state
- The document viewer (either a modal overlay or an inline panel) must track the current document, current event, and current reference independently
- Browser back/forward navigation (popstate) can break the modal stack — pressing "back" might navigate away from the app instead of closing the highlight

**Why it happens:**
- The SPA is a single `index.html` file with vanilla JS — no state management, no routing, no component lifecycle
- The existing tab system manages one level of state (which tab is active) — adding nested state (event detail panel → reference highlight → document viewer) creates 3 levels of modal state
- The existing code uses global variables (`currentPage`, `currentSearch`, `currentFilter`) — adding `currentEvent`, `currentDocumentView`, `currentHighlight` creates naming collisions and state inconsistency
- Text highlighting in the document viewer requires computing character positions from `span_start`/`span_end` and mapping them to rendered DOM elements — if the document text is rendered as innerHTML of a `<pre>` or `<div>`, the offset-to-DOM mapping is fragile
- The document text might be HTML-encoded (e.g., `&ntilde;` for ñ) — character offsets in the text_content (which are UTF-8 based) don't match character positions in the rendered HTML (which are HTML-entity based)

**Prevention:**
- **Use a simple state machine, not global variables.** Define a `ViewState` object:
  ```javascript
  const viewState = {
    activeTab: 'events',
    activeEventId: null,
    activeDocumentId: null,
    activeHighlightRef: null,
    modalStack: [], // ['event-detail', 'document-viewer']
  };
  ```
  All UI state transitions go through a single `setViewState(updates)` function that handles transitions cleanly (e.g., setting `activeHighlightRef` opens the document viewer, which pushes onto `modalStack`).
- **Render reference highlights using absolute positioning, not inline `<mark>` tags.** The document viewer should:
  1. Render document text in a `<div>` with `position: relative`
  2. For each highlighted span, create an absolutely-positioned `<mark>` element with `top`/`left` computed from the character offset (using a character-width estimation or a hidden `<span>` ruler element)
  3. This avoids HTML entity offset issues and works with monospace rendering
- **Or use a `<textarea>` for the document viewer** with `selectionStart`/`selectionEnd` for highlighting — but this limits formatting options and feels less polished
- **Better approach: render the document in a `<pre>` tag with character-by-character highlight spans.** For each character position, emit either `<span class="highlight">` or plain text:
  ```javascript
  function renderDocumentWithHighlights(text, highlights) {
    let html = '';
    let pos = 0;
    for (const h of highlights.sort((a,b) => a.start - b.start)) {
      html += escapeHtml(text.slice(pos, h.start));
      html += `<mark class="ref-highlight" data-ref-id="${h.id}">`;
      html += escapeHtml(text.slice(h.start, h.end));
      html += '</mark>';
      pos = h.end;
    }
    html += escapeHtml(text.slice(pos));
    return html;
  }
  ```
  This is O(n) in document length and handles any encoding issues since it uses the raw text.
- **Handle browser back/back history:** Before showing the document viewer, push state to `history`:
  ```javascript
  window.history.pushState({modal: 'document-viewer', refId: refId}, '');
  window.addEventListener('popstate', (e) => {
    if (e.state?.modal === 'document-viewer') closeDocumentViewer();
  });
  ```
- **Debounce highlight scroll.** When opening a reference highlight, scroll the document to the highlight position. But if the user clicks through references quickly, don't scroll-lock the viewport. Use a 200ms debounce on scroll-to operations.
- **Test with a 1000-page document and 200 references.** The JS rendering should not block the main thread for >100ms. If it does, virtualize: render only the visible portion of the document text.

**Phase to address:**
- Phase 5 (Event List UI) and Phase 6 (Event Detail UI): Build the state machine first, then the rendering components. Test with large documents.

---

### Pitfall 10: Chunk Boundary Crossing — References That Span Multiple Chunks

**What goes wrong:**
When chunking at 512KB, a single reference in the document might span across two chunks (e.g., a 5-page judicial resolution that starts in chunk 3 and ends in chunk 4). The LLM extracts the reference in the chunk where it *starts* (chunk 3) and records `span_start` and `span_end` based on global character offsets. But when the UI tries to highlight this span, it needs to know which chunk(s) contain the referenced text. If the `span_start` is in chunk 3 and `span_end` is in chunk 4, highlighting requires loading both chunks and rendering them contiguously — or at least knowing that the span crosses a chunk boundary.

The current system stores chunk-level page offsets but NOT chunk-to-global-offset mapping at the reference level. The `reference` table has `page_number`, `page_offset_start`, `page_offset_end` — but these are page-level, not chunk-level. A reference that spans chunk boundaries can't be highlighted without loading all chunks and computing offsets.

**Why it happens:**
- The original chunker was designed for independent chunk processing (each chunk goes to the LLM separately) — cross-chunk offsets were never considered
- The `reference.page_number` field stores the page, not the chunk — a reference can span 2+ pages, but page boundaries don't always match chunk boundaries
- The `compute_reference_offsets` function in `offsets.py` maps spans to pages, not to chunks — it doesn't detect chunk boundary crossing
- At 128KB (current chunk size), cross-chunk references are rare. At 512KB, they become much more common (because each chunk covers more text, so a reference that starts in the last paragraph of chunk N and ends in the first paragraph of chunk N+1 spans chunks even though it's a single continuous text span

**Prevention:**
- **Add `chunk_index` + `chunk_offset_start` + `chunk_offset_end` to the reference table.** These store the reference's position relative to the chunk it was extracted from, not the global document. The global offsets are also stored (for backward compat) but the chunk-relative offsets are used for UI highlighting.
- **Track chunk boundaries in the extraction activity.** When `extract_events_activity` processes chunk N, it should record `chunk_index` for each reference. When storing, save this along with the offsets relative to the chunk start:
  ```sql
  -- In the reference table (new fields):
  extraction_chunk_index INTEGER,     -- which chunk produced this reference
  chunk_offset_start INTEGER,          -- offset within that chunk
  chunk_offset_end INTEGER             -- offset within that chunk
  ```
- **In the UI, render references by chunk.** When highlighting a reference, load only the chunk that produced it, not the full document. This avoids loading 10MB of text to highlight 200 characters.
- **Detect cross-chunk references at storage time.** If a reference's `span_end` exceeds the chunk's `offset_end`, it crosses a boundary. Flag it with `crosses_chunk_boundary = true`. The UI can show "Esta referencia cruza el límite entre fragmentos" but still attempt to highlight up to the chunk boundary.
- **Post-processing merge of cross-chunk references.** The deduplication step (Pitfall 3) should detect when two references in adjacent chunks have the same text and are continuous — merge them into one.

**Phase to address:**
- Phase 3 (LLM Pipeline): Add chunk-relative offsets to reference storage.
- Phase 6 (Event Detail UI): Handle cross-chunk reference display.

---

### Pitfall 11: Temporal Replay Safety — Stripping Old Tables Breaks the Nullify-Then-Recreate Pattern

**What goes wrong:**
The current `store_extraction_results_activity` deletes old data before writing new data:
```python
await conn.execute("DELETE FROM event_participant WHERE in_event IN ...")
await conn.execute("DELETE FROM reference WHERE event IN ...")
await conn.execute("DELETE FROM event WHERE document = $1", document_id)
```

If v7.0 removes or renames these tables, the activity crashes on Temporal replay because it tries to `DELETE FROM event_participant` but that table no longer exists. Even with the feature flag approach (Pitfall 1), if an old workflow is replayed after the schema change, the replay will fail because the activity code references tables that were dropped.

Temporal replay replays the ENTIRE workflow history — including activities that ran before the schema change. On replay, it calls the activity with the same arguments. If the activity code has changed to use new table names, the replay fails. If the activity code has NOT changed (still uses old table names), but the old tables were dropped, the replay also fails.

**Why it happens:**
- Temporal workflow history is immutable — replay always uses the CURRENT code, not the code that was deployed when the workflow first ran
- The nullify-then-recreate pattern hardcodes table names in SQL strings — changing these names breaks replay of in-flight workflows
- There are `~50` in-flight documents at any given time (documents being processed) — the schema change affects ALL of them, not just new ones
- The existing codebase has no versioning mechanism for Temporal activities — no `patch`, no version markers

**Prevention:**
- **Wait for all in-flight workflows to complete before applying destructive schema changes.** Before deploying the v7.0 schema migration:
  1. Check `SELECT COUNT(*) FROM document WHERE status NOT IN ('processed', 'failed')` — ensure zero in-flight
  2. Process all pending documents to completion
  3. Then apply the migration + deploy new worker code
- **If zero in-flight is impossible (very long documents), use Temporal patches:**
  ```python
  @workflow.defn
  class DocumentProcessingWorkflow:
      @workflow.run
      async def run(self, document_id: str) -> dict:
          use_v2 = workflow.patched("v7-event-schema")
          # ... later in the workflow:
          if use_v2:
              await workflow.execute_activity(
                  store_extraction_results_v2_activity, ...
              )
          else:
              await workflow.execute_activity(
                  store_extraction_results_activity, ...
              )
  ```
  This ensures old workflows use old activities and new workflows use new ones.
- **DO NOT reuse activity function names for new logic.** Create `store_extraction_results_v2_activity` as a new function. The old activity stays unchanged (even if it's dead code) to support replay of in-flight workflows.
- **Test replay explicitly.** Start a document workflow, stop the worker during extraction, apply the schema migration, restart the worker. Verify the workflow completes successfully.

**Phase to address:**
- Phase 7 (Cleanup): Wait for in-flight workflows, use Temporal patches if necessary, keep old activity functions for replay support.

---

### Pitfall 12: PostgreSQL Full-Text Search — JSONB References Break Text Search

**What goes wrong:**
The existing `reference` table is a flat structure with `verbatim_text` — queryable via PostgreSQL full-text search (`to_tsvector('spanish', verbatim_text) @@ plainto_tsquery('spanish', $search)`). The References tab supports text search across all references.

If v7.0 embeds references in `event.references` JSONB, the full-text search must use `jsonb_to_tsvector('spanish', references, '"verbatim_text"')` — a PostgreSQL 14+ function that converts selected JSONB keys to tsvector. This is:
- Slower than a direct tsvector column (the JSONB must be parsed on every query)
- Harder to index (requires a GIN index on `to_tsvector` expression, not a simple GIN on JSONB)
- Impossible to filter independently of events (you can't search "all references containing 'tortura'" — you must search "all events where any reference contains 'tortura'")

The current `reference` table has 7 indexes including `idx_reference_entity_id` and `idx_reference_canonical_entity`. Replacing these with JSONB expressions loses query performance and expressiveness.

**Why it happens:**
- "JSONB is flexible and queryable" — while true for simple lookups, JSONB is NOT good for full-text search or FK-like queries
- The existing text search is on `reference.verbatim_text` — if references go into JSONB, this search index must be recreated as a GIN expression index, which many developers don't know about
- The `event.references` JSONB contains an array of objects — querying array-of-objects JSONB requires `jsonb_array_elements` (a set-returning function) which can't use indexes efficiently

**Prevention:**
- **Keep the separate `reference` table.** It already has everything needed: FK to event, FK to canonical_entity, verbatim_text with full-text search, span offsets, page numbers. Restructuring it from separate table to JSONB removes NO value and adds NO new capabilities.
- **If you MUST embed, add a materialized tsvector column:**
  ```sql
  ALTER TABLE event ADD COLUMN references_tsvector tsvector
    GENERATED ALWAYS AS (jsonb_to_tsvector('spanish', references, '"verbatim_text"')) STORED;
  CREATE INDEX idx_event_references_fts ON event USING GIN (references_tsvector);
  ```
  This makes full-text search fast but adds storage overhead and won't help with independent reference queries.
- **For the "find by entity" use case, keep the FK.** Even with embedded references, maintain `reference` table entries for querying. The LLM output can produce embedded references; the pipeline can normalize them into the table.

**Phase to address:**
- Phase 1 (Foundation): Keep the references table. Extend it with v7.0 fields (chunk_relative offsets, crossing_boundary flag). Do NOT migrate to JSONB embedding.

---

### Pitfall 13: Cascade Delete — Old and New Tables Both Must Be Cleaned Up

**What goes wrong:**
The `DELETE /documents/{id}` endpoint currently cascades through `event_participant` → `reference` → `event` → `document_event_log` → `llm_usage` → `llm_call_log` → `document_chunk` → `document`. If v7.0 adds new tables (or restructures old ones) without updating the cascade delete, deleting a document leaves orphaned records in the new tables.

The order matters: if new tables reference `event` (which is being replaced), the DELETE must handle new tables before or after the event deletion depending on FK direction. If a new `event_v2.reference_highlights` table has FKs to `event_v2`, but `event_v2` is deleted by the cascade, the FKs must be handled (ON DELETE CASCADE) or explicitly deleted first.

The delete cascade in `documents.py` (1322 lines — one of the most complex files) is implemented as a sequence of parameterized SQL DELETE statements. Adding a new table means adding another DELETE statement in the correct position. Missing it means orphans.

**Why it happens:**
- The cascade delete is a ~30-line sequence of DELETE statements, added incrementally across 6 milestones — each milestone added tables but not all added cleanup code
- The new schema may use `ON DELETE CASCADE` FKs (which auto-clean) or manual DELETE statements — mixing both patterns creates confusion about which tables auto-clean and which need explicit deletion
- The test for cascade delete (`create → delete → assert zero records`) must enumerate ALL tables — if a new table is added, the test must be updated too
- The existing test might only check a subset of tables: "Does the document row still exist?" (no) but not "Does every new table have zero rows for this document?" — a partial check

**Prevention:**
- **Enumerate ALL tables in the cascade delete code as a list, with a comment for each:**
  ```python
  # New v7.0 tables:
  await conn.execute("DELETE FROM event_v2_reference WHERE event_v2_id IN ...")
  await conn.execute("DELETE FROM event_v2 WHERE document = $1", document_id)
  
  # Old tables (v6.x):
  await conn.execute("DELETE FROM event_participant WHERE in_event IN ...")
  await conn.execute("DELETE FROM reference WHERE event IN ...")
  await conn.execute("DELETE FROM event WHERE document = $1", document_id)
  # ... etc
  ```
- **Write a test that verifies zero records across ALL tables after delete.** The test should fetch all table names from `information_schema.tables` and for each table, check `SELECT COUNT(*) FROM table_name WHERE document_id_field = $1`:
  ```python
  async def test_cascade_delete_all_tables():
      # Process document → delete document
      # Then for every table that has a document FK:
      tables_with_doc_fk = [
          ("event_participant", "in_event", "event", "id"),
          ("event_participant", "out_entity", "canonical_entity", "id"),
          ("reference", "event", "event", "id"),
          ("event", "document", "document", "id"),
          ("event_v2", "document", "document", "id"),
          # ... every table
      ]
      for table, fk_col, ref_table, ref_col in tables_with_doc_fk:
          count = await conn.fetchval(
              f"SELECT COUNT(*) FROM {table} WHERE {fk_col} IN "
              f"(SELECT {ref_col} FROM {ref_table} WHERE document = $1)",
              document_id
          )
          assert count == 0, f"{table} still has {count} records after document delete"
  ```
- **Use ON DELETE CASCADE on new FKs.** For any new table that references `event_v2` or `document`, add `ON DELETE CASCADE` to the FK:
  ```sql
  event_v2_id TEXT NOT NULL REFERENCES event_v2(id) ON DELETE CASCADE
  ```
  This ensures that deleting an event_v2 row automatically cleans up its children, even if the code forgets.
- **But verify ON DELETE CASCADE actually works.** PostgreSQL's ON DELETE CASCADE is invisible — it works silently. The test above should catch any cascade failures.

**Phase to address:**
- Phase 1 (Foundation): Add ON DELETE CASCADE to all new FKs.
- Phase 7 (Cleanup): Update both old and new table cascade deletions. Write the exhaustive test.

---

### Pitfall 14: UI Performance — Rendering 200+ Events With References Crashes Vanilla JS

**What goes wrong:**
The event list shows ~20 events per page (pagination). Each event has up to 20 references, each with verbatim text, offsets, and clickable links. If the event detail panel renders ALL references for the selected event at once (no pagination for references), and a single event has 20 references with full verbatim text (average 200 characters each), that's 4,000 characters of reference text + DOM elements for highlights + event metadata. With 20 events on a page, that's 400 references potentially lurking in the DOM (hidden until expanded). The browser DOM size grows to 10,000+ nodes. Tab switching between Events and Documents becomes sluggish because the hidden references are still in the DOM.

Vanilla JS SPA has no virtual DOM, no lazy rendering, no component lifecycle. Everything rendered is in the DOM until cleared. A single `innerHTML = ...` call with 10,000+ nodes freezes the main thread for 100-500ms.

**Why it happens:**
- The existing `index.html` is already 2,277+ lines and growing — the file has poor separation of concerns between data fetching, rendering, and state management
- Each tab's render function replaces `innerHTML` for the entire tab content — even if only the data changes, the entire DOM subtree is destroyed and recreated
- References are rendered as nested elements inside each event row — when a user expands an event, references are created eagerly (all at once)
- There's no pagination for references within an event — 20 references for 20 events = 400 reference DOM nodes on one page

**Prevention:**
- **Limit references rendered per event to 5.** Show the most relevant references (by confidence). Add a "Ver todas las referencias" link that opens a modal with the full reference list (paginated).
- **Use event delegation for clickable references, not inline onclick handlers.** Instead of `<span onclick="showReference('...')">`, use `<span class="ref-highlight" data-ref-id="...">` and handle clicks at the container level:
  ```javascript
  document.getElementById('tab-events').addEventListener('click', (e) => {
    const ref = e.target.closest('.ref-highlight');
    if (ref) showReference(ref.dataset.refId);
  });
  ```
  This eliminates thousands of event listeners and reduces memory.
- **Lazy-render event detail panels.** When a user clicks an event row, only THEN fetch and render the references:
  ```javascript
  async function onEventClick(eventId) {
    const detailDiv = document.getElementById('event-detail');
    detailDiv.innerHTML = '<div class="placeholder-card">Cargando...</div>';
    const response = await fetch(`/events/${eventId}/detail`);
    const data = await response.json();
    detailDiv.innerHTML = renderEventDetail(data); // only now create DOM nodes
  }
  ```
- **Use `<template>` fragments for event rows.** Instead of building HTML strings, clone a `<template>` element. This is faster than innerHTML for repeated structures and avoids the "escaped HTML" problem.
- **Virtualize the event list.** If the document has 1,000+ events, render only the visible 20 and a buffer of 10 above/below. Use `IntersectionObserver` to detect when the user scrolls near the end and append more rows.
- **Profile before optimizing.** Measure the DOM size and interaction latency with 20 events × 20 references. If <100ms, optimization is unnecessary. If >500ms, implement the above.

**Phase to address:**
- Phase 5 (Event List UI): Use event delegation, lazy detail panels, reference limit.
- Phase 6 (Event Detail UI): Virtualize if needed, profile before optimizing.

---

### Pitfall 15: Event List API Performance — N+1 Queries for Reference Counts and Participant Counts

**What goes wrong:**
The current `GET /events` endpoint returns `reference_count` and `participant_count` for each event. With the current separate-table approach, this is straightforward:
```sql
SELECT e.*, 
  (SELECT COUNT(*) FROM reference r WHERE r.event = e.id) AS reference_count,
  (SELECT COUNT(*) FROM event_participant ep WHERE ep.in_event = e.id) AS participant_count
FROM event e
WHERE e.document = $1
ORDER BY e.created_at
LIMIT 20 OFFSET 0;
```

This is a single query with correlated subqueries — efficient. But if v7.0 changes to embedded JSONB references, these counts must be computed from the JSON:
```sql
SELECT e.*,
  jsonb_array_length(e.references) AS reference_count,
  jsonb_array_length(e.participants) AS participant_count
FROM event_v2 e
WHERE e.document = $1
ORDER BY e.created_at
LIMIT 20 OFFSET 0;
```

The JSONB version is simpler! But if references are in a separate table (recommended), correlated subqueries are fine for 20 events but slow for 10,000 (pagination across all documents, not per-document). The UI shows events for a single document (typically 5–50 events), so per-document queries are fast regardless of approach.

The real problem: when showing ALL events across all documents (the timeline view), a naive query without indexes on `document_id, created_at` scans the entire event table. With 10,000 events across 500 documents (20 events/doc), this is a 10K-row sequential scan + 10K correlated subqueries. At 10K documents, it's 200K events — now the correlated subqueries add ~400K additional index lookups.

**Why it happens:**
- The existing events endpoint is designed for per-document queries (always filtered by document_id) — the timeline endpoint (cross-document) was added later without adjusting the query pattern
- The correlated subqueries for reference/participant counts work well for single-document queries but are inefficient for cross-document queries
- PostgreSQL can optimize `COUNT(*)` subqueries into hash/semi-joins with the right indexes, but only if statistics are up-to-date (autovacuum must be running) and the query plan is analyzed

**Prevention:**
- **For per-document event queries (the common case):** The correlated subquery pattern works fine. Add an index on `reference.event` if not already present (it is: `idx_reference_event`).
- **For cross-document event queries (timeline):** Use a separate index-only query for counts:
  ```sql
  -- First query: get the events
  SELECT e.* FROM event e ORDER BY e.created_at DESC LIMIT 20 OFFSET 0;
  -- Second query: batch-fetch counts for all 20 events
  SELECT r.event, COUNT(*) as ref_count 
  FROM reference r WHERE r.event = ANY($event_ids) GROUP BY r.event;
  ```
  This avoids 20 correlated subqueries with 2 efficient queries.
- **Use PostgreSQL's `EXPLAIN ANALYZE` to verify query plans.** Before adding any index, check the plan. After adding, check again. `Index Only Scan` is the goal.
- **Materialize reference counts on the event table if cross-document queries are frequent.** Add `reference_count INTEGER NOT NULL DEFAULT 0` and update it during `store_extraction_results_activity`. This trades storage for query speed.
- **Add a composite index for the timeline query:**
  ```sql
  CREATE INDEX idx_event_document_created ON event(document, created_at DESC);
  ```

**Phase to address:**
- Phase 4 (Event API): Optimize queries with the two-query pattern for cross-document lists. Add composite indexes.

---

### Pitfall 16: Document Re-processing After Schema Change — Mixed-Format Events in the Same Document

**What goes wrong:**
After v7.0's schema change, a user might want to reprocess an old document. The workflow runs `extract_events_activity` with the new v7.0 prompt, producing v7.0-style events. But the old v6.x events are still in the old tables (if the cleanup hasn't happened yet, per Pitfall 8). The reprocess uses `store_extraction_results_activity` which:
1. Deletes old events (from old tables)
2. Creates new events (in old tables? or new tables?)

If `store_extraction_results` still writes to old tables but the new schema expects data in new tables, the reprocessed data is invisible to the new UI. The user sees "no events" for a document they know has been processed.

If `store_extraction_results` writes to new tables but the old tables still have data (because cleanup skipped this document), both old and new events exist — but they're from the same reprocess. The UI might show duplicates: "Evento: audiencia del 15 de marzo" (from old schema) and "Audiencia del 15 de marzo" (from new schema).

**Why it happens:**
- The migration might not include a step to migrate old events to the new schema — leaving old events in place but writing new events in the new format
- The `store_extraction_results` activity has dual behavior (Pitfall 1's feature flag) — but reprocessing toggles the flag, creating inconsistency
- The UI serves events from either old tables OR new tables, not both — switching the query endpoint mid-migration creates a "now you see them, now you don't" effect
- The document's `status` field is changed to `processed` after reprocessing, but the old events in old tables are not cleaned up because the cleanup script only processes the new tables

**Prevention:**
- **Implement a "schema version" per document.** Add `schema_version TEXT NOT NULL DEFAULT 'v6'` to the document table. When reprocessing with v7.0:
  1. Set `schema_version = 'v7'` before the extraction workflow starts
  2. The API checks `schema_version` and queries the appropriate table(s)
  3. If `schema_version = 'v6'`, query old tables; if `schema_version = 'v7'`, query new tables
- **Clean old events BEFORE writing new ones during reprocessing.** The `store_extraction_results` activity for v7.0 must:
  1. Delete old events from old tables (if any exist)
  2. Delete old events from new tables (if any exist — from a previous v7.0 reprocess)
  3. Write new events to new tables
- **Use a transaction for the entire reprocess.** Wrap the cleanup + write in a single PostgreSQL transaction. If any step fails, everything rolls back — no mixed state.
- **The UI must never query both old and new tables in the same call.** The `schema_version` check ensures you query one or the other. If the document has `schema_version = 'v7'`, the API only queries new tables. If `schema_version = 'v6'`, it only queries old tables.

**Phase to address:**
- Phase 4 (Event API): Add `schema_version` to document table. API routes check version and query appropriate tables.
- Phase 3 (LLM Pipeline): Reprocess workflow deletes from both old and new tables before writing.

---

## Technical Debt Patterns

Shortcuts that seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Keep old AND new tables running in parallel during v7.0 (no cleanup) | Zero migration risk; instant rollback | Schema confusion: 5 old tables + 5 new tables = 10 tables to maintain; every API query checks `schema_version`; future developers must learn both schemas | Acceptable during v7.0 development (Phases 1-6). MUST be resolved in Phase 7. |
| Skip migration of old canonical_entity records to new schema | No migration script needed; old entities remain readable | Old entities can't use new features; merge/split only works on new entities; user has two "entity management" systems | Acceptable only if old entities are clearly marked "legacy" in the UI and merge/split is disabled for them |
| Use a single chunk_size for all documents (512KB) regardless of document length | Simple configuration; one code path | A 2-page document is chunked into one 512KB-attempted chunk (wastes LLM context); a 1000-page document creates 50+ chunks (too many) | Acceptable if the chunker dynamically adjusts: min chunk size (100KB), target chunk size (512KB), max chunks (20) — document smaller than 512KB = single chunk |
| Skip the merge/split API for new event schema (rely on reprocess instead) | Avoids building complex merge/split logic for the new schema | Users can't fix extraction errors without reprocessing the entire document; reprocessing costs tokens; for large documents this is expensive ($0.50-2.00 per reprocess) | NEVER — merge/split is a core feature. Port it to the new schema before releasing. |
| Store LLM usage stats in JSONB on the event table instead of the separate `llm_usage` table | Avoids JOIN for cost-per-event queries | Breaks existing llm_usage reporting; breaks the cost tracking dashboard; migration needed for all historical cost data | NEVER — the `llm_usage` table is already well-designed. Don't restructure it. |
| Hardcode the v7.0 chunker into `chunk_document_activity` without keeping the old chunker as fallback | Simple code; one chunker code path | If the new chunker has a bug (bad splits, wrong offsets), ALL documents fail. No rollback without code revert + deploy. | Acceptable only during active development. Production rollback requires the old chunker to be importable via feature flag. |
| Skip integration tests for "temporary" parallel schema mode | Faster development; fewer test files to maintain | The parallel mode is NOT temporary — it becomes production. Without tests, the parallel mode silently breaks when activities are refactored. The feature flag becomes untested and dangerous to flip. | NEVER — the parallel schema mode is the most critical code path of the migration. Test it. |

## Integration Gotchas

Common mistakes when connecting the new v7.0 schema to the existing pipeline.

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| `store_extraction_results_activity` | Writing new v7.0 events to the SAME table but with new fields | Write to a NEW table (`event_v2` or similar). Old and new tables are separate. The `store_extraction_results` function must check the feature flag and write to the appropriate table. |
| `extract_events_activity` → LLM payload | Passing 512KB of text + 200 prior events = context overflow | Cap prior events at 10 or use summary-based context passing. The LLM provider silently truncates prompts > context window — detect this and log it. |
| `resolve_entities_activity` | Trying to resolve references from both old and new schemas simultaneously | Resolution runs against ONE schema, not both. If the feature flag is `USE_V2=true`, only resolve v7.0 events. If not, resolve v6.x events. Never interleave. |
| `DELETE /documents/{id}` cascade | Adding new v7.0 tables but not updating the cascade delete in `documents.py` | Every new table with a document FK must have an explicit DELETE statement in the correct position. Add a test that verifies zero records across ALL tables after delete. |
| Entity merge/split endpoints | Rewriting merge/split to handle the new schema but breaking the old schema's merge/split | Merge/split should work on `canonical_entity` regardless of which schema produced it. The canonical entity table persists across schemas. If v7.0 changes canonical_entity, retain backward-compatible merge/split for old entries. |
| API routes (events, timeline, participants) | Building new v7.0 API routes that query only new tables — old documents return empty results | API routes must check `document.schema_version` and query the appropriate table. If `schema_version = 'v6'`, fall back to old table queries. This is a TEMPORARY measure — remove once all documents are migrated. |
| Web UI — Event tab | Building a completely new Event tab HTML/CSS/JS from scratch, duplicating the existing patterns | The new Event tab should REPLACE the old Events and References tabs. Don't add a fourth tab — the v7.0 event list IS the new event system. Remove old tabs when the new one is validated. |
| Migration SQL (schema.surql → schema.sql) | Mixing SurrealDB DDL syntax with PostgreSQL DDL in the same migration file | The old SurrealDB schema.surql is dead — the system now uses PostgreSQL schema.sql (176 lines). ALL new DDL goes in schema.sql. Remove any remaining .surql files to prevent confusion. |

## Performance Traps

Patterns that work at small scale but fail as usage grows.

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Correlated subqueries for reference/participant counts on cross-document event list | `/events/timeline` takes >1s; PostgreSQL seq-scans the event table | Two-query pattern: fetch events, then batch-fetch counts. Add composite index. | ~5,000 total events in the database |
| 512KB chunks without prior context summarization | LLM provider returns "response too large" or silently truncates; chunk 15+ produces zero events | Cap prior events at 10; use summary-based context; monitor prompt token count per chunk | ~3 chunks into a 512KB chunk document (cumulative prior events exceed 128K tokens) |
| Loading full document text for every reference highlight click | Clicking "Ver en documento" loads 10MB text for a 500-page document; 5s delay | Load only the chunk that produced the reference, not the full document. Use chunk-relative offsets. | ~200KB document text (above which fetch + render >1s) |
| No pagination for event detail panel references | Event with 30 references renders all 30 verbatim texts; DOM grows; layout shift | Show 5 references in the detail panel; "Ver más" expands to 20; paginated modal for full list | ~15 references per event (30+ reference DOM nodes = slow expand) |
| Rendering document text as innerHTML without offset validation | A reference highlight at `span_start=500` renders in the wrong place if the document text has HTML entities | Use character-by-character rendering with `<mark>` spans. Validate offsets before rendering. | First document with accented characters (ñ, á, é) in highlighted spans |
| Running entity resolution across ALL documents when v7.0 schema goes live | A single huge Temporal workflow that processes every old document to create v7.0 events | No bulk reprocess. Users reprocess individual documents as needed. The `schema_version` field prevents unnecessary work. | ~50 documents (above which a bulk job takes >1 hour and costs >$50 in LLM tokens) |
| `jsonb_array_length` on event.references for every event in a paginated list | If references ARE embedded as JSONB (not recommended), every SELECT computes lengths from JSONB | Denormalize: store `reference_count` and `participant_count` as INTEGER columns on the event table, updated during extraction | ~100 events in a paginated list query |
| Chunking without page-number-aware boundary detection | A multi-paragraph court resolution that spans pages 5-10 is split into chunks that don't align with logical sections | Use the existing `page_offsets` metadata from ExtractionResult to detect section boundaries. Split at page boundaries where possible. | First multi-page legal document (always — every legal document spans pages) |

## Security Mistakes

Domain-specific security issues beyond general web security.

| Mistake | Risk | Prevention |
|---------|------|------------|
| Exposing verbatim reference text through the API without redaction checks | References contain exact text from legal documents — including personally identifiable information (victim names, national ID numbers, addresses, phone numbers) | Add an optional `redact_pii` query parameter to event/reference endpoints. If set, run reference text through a PII detection pipeline (regex for IDs, phone numbers, etc.) before returning. |
| LLM prompt including full document text with human rights context instruction | The prompt tells the LLM "this is a legal document about human rights" — the LLM response may contain the full document text in the response field (recorded in llm_call_log), persisting sensitive content in the database | The `llm_call_log` table already stores prompt/response text (v6.1). Ensure this data is encrypted at rest (PostgreSQL pgcrypto or filesystem-level encryption). Document the data retention policy for call logs. |
| No access control on `/events` and `/references` endpoints | The API is single-user (per PROJECT.md, auth is out of scope) — but if deployed publicly, anyone can query all extracted events | This is acceptable for a single-user research tool. If multi-user is added later, every endpoint must filter by user's document access. For now, ensure the API is only exposed on localhost:8001 or behind the cloudflared tunnel. |
| Reference offset validation failing silently | If `text[span_start:span_end]` doesn't match `reference.verbatim_text`, the UI could highlight the wrong passage — potentially highlighting a different victim's name or different location | Always validate offsets at render time (Pitfall 6). If validation fails, return `offset_valid: false`. The UI shows "no se pudo verificar la ubicación" instead of highlighting wrong text. |
| Storing LLM provider API keys in code or environment files committed to git | `OPENROUTER_API_KEY` is set via environment variable, which is standard. But if `.env` files or docker-compose.yml are committed with the key, it's leaked. | The existing setup uses environment variables, which is correct. Ensure `.env` files are in `.gitignore`. Never hardcode API keys in docker-compose.yml or schema.sql. |
| New schema tables lacking input validation on user-supplied text (merge/split entity names) | SQL injection if user input is directly interpolated into PostgreSQL queries | The existing pattern uses parameterized queries (`$1`, `$2`), which prevents injection. Ensure any new v7.0 endpoints follow the same pattern. |

## UX Pitfalls

Common user experience mistakes in the event-centric rewrite.

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Event detail panel shows ALL references with full offset data — user must scroll through 30 references to see the event summary | Cognitive overload: too much information at once; user can't find the relevant reference | Show event summary (que_paso, fecha, lugar) prominently at the top. References are a collapsible section below, with the first 3 visible and a "Ver todas las N referencias" expand button. |
| Clickable reference takes user to document viewer — no "back to event" navigation | User gets lost: they were looking at Event 5, clicked a reference, now they're in the document viewer with no way to return to Event 5 | Use a modal overlay for the document viewer (not a full-page navigation). The modal has a close button. When closed, the user is back at the event detail panel, which they were viewing. Preserve scroll position. |
| Event list shows all events in a flat table — no grouping by date, location, or participant | User sees 200 events in a paginated table and can't find the ones that matter | Add grouping options: "Agrupar por fecha" (collapse events by month), "Agrupar por ubicación" (by location), "Agrupar por participante" (by person). These are client-side groupings on the already-fetched page. |
| Smart chunking changes the document's event count — a document that previously had 10 events now has 15 after reprocessing | User doesn't trust the system: "Why does the same document have different event counts?" | Show both the old event count and new on the document detail page: "Procesado con esquema v7 — 15 eventos (antes: 10 con esquema v6)". Document the change in a changelog or tooltip. |
| Delete events + reprocess doesn't clear old reference data if the schema changed | User reprocesses a document expecting fresh data, but old references persist in the old tables (invisible to the new UI) — if they switch back to the old UI, old references reappear | The reprocess must clean BOTH old and new tables (Pitfall 16). After reprocess, the document's `schema_version` is updated, so the API never queries old tables for this document. |
| Human rights safety filter triggers silently — user sees "0 eventos extraídos" with no explanation | User thinks the document has no events, but actually the LLM refused to process it | Log the filter trigger in the processing log with a clear message: "El filtro de seguridad del modelo LLM rechazó el contenido del fragmento 5. Los eventos de este fragmento no se extrajeron." Show this in the UI. |
| Clickable reference highlights are yellow — same color as selected text or browser's default find-highlight | User can't distinguish between a highlight they created (select text) and a reference highlight | Use a distinct color (e.g., light blue `#BBDEFB` or light green `#C8E6C9`) for reference highlights. Add a subtle underline or left border. The highlight should NOT obscure the text — use a transparent background color with <50% opacity. |
| No "expand all references"/"collapse all" — user must click each event individually to see its references | Tedious for reviewing a document: user clicks 15 events to see their first reference each time | Add "Expandir todos" / "Colapsar todos" buttons at the top of the event list. This is a one-line event delegation handler. |

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical pieces.

- [ ] **Smart chunker:** Often produces unbalanced chunks — verify min/max chunk sizes are within 20% of target. Verify zero sentence fragments. Verify chunk boundaries don't fall in the middle of numbered legal articles.
- [ ] **New event schema:** Often missing the feature flag — verify `USE_V2_EVENT_SCHEMA` environment variable exists and toggles between old and new table writes. Verify default is `false` during development.
- [ ] **Temporal replay safety:** Often missing dual-table cleanup — verify that `store_extraction_results_v2_activity` (or the new storage activity) deletes from BOTH old and new tables before writing. Verify on worker restart.
- [ ] **Cascade delete:** Often missing new v7.0 tables — verify `DELETE /documents/{id}` removes records from ALL tables, including any new event_v2 tables. Run the exhaustive table enumeration test.
- [ ] **Offsets validation:** Often missing at render time — verify that the API validates `text[span_start:span_end]` matches `reference.verbatim_text` before returning highlight coordinates. Return `offset_valid: false` on mismatch.
- [ ] **Prior context summarization:** Often missing — verify that `extract_events_activity` passes a summary (not the full event list) as prior context to chunk N+1. Verify the summary is ≤500 tokens.
- [ ] **Safety filter detection:** Often missing — verify the pipeline detects "I cannot process this content" patterns and handles them gracefully (empty chunk, log warning, continue). Verify it doesn't fail the entire workflow.
- [ ] **Schema version per document:** Often missing — verify `document.schema_version` is set during reprocessing and the API checks it. Old documents (`schema_version = 'v6'`) must still render in the new UI.
- [ ] **Backward-compatible API:** Often missing — verify that `GET /events` works for documents with `schema_version = 'v6'` (querying old tables) and `schema_version = 'v7'` (querying new tables). Same for `/references`.
- [ ] **Temporal patching:** Often missing for in-flight workflows — verify that workflows started before the v7.0 deploy complete successfully after the deploy. Either wait for them to finish, or use Temporal patches.
- [ ] **Empty states in UI:** Often missing — verify the event list shows "No hay eventos para este documento" when empty. The event detail panel shows "Selecciona un evento para ver detalles" when no event is selected. The document viewer shows "No se pudo cargar el documento" on fetch failure.
- [ ] **LLM prompt regression:** Often untested — verify that the new human-rights-context prompt produces the same extraction quality on historical documents as the old prompt. Run the 5-document benchmark.

## Recovery Strategies

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Schema applied but pipeline broken (P1) | MEDIUM | Flip `USE_V2_EVENT_SCHEMA` back to `false`. Old tables are unchanged. Roll back the worker code. Fix the schema bug. Re-deploy. New documents go to old tables. |
| Chunking splits mid-sentence (P2) | LOW | Add sentence-boundary detection to the chunker. Reprocess affected documents (one at a time). Verify no more mid-sentence splits. The old chunks in `document_chunk` table are overwritten on reprocess. |
| Hallucination cascade from prior-context bloat (P3) | LOW | Switch to summary-based prior context. Run a deduplication pass on existing events (SQL: group by `que_paso` text similarity, merge duplicates in the reference table). |
| Embedded references break entity merge/split (P4) | HIGH | Convert JSONB references back to a separate table. Query `event.references` → `jsonb_array_elements` → `INSERT INTO reference`. This is a one-time migration, but the entity merge/split code needs rewriting to handle the old table structure. |
| Over-normalized N-N junction tables cause query complexity (P5) | MEDIUM | Drop unnecessary junction tables. Add `event.location_point` JSONB + `event.location_place_id` FK (the current approach). Migration: `INSERT INTO event (location_point) SELECT jsonb_build_object('label', l.name) FROM location l JOIN event_location el ON ...` — complex but one-time. |
| Reference highlight offsets wrong after document re-OCR (P6) | LOW | Re-extract document text (re-OCR) → new offsets are computed during extraction. Old references (with wrong offsets) are deleted and recreated. The `text_content_hash` check on the UI detects stale offsets — user sees "Ubicación no disponible" until reprocess. |
| Safety filter triggering on a specific document (P7) | LOW | Add the document to a "bypass safety filter" list. For that document, use a stripped-down prompt with no system message. Flag for manual review. Log the trigger for future prompt improvement. |
| Orphan data after schema cleanup (P8) | MEDIUM | Run a PostgreSQL cleanup script: identify all records where FK references point to non-existent parent rows. Delete orphans. The script is: `SELECT * FROM table_name WHERE fk_col NOT IN (SELECT id FROM parent_table)`. |
| UI crashes from too many DOM nodes (P14) | MEDIUM | Add lazy rendering for event detail panels. Limit references shown to 5 per event. Add pagination for the reference list. If the DOM is already corrupted (event listeners lost), reload the page. |
| N+1 query on event list (P15) | LOW | Add the two-query batch pattern. Add composite index `(document, created_at DESC)`. Run `EXPLAIN ANALYZE` to verify the plan changed from seq-scan to index-scan. |
| Document reprocessed but old events persist in old tables (P16) | LOW | Run a one-time cleanup: `DELETE FROM event WHERE document = $doc_id` and `DELETE FROM reference WHERE event IN (SELECT id FROM event WHERE document = $doc_id)`. Verify the new events are in the new tables. Update `document.schema_version = 'v7'`. |

## Pitfall-to-Phase Mapping

How roadmap phases should address these pitfalls.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Dropping old tables too early (P1) | Phase 1: Foundation | `USE_V2_EVENT_SCHEMA` flag exists. Old tables have NOT been dropped. Integration tests pass with both `true` and `false`. |
| Mid-sentence chunk splits (P2) | Phase 2: Smart Chunking | Zero sentence fragments in test corpus. Chunk size variance <20%. All chunks between 100KB and 600KB. |
| Prior-context hallucination (P3) | Phase 3: LLM Pipeline | Prior context is summarized, capped, or eliminated. No duplicate events in test corpus. Monotonically decreasing event count across chunks. |
| Embedded references (P4) | Phase 1: Foundation | Decision documented: references stay as separate table (recommended) or embedded with GIN index + helper function. Entity merge/split code updated for v7.0 schema. |
| Over-normalized N-N tables (P5) | Phase 1: Foundation | N-N junction table count is 1 (event_participant) or 2 (if strict requirement exists). All other relationships are JSONB or FK. |
| Offset drift (P6) | Phase 4: Event API + Phase 6: Event Detail UI | `text_content_hash` stored on reference. API validates offsets before returning. UI shows "offset invalid" gracefully. |
| Safety filter triggering (P7) | Phase 3: LLM Pipeline | System prompt includes human rights context. Refusal detection handles "I cannot" responses gracefully. Zero workflow failures on test corpus. |
| Orphan cleanup (P8) | Phase 7: Cleanup | Phased migration: freeze → migrate select data → archive → drop. `schema_version` field exists on `document`. API handles both versions. |
| Modal state management (P9) | Phase 5-6: Event List + Detail UI | `ViewState` object manages modal stack. Browser back/forward works. Event listeners use delegation. No inline onclick handlers. |
| Cross-chunk references (P10) | Phase 3: LLM Pipeline + Phase 6: Event Detail UI | Chunk-relative offsets stored. Cross-chunk references detected and flagged. UI shows boundary warning. |
| Temporal replay (P11) | Phase 7: Cleanup | Zero in-flight workflows before schema change. Temporal patches used if necessary. Old activity functions kept for replay. |
| Full-text search broken (P12) | Phase 1: Foundation | References kept as separate table. Full-text search indexes on `reference.verbatim_text` preserved. No GIN expression indexes needed. |
| Cascade delete misses new tables (P13) | Phase 1: Foundation + Phase 7: Cleanup | ON DELETE CASCADE on all new FKs. Exhaustive test verifies zero records across ALL tables after delete. |
| UI DOM performance (P14) | Phase 5-6: Event List + Detail UI | Event delegation used. References limited to 5 per event. Lazy-render detail panels. Profile: <100ms for 20 events × 20 references. |
| N+1 event list queries (P15) | Phase 4: Event API | Two-query batch pattern for cross-document lists. Composite indexes for timeline queries. `EXPLAIN ANALYZE` shows index-only scans. |
| Mixed-format events on reprocess (P16) | Phase 3: LLM Pipeline + Phase 4: Event API | `schema_version` on document. Reprocess deletes from both old and new tables. Transaction wraps the entire cleanup + write. |

## Sources

- **Primary:** Project source code — `schema.sql` (176 lines), `store_extraction_results.py` (357 lines), `extract_events.py` (155 lines), `chunker.py` (271 lines), `workflows.py` (249 lines), `resolve_entities.py` (433 lines), `documents.py` (1322 lines), `index.html` (2277+ lines), `models.py` (646 lines)
- **Reliability patterns for Temporal schema migration:** Temporal.io documentation — "Versioning Workflow Definitions" and "Patching" patterns (HIGH confidence — verified against existing workflow patterns)
- **PostgreSQL foreign key behavior:** PostgreSQL docs 5.5 — ON DELETE CASCADE, ON DELETE SET NULL behaviors. Verified for FK cascade patterns. (HIGH confidence)
- **LLM prompt engineering for safety filter avoidance:** Anthropic "Reducing Refusals" guide, OpenAI "Safety best practices" — Providing explicit context for legitimate use cases reduces false refusals. (MEDIUM confidence — empirical, document-specific)
- **RecursiveCharacterTextSplitter behavior (LangChain):** Verified against current codebase usage in `chunker.py` — separator fallthrough to character-level splitting at `[""]` separator. (HIGH confidence — reading source code)
- **PostgreSQL full-text search on JSONB:** PostgreSQL 14+ `jsonb_to_tsvector` function, GIN expression indexes. (HIGH confidence — PostgreSQL documentation)
- **Vanilla JS state management patterns:** Existing `index.html` tab system — uses global variables and manual DOM manipulation. Pattern for adding modal state machine derived from existing tab-management code. (HIGH confidence — reading source code)
- **Chunk boundary detection in text highlighting:** Derived from current `compute_reference_offsets` function in `offsets.py` and chunk-level offset tracking. Cross-chunk reference detection is a known gap. (HIGH confidence — no support exists in current code)

---
*Pitfalls research for: v7.0 Event-Centric Rewrite*
*Researched: 2026-06-08*