---
phase: 9
slug: ui-foundation
status: draft
created: 2026-06-01
---

# Phase 9 — UI Design Contract

> Visual and interaction contract for the UI Foundation phase. Three-tab SPA served from FastAPI at `/ui`.

---

## Design System

| Property | Value |
|----------|-------|
| Tool | none (vanilla HTML/CSS/JS) |
| Preset | not applicable |
| Component library | none |
| Icon library | none (Unicode symbols / CSS shapes) |
| Font | System font stack: `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif` |

---

## Spacing Scale

| Token | Value | Usage |
|-------|-------|-------|
| xs | 4px | Icon gaps, inline padding |
| sm | 8px | Compact element spacing |
| md | 16px | Default element spacing |
| lg | 24px | Section padding |
| xl | 32px | Layout gaps |
| 2xl | 48px | Major section breaks |
| 3xl | 64px | Page-level spacing |

Exceptions: none

---

## Typography

| Role | Size | Weight | Line Height |
|------|------|--------|-------------|
| Body | 16px | 400 | 1.5 |
| Label | 14px | 500 | 1.4 |
| Heading | 24px | 600 | 1.3 |
| Display | 28px | 700 | 1.2 |

---

## Color

| Role | Value | Usage |
|------|-------|-------|
| Dominant (60%) | #ffffff | Background, surfaces |
| Secondary (30%) | #f8fafc | Card backgrounds, subtle surfaces |
| Accent (10%) | #2563eb | Active tab indicator, header background, interactive elements |
| Text Primary | #1e293b | Body text |
| Text Secondary | #64748b | Subtle text, placeholder messages |

Accent reserved for: header background, active tab underline, tab hover state

---

## Layout Contract

| Element | Property | Value |
|---------|----------|-------|
| Header | Height | 56px |
| Header | Background | #2563eb |
| Header | Alignment | flex, centered vertically |
| Tab bar | Position | sticky top, below header |
| Tab bar | Height | 44px |
| Tab bar | Background | #ffffff |
| Tab bar | Border-bottom | 1px solid #e2e8f0 |
| Tab item (active) | Font weight | 600 |
| Tab item (active) | Color | #2563eb |
| Tab item (active) | Indicator | 2px bottom border |
| Content area | Padding | 24px |
| Content area | Max width | 960px, centered |

---

## Copywriting Contract

| Element | Copy |
|---------|------|
| Page title | ETH Pipeline |
| Main heading | ETH Pipeline |
| Tab label 1 | Upload |
| Tab label 2 | Documents |
| Tab label 3 | Entities |
| Upload placeholder | Upload documents to the extraction pipeline |
| Documents placeholder | View your uploaded documents |
| Entities placeholder | Browse extracted entities |

---

## Interaction Contract

| Action | Behavior |
|--------|----------|
| Click tab | Show matching section, hide others, update active tab style |
| Default active tab | Upload (first tab active on load) |
| Tab hover | Light background tint |
| Tab transition | Instant (show/hide, no animation for Phase 9) |

---

## File Structure

| File | Location | Content |
|------|----------|---------|
| index.html | `src/eth_pipeline/static/` | Single HTML file with embedded `<style>` and `<script>` |
| FastAPI mount | `src/eth_pipeline/api.py` | `StaticFiles(directory=..., html=True)` mounted at `/ui` |

---

## Checker Sign-Off

- [ ] Dimension 1 Copywriting: PASS
- [ ] Dimension 2 Visuals: PASS
- [ ] Dimension 3 Color: PASS
- [ ] Dimension 4 Typography: PASS
- [ ] Dimension 5 Spacing: PASS
- [ ] Dimension 6 Registry Safety: PASS (no registry dependencies)

**Approval:** pending
