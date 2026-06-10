---
phase: 37
slug: event-ui
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-10
---

# Phase 37 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | none — vanilla JS SPA (index.html), manual browser testing |
| **Config file** | none |
| **Quick run command** | `npx serve .` (manual verification in browser) |
| **Full suite command** | manual browser testing + API endpoint curl checks |
| **Estimated runtime** | ~120 seconds (manual) |

---

## Sampling Rate

- **After every task commit:** Run `curl -s localhost:8000/events | head` to verify endpoint availability
- **After every plan wave:** Manual browser test of the implemented features
- **Before `/gsd-verify-work`:** All success criteria verified manually in browser
- **Max feedback latency:** 10 seconds (API curl check)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| — | — | — | — | — | — | — | — | — | — |

*Populated by planner. Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] No new files needed — all code extends existing `index.html`
- [ ] `curl -s http://localhost:8000/events?page=1&per_page=20` returns 200 with valid JSON
- [ ] `curl -s http://localhost:8000/events/1` returns 200 with valid event detail JSON
- [ ] `curl -s "http://localhost:8000/documents/{id}/chunks/0"` returns 200 with chunk text

*Existing backend infrastructure from Phase 36 covers all API requirements.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Event table renders with correct columns | UI-01 | DOM rendering | Open browser, navigate to Eventos tab, verify columns: id, starting time, title, location name, participant count |
| Event detail panel opens on row click | UI-02 | DOM interaction | Click an event row, verify detail panel shows all components (title, description, time window, location, participants, references) |
| Reference click opens document viewer with highlight | UI-03 | DOM interaction + scroll | Click a reference link in event detail, verify document viewer modal opens at correct chunk with text highlighted |
| Document filter works with clear button | UI-04 | DOM interaction | Select a document from dropdown filter, verify events are filtered; click clear, verify all events shown |
| Default sort and search | UI-05 | DOM interaction | Verify events sorted by starting time descending; type in search input, verify title filtering |
| XSS safety — reference text rendered safely | UI-03 | Security | Verify reference text with HTML tags is rendered as text (not executed) |
| Document viewer Escape key and backdrop dismiss | UI-03 | Accessibility | Press Escape, verify modal closes; click backdrop, verify modal closes |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
