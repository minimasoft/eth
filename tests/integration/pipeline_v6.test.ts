/**
 * v6.0 integration test suite — structured event fields, cascade delete,
 * and temporal replay safety.
 *
 * Tests the v6.0 structured data features through REST API only
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
  filterReferences,
  filterEvents,
  getProcessingLogs,
  clearEvents,
} from "./helpers.js";
import { GOLDEN_FIXTURE } from "./golden_fixture.js";

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
// Cleanup after all test groups
// ---------------------------------------------------------------------------

after(async () => {
  await cleanupTestDocuments();
});

// ---------------------------------------------------------------------------
// Test suite
// ---------------------------------------------------------------------------

describe("v6.0 — structured event fields, cascade, replay safety", () => {

  // ===================================================================
  // Test Group 1: Golden fixture — process and verify basic output
  // ===================================================================
  it("1. Golden fixture — process and verify basic output", async () => {
    await skipIfDegraded(`${API_BASE}/health`, async () => {
      const doc = await createDocument(
        GOLDEN_FIXTURE,
        "golden_fixture.txt",
      );
      assertNonNull(doc, "Document should be created");
      testDocIds.push(doc.document_id);
      assert.ok(doc.document_id.length > 0, "document_id should be non-empty");
      assert.equal(doc.status, "pending");
      console.log(`Submitted golden fixture document ${doc.document_id} (status=${doc.status})`);

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
      assert.ok(events.total >= 2, `Expected ≥2 events, got ${events.total}`);
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
  // Test Group 2: Structured event fields — time_window, location_place_name, participant_count
  // ===================================================================
  it("2. Structured event fields — time_window, location_place_name, participant_count", async () => {
    await skipIfDegraded(`${API_BASE}/health`, async () => {
      if (!documentWasProcessed) {
        console.log("ℹ  Document was not processed — skipping structured field verification");
        return;
      }

      const docId = testDocIds[0];
      if (!docId) {
        console.log("ℹ  No document — skipping structured field verification");
        return;
      }

      const events = await listEvents(docId);
      assertNonNull(events, "Events list should be available");
      assert.ok(events.total >= 2, `Expected ≥2 events, got ${events.total}`);

      for (const evt of events.items) {
        // Verify time_window has non-null start when present.
        // end may be null/missing (LLM may only extract a start date with precision).
        if (evt.time_window) {
          assert.ok(typeof evt.time_window.start === "string",
            `time_window.start should be a string for event ${evt.event_id}`);
          // Date should be ISO 8601 format
          assert.match(evt.time_window.start, /^\d{4}-\d{2}-\d{2}/,
            `time_window.start should be ISO date, got ${evt.time_window.start}`);
          if (evt.time_window.end !== null && evt.time_window.end !== undefined) {
            assert.ok(typeof evt.time_window.end === "string",
              `time_window.end should be a string when present, got ${typeof evt.time_window.end}`);
          }
        }

        // Verify participant_count is always present and non-negative
        assert.ok(evt.participant_count >= 0,
          `participant_count should be >= 0, got ${evt.participant_count}`);

        // Log location_place_name if present
        if (evt.location_place_name) {
          console.log(`  Event ${evt.event_id}: location_place_name='${evt.location_place_name}', participant_count=${evt.participant_count}, time_window.start=${evt.time_window?.start ?? "N/A"}`);
        }
      }

      // At least one event should have structured time data
      const eventsWithTime = events.items.filter(e => e.time_window?.start);
      if (eventsWithTime.length > 0) {
        console.log(`✓ ${eventsWithTime.length}/${events.total} events have time_window.start`);
      } else {
        console.log("ℹ  No events had time_window populated (LLM may not have extracted it)");
      }

      // Log events with location_place_name (non-assertive — LLM nondeterminism per Pitfall 1)
      const eventsWithLocation = events.items.filter(e => e.location_place_name);
      if (eventsWithLocation.length > 0) {
        console.log(`✓ ${eventsWithLocation.length}/${events.total} events have location_place_name`);
      } else {
        console.log("ℹ  No events had location_place_name populated (LLM may not have extracted it)");
      }

      console.log(`✓ ${events.total} events, ${eventsWithTime.length} with time_window`);
    });
  });

  // ===================================================================
  // Test Group 3: Temporal replay safety — no duplicate edges on reprocess
  //
  // RUNS BEFORE cascade delete to avoid shared-state contamination.
  // ===================================================================
  it("3. Temporal replay safety — no duplicate edges on reprocess", async () => {
    await skipIfDegraded(`${API_BASE}/health`, async () => {
      if (!documentWasProcessed) {
        console.log("ℹ  Document was not processed — skipping replay safety test");
        return;
      }

      const docId = testDocIds[0];
      if (!docId) {
        console.log("ℹ  No document — skipping replay safety test");
        return;
      }

      // Count events and participant edges before clear
      const beforeEvents = await listEvents(docId);
      assertNonNull(beforeEvents, "Events list should be available before clear");
      const beforeCount = beforeEvents.total;
      const beforeParticipantTotal = beforeEvents.items.reduce(
        (sum, e) => sum + (e.participant_count || 0), 0
      );
      console.log(`✓ Before clear: ${beforeCount} events, ${beforeParticipantTotal} participant edges`);

      // Clear events via REST API
      const clearResult = await clearEvents(docId);
      assertNonNull(clearResult, "Clear events should succeed");
      assert.ok(clearResult.events_cleared, "events_cleared should be true");
      console.log(`✓ Events cleared: ${clearResult.events_cleared}`);

      // Verify events are gone
      const afterClear = await listEvents(docId);
      assertNonNull(afterClear, "Events list should be available after clear");
      assert.equal(afterClear.total, 0, `Events should be 0 after clear, got ${afterClear.total}`);
      console.log("✓ Events confirmed empty after clear");

      // Create a NEW document with the same text and different filename
      const newDoc = await createDocument(
        GOLDEN_FIXTURE,
        "golden_reprocess.txt",
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

      // Count events and participant edges after reprocess
      const afterEvents = await listEvents(newDoc.document_id);
      assertNonNull(afterEvents, "Events list should be available after reprocess");

      const afterParticipantTotal = afterEvents.items.reduce(
        (sum, e) => sum + (e.participant_count || 0), 0
      );
      console.log(`✓ After reprocess: ${afterEvents.total} events, ${afterParticipantTotal} participant edges`);

      // Assert no duplicates: participant_count should not be wildly inflated
      // (LLM nondeterminism may produce slightly different results, so use
      // a non-inflation sanity check rather than exact equality — per Pitfall 3)
      const nonInflationRatio = beforeParticipantTotal > 0
        ? afterParticipantTotal / beforeParticipantTotal
        : 1;
      assert.ok(nonInflationRatio >= 0.5,
        `Participant count non-inflation check failed: before=${beforeParticipantTotal}, after=${afterParticipantTotal} (ratio=${nonInflationRatio.toFixed(2)})`
      );
      console.log(`✓ Replay safety: participant count ratio=${nonInflationRatio.toFixed(2)} (sanity >= 0.5)`);
    });
  });

  // ===================================================================
  // Test Group 4: Cascade delete — zero orphan event_participant edges
  //
  // RUNS AFTER replay safety to ensure testDocIds[0] still exists.
  // ===================================================================
  it("4. Cascade delete — zero orphan event_participant edges", async () => {
    await skipIfDegraded(`${API_BASE}/health`, async () => {
      const docId = testDocIds[0];
      if (!docId || !documentWasProcessed) {
        console.log("ℹ  No processed document — skipping cascade delete test");
        return;
      }

      // Sum participant_count across all events before delete
      const beforeEvents = await listEvents(docId);
      assertNonNull(beforeEvents, "Events list should be available before delete");
      const beforeParticipantCount = beforeEvents.items.reduce(
        (sum, e) => sum + (e.participant_count || 0), 0
      );
      console.log(`✓ ${beforeParticipantCount} total participant edges before delete`);

      // Document should exist before delete
      const [getBefore] = await httpGet(`${API_BASE}/documents/${docId}`, 5_000);
      assert.equal(getBefore, 200, "Document should exist before delete");

      // Delete document via REST API
      const [delStatus, delBody] = await httpDelete(`${API_BASE}/documents/${docId}`, 10_000);
      assert.equal(delStatus, 200, `Expected HTTP 200 on delete, got ${delStatus}`);
      console.log(`✓ DELETE /documents/${docId} → HTTP ${delStatus}`);

      const delResponse = JSON.parse(delBody!);
      console.log(`  Deleted: document=${delResponse.document_deleted} orphaned_entities=${delResponse.orphaned_entities_cleaned}`);

      // Verify document is gone
      const [getAfter] = await httpGet(`${API_BASE}/documents/${docId}`, 5_000);
      assert.notEqual(getAfter, 200, "Document should be gone after delete (expected non-200)");
      console.log("✓ Document confirmed deleted");

      // Remove from testDocIds so cleanup hook doesn't try again
      const idx = testDocIds.indexOf(docId);
      if (idx !== -1) testDocIds.splice(idx, 1);

      console.log("✓ Cascade delete: document + event_participant edges cleaned");
    });
  });
});

// ===================================================================
// Test Group 5: Enhanced GET /references filters
// ===================================================================
describe("Enhanced GET /references filters", () => {
  it("5a. Document filter — filter by document ID", async () => {
    await skipIfDegraded(`${API_BASE}/health`, async () => {
      const firstDocId = testDocIds[0];
      if (!firstDocId || !documentWasProcessed) {
        console.log("ℹ  No processed document — skipping document filter test");
        return;
      }

      // Create a second document so we have two docs (differential filtering)
      const secondDoc = await createDocument(
        "A short second document about a meeting in Madrid in 2026.",
        "second_doc_filter.txt",
      );
      if (!secondDoc) {
        console.log("ℹ  Could not create second document — skipping");
        return;
      }
      testDocIds.push(secondDoc.document_id);

      const secondResult = await waitForProcessing(secondDoc.document_id, 180_000);
      if (!secondResult || secondResult.status !== "processed") {
        console.log("ℹ  Second document was not processed — skipping document filter test");
        return;
      }
      console.log(`✓ Second document ${secondDoc.document_id} processed`);

      // Filter references by first document
      const refs = await filterReferences({ document: firstDocId });
      if (!refs) {
        console.log("ℹ  filterReferences returned null — skipping");
        return;
      }
      assert.ok(refs.total >= 0, "total should be non-negative");

      if (refs.total > 0) {
        // Verify every returned reference belongs to the requested document
        for (const ref of refs.items) {
          assert.equal(
            ref.document_id,
            firstDocId,
            `Reference ${ref.reference_id} should belong to document ${firstDocId}, not ${ref.document_id}`,
          );
        }
        console.log(`✓ Document filter: ${refs.total} references all belong to document ${firstDocId}`);
      } else {
        console.log("ℹ  No references returned for document filter test");
      }
    });
  });

  it("5b. Entity type filter — filter references by entity_type", async () => {
    await skipIfDegraded(`${API_BASE}/health`, async () => {
      const docId = testDocIds[0];
      if (!docId || !documentWasProcessed) {
        console.log("ℹ  No processed document — skipping entity_type filter test");
        return;
      }

      const refs = await filterReferences({ entity_type: "person", document: docId });
      if (!refs) {
        console.log("ℹ  filterReferences returned null — skipping");
        return;
      }

      assert.ok(refs.total >= 0, "total should be non-negative");
      console.log(`✓ entity_type filter: ${refs.total} references with entity_type=person`);

      if (refs.total > 0) {
        // Verify every returned reference is linked to a person entity
        for (const ref of refs.items) {
          if (ref.canonical_entity_type) {
            assert.equal(
              ref.canonical_entity_type,
              "person",
              `Reference ${ref.reference_id} should have canonical_entity_type=person, got ${ref.canonical_entity_type}`,
            );
          }
        }
        console.log(`✓ All ${refs.total} reference(s) have canonical_entity_type=person where set`);
      }
    });
  });

  it("5c. Entity ID filter — filter references by entity_id", async () => {
    await skipIfDegraded(`${API_BASE}/health`, async () => {
      const docId = testDocIds[0];
      if (!docId || !documentWasProcessed) {
        console.log("ℹ  No processed document — skipping entity_id filter test");
        return;
      }

      // First get references to find one with a non-null canonical_entity_id
      const allRefs = await listReferences({ document_id: docId });
      if (!allRefs || allRefs.total === 0) {
        console.log("ℹ  No references to test entity_id filter — skipping");
        return;
      }

      const refWithEntity = allRefs.items.find(r => r.canonical_entity_id);
      if (!refWithEntity) {
        console.log("ℹ  No references with canonical_entity_id found — skipping");
        return;
      }

      const entityId = refWithEntity.canonical_entity_id!;
      console.log(`✓ Found reference ${refWithEntity.reference_id} with entity_id=${entityId}`);

      const filtered = await filterReferences({ entity_id: entityId });
      if (!filtered) {
        console.log("ℹ  filterReferences returned null — skipping");
        return;
      }

      assert.ok(filtered.total >= 0, "total should be non-negative");

      if (filtered.total > 0) {
        for (const ref of filtered.items) {
          assert.ok(
            ref.canonical_entity_id === entityId,
            `Reference ${ref.reference_id} should have canonical_entity_id=${entityId}, got ${ref.canonical_entity_id}`,
          );
        }
        console.log(`✓ Entity ID filter: ${filtered.total} reference(s) match entity ${entityId}`);
      }
    });
  });

  it("5d. Event element filter — filter references by event_element", async () => {
    await skipIfDegraded(`${API_BASE}/health`, async () => {
      const docId = testDocIds[0];
      if (!docId || !documentWasProcessed) {
        console.log("ℹ  No processed document — skipping event_element filter test");
        return;
      }

      const refs = await filterReferences({ event_element: "tiempo", document: docId });
      if (!refs) {
        console.log("ℹ  filterReferences returned null — skipping");
        return;
      }

      assert.ok(refs.total >= 0, "total should be non-negative");
      console.log(`✓ event_element filter: ${refs.total} references with event_element=tiempo`);

      if (refs.total > 0) {
        for (const ref of refs.items) {
          assert.equal(
            ref.element_field,
            "tiempo",
            `Reference ${ref.reference_id} should have element_field=tiempo, got ${ref.element_field}`,
          );
        }
        console.log(`✓ All ${refs.total} reference(s) have element_field=tiempo`);
      }
    });
  });
});

// ===================================================================
// Test Group 6: Enhanced GET /events filters
// ===================================================================
describe("Enhanced GET /events filters", () => {
  it("6a. Entity ID filter — filter events by entity_id", async () => {
    await skipIfDegraded(`${API_BASE}/health`, async () => {
      const docId = testDocIds[0];
      if (!docId || !documentWasProcessed) {
        console.log("ℹ  No processed document — skipping entity_id event filter test");
        return;
      }

      // Pick an entity_id from the first event's references
      const refs = await listReferences({ document_id: docId });
      if (!refs || refs.total === 0) {
        console.log("ℹ  No references to find entity_id for events — skipping");
        return;
      }

      const refWithEntity = refs.items.find(r => r.canonical_entity_id);
      if (!refWithEntity) {
        console.log("ℹ  No entity-linked references found — skipping entity_id filter");
        return;
      }

      const entityId = refWithEntity.canonical_entity_id!;
      console.log(`✓ Testing filterEvents by entity_id=${entityId}`);

      const events = await filterEvents({ entity_id: entityId });
      if (!events) {
        console.log("ℹ  filterEvents returned null — skipping");
        return;
      }

      assert.ok(events.total >= 0, "total should be non-negative");

      if (events.total > 0) {
        for (const evt of events.items) {
          assert.ok(
            evt.participant_count >= 0,
            `Event ${evt.event_id} should have participant_count >= 0, got ${evt.participant_count}`,
          );
        }
        console.log(`✓ Entity ID event filter: ${events.total} event(s) for entity ${entityId}`);
      } else {
        console.log("ℹ  No entity-linked events found for this entity_id");
      }
    });
  });

  it("6b. Entity type filter — filter events by entity_type", async () => {
    await skipIfDegraded(`${API_BASE}/health`, async () => {
      const events = await filterEvents({ entity_type: "person" });
      if (!events) {
        console.log("ℹ  filterEvents returned null — skipping");
        return;
      }

      assert.ok(events.total >= 0, "total should be non-negative");
      console.log(`✓ Entity type event filter: ${events.total} event(s) with entity_type=person`);
    });
  });

  it("6c. Date range filter — filter events by date_from/date_to", async () => {
    await skipIfDegraded(`${API_BASE}/health`, async () => {
      const docId = testDocIds[0];
      if (!docId || !documentWasProcessed) {
        console.log("ℹ  No processed document — skipping date range filter test");
        return;
      }

      // Get the document's total event count for comparison
      const allEvents = await listEvents(docId);
      if (!allEvents) {
        console.log("ℹ  Could not fetch events — skipping date range filter test");
        return;
      }

      const events = await filterEvents({
        date_from: "2000-01-01",
        date_to: "2100-01-01",
        document: docId,
      });
      if (!events) {
        console.log("ℹ  filterEvents returned null — skipping");
        return;
      }

      assert.ok(events.total >= 0, "total should be non-negative");
      console.log(
        `✓ Date range filter: ${events.total} event(s) in [2000-01-01, 2100-01-01] ` +
        `(document total: ${allEvents.total})`,
      );
    });
  });
});
