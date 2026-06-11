---
status: complete
---

# Quick Task 260611: Clean up dead code in llm.py

Removed 682 lines of dead code:
- `EVENT_EXTRACTION_SCHEMA` (old v1 schema, replaced by v7)
- `ENTITY_RESOLUTION_SCHEMA` + `ENTITY_RESOLUTION_SYSTEM_PROMPT` (unused)
- `LLMProvider` Protocol class (unused)
- `OpenRouterProvider.extract_events()` (replaced by `extract_events_v7()`)
- `OpenRouterProvider.resolve_references()` (unused)
- `_build_payload()`, `_build_resolution_payload()` (old helpers)
- Top-level `extract_events()` and `resolve_references()` convenience functions
- Updated module docstring and class docstring to reference v7 only
