# Phase 2: Project Documentation - Context

**Gathered:** 2026-05-31
**Status:** Ready for planning

<domain>
## Phase Boundary

Full README rewrite covering project overview, quickstart, system architecture, complete API documentation with examples, environment configuration reference, and troubleshooting guide. Target audience is new developers who need to understand, set up, and use the Espacio Tiempo Humanos system.

</domain>

<decisions>
## Implementation Decisions

### README Structure
- Section order: Overview → Quickstart → Architecture → API Docs → Configuration → Troubleshooting
- Architecture visualization: Mermaid.js diagram

### API Documentation Format
- Use `httpie` commands instead of curl (better syntax, debug output)
- Include request/response JSON blocks

### Environment Configuration
- Table format: variable, description, default/example

### Content Requirements
- DOC-01: Project purpose + working quickstart
- DOC-02: Every API endpoint with httpie request/response examples (ingest document, GraphQL queries, entity merge/split)
- DOC-03: System architecture (SurrealDB, Temporal, LLM extraction, entity resolution) and data flow from ingest to query
- DOC-04: Environment config reference + troubleshooting section

</decisions>

<code_context>
## Existing Code Insights

### Integration Points
- README.md — file to be rewritten
- API endpoints to document: POST /documents (ingest), POST /graphql (GraphQL proxy), POST /entities/merge, POST /entities/{type}/{id}/split
- Architecture components: SurrealDB, Temporal Server/Worker/UI, FastAPI, OpenRouter LLM, entity resolution pipeline
- Environment variables from .env file

### Established Patterns
- Existing README structure (if any) to be replaced
- Project purpose: Spanish-language legal document ingestion and event extraction
- Key value: Traceability from query to source document

</code_context>

<specifics>
## Specific Ideas

- Use httpie for API examples (user preference over curl)
- Mermaid.js for architecture diagram
- Table format for config reference
- Reference port 1985 (Phase 1 change) in docs

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>
