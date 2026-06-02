---
status: complete
quick_id: "260601-w4g"
date: "2026-06-02"
commit: "4615b6e"
---

# Quick Task 260601-w4g: Format detection for extract_text_activity

## Objective

Prevent `PdfExtractor` from blindly processing non-PDF uploads (`.txt`, `.md`,
extensionless plain text, and other unsupported formats).

## Changes

**`src/eth_pipeline/activities.py`** — `extract_text_activity`:

- Added format detection from `filename` extension and `mime_type` after
  the binary content is fetched.
- **PDF** (`.pdf` / `application/pdf`): unchanged `PdfExtractor` path with
  quality gate.
- **Plain text** (`.txt`, `.md`, extensionless with text mime): decodes
  content as UTF-8, emits `page_count=1`, `page_offsets=[0, len(text)]`.
- **Unsupported** (`.docx`, `.html`, `.xlsx`, etc.): marks document as
  `failed` with a clear error message.
- Updated docstring to document the three branches.

## Verification

- `grep -n 'doc_format' src/eth_pipeline/activities.py` → confirms three
  branches (pdf, plain_text, unsupported).
- `PdfExtractor` is only invoked in the `"pdf"` branch.
- Existing PDF upload flow is unchanged (extension `.pdf` and mime
  `application/pdf` route to the exact same code path).

## Files

- `src/eth_pipeline/activities.py` (modified)
