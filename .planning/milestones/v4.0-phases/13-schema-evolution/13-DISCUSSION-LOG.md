# Phase 13: Schema Evolution - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-03
**Phase:** 13-Schema Evolution
**Areas discussed:** Schema file organization, document_event_log table design, Event entity_type enum extension, RELATE graph edge schema, GraphQL exposure

---

## Schema File Organization

| Option | Description | Selected |
|--------|-------------|----------|
| Single-file (append to schema.surql) | All Phase 13 DDL appended to existing schema.surql under a separator block | ✓ |
| Separate migration files | New .surql file per phase, requires init_schema.py update | |

**User's choice:** Single file for now
**Notes:** Use `-- ====== v4.0 Schema Evolution ======` separator block. No init script changes needed.

---

## document_event_log Table Design

| Option | Description | Selected |
|--------|-------------|----------|
| enum for severity | ASSERT enum (like existing reference_type) | ✓ |
| hash-based IDs | SHA256(document_id + step_name + sequence_number) | ✓ |
| No log cap | No schema-level entry cap | ✓ |
| Free-form step_name | String field documented in COMMENT, no ASSERT | ✓ |
| Log cleanup deferred | No TTL or cleanup now | ✓ |

**User's choice:** enum for log; hash-based timestamp indexed; no log cap; auto-expire deferred to future milestone; step_name as free-form string

---

## Event entity_type Enum Extension

| Option | Description | Selected |
|--------|-------------|----------|
| DEFINE FIELD with new ASSERT | Redefine canonical_entity.entity_type ASSERT to include 'event' | ✓ |
| Remove + redefine | Two-step REMOVE FIELD + DEFINE FIELD | |

**User's choice:** DEFINE FIELD with new ASSERT
**Notes:** Prototype stage — destructive changes are acceptable. Researcher should verify if SurrealDB supports redefining an existing DEFINE FIELD's ASSERT.

---

## RELATE Graph Edge Schema

| Option | Description | Selected |
|--------|-------------|----------|
| Dedicated event_entity_link table | Separate table for event→entity edges | ✓ |
| Full field set | event, entity, relationship_type, role, confidence, notes, created_at | ✓ |

**User's choice:** Dedicated event_entity_link table with event, entity, relationship_type, role, confidence, notes, created_at

---

## GraphQL Exposure

| Option | Description | Selected |
|--------|-------------|----------|
| Accept auto-GraphQL | Default (both read+write) — document which mutations to avoid | ✓ |
| Try to restrict | Attempt read-only for log table | |

**User's choice:** Accept auto-GraphQL defaults, document which mutations to avoid

---

## the agent's Discretion

- Hash length for deterministic log IDs (16 hex chars suggested)
- relationship_type and role value documentation in COMMENT annotations
- ORDER/INDEX definitions on new tables

## Deferred Ideas

- **Log cleanup (30-day auto-expire):** SurrealDB has no native TTL. Deferred to future milestone.
- **GraphQL mutation restrictions:** If write-protection becomes needed, it's a future concern.
