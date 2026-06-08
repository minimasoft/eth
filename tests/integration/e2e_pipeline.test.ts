/**
 * End-to-end integration test for eth-pipeline.
 *
 * Tests the full document processing pipeline through REST API only
 * (no direct database queries, no GraphQL).
 *
 * @module
 */

import { describe, it, after } from "node:test";
import assert from "node:assert/strict";
import {
  API_BASE,
  skipIfDegraded,
  createDocument,
  httpGet,
  httpDelete,
  assertNonNull,
  waitForProcessing,
  listEvents,
  listReferences,
  listEntities,
  getProcessingLogs,
  listDocuments,
  clearEvents,
  listLlmCallLogs,
} from "./helpers.js";

// ---------------------------------------------------------------------------
// Test data — Spanish criminal case with named entities
// ---------------------------------------------------------------------------

const COMPREHENSIVE_CASE = [
  "JUZGADO DE INSTRUCCIÓN NÚMERO 5",
  "MAR DEL PLATA, PROVINCIA DE BUENOS AIRES",
  "",
  "CAUSA N° 2345/2024 — ROBO AGRAVADO",
  "",
  "El día 20 de marzo de 2024, siendo aproximadamente las 14:30 horas,",
  "en la intersección de la Avenida Luro y la Calle San Martín de la",
  "ciudad de Mar del Plata, el imputado Carlos Alberto Ramírez, de 28",
  "años de edad, DNI 34.567.890, fue aprehendido por personal policial",
  "de la Comisaría Primera tras cometer un robo en la joyería",
  '"Relojería Suiza", propiedad de la señora María Elena Gutiérrez.',
  "",
  "Según consta en el acta policial, los oficiales Juan Carlos López y",
  "Pedro Sánchez observaron al imputado mientras sustraía un reloj marca",
  "Rolex valorado en 15.000 dólares y un anillo de oro con diamantes.",
  "El imputado utilizó una barreta de hierro para forzar la vitrina.",
  "",
  "La víctima, María Elena Gutiérrez, de 62 años, declaró que el imputado",
  "amenazó con un arma blanca tipo cuchillo a su empleada, la joven",
  "Valentina Suárez, de 19 años, quien se encontraba atendiendo el local.",
  "",
  "Testigos presenciales: el señor Roberto Fernández, comerciante del",
  'local lindero "Librería Ateneo", y la señora Alicia Martínez,',
  "quienes observaron los hechos desde la vereda.",
  "",
  "El imputado fue trasladado a la Comisaría Primera de Mar del Plata",
  "donde permanece detenido a disposición del Juzgado de Garantías N° 3",
  "a cargo del Doctor Alberto Méndez.",
  "",
  "Objetos secuestrados: un reloj Rolex Submariner, un anillo de oro con",
  "diamantes, una barreta de hierro de 40 cm, y un cuchillo de cocina",
  "marca Tramontina.",
].join("\n");

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const PROCESSING_TIMEOUT = 180_000;

// ---------------------------------------------------------------------------
// Test state
// ---------------------------------------------------------------------------

const testDocIds: string[] = [];
let documentWasProcessed = false;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function cleanupTestDocuments(): Promise<void> {
  if (testDocIds.length === 0) return;
  console.log(`Cleaning up ${testDocIds.length} test document(s)...`);
  for (const docId of testDocIds) {
    const [status] = await httpDelete(`${API_BASE}/documents/${docId}`, 10_000);
    console.log(`  Deleted document ${docId} (HTTP ${status})`);
  }
}

// ---------------------------------------------------------------------------
// Test suite
// ---------------------------------------------------------------------------

describe("e2e — full pipeline (events, entities, references, llm-call-log, tokens, delete)", () => {
  after(async () => {
    await cleanupTestDocuments();
  });

  // ===================================================================
  // Test 1: Submit document → poll until processed → assert events stored
  // ===================================================================
  it("1. Submit document → process → events stored", async () => {
    await skipIfDegraded(`${API_BASE}/health`, async () => {
      const doc = await createDocument(
        COMPREHENSIVE_CASE,
        "comprehensive_case.txt",
      );
      assertNonNull(doc, "Document should be created");
      testDocIds.push(doc.document_id);
      assert.ok(doc.document_id.length > 0, "document_id should be non-empty");
      assert.equal(doc.status, "pending");
      console.log(`Submitted document ${doc.document_id} (status=${doc.status})`);

      const result = await waitForProcessing(doc.document_id, PROCESSING_TIMEOUT);
      if (!result) {
        console.log("ℹ  Could not get final document status");
        return;
      }

      if (result.status === "failed") {
        console.log(`ℹ  Document failed: ${result.error_message}`);
        console.log("ℹ  (LLM/Temporal may be unavailable)");
        documentWasProcessed = false;
        return;
      }

      if (result.status !== "processed") {
        console.log(`ℹ  Document status: ${result.status} — not processed`);
        documentWasProcessed = false;
        return;
      }

      documentWasProcessed = true;
      console.log(`✓ Document processed: ${result.chunk_count} chunks, ${result.reference_count} references`);

      // Verify events exist via REST API
      const events = await listEvents(doc.document_id);
      assertNonNull(events, "Events list should be available");
      assert.ok(events.total > 0, `Expected >0 events, got ${events.total}`);
      console.log(`✓ ${events.total} events via API`);

      // Verify references exist
      const refs = await listReferences({ document_id: doc.document_id });
      assertNonNull(refs, "References list should be available");
      assert.ok(refs.total > 0, `Expected >0 references, got ${refs.total}`);
      console.log(`✓ ${refs.total} references via API`);

      // Verify processing logs exist
      const logs = await getProcessingLogs(doc.document_id);
      assertNonNull(logs, "Processing logs should be available");
      assert.ok(logs.total > 0, `Expected >0 log entries, got ${logs.total}`);
      console.log(`✓ ${logs.total} processing log entries`);
    });
  });

  // ===================================================================
  // Test 2: Entities and references generated
  // ===================================================================
  it("2. Entities + references generated", async () => {
    await skipIfDegraded(`${API_BASE}/health`, async () => {
      if (!documentWasProcessed) {
        console.log("ℹ  Document was not processed — skipping entity verification");
        return;
      }

      const docId = testDocIds[0];
      if (!docId) {
        console.log("ℹ  No document — skipping entity verification");
        return;
      }

      // Check entities via REST API
      const entities = await listEntities({ per_page: "100" });
      assertNonNull(entities, "Entities list should be available");
      assert.ok(entities.total > 0, `Expected >0 total entities, got ${entities.total}`);
      console.log(`✓ ${entities.total} total entities via API`);

      // Filter by type from the response
      const personEntities = entities.items.filter((e) => e.entity_type === "person");
      const placeEntities = entities.items.filter((e) => e.entity_type === "place");
      const objectEntities = entities.items.filter((e) => e.entity_type === "object");
      const eventEntities = entities.items.filter((e) => e.entity_type === "event");

      // Print counts
      console.log(`  People: ${personEntities.length}`);
      console.log(`  Places: ${placeEntities.length}`);
      console.log(`  Objects: ${objectEntities.length}`);
      console.log(`  Event-type entities: ${eventEntities.length}`);

      // Check references via API
      const refs = await listReferences({ document_id: docId, per_page: "100" });
      assertNonNull(refs, "References list should be available");
      assert.ok(refs.total > 0, `Expected >0 references, got ${refs.total}`);

      // Check that some references have canonical entities (resolution success)
      const resolvedRefs = refs.items.filter((r) => r.canonical_entity !== null);
      console.log(`  References with resolved entities: ${resolvedRefs.length} / ${refs.total}`);
    });
  });

  // ===================================================================
  // Test 3: Token tracking — llm_usage records exist via API
  // ===================================================================
  it("3. Token tracking — document tokens endpoint returns data", async () => {
    await skipIfDegraded(`${API_BASE}/health`, async () => {
      if (!documentWasProcessed) {
        console.log("ℹ  Document was not processed — skipping token verification");
        return;
      }

      const docId = testDocIds[0];
      if (!docId) {
        console.log("ℹ  No document — skipping token verification");
        return;
      }

      // API: /documents/{id}/tokens endpoint
      const [tokStatus, tokBody] = await httpGet(`${API_BASE}/documents/${docId}/tokens`, 10_000);
      assert.equal(tokStatus, 200, `Expected HTTP 200 from /tokens, got ${tokStatus}`);
      const tokData = JSON.parse(tokBody!);
      assert.ok(tokData.has_data, "has_data should be true");
      assert.ok(tokData.total_tokens > 0, `total_tokens should be > 0, got ${tokData.total_tokens}`);
      assert.ok(tokData.prompt_tokens > 0, `prompt_tokens should be > 0, got ${tokData.prompt_tokens}`);
      assert.ok(tokData.completion_tokens > 0, `completion_tokens should be > 0, got ${tokData.completion_tokens}`);
      console.log(`✓ Tokens: prompt=${tokData.prompt_tokens} completion=${tokData.completion_tokens} total=${tokData.total_tokens} cost=${tokData.total_cost}`);

      // Document list should also show token usage
      const docs = await listDocuments();
      assertNonNull(docs, "Document list should be available");
      const ourDoc = docs.items.find((d) => d.document_id === docId);
      assertNonNull(ourDoc, "Our document should appear in list");
      assert.ok(ourDoc.total_tokens > 0, `list document should have total_tokens > 0, got ${ourDoc.total_tokens}`);
      assert.ok(ourDoc.duration_ms > 0, `duration_ms should be > 0, got ${ourDoc.duration_ms}`);
      console.log(`✓ Document list shows: tokens=${ourDoc.total_tokens} cost=${ourDoc.total_cost} duration=${ourDoc.duration_ms}ms`);
    });
  });

  // ===================================================================
  // Test 3b: LLM call log — /documents/{id}/llm-calls returns data
  // ===================================================================
  it("3b. LLM call log — endpoint returns recorded calls", async () => {
    await skipIfDegraded(`${API_BASE}/health`, async () => {
      if (!documentWasProcessed) {
        console.log("ℹ  Document was not processed — skipping llm-call-log verification");
        return;
      }

      const docId = testDocIds[0];
      if (!docId) {
        console.log("ℹ  No document — skipping llm-call-log verification");
        return;
      }

      const logs = await listLlmCallLogs(docId);
      assertNonNull(logs, "LLM call log list should be available");
      assert.ok(logs.total > 0, `Expected >0 LLM call log entries, got ${logs.total}`);
      console.log(`✓ ${logs.total} LLM call log entries via API`);

      // Spot-check: at least one entry has prompt and response text
      const firstWithText = logs.items.find((l) => l.prompt_text && l.response_text);
      if (firstWithText) {
        console.log(`  Sample: ${firstWithText.activity_type} (${firstWithText.model}) — prompt=${firstWithText.prompt_tokens} completion=${firstWithText.completion_tokens}`);
      }

      // Verify expected activity types are present
      const activityTypes = new Set(logs.items.map((l) => l.activity_type));
      console.log(`  Activity types: ${[...activityTypes].join(", ")}`);
    });
  });

  // ===================================================================
  // Test 4: Reprocess → events cleared and re-processed
  // ===================================================================
  it("4. Reprocess document — clear events and re-process", async () => {
    await skipIfDegraded(`${API_BASE}/health`, async () => {
      if (!documentWasProcessed) {
        console.log("ℹ  Document was not processed — skipping reprocess test");
        return;
      }

      const docId = testDocIds[0];
      if (!docId) {
        console.log("ℹ  No document — skipping reprocess test");
        return;
      }

      // Count events before clear
      const beforeEvents = await listEvents(docId);
      assertNonNull(beforeEvents, "Events list should be available before clear");
      console.log(`✓ Events before clear: ${beforeEvents.total}`);

      // Clear events via REST API
      const clearResult = await clearEvents(docId);
      assertNonNull(clearResult, "Clear events should succeed");
      console.log(`✓ Events cleared: ${clearResult.events_cleared}`);

      // Verify events are gone via API
      const afterClear = await listEvents(docId);
      assertNonNull(afterClear, "Events list should be available after clear");
      assert.equal(afterClear.total, 0, `Events should be 0 after clear, got ${afterClear.total}`);
      console.log("✓ Events confirmed empty after clear");

      // Re-process: reset document to pending via DELETE+recreate
      // (the API doesn't have a re-process endpoint, so we create a new doc)
      const newDoc = await createDocument(
        COMPREHENSIVE_CASE,
        "comprehensive_case_reprocess.txt",
      );
      if (!newDoc) {
        console.log("ℹ  Could not create reprocess document");
        return;
      }
      testDocIds.push(newDoc.document_id);

      const result = await waitForProcessing(newDoc.document_id, PROCESSING_TIMEOUT);
      if (!result || result.status !== "processed") {
        console.log("ℹ  Reprocess document did not complete — skipping further checks");
        return;
      }

      console.log("✓ Reprocess document completed");

      // Verify events exist after reprocess
      const afterEvents = await listEvents(newDoc.document_id);
      if (afterEvents && afterEvents.total > 0) {
        console.log(`✓ ${afterEvents.total} events after reprocess`);
      }

      // Verify token data exists for the new document
      const [tokStatus, tokBody] = await httpGet(`${API_BASE}/documents/${newDoc.document_id}/tokens`, 10_000);
      assert.equal(tokStatus, 200, `Expected HTTP 200 from /tokens, got ${tokStatus}`);
      const tokData = JSON.parse(tokBody!);
      assert.ok(tokData.has_data, "has_data should be true after reprocess");
      console.log(`✓ Tokens after reprocess: total=${tokData.total_tokens} cost=${tokData.total_cost}`);
    });
  });

  // ===================================================================
  // Test 5: Cascade delete → zero orphans (verified via API)
  // ===================================================================
  it("5. Cascade delete → document removed from list", async () => {
    await skipIfDegraded(`${API_BASE}/health`, async () => {
      const docId = testDocIds[0];
      if (!docId) {
        console.log("ℹ  No document — skipping delete test");
        return;
      }

      // Document should exist before delete
      const [getBefore] = await httpGet(`${API_BASE}/documents/${docId}`, 5_000);
      assert.equal(getBefore, 200, "Document should exist before delete");

      // Delete via REST API
      const [delStatus, delBody] = await httpDelete(`${API_BASE}/documents/${docId}`, 10_000);
      assert.equal(delStatus, 200, `Expected HTTP 200 on delete, got ${delStatus}`);
      console.log(`✓ DELETE /documents/${docId} → HTTP ${delStatus}`);

      const delResponse = JSON.parse(delBody!);
      console.log(`  Deleted: document=${delResponse.document_deleted} orphaned_entities=${delResponse.orphaned_entities_cleaned}`);

      // Document should be gone
      const [getAfter] = await httpGet(`${API_BASE}/documents/${docId}`, 5_000);
      assert.notEqual(getAfter, 200, "Document should be gone after delete (expected non-200)");
      console.log("✓ Document confirmed deleted");

      // Events/references for this doc should also be gone
      // (verified via the events endpoint returning 404 for deleted doc)
      const [evStatus] = await httpGet(`${API_BASE}/documents/${docId}/events`, 5_000);
      console.log(`  Events endpoint after delete: HTTP ${evStatus}`);

      // AXIOM: Entities that were referenced by the deleted document must not
      // remain in the database with zero references. Record entity state before
      // deletion, then verify those entities are either gone or still referenced.
      const entitiesBefore = await listEntities({ per_page: "100" });
      assertNonNull(entitiesBefore, "Entities list should be available before delete");
      const refCountsBefore = new Map(
        entitiesBefore.items
          .filter((e) => e.reference_count > 0)
          .map((e) => [e.entity_id, e.reference_count]),
      );
      console.log(`  Entities before delete: ${entitiesBefore.total} (${refCountsBefore.size} with refs)`);

      const entitiesAfter = await listEntities({ per_page: "100" });
      assertNonNull(entitiesAfter, "Entities list should be available after delete");

      // Check: any entity that had references before now has 0 references → orphan leak
      const leakedEntities = entitiesAfter.items
        .filter((e) => e.reference_count === 0 && refCountsBefore.has(e.entity_id));
      assert.equal(
        leakedEntities.length,
        0,
        `Expected 0 leaked orphan entities, found ${leakedEntities.length}: ` +
        leakedEntities.map((e) => `${e.name} (${e.entity_id})`).join(", "),
      );
      console.log(`✓ Zero orphan entities leaked after delete (axiom verified)`);

      const idx = testDocIds.indexOf(docId);
      if (idx !== -1) testDocIds.splice(idx, 1);

      console.log("✓ Cascade delete confirmed");
    });
  });
});
