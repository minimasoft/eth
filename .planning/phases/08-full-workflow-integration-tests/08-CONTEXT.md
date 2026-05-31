# Phase 8: Full Workflow Integration + Tests - Context

**Gathered:** 2026-05-31
**Status:** Ready for planning
**Mode:** Auto-generated (use ROADMAP phase goal as spec)

<domain>
## Phase Boundary

All new pipeline components integrate with the existing document lifecycle (reprocess, delete, lazy migration); all existing and new tests pass with chunk transparency verified

**Depends on:** Phase 7 (PDF extraction + chunking)

**Success Criteria:**
1. `DocumentProcessingWorkflow` handles both blob-path (binary PDF) and direct-text-path documents via conditional branch
2. Processing status transitions through `extracting_blob` → `extracting_text` → `chunking` → `extracting_events` correctly
3. `DELETE /documents/{id}/events` also clears `document_chunk` records — reprocess cycle leaves zero orphaned chunks
4. Old base64-stored documents remain fully accessible alongside new MinIO-stored documents (lazy migration)
5. All 11/11 existing integration tests pass; new v2.0 pipeline integration tests pass
6. Chunk transparency verified — `extract_events_activity` receives full reconstructed text from `document.text_content`, never sees individual chunk records

</domain>

<decisions>
## Implementation Decisions

### At the Agent's Discretion
All implementation choices are at the agent's discretion. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

Key patterns:
- Workflow conditional branch based on `blob_format`
- Status tracking using existing status enum pattern
- DELETE cascade follows existing document/event pattern
- Lazy migration: old base64 docs read `text_content` directly, new docs reconstruct from chunks
- All integration tests in TypeScript under `tests/integration/`

</decisions>

<code_context>
## Existing Code Insights

Codebase context will be gathered during plan-phase research. Key areas to explore:
- Existing `DocumentProcessingWorkflow` definition
- Status enum and transition logic
- DELETE /documents/{id}/events implementation
- Integration test framework and patterns
- `extract_events_activity` implementation

</code_context>

<specifics>
## Specific Ideas

No specific requirements — auto-generated context. Refer to ROADMAP section for phase 8.

Requirements: WFLW-01, WFLW-02, WFLW-03, WFLW-04, TEST-01, TEST-02, TEST-03

</specifics>

<deferred>
## Deferred Ideas

None.
</deferred>
