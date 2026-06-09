# Feature Research

**Domain:** Event-centric document extraction & visualization (legal/human rights)
**Researched:** 2026-06-08
**Confidence:** HIGH

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist in an event extraction system. Missing these = product feels incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Event list with document filtering** | Every document produces multiple events; researchers need to see "all events from this document" immediately. This is the primary navigation pattern in MUC-style IE systems. | LOW | Paginated list, filter by document_id. Pagination envelope already established in existing UI (v3.0 pattern). |
| **Event detail view** | After selecting an event, users need to see all extracted fields (what happened, who, when, where) in one place. | LOW | Full field display of the unified event object. Reuses existing tab-based UI pattern. |
| **Sort by time** | Events have inherent temporal ordering; viewing them chronologically is the default mental model. | LOW | Sort by extracted time_window. ISO 8601 timestamps sort natively as strings. |
| **Search by title/description** | Users need to find specific events across documents without scrolling. | MEDIUM | Search over que-paso (what-happened) and event title fields. Existing GraphQL search pattern from M001 can be adapted. |
| **Clickable references that show source text** | Core value proposition: every extraction must be traceable to exact source text. Without this, users can't verify LLM output. | MEDIUM | Reference stored with character offsets + page number. Need modal/panel that shows surrounding text with highlighted reference span. |
| **Participants and locations displayed as linked objects** | Events are meaningless without knowing who was involved and where. Participants and locations are first-class entities, not just text fields. | HIGH | Requires new PostgreSQL N-N relations for event↔participant and event↔location. Separate participant/location tables with their own detail views. |
| **Processing status per chunk** | Users need visibility into which chunks have been processed, which are pending, and which failed. | MEDIUM | Chunk-level status tracking in the pipeline. Extends existing document status pattern (uploaded → extracting → complete) to the chunk level. |
| **Provenance trace from event back to source document** | Every extracted event must be traceable: event → chunk → page → source document. This is the core audit value of the system. | MEDIUM | Chain of references: event has source_chunk_id → chunk has page_ranges, document_id. All already tracking in existing pipeline; just needs UI exposure. |

### Differentiators (Competitive Advantage)

Features that set the product apart. Not required in basic IE systems, but create significant value for legal/human rights research.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Smart document chunking (512KB target, balanced splits)** | Standard chunking splits at fixed token counts, breaking across semantic boundaries. Smart chunking respects section structure (headers, paragraphs) and produces balanced chunks near 512KB. Prevents "lost in the middle" for long legal documents. | HIGH | Content-aware chunking: use document structure (headings, paragraph breaks) as primary split points, fall back to recursive character splitting only when a single section exceeds 512KB. Overlap of ~200 characters between chunks preserves reference continuity. This is the Unstructured.io "by_title" strategy adapted for LLM extraction rather than RAG. |
| **Text highlighting showing exact reference context** | When viewing an event, highlight the exact source text within the original document page. This is the core audit requirement — seeing *why* the LLM extracted a particular value. | MEDIUM | Use character offset + page number from reference metadata. Display source text snippet with highlighted span. Prefer server-side extraction of context window (prevents data duplication to client). |
| **Modal-based event detail with reference navigation** | Clicking an event opens a modal overlay that shows all event fields AND the source reference inline. Click references within the event to jump to source text position. | MEDIUM | Modal pattern avoids page navigation and keeps the event list visible. Reference chips/badges within event fields that expand to show source. Implement as vanilla JS overlay component (matching v3.0 SPA pattern). |
| **Geospatial location display** | Human rights violations have specific locations. Showing events on a map (even a simple one) reveals geographic patterns that a list alone hides. | MEDIUM | Requires lat/lng in location data. Display via Leaflet.js (lightweight, no build step, CDN-loaded). Map shows pins for event locations with click-to-detail. |
| **LLM prompt with human rights context** | Safety filters on LLM APIs can block extraction of violent/abusive content common in human rights documentation. Explicit system prompts with "human rights documentation, legal analysis" framing reduce false positives significantly. | LOW | System prompt engineering only. Test with the Spanish legal document corpus to catch false positives. Should be applied to both extraction and entity resolution activities. |
| **Reference integrity verification** | Every extracted reference should be verifiable against the source document. Detect when reference text doesn't exactly match the source (a sign of LLM hallucination). | HIGH | After extraction, verify each reference's verbatim text against the source text at its claimed offset. Flag mismatches as "reference integrity warnings" in the UI. Requires careful handling of whitespace and formatting differences. |
| **Temporal precision indicators** | Legal events often have imprecise dates ("around March 2023", "between 2020-2022"). Showing confidence/precision of extracted time data (vs treating all timestamps as exact) is critical for legal analysis. | MEDIUM | TimeML-style time expression typing: exact date, approximate range, duration, recurring. Store precision level alongside time_window. Display differently in UI (exact: "March 15, 2023" vs approximate: "~March 2023"). |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem good but create problems for this document-centric, single-user research tool.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| **Cross-document event de-duplication** | "I want to see all unique events across all documents" — seems natural for aggregation. | Fundamentally changes the system from document-centric (auditable) to knowledge-base (non-auditable). Which document gets credit for an event? What if two documents give conflicting accounts? Requires consensus resolution that's out of scope for v7.0. | Keep document-centric per explicit v7.0 scope boundary. Cross-document analysis can be a future milestone after event-centric foundations are solid. |
| **Real-time streaming of extraction results** | "I want to see events appear as they're extracted" — reduces perceived latency. | Adds significant complexity to the SPA (WebSocket or polling), while pipeline already processes in seconds-to-minutes. The benefit doesn't justify the complexity for a single-user tool. | Show a spinner with status messages during processing. When complete, refresh the event list. |
| **Automated timeline/chart generation** | "I want a visual timeline of all events automatically" — compelling demo feature. | Edge cases dominate: events with imprecise dates, multi-day events, recurring events, conflicting temporal information. A naive timeline is actively misleading. | Build the structured data first (v7.0), add timeline visualization as a future differentiator once temporal precision indicators are solid. |
| **Editing extracted events in-place** | "The LLM got it wrong, let me fix it" — natural user desire. | In-place editing breaks the audit trail. If a user edits an event, is it still traceable? Does reprocessing overwrite edits? Creates tension between correction and provenance. | The existing merge/split entity correction pattern (M002) is the right approach — corrections are tracked as operations, not in-place mutations. Apply same pattern to events in a future milestone. |
| **Full-text search across all events** | General search across all extracted content. | Overlaps with GraphQL search on que-paso, adds PostgreSQL full-text search indexing complexity, and crosses documents (implying cross-document scope). | Start with per-document event search and title text search. Full-text across documents requires different indexing strategy. |

## Feature Dependencies

```
Smart Document Chunking
    ├──requires──> Chunk-level status tracking
    └──enables──> LLM extraction on balanced chunks

Unified Event Object (PostgreSQL schema)
    ├──requires──> Smart Document Chunking (chunks are extraction unit)
    ├──requires──> New PostgreSQL schema migration (event table with embedded references, N-N relations)
    └──requires──> LLM prompt update (emit unified event objects, not separate references/entities)

Event List UI
    ├──requires──> Unified Event Object (data to display)
    ├──requires──> Event list API endpoint (GET /documents/{id}/events?page=&sort=&search=)
    └──enhances──> Existing v3.0 pagination pattern

Event Detail UI (modal)
    ├──requires──> Unified Event Object (data to display)
    ├──requires──> Event detail API endpoint (GET /events/{id})
    ├──requires──> Text highlighting (reference offset + context extraction)
    └──enhances──> Clickable reference navigation

Participants & Locations as linked objects
    ├──requires──> New PostgreSQL schema (participant + location tables, N-N junction tables)
    ├──requires──> LLM prompt update (emit structured participants/locations)
    └──enhances──> Event Detail UI (show linked participants/locations)

Geospatial location data
    ├──requires──> Participants & Locations (structured location objects)
    └──enhances──> Event Detail UI (map component for location)

LLM prompt with human rights context
    ├──enhances──> Smart Document Chunking (works with any chunk strategy)
    └──enhances──> Unified Event Object (extraction quality)

Reference integrity verification
    ├──requires──> Unified Event Object (references embedded with offsets)
    └──requires──> Source text accessible (MinIO blob store)
```

### Dependency Notes

- **Smart Document Chunking is the foundation:** Everything depends on chunks being the unit of extraction. Without smart chunking, LLM extraction quality degrades on long documents (lost-in-the-middle effect). The existing chunker splits by page; smart chunking must balance to 512KB while respecting section boundaries.
- **PostgreSQL schema migration is the highest-risk item:** Moving from SurrealDB document model to PostgreSQL relational model for events requires clean migration with full data preservation. All downstream features depend on this schema being correct and stable.
- **LLM prompt changes affect extraction quality:** The unified event object requires a different prompt schema than the current separate references/entities/events prompts. Prompt engineering iteration will be needed.
- **Participants/Locations as linked objects is the most complex dependency chain:** Requires: schema → prompt → extraction → API → UI. Each link must be reliable for the chain to work.

## MVP Definition

### Launch With (v7.0 - Current Milestone)

Minimum viable event-centric rewrite — what's needed to validate the unified event model.

- [x] **Smart Document Chunking** — 512KB target, balanced splits respecting section boundaries. Foundation of all extraction quality improvements.
- [ ] **Unified Event Object (PostgreSQL schema)** — Event table with embedded references, participant/location junction tables. Migration from existing SurrealDB event model.
- [ ] **Event List API + UI** — Paginated, filterable by document, sortable by time, searchable by title. Reuse existing v3.0 pagination and tab patterns.
- [ ] **Event Detail API + UI (modal)** — Full event fields with clickable references showing source context. Modal overlay pattern, no page navigation.
- [ ] **Participants & Locations as linked objects** — Participant and location tables with N-N relations to events. Displayed in event detail.
- [ ] **LLM prompt with human rights context** — System prompt framing to avoid safety filter false positives. Test with real Spanish legal document corpus.
- [ ] **Clean removal of old SurrealDB references/entities/events system** — Drop old tables, update all code paths, ensure zero regression.

### Add After v7.0 Validation

Features to add once the unified event model is working and verified.

- [ ] **Geospatial map view** — Leaflet.js map showing event locations with click-to-detail. Requires lat/lng data quality from LLM extraction.
- [ ] **Reference integrity verification** — Auto-verify verbatim reference text against source document. Flag mismatches in UI.
- [ ] **Temporal precision indicators** — TimeML-style typing of extracted times (exact/approximate/duration/recurring). Display confidence in event detail.

### Future Consideration (Post-v7.0)

Features to defer until event-centric foundations are solid.

- [ ] **Cross-document event de-duplication** — Need to solve the audit/pedigree problem first. Requires deciding which document "owns" a deduplicated event. Out of scope per v7.0 boundary.
- [ ] **Timeline visualization** — High edge-case surface (imprecise dates, conflicting accounts). Build after temporal precision indicators are solid.
- [ ] **In-event editing with audit trail** — Corrections must preserve provenance. Apply M002 merge/split pattern to events.
- [ ] **Authentication / Multi-user** — Not needed for single-user research tool. Defer indefinitely.

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Smart Document Chunking | HIGH | HIGH | P1 |
| Unified Event Object (PostgreSQL schema) | HIGH | HIGH | P1 |
| Event List API + UI | HIGH | MEDIUM | P1 |
| Event Detail UI with clickable references | HIGH | MEDIUM | P1 |
| Participants & Locations as linked objects | HIGH | HIGH | P1 |
| LLM prompt with human rights context | MEDIUM | LOW | P1 |
| Clean removal of old SurrealDB system | MEDIUM | MEDIUM | P1 |
| Reference integrity verification | HIGH | HIGH | P2 |
| Geospatial location display | MEDIUM | MEDIUM | P2 |
| Temporal precision indicators | MEDIUM | MEDIUM | P2 |
| Timeline visualization | MEDIUM | HIGH | P3 |
| Cross-document event de-duplication | HIGH | VERY HIGH | P3 |
| In-event editing with audit trail | MEDIUM | HIGH | P3 |

**Priority key:**
- P1: Must have for v7.0
- P2: Should have, add after v7.0 validation
- P3: Nice to have, future milestone

## Competitor Feature Analysis

| Feature | Academic IE Systems (TimeML/FRED/EventCognition) | Commercial Legal Analytics (LexisNexis/Westlaw) | Our Approach |
|---------|--------------------------------------------------|------------------------------------------------|--------------|
| Event extraction approach | Rule-based or fine-tuned ML, limited to specific schemas | Proprietary NLP, closed systems, expensive | LLM-powered with structured JSON schema output, provider-agnostic |
| Document chunking | Whole-document or sentence-level | Proprietary | Smart chunking (512KB balanced), section-boundary aware, with overlap |
| Reference tracing | Academic (offset-based in corpus) | Limited or non-existent | First-class references with character offsets + page number, source text verification |
| Event UI | Mostly academic datasets, no user-facing UIs | Form-based data entry, not automated extraction | Filterable list + modal detail with clickable source references |
| Geospatial | Rare in IE systems | Some (LexisNexis Map) | Leaflet.js map for event locations |
| Human rights context | Academic corpora (MUC terrorism, clinical) | US/western legal focus only | Explicit human rights framing in prompts for Spanish-language legal docs |
| Auditability | Academic (corpus-level) | Limited | Full provenance: event → chunk → page → source document, LLM call logging |
| LLM cost tracking | N/A | N/A | Per-LLM-call token/cost tracking (v5.0) |
| Open source? | Some (FRED, GATE) | No | Yes (MIT) |

**Key insight:** No existing tool combines LLM-powered extraction, smart chunking, reference tracing, geospatial display, and human-rights context in an open-source package. The gaps are in the UX for event-centric navigation (most academic tools don't have UIs) and in the specific domain framing for human rights.

## Sources

- Wikipedia: Temporal Annotation / Event Extraction — Academic background on MUC conferences, TimeML standard, template-filling approach
- Wikipedia: TimeML (ISO-TimeML) — EVENT, TIMEX3, TLINK tag specifications for temporal annotation markup
- Unstructured.io: Chunking Documentation — Content-aware chunking strategies (by_title, basic), max_characters/new_after_n_chars patterns, overlap, element boundary preservation
- Pinecone: Chunking Strategies for LLM Applications — Fixed-size, content-aware, semantic chunking methods; chunk size selection guidance; chunk expansion for context preservation
- PROJECT.md (v7.0 Event-Centric Rewrite) — Current project state, scope boundaries, architectural constraints
- Temporal: Workflow Documentation — Deterministic workflow/replay constraints relevant to pipeline design
- MUC Conference Series (1987-1998) — DARPA-funded information extraction competitions, terrorism extraction domain template

---

*Feature research for: Event-centric document extraction & visualization (legal/human rights)*
*Researched: 2026-06-08*
