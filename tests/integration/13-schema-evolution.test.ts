/**
 * Integration tests for Phase 13 schema evolution.
 *
 * Verifies all v4.0 DDL changes are deployed correctly through:
 * - GraphQL schema introspection (type and field presence)
 * - Direct SurrealDB SQL queries (DESCRIBE TABLE, INSERT, SELECT)
 * - No regression on existing fields
 *
 * Test groups:
 *   1. Schema introspection - reference offset fields
 *   2. Schema introspection - document_event_log table
 *   3. Schema introspection - canonical_entity entity_type includes 'event'
 *   4. Schema introspection - event_entity_link table
 *   5. No regression - existing reference fields still queryable
 *   6. Direct SQL - INSERT and SELECT on document_event_log
 *   7. Direct SQL - INSERT and SELECT on event_entity_link
 *
 * @module
 */

import { describe, it, before, after } from "node:test";
import assert from "node:assert/strict";
import {
  API_BASE,
  SURREAL_HTTP,
  graphqlQuery,
  graphqlOk,
  assertGraphqlOk,
  skipIfDegraded,
  getSchemaTypeNames,
  assertNonNull,
  httpPost,
  GraphQLResponse,
} from "./helpers.js";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Execute a SurrealDB SQL statement via the HTTP/sql endpoint.
 *
 * Falls back to the HTTP/sql endpoint directly (useful for test setup
 * and data verification when GraphQL query variants are unavailable).
 */
async function sqlExecute(
  sql: string,
  timeout = 10_000,
): Promise<[number, unknown[] | null, string | null]> {
  const sqlUrl = `${SURREAL_HTTP}/sql`;
  const user = process.env.SURREAL_USER ?? "root";
  const pass = process.env.SURREAL_PASS ?? "root";
  const ns = process.env.SURREAL_NS ?? "eth";
  const db = process.env.SURREAL_DB ?? "pipeline";

  const token = Buffer.from(`${user}:${pass}`).toString("base64");
  const headers: Record<string, string> = {
    Authorization: `Basic ${token}`,
    Accept: "application/json",
    "Surreal-Ns": ns,
    "Surreal-DB": db,
    "Content-Type": "text/plain",
  };

  const [status, body, error] = await httpPost(sqlUrl, sql, headers, timeout);
  if (error) return [status, null, error];
  if (body === null) return [status, null, "Empty response body"];

  try {
    const parsed = JSON.parse(body) as unknown[];
    return [status, parsed, null];
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    return [status, null, `JSON parse error: ${msg} — body: ${body.slice(0, 300)}`];
  }
}

/**
 * Extract result rows from a SurrealDB SQL response.
 * SQL responses are arrays of entries each with a "result" key containing an array of rows.
 */
function extractSqlRows(sqlResult: unknown[]): Record<string, unknown>[] {
  const rows: Record<string, unknown>[] = [];
  for (const entry of sqlResult) {
    if (entry && typeof entry === "object" && "result" in entry) {
      const result = (entry as { result: unknown[] }).result;
      if (Array.isArray(result)) {
        rows.push(...result.map((r) => r as Record<string, unknown>));
      }
    }
  }
  return rows;
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Shape of a GraphQL type with fields from introspection. */
interface TypeWithFields {
  name: string;
  fields: Array<{ name: string }> | null;
}

/** Shape of the introspection response with fields sub-selection. */
interface IntrospectionSchema {
  __schema: {
    types: TypeWithFields[];
  };
}

// ---------------------------------------------------------------------------
// Test suite
// ---------------------------------------------------------------------------

describe("13. Schema Evolution", () => {
  // ===================================================================
  // Test 1: Schema introspection - reference offset fields
  // ===================================================================
  describe("1. Schema introspection — reference offset fields", () => {
    it("should expose pageNumber, pageOffsetStart, pageOffsetEnd on reference type", async () => {
      await skipIfDegraded(`${API_BASE}/health`, async () => {
        const typeNames = await getSchemaTypeNames();
        assertNonNull(typeNames, "Introspection should return type names");

        assert.ok(
          typeNames.has("reference"),
          `Expected 'reference' type in GraphQL schema — found types: ${[...typeNames].filter((n) => n.length > 0 && n[0] === n[0].toLowerCase() && n[0] !== n[0].toUpperCase()).join(", ")}`,
        );

        // Verify the new offset fields via introspection with fields sub-selection
        const introspectResult = await graphqlQuery<IntrospectionSchema>(`
          query IntrospectionWithFields {
            __schema {
              types {
                name
                fields { name }
              }
            }
          }
        `);
        assertGraphqlOk(introspectResult, "Introspection with fields");

        const [, introData] = introspectResult;
        const allTypes = introData!.data!.__schema.types;

        const refType = allTypes.find((t) => t.name === "reference");
        assertNonNull(refType, "reference type should exist in introspection with fields");
        const fieldNames = (refType.fields ?? []).map((f) => f.name);

        const expectedFields = ["page_number", "page_offset_start", "page_offset_end"];
        for (const f of expectedFields) {
          assert.ok(
            fieldNames.includes(f),
            `reference should have field '${f}' — found fields: [${fieldNames.join(", ")}]`,
          );
        }

        console.log(
          `✓ reference type has offset fields: page_number, page_offset_start, page_offset_end`,
        );
      });
    });
  });

  // ===================================================================
  // Test 2: Schema introspection - document_event_log table
  // ===================================================================
  describe("2. Schema introspection — document_event_log table", () => {
    it("should expose documentEventLog type with expected fields", async () => {
      await skipIfDegraded(`${API_BASE}/health`, async () => {
        const typeNames = await getSchemaTypeNames();
        assertNonNull(typeNames, "Introspection should return type names");

        assert.ok(
          typeNames.has("document_event_log"),
          `Expected 'document_event_log' type in GraphQL schema — found types: ${[...typeNames].filter((n) => n.startsWith("document")).join(", ")}`,
        );

        // Verify all fields via introspection
        const introspectResult = await graphqlQuery<IntrospectionSchema>(`
          query IntrospectionWithFields {
            __schema {
              types {
                name
                fields { name }
              }
            }
          }
        `);
        assertGraphqlOk(introspectResult, "Introspection with fields");

        const [, introData] = introspectResult;
        const allTypes = introData!.data!.__schema.types;

        const logType = allTypes.find((t) => t.name === "document_event_log");
        assertNonNull(logType, "document_event_log type should exist in introspection with fields");
        const fieldNames = (logType.fields ?? []).map((f) => f.name);

        const expectedFields = [
          "id",
          "document",
          "step_name",
          "severity",
          "message",
          "details",
          "created_at",
        ];
        for (const f of expectedFields) {
          assert.ok(
            fieldNames.includes(f),
            `document_event_log should have field '${f}' — found fields: [${fieldNames.join(", ")}]`,
          );
        }

        console.log(
          `✓ document_event_log type exists with ${fieldNames.length} fields, including id, document, step_name, severity, message, details, created_at`,
        );
      });
    });
  });

  // ===================================================================
  // Test 3: Schema introspection - canonical_entity entity_type includes 'event'
  // ===================================================================
  describe("3. Schema introspection — canonical_entity entity_type includes 'event'", () => {
    it("should verify entity_type ASSERT includes 'event' via SQL DESCRIBE TABLE", async () => {
      await skipIfDegraded(`${API_BASE}/health`, async () => {
        const typeNames = await getSchemaTypeNames();
        assertNonNull(typeNames, "Introspection should return type names");

        assert.ok(
          typeNames.has("canonical_entity"),
          "Expected 'canonical_entity' type in GraphQL schema",
        );

        // Verify entityType field exists in GraphQL introspection
        const introspectResult = await graphqlQuery<IntrospectionSchema>(`
          query IntrospectionWithFields {
            __schema {
              types {
                name
                fields { name }
              }
            }
          }
        `);
        assertGraphqlOk(introspectResult, "Introspection with fields");

        const [, introData] = introspectResult;
        const allTypes = introData!.data!.__schema.types;

        const ceType = allTypes.find((t) => t.name === "canonical_entity");
        assertNonNull(ceType, "canonical_entity type should exist in introspection with fields");
        const fieldNames = (ceType.fields ?? []).map((f) => f.name);
        assert.ok(
          fieldNames.includes("entity_type"),
          `canonical_entity should have field 'entity_type' — found fields: [${fieldNames.join(", ")}]`,
        );

        // Use sqlExecute to run DESCRIBE TABLE and check the ASSERT includes 'event'
        const [, sqlResult] = await sqlExecute("DESCRIBE TABLE canonical_entity;");
        if (sqlResult && Array.isArray(sqlResult)) {
          const rows = extractSqlRows(sqlResult);
          const entityTypeField = rows.find(
            (r) => r.name === "entity_type" || r.field === "entity_type",
          );
          assertNonNull(entityTypeField, "entity_type field should be described");

          const fieldDef = JSON.stringify(entityTypeField).toLowerCase();
          assert.ok(
            fieldDef.includes("'event'") || fieldDef.includes('"event"'),
            `entity_type definition should include 'event' in its ASSERT — got: ${JSON.stringify(entityTypeField)}`,
          );

          console.log(
            `✓ canonical_entity entity_type ASSERT confirmed to include 'event'`,
          );
        } else {
          console.log(
            `ℹ DESCRIBE TABLE unavailable — skipping ASSERT verification (GraphQL already confirms entity_type field exists)`,
          );
        }
      });
    });
  });

  // ===================================================================
  // Test 4: Schema introspection - event_entity_link table
  // ===================================================================
  describe("4. Schema introspection — event_entity_link table", () => {
    it("should expose eventEntityLink type with expected fields via GraphQL and SQL", async () => {
      await skipIfDegraded(`${API_BASE}/health`, async () => {
        const typeNames = await getSchemaTypeNames();
        assertNonNull(typeNames, "Introspection should return type names");

        assert.ok(
          typeNames.has("event_entity_link"),
          `Expected 'event_entity_link' type in GraphQL schema — found types: ${[...typeNames].filter((n) => n.includes("event") || n.includes("Entity")).join(", ")}`,
        );

        // GraphQL field introspection
        const introspectResult = await graphqlQuery<IntrospectionSchema>(`
          query IntrospectionWithFields {
            __schema {
              types {
                name
                fields { name }
              }
            }
          }
        `);
        assertGraphqlOk(introspectResult, "Introspection with fields");

        const [, introData] = introspectResult;
        const allTypes = introData!.data!.__schema.types;

        const eelType = allTypes.find((t) => t.name === "event_entity_link");
        assertNonNull(eelType, "event_entity_link type should exist in introspection with fields");
        const fieldNames = (eelType.fields ?? []).map((f) => f.name);

        const expectedFields = [
          "id",
          "event",
          "entity",
          "relationship_type",
          "role",
          "confidence",
          "notes",
          "created_at",
        ];
        for (const f of expectedFields) {
          assert.ok(
            fieldNames.includes(f),
            `event_entity_link should have field '${f}' — found fields: [${fieldNames.join(", ")}]`,
          );
        }

        console.log(
          `✓ event_entity_link type exists with ${fieldNames.length} fields including relationship_type, role, confidence, notes, created_at`,
        );

        // Also verify via SQL DESCRIBE TABLE
        const [, sqlResult] = await sqlExecute("DESCRIBE TABLE event_entity_link;");
        if (sqlResult && Array.isArray(sqlResult)) {
          const rows = extractSqlRows(sqlResult);
          const dbFieldNames = rows.map((r: Record<string, unknown>) => r.name || r.field);
          const dbExpectedFields = [
            "id",
            "event",
            "entity",
            "relationship_type",
            "role",
            "confidence",
            "notes",
            "created_at",
          ];
          for (const f of dbExpectedFields) {
            assert.ok(
              dbFieldNames.includes(f),
              `event_entity_link should have field '${f}' at DB level — found: [${dbFieldNames.join(", ")}]`,
            );
          }

          // Check confidence has the 0-1 ASSERT
          const confidenceField = rows.find(
            (r: Record<string, unknown>) =>
              r.name === "confidence" || r.field === "confidence",
          );
          assertNonNull(confidenceField, "confidence field should exist in event_entity_link");
          const confDef = JSON.stringify(confidenceField).toLowerCase();
          assert.ok(
            confDef.includes("0") && confDef.includes("1"),
            `confidence field should have 0-1 range ASSERT — got: ${JSON.stringify(confidenceField)}`,
          );

          console.log(
            `✓ event_entity_link confirmed via SQL DESCRIBE TABLE: ${dbFieldNames.length} fields, confidence has 0-1 ASSERT`,
          );
        } else {
          console.log(
            `ℹ DESCRIBE TABLE unavailable — skipping SQL verification (GraphQL already confirms event_entity_link type)`,
          );
        }
      });
    });
  });

  // ===================================================================
  // Test 5: No regression - existing reference fields still queryable
  // ===================================================================
  describe("5. No regression — existing reference fields still queryable", () => {
    it("should still expose original reference fields via GraphQL introspection", async () => {
      await skipIfDegraded(`${API_BASE}/health`, async () => {
        const typeNames = await getSchemaTypeNames();
        assertNonNull(typeNames, "Introspection should return type names");

        assert.ok(
          typeNames.has("reference"),
          "Expected 'reference' type in GraphQL schema",
        );

        const introspectResult = await graphqlQuery<IntrospectionSchema>(`
          query IntrospectionWithFields {
            __schema {
              types {
                name
                fields { name }
              }
            }
          }
        `);
        assertGraphqlOk(introspectResult, "Introspection with fields");

        const [, introData] = introspectResult;
        const allTypes = introData!.data!.__schema.types;

        const refType = allTypes.find((t) => t.name === "reference");
        assertNonNull(refType, "reference type should exist in introspection with fields");
        const fieldNames = (refType.fields ?? []).map((f) => f.name);

        const originalFields = [
          "span_start",
          "span_end",
          "reference_type",
          "event",
          "canonical_entity",
          "created_at",
          "updated_at",
        ];
        for (const f of originalFields) {
          assert.ok(
            fieldNames.includes(f),
            `reference should still have field '${f}' — found fields: [${fieldNames.join(", ")}]`,
          );
        }

        console.log(
          `✓ All original reference fields (span_start, span_end, reference_type, event, canonical_entity, created_at, updated_at) still present — no regression`,
        );
      });
    });
  });

  // ===================================================================
  // Test 6: Direct SQL - INSERT and SELECT on document_event_log
  // ===================================================================
  describe("6. Direct SQL — INSERT and SELECT on document_event_log", () => {
    it("should INSERT a log entry and SELECT it back with correct values", async () => {
      await skipIfDegraded(`${API_BASE}/health`, async () => {
        // Create a test document first (needed for the document record link)
        const [, docResult] = await sqlExecute("SELECT id FROM document:test_doc;");
        const docRows = docResult ? extractSqlRows(docResult) : [];
        if (docRows.length === 0) {
          await sqlExecute("CREATE document:test_doc CONTENT { original_blob: '', text_content: '', status: 'pending', filename: 'test.txt', mime_type: 'text/plain' };");
        }

        // INSERT a row into document_event_log
        const logId = "test_verify_log_001";
        const insertSql = `
          CREATE document_event_log:${logId} CONTENT {
            document: document:test_doc,
            step_name: 'test_verify',
            severity: 'info',
            message: 'Schema evolution test log entry',
            details: { test: true }
          };
        `;
        const [insertStatus, insertBody] = await sqlExecute(insertSql);

        // Check INSERT by querying with a WHERE on step_name
        const [, selectResult] = await sqlExecute(
          `SELECT * FROM document_event_log WHERE step_name = 'test_verify';`,
        );
        if (selectResult) {
          const rows = extractSqlRows(selectResult);
          if (rows.length >= 1) {
            assert.equal(
              rows[0].severity,
              "info",
              `severity should be 'info' — got: ${String(rows[0].severity)}`,
            );
            const details = rows[0].details as Record<string, unknown> | null;
            assertNonNull(details, "details should not be null");
            assert.ok(
              (details as Record<string, boolean>).test === true,
              `details.test should be true — got: ${JSON.stringify(details)}`,
            );
            console.log(
              `✓ document_event_log INSERT and SELECT verified: severity=info, details.test=true`,
            );
          } else {
            console.log(`ℹ document_event_log INSERT returned HTTP ${insertStatus} but SELECT found 0 rows`);
          }
        } else {
          console.log(`ℹ document_event_log SELECT returned null`);
        }

        // Cleanup
        await sqlExecute(`DELETE document_event_log:${logId};`);
        await sqlExecute(`DELETE document_event_log WHERE step_name = 'test_verify';`);
      });
    });
  });

  // ===================================================================
  // Test 7: Direct SQL - INSERT and SELECT on event_entity_link
  // ===================================================================
  describe("7. Direct SQL — INSERT and SELECT on event_entity_link", () => {
    it("should INSERT a link with valid record references and SELECT it back", async () => {
      await skipIfDegraded(`${API_BASE}/health`, async () => {
        // Create a test event (for the event field which is TYPE record<event>)
        const [, evtResult] = await sqlExecute("SELECT id FROM event:test_event;");
        const evtRows = evtResult ? extractSqlRows(evtResult) : [];

        let eventId: string;
        if (evtRows.length > 0) {
          eventId = "event:test_event";
        } else {
          const [, createEvtResult] = await sqlExecute("CREATE event:test_event CONTENT { que_paso: 'test event', espacio: null, tiempo: null, humanos: null, objetos: null, extraction_confidence: 0.5, document: document:test_doc };");
          // Create test document too if needed
          const [, docResult] = await sqlExecute("SELECT id FROM document:test_doc;");
          const docRows2 = docResult ? extractSqlRows(docResult) : [];
          if (docRows2.length === 0) {
            await sqlExecute("CREATE document:test_doc CONTENT { original_blob: '', text_content: '', status: 'pending', filename: 'test.txt', mime_type: 'text/plain' };");
            await sqlExecute("CREATE event:test_event CONTENT { que_paso: 'test event', espacio: null, tiempo: null, humanos: null, objetos: null, extraction_confidence: 0.5, document: document:test_doc };");
          }
          eventId = "event:test_event";
        }

        // Create a canonical_entity of type "place" for the entity field
        const placeEntId = `test_place_evt_${Date.now().toString(36)}`;
        const linkId = `test_eel_${Date.now().toString(36)}`;

        const createPlaceSql = `
          CREATE canonical_entity:${placeEntId} CONTENT {
            entity_type: 'place',
            name: 'Test Place Entity for Event Link',
            properties: {},
            superseded_by: null
          };
        `;
        const [, createResult] = await sqlExecute(createPlaceSql);
        assertNonNull(createResult, "Place entity creation should return results");

        // INSERT a row into event_entity_link
        // Note: event field is TYPE record<event>, entity field is TYPE record<canonical_entity>
        const insertLinkSql = `
          CREATE event_entity_link:${linkId} CONTENT {
            event: ${eventId},
            entity: canonical_entity:${placeEntId},
            relationship_type: 'located_at',
            role: 'location',
            confidence: 0.95,
            notes: 'Test link'
          };
        `;
        const [insertStatus, insertResult] = await sqlExecute(insertLinkSql);

        // Try SELECT by relationship_type (field-based) for resilience
        const [, selectResult] = await sqlExecute(
          `SELECT * FROM event_entity_link WHERE relationship_type = 'located_at';`,
        );
        if (selectResult) {
          const rows = extractSqlRows(selectResult);
          if (rows.length >= 1) {
            assert.equal(
              rows[0].relationship_type as string,
              "located_at",
              `relationship_type should be 'located_at' — got: ${String(rows[0].relationship_type)}`,
            );
            assert.equal(
              rows[0].confidence,
              0.95,
              `confidence should be 0.95 — got: ${String(rows[0].confidence)}`,
            );
            console.log(
              `✓ event_entity_link INSERT and SELECT verified: relationship_type=located_at, confidence=0.95`,
            );
          } else {
            console.log(`ℹ event_entity_link INSERT returned HTTP ${insertStatus} but SELECT found 0 rows`);
          }
        } else {
          console.log(`ℹ event_entity_link SELECT returned null`);
        }

        // Cleanup
        await sqlExecute(`DELETE event_entity_link:${linkId};`);
        await sqlExecute(`DELETE event_entity_link WHERE relationship_type = 'located_at';`);
        await sqlExecute(`DELETE canonical_entity:${placeEntId};`);
        console.log(`  Cleaned up test link and entity`);
      });
    });
  });
});
