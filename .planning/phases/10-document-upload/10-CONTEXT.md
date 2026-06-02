# Phase 10: Document Upload - Context

**Gathered:** 2026-06-01
**Status:** Ready for planning

<domain>
## Phase Boundary

Users can upload documents to the pipeline through the web UI. The Upload tab (from Phase 9 foundation) gets a functional file upload form with file selection, upload to `POST /documents/upload`, success/error feedback, and loading state. This builds on the existing Phase 9 SPA — modifying `index.html` inline.

</domain>

<decisions>
## Implementation Decisions

### Upload UX
- Native `<input type="file" multiple>` with styled "Choose Files" button — no drag-and-drop
- Simple file list: filename + size after selection
- Single "Upload" button below file list — uploads all selected files
- Sequential upload — files uploaded one by one with per-file progress

### Feedback & States
- In-progress: disabled upload button + CSS spinner beside each uploading file
- Success: green banner "Uploaded: filename (ID: xxxx)" — auto-dismiss after 5s
- Error: red banner "Failed: filename — reason" — persists until dismissed or next upload
- Empty state: "Select files to upload" centered message matching Phase 9 placeholder-card pattern

### Code Integration
- Upload JS inline in `index.html` — same pattern as Phase 9
- `fetch()` with `FormData` — relative URL `/documents/upload`
- Show first 8 chars of hex document ID on success

### the agent's Discretion
- Exact CSS spinner design (border-based spinner is standard)
- Banner animation (slide-in is recommended)
- Button styling details within the existing design system
- Error message formatting from API response

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- Phase 9 `index.html` at `src/eth_pipeline/static/index.html` — modify Upload section
- `POST /documents/upload` endpoint already exists (accepts multipart, returns `{ document_id }`)
- Phase 9 card pattern (`.placeholder-card`) — reuse for empty state
- Blue accent #2563eb for buttons, green/red for success/error banners

### Integration Points
- Upload tab currently has `.placeholder-card` — replace with functional form
- JS in existing `<script>` block — add upload functions
- API endpoint available at `/documents/upload` (relative URL from same origin)

</code_context>

<specifics>
## Specific Ideas

No specific requirements beyond ROADMAP success criteria and approved decisions above.

</specifics>

<deferred>
## Deferred Ideas

- Drag-and-drop upload zone (Phase 10+ enhancement)
- File type validation before upload (can add in future)
- Upload progress bar (sequential upload with per-file progress is sufficient for v3.0)
- Multiple concurrent uploads (sequential is simpler and more reliable)
</deferred>
