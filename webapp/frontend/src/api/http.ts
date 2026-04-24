// =============================================================================
// HTTP Layer
// =============================================================================
//
// Shared fetch wrapper and query-string helpers used by all API modules.
// ApiError is defined in types.ts and re-exported here so call sites can
// import everything they need from a single module.

import { ApiError } from "@/api/types";

export { ApiError };

// ---------------------------------------------------------------------------
// Core fetch wrapper
// ---------------------------------------------------------------------------

/**
 * Perform a fetch and throw ApiError on non-2xx responses.
 *
 * Tries to extract a human-readable detail message from a JSON body shaped
 * like FastAPI's standard error envelope `{ "detail": "..." }`.
 */
export async function apiFetch(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<Response> {
  const res = await fetch(input, init);
  if (!res.ok) {
    let message = `HTTP ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") {
        message = body.detail;
      } else if (body.detail !== undefined) {
        message = JSON.stringify(body.detail);
      }
    } catch {
      // JSON parse failed; fall back to the generic status message.
    }
    throw new ApiError(res.status, message);
  }
  return res;
}

// ---------------------------------------------------------------------------
// Query-string helpers
// ---------------------------------------------------------------------------

/**
 * Build a URLSearchParams string from a plain object, omitting keys whose
 * value is undefined, null, or the empty string.
 *
 * Callers pass API-level parameter names directly, so no camelCase
 * conversion happens here.
 */
export function buildQueryString(
  params: Record<string, string | number | boolean | undefined | null>,
): string {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    qs.set(key, String(value));
  }
  const str = qs.toString();
  return str ? `?${str}` : "";
}
