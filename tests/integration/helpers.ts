/**
 * Test helpers for eth-pipeline integration tests.
 *
 * Provides constants and helper functions for making REST API calls
 * and graceful-degradation-aware assertions.
 *
 * @module
 */

import { describe, it, before, after } from "node:test";
import assert from "node:assert/strict";

// ── Configuration ──────────────────────────────────────────────────────

/** Base URL of the eth-pipeline FastAPI server. */
export const API_BASE = process.env.API_URL ?? "http://localhost:8001";

// ── Timeouts ───────────────────────────────────────────────────────────

/** Default timeout for HTTP requests (ms). */
export const REQUEST_TIMEOUT = 10_000;

/** Timeout for waiting on API server startup or document processing (ms). */
export const SERVER_WAIT_TIMEOUT = 60_000;

/** Timeout for polling document status during processing (ms). */
export const POLL_INTERVAL = 5_000;

/** Max document processing wait time (ms). */
export const MAX_PROCESS_WAIT = 120_000;

// ── HTTP helpers ───────────────────────────────────────────────────────

export async function httpGet(
  url: string,
  timeout = REQUEST_TIMEOUT,
): Promise<[number, string | null, string | null]> {
  try {
    const resp = await fetch(url, {
      method: "GET",
      signal: AbortSignal.timeout(timeout),
    });
    const body = await resp.text();
    return [resp.status, body, null];
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    return [-1, null, msg];
  }
}

export async function httpPost(
  url: string,
  body: string,
  headers: Record<string, string> = {},
  timeout = REQUEST_TIMEOUT,
): Promise<[number, string | null, string | null]> {
  try {
    const resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...headers },
      body,
      signal: AbortSignal.timeout(timeout),
    });
    const text = await resp.text();
    return [resp.status, text, null];
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    return [-1, null, msg];
  }
}

export async function httpDelete(
  url: string,
  timeout = REQUEST_TIMEOUT,
): Promise<[number, string | null, string | null]> {
  try {
    const resp = await fetch(url, {
      method: "DELETE",
      signal: AbortSignal.timeout(timeout),
    });
    const body = await resp.text();
    return [resp.status, body, null];
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    return [-1, null, msg];
  }
}

// ── Graceful degradation helpers ────────────────────────────────────────

export type ServiceState = "available" | "degraded" | "unavailable";

export async function checkService(url: string): Promise<ServiceState> {
  const [status, , error] = await httpGet(url, 3000);
  if (error) return "unavailable";
  if (status === 200) return "available";
  return "degraded";
}

export async function skipIfDegraded<T>(
  url: string,
  fn: () => Promise<T>,
): Promise<T | undefined> {
  const state = await checkService(url);
  if (state === "unavailable") {
    console.warn(`⚠️  Service at ${url} unreachable — skipping test`);
    return undefined;
  }
  if (state === "degraded") {
    console.warn(`⚠️  Service at ${url} degraded — running test anyway`);
  }
  return fn();
}

// ── API helpers ─────────────────────────────────────────────────────────

export interface DocumentCreated {
  document_id: string;
  status: string;
}

export interface DocumentStatus {
  document_id: string;
  status: string;
  filename: string;
  error_message: string | null;
  created_at: string | null;
  blob_format: string | null;
  blob_path: string | null;
  reference_count?: number;
  entity_count?: number;
  chunk_count?: number;
  text_word_count?: number;
}

export interface EventListItem {
  event_id: string;
  que_paso: string;
  espacio: string | null;
  tiempo: string | null;
  humanos: string | null;
  objetos: string | null;
  document_id: string;
  reference_count: number;
  participant_count: number;
}

export interface EventListResponse {
  items: EventListItem[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

export interface ReferenceListItem {
  reference_id: string;
  reference_type: string;
  verbatim_text: string;
  event_id: string;
  canonical_entity: string | null;
  event_que_paso: string;
  document_filename: string;
  document_id: string;
}

export interface ReferenceListResponse {
  items: ReferenceListItem[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

export interface EntityListItem {
  entity_id: string;
  entity_type: string;
  name: string;
  reference_count: number;
  created_at: string | null;
}

export interface EntityListResponse {
  items: EntityListItem[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

export interface DocumentListItem {
  document_id: string;
  status: string;
  filename: string;
  created_at: string;
  error_message: string | null;
  chunk_count: number;
  reference_count: number;
  entity_count: number;
  text_word_count: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  duration_ms: number;
  total_cost: number;
}

export interface DocumentListResponse {
  items: DocumentListItem[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

export interface ProcessingLogListItem {
  id: string;
  step_name: string;
  severity: string;
  message: string;
  details: string | null;
  created_at: string;
}

export interface ProcessingLogListResponse {
  items: ProcessingLogListItem[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

export interface ClearEventsResponse {
  document_id: string;
  status: string;
  events_cleared: boolean;
}

export interface MergeResponse {
  source_id: string;
  target_id: string;
  references_updated: number;
  events_updated: number;
}

export interface SplitResponse {
  source_id: string;
  partitions: number;
  references_moved: number;
}

/**
 * Create a test document via REST API.
 */
export async function createDocument(
  text: string,
  filename: string,
  mimeType?: string,
): Promise<DocumentCreated | null> {
  const payload = JSON.stringify({
    text,
    filename,
    mime_type: mimeType ?? "text/plain",
  });

  const [status, body, error] = await httpPost(
    `${API_BASE}/documents`,
    payload,
    {},
    10_000,
  );

  if (error) {
    console.warn(`POST /documents — transport error: ${error}`);
    return null;
  }

  if (status === 503) {
    console.warn("POST /documents — 503 (degraded mode, DB unavailable)");
    return null;
  }

  if (status !== 201) {
    console.warn(`POST /documents — unexpected HTTP ${status}: ${body}`);
    return null;
  }

  try {
    return JSON.parse(body!) as DocumentCreated;
  } catch {
    console.warn(`POST /documents — failed to parse response: ${body}`);
    return null;
  }
}

/**
 * Retrieve a document status via REST API.
 */
export async function getDocument(id: string): Promise<DocumentStatus | null> {
  const [status, body, error] = await httpGet(`${API_BASE}/documents/${id}`);
  if (error) {
    console.warn(`GET /documents/${id} — transport error: ${error}`);
    return null;
  }
  if (status !== 200) return null;
  try {
    return JSON.parse(body!) as DocumentStatus;
  } catch {
    return null;
  }
}

/**
 * Upload a binary file via POST /documents/upload.
 */
export async function uploadDocument(
  filePath: string,
  filename: string,
): Promise<DocumentCreated | null> {
  const url = `${API_BASE}/documents/upload`;
  try {
    const fs = await import("fs/promises");
    const content = await fs.readFile(filePath);
    const form = new FormData();
    const blob = new Blob([content], { type: "application/pdf" });
    form.append("file", blob, filename);

    const resp = await fetch(url, {
      method: "POST",
      body: form,
      signal: AbortSignal.timeout(REQUEST_TIMEOUT),
    });

    const body = await resp.text();
    if (resp.status === 503) {
      console.warn("POST /documents/upload -- 503 (degraded mode)");
      return null;
    }
    if (resp.status !== 201) {
      console.warn(`POST /documents/upload -- HTTP ${resp.status}: ${body}`);
      return null;
    }
    return JSON.parse(body) as DocumentCreated;
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    console.warn(`POST /documents/upload -- error: ${msg}`);
    return null;
  }
}

/**
 * Wait for a document to reach a non-terminal status or timeout.
 * Returns the final document status.
 */
export async function waitForProcessing(
  docId: string,
  maxWait = MAX_PROCESS_WAIT,
): Promise<DocumentStatus | null> {
  const deadline = Date.now() + maxWait;
  while (Date.now() < deadline) {
    const doc = await getDocument(docId);
    if (!doc) return null;
    if (doc.status === "processed" || doc.status === "failed") return doc;
    await new Promise((r) => setTimeout(r, POLL_INTERVAL));
  }
  return await getDocument(docId);
}

/**
 * List documents via REST API.
 */
export async function listDocuments(
  page = 1,
  perPage = 20,
): Promise<DocumentListResponse | null> {
  const [status, body, error] = await httpGet(
    `${API_BASE}/documents?page=${page}&per_page=${perPage}`,
  );
  if (error || status !== 200) return null;
  return JSON.parse(body!) as DocumentListResponse;
}

/**
 * List events for a document via REST API (GET /events?document=X).
 */
export async function listEvents(
  documentId?: string,
): Promise<EventListResponse | null> {
  const params = new URLSearchParams({ per_page: "100" });
  if (documentId) params.set("document", documentId);
  const [status, body, error] = await httpGet(
    `${API_BASE}/events?${params.toString()}`,
  );
  if (error || status !== 200) return null;
  return JSON.parse(body!) as EventListResponse;
}

/**
 * List references via REST API.
 */
export async function listReferences(
  params?: Record<string, string>,
): Promise<ReferenceListResponse | null> {
  const query = params
    ? "?" + new URLSearchParams(params).toString()
    : "?per_page=100";
  const [status, body, error] = await httpGet(`${API_BASE}/references${query}`);
  if (error || status !== 200) return null;
  return JSON.parse(body!) as ReferenceListResponse;
}

/**
 * List entities via REST API.
 */
export async function listEntities(
  params?: Record<string, string>,
): Promise<EntityListResponse | null> {
  const query = params
    ? "?" + new URLSearchParams(params).toString()
    : "?per_page=100";
  const [status, body, error] = await httpGet(`${API_BASE}/entities${query}`);
  if (error || status !== 200) return null;
  return JSON.parse(body!) as EntityListResponse;
}

/**
 * Get processing logs for a document via REST API.
 */
export async function getProcessingLogs(
  documentId: string,
): Promise<ProcessingLogListResponse | null> {
  const [status, body, error] = await httpGet(
    `${API_BASE}/documents/${documentId}/logs`,
  );
  if (error || status !== 200) return null;
  return JSON.parse(body!) as ProcessingLogListResponse;
}

/**
 * Clear events for a document via REST API.
 */
export async function clearEvents(
  documentId: string,
): Promise<ClearEventsResponse | null> {
  const [status, body, error] = await httpDelete(
    `${API_BASE}/documents/${documentId}/events`,
  );
  if (error || status !== 200) return null;
  return JSON.parse(body!) as ClearEventsResponse;
}

/**
 * Merge two entities via REST API.
 */
export async function mergeEntities(
  sourceId: string,
  targetId: string,
): Promise<MergeResponse | null> {
  const [status, body, error] = await httpPost(
    `${API_BASE}/entities/merge`,
    JSON.stringify({ source_id: sourceId, target_id: targetId }),
  );
  if (error || status !== 200) return null;
  return JSON.parse(body!) as MergeResponse;
}

// ── Assertion helpers ──────────────────────────────────────────────────

export function assertNonNull<T>(
  value: T,
  message = "Expected non-null value",
): asserts value is NonNullable<T> {
  assert.ok(value !== null && value !== undefined, message);
}
