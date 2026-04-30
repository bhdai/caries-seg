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
 * `credentials: "include"` is merged into every request so the browser
 * sends the httponly auth cookie to the backend automatically — callers do
 * not need to manage tokens themselves.
 *
 * On a 401 response the wrapper dispatches a window-level
 * `"auth:unauthorized"` event before throwing. AuthContext listens for this
 * event to clear the user state and trigger a redirect to /login. This
 * approach keeps the HTTP layer decoupled from React context (no circular
 * imports).
 *
 * Tries to extract a human-readable detail message from a JSON body shaped
 * like FastAPI's standard error envelope `{ "detail": "..." }`.
 */
export async function apiFetch(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<Response> {
  // Merge caller-supplied init with the baseline credentials policy so every
  // request carries the auth cookie without requiring callers to remember it.
  const mergedInit: RequestInit = { credentials: "include", ...init };

  const res = await fetch(input, mergedInit);
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

    // Notify AuthContext that the session has expired or was never established.
    // Using a custom DOM event decouples this module from React's context API.
    if (res.status === 401) {
      window.dispatchEvent(new Event("auth:unauthorized"));
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
