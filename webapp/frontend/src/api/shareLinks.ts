// =============================================================================
// Share Links API
// =============================================================================
//
// Typed wrappers for all share-link endpoints.  Two fetch patterns are used:
//
//   - Authenticated endpoints (create, get-by-job, revoke) use `apiFetch` so
//     the httponly auth cookie is sent automatically.
//
//   - The public endpoint (`getSharedResult`) uses plain `fetch` without
//     credentials so it works for unauthenticated patients following a link.
//     This function must remain decoupled from the auth layer — it is called
//     by SharedResultPage which intentionally has no auth context.

import { apiFetch } from "@/api/http";
import { ApiError } from "@/api/types";
import type { BBoxResponse } from "@/api/types";

// ---------------------------------------------------------------------------
// Types — authenticated side (doctor's UI)
// ---------------------------------------------------------------------------

/**
 * A share link record returned by the create and get-by-job endpoints.
 * `is_active` is true when the link has not been revoked and (if `expires_at`
 * is set) has not yet passed its expiry timestamp.
 */
export interface ShareLinkResponse {
  id: string;
  job_id: string;
  token: string;
  /** ISO 8601 datetime, or null when the link was created with no expiry. */
  expires_at: string | null;
  created_at: string;
  is_active: boolean;
}

/**
 * Extended share link record included in the patient detail response.
 * Carries job context (scan date and primary filename) so ShareLinksTable
 * can display per-row job information without an extra fetch per link.
 */
export interface PatientShareLinkSummary {
  id: string;
  job_id: string;
  token: string;
  expires_at: string | null;
  created_at: string;
  is_active: boolean;
  /** `created_at` of the linked job (ISO 8601 datetime). */
  job_date: string;
  /** `primary_filename` of the linked job. */
  job_primary_filename: string;
}

/** Payload for creating a new share link. */
export interface CreateShareLinkPayload {
  job_id: string;
  /**
   * Number of days until the link expires.
   * Pass null to create a link that never expires.
   */
  expires_in_days: number | null;
}

// ---------------------------------------------------------------------------
// Types — public side (patient's device, no auth)
// ---------------------------------------------------------------------------

/**
 * One image result as returned by the public shared endpoint.
 * Structurally similar to ImageResultResponse but exposed via an
 * unauthenticated route — callers must not assume the auth cookie is present.
 */
export interface SharedImageResult {
  id: string;
  original_filename: string;
  original_size: { width: number; height: number };
  bounding_boxes: BBoxResponse[] | null;
  is_ready: boolean;
}

/**
 * Full payload returned by GET /api/shared/:token.
 * Consumed by SharedResultPage — no auth cookie required.
 */
export interface SharedResultResponse {
  patient_name: string | null;
  /** ISO 8601 datetime derived from the linked job's `created_at`. */
  scan_date: string;
  pipeline_type: "single_stage" | "two_stage";
  expires_at: string | null;
  image_results: SharedImageResult[];
}

// ---------------------------------------------------------------------------
// Authenticated API functions (doctor's UI)
// ---------------------------------------------------------------------------

/**
 * Create a new share link for the given job.
 *
 * @param payload - Job ID and optional expiry in days (null = no expiry).
 * @returns The newly created share link record.
 */
export async function createShareLink(
  payload: CreateShareLinkPayload,
): Promise<ShareLinkResponse> {
  const res = await apiFetch("/api/share-links", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json() as Promise<ShareLinkResponse>;
}

/**
 * Fetch the active share link for a job, if one exists.
 *
 * Returns null when no active link exists (server returns 404).
 * Re-throws ApiError for other non-2xx responses.
 *
 * @param jobId - The job UUID to look up.
 */
export async function getShareLinkForJob(
  jobId: string,
): Promise<ShareLinkResponse | null> {
  try {
    const res = await apiFetch(`/api/share-links/by-job/${jobId}`);
    return res.json() as Promise<ShareLinkResponse>;
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) {
      return null;
    }
    throw err;
  }
}

/**
 * Revoke a share link by its ID.
 * After revocation the link token can no longer be used to view results.
 *
 * @param linkId - The share link UUID to revoke.
 */
export async function revokeShareLink(linkId: string): Promise<void> {
  await apiFetch(`/api/share-links/${linkId}`, { method: "DELETE" });
}

// ---------------------------------------------------------------------------
// Public API function (patient's device — no auth cookie)
// ---------------------------------------------------------------------------

/**
 * Fetch the shared result data for a public share token.
 *
 * Uses plain `fetch` without credentials so the browser does not include
 * the auth cookie.  This function is intentionally isolated from `apiFetch`
 * to keep SharedResultPage free of any authentication assumptions.
 *
 * @param token - The URL-safe share token from the `/shared/:token` route.
 * @throws ApiError with status 404 when the token is not recognised.
 * @throws ApiError with status 410 when the link has expired or been revoked.
 */
export async function getSharedResult(
  token: string,
): Promise<SharedResultResponse> {
  const res = await fetch(`/api/shared/${token}`);

  if (!res.ok) {
    let message = `HTTP ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") {
        message = body.detail;
      }
    } catch {
      // JSON parse failed; fall back to the generic status message.
    }
    throw new ApiError(res.status, message);
  }

  return res.json() as Promise<SharedResultResponse>;
}
