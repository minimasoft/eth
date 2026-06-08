---
status: complete
---

## Summary

Both UI fixes completed in `src/eth_pipeline/static/index.html`:

1. **Document view column cleanup**: Renamed "Refs" → "Referencias", "Ents" → "Entidades", removed "Fragmentos" column (header, CSS, JS rendering).
2. **LLM tab redundancy removed**: Removed the "Resumen de Llamadas LLM" summary card and all associated JS (the `updateLlmCallsSummary` function, `fetchLlmCallsSummary`, aggregation code in `renderLlmCalls`, and CSS).
