/**
 * Test helpers for eth-pipeline integration tests.
 *
 * Provides constants and helper functions for making GraphQL queries,
 * REST API calls, and graceful-degradation-aware assertions.
 *
 * @module
 */

import { describe, it, before, after } from "node:test";
import assert from "node:assert/strict";

// ── Configuration ──────────────────────────────────────────────────────

/** Base URL of the eth-pipeline FastAPI server. */
export const API_BASE = process.env.API_URL ?? "http://localhost:8001";

/** URL of the GraphQL proxy endpoint. */
export const GRAPHQL_URL = `${API_BASE}/graphql`;

/** SurrealDB direct HTTP endpoint (used for SQL fallback checks). */
export const SURREAL_HTTP = process.env.SURREAL_HTTP ?? "http://localhost:8000";

/** SurrealDB SQL endpoint. */
export const SURREAL_SQL_URL = `${SURREAL_HTTP}/sql`;

// ── Credentials ────────────────────────────────────────────────────────

export const SURREAL_USER = process.env.SURREAL_USER ?? "root";
export const SURREAL_PASS = process.env.SURREAL_PASS ?? "root";
export const SURREAL_NS = process.env.SURREAL_NS ?? "eth";
export const SURREAL_DB = process.env.SURREAL_DB ?? "pipeline";

// ── Timeouts ───────────────────────────────────────────────────────────

/** Default timeout for HTTP requests (ms). */
export const REQUEST_TIMEOUT = 10_000;

/** Timeout for GraphQL queries that may involve slower operations (ms). */
export const GRAPHQL_TIMEOUT = 15_000;

/** Timeout for waiting on API server startup or document processing (ms). */
export const SERVER_WAIT_TIMEOUT = 30_000;

// ── HTTP helpers ───────────────────────────────────────────────────────

/**
 * Perform an HTTP GET request.
 *
 * @param url - The URL to fetch.
 * @param timeout - Request timeout in milliseconds.
 * @returns A tuple of `[statusCode, bodyOrNull, errorOrNull]`.
 */
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

/**
 * Perform an HTTP POST request.
 *
 * @param url - The URL to post to.
 * @param body - The request body string.
 * @param headers - Optional headers.
 * @param timeout - Request timeout in milliseconds.
 * @returns A tuple of `[statusCode, bodyOrNull, errorOrNull]`.
 */
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

/**
 * Perform an HTTP DELETE request.
 *
 * @param url - The URL to delete.
 * @param timeout - Request timeout in milliseconds.
 * @returns A tuple of `[statusCode, bodyOrNull, errorOrNull]`.
 */
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

// ── GraphQL helpers ─────────────────────────────────────────────────────

/** Shape of a GraphQL response with optional errors. */
export interface GraphQLResponse<T = unknown> {
  data?: T;
  errors?: Array<{ message: string; locations?: unknown[]; path?: string[] }>;
}

/**
 * Execute a GraphQL query via the API proxy.
 *
 * @param query - The GraphQL query string.
 * @param variables - Optional variables object.
 * @param timeout - Request timeout in milliseconds.
 * @returns A tuple of `[statusCode, parsedResponse, errorOrNull]`.
 */
export async function graphqlQuery<T = unknown>(
  query: string,
  variables?: Record<string, unknown>,
  timeout = GRAPHQL_TIMEOUT,
): Promise<[number, GraphQLResponse<T> | null, string | null]> {
  const payload = JSON.stringify({ query, variables });
  const [status, body, error] = await httpPost(GRAPHQL_URL, payload, {}, timeout);

  if (error) return [status, null, error];
  if (body === null) return [status, null, "Empty response body"];

  try {
    const parsed = JSON.parse(body) as GraphQLResponse<T>;
    return [status, parsed, null];
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    return [status, null, `JSON parse error: ${msg} — body: ${body.slice(0, 300)}`];
  }
}

/**
 * Check whether a GraphQL response was successful (no errors and no transport error).
 */
export function graphqlOk<T>(response: [number, GraphQLResponse<T> | null, string | null]): boolean {
  const [, parsed, error] = response;
  if (error) return false;
  if (!parsed) return false;
  if (parsed.errors) return false;
  return true;
}

/**
 * Assert that a GraphQL response is successful.  Provides a clear failure
 * message when the query had errors.
 */
export function assertGraphqlOk<T>(
  response: [number, GraphQLResponse<T> | null, string | null],
  label = "GraphQL query",
): asserts response is [number, GraphQLResponse<T>, null] {
  const [status, parsed, error] = response;
  assert.equal(error, null, `${label} — transport error: ${error}`);
  assert.ok(parsed, `${label} — no response body`);
  if (parsed!.errors) {
    const msgs = parsed!.errors.map((e) => e.message).join("; ");
    assert.fail(`${label} — GraphQL errors: ${msgs}`);
  }
}

// ── Graceful degradation helpers ────────────────────────────────────────

/**
 * Possible service availability states used by graceful-degradation checks.
 */
export type ServiceState = "available" | "degraded" | "unavailable";

/**
 * Check whether a service endpoint is reachable.
 *
 * Returns a state string so tests can adapt assertions based on the
 * current environment (e.g. allow 503 in CI where Docker may not be
 * running).  This mirrors the degraded-mode pattern in the FastAPI
 * lifespan handler.
 *
 * @param url - The health-check URL (e.g. `${API_BASE}/health`).
 * @returns The service state.
 */
export async function checkService(url: string): Promise<ServiceState> {
  const [status, , error] = await httpGet(url, 3000);
  if (error) return "unavailable";
  if (status === 200) return "available";
  return "degraded";
}

/**
 * Run a test function only if the given service is reachable.
 *
 * Usage in a test file:
 * ```ts
 * await skipIfDegraded(`${API_BASE}/health`, async () => {
 *   // your integration test here
 * });
 * ```
 *
 * @param url - The health-check URL.
 * @param fn - The test function to execute if the service is available.
 * @returns The result of `fn`, or `undefined` if skipped.
 */
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

/** Minimal document shape returned by the REST API. */
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
}

/**
 * Create a test document via the REST API.
 *
 * @param text - Document text content.
 * @param filename - Original filename.
 * @param mimeType - Optional MIME type (defaults to text/plain).
 * @returns The created document info, or `null` if the service is unavailable.
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
    console.warn("POST /documents — 503 (degraded mode, SurrealDB unavailable)");
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
 * Retrieve a document status via the REST API.
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

// ── Introspection helpers ───────────────────────────────────────────────

/** Minimal schema type shape from introspection. */
export interface SchemaType {
  name: string;
  kind?: string;
}

/**
 * Fetch GraphQL schema type names via introspection.
 *
 * @returns A set of type names, or `null` if introspection failed.
 */
export async function getSchemaTypeNames(): Promise<Set<string> | null> {
  const query = `
    query IntrospectionTypes {
      __schema {
        types { name }
      }
    }
  `;

  const [, parsed, error] = await graphqlQuery<{
    __schema: { types: Array<{ name: string }> };
  }>(query);

  if (error || !parsed?.data?.__schema?.types) return null;

  return new Set(parsed.data.__schema.types.map((t) => t.name));
}

// ── Assertion helpers ──────────────────────────────────────────────────

/**
 * Assert that a value is non-null and return it (narrowing the type).
 */
export function assertNonNull<T>(
  value: T,
  message = "Expected non-null value",
): asserts value is NonNullable<T> {
  assert.ok(value !== null && value !== undefined, message);
}

