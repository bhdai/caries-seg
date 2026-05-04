// =============================================================================
// Patients API
// =============================================================================
//
// All functions that touch /api/patients/* live here.  Each function converts
// UI-level models into HTTP requests and returns typed response objects.
//
// Two fetch patterns are intentionally separated:
//   - `searchPatients` — lightweight typeahead used by PatientCombobox.
//     Returns only the items array (no pagination envelope) for simplicity.
//   - `listPatients` — full paginated fetch used by PatientsPage.
//     Returns the complete PatientsPage envelope.

import { apiFetch, buildQueryString } from "@/api/http";
import type { JobSummary } from "@/api/types";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/**
 * Full patient record returned by create, detail, and update endpoints.
 * All optional demographic fields are nullable so the form can represent
 * a partial record without special sentinel values.
 */
export interface PatientResponse {
  id: string;
  full_name: string;
  date_of_birth: string | null; // ISO date "YYYY-MM-DD"
  phone: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

/**
 * Compact patient record used in the list endpoint.  Includes computed
 * aggregates (scan_count, last_visit) so the table can display them without
 * a separate detail fetch per row.
 */
export interface PatientSummary {
  id: string;
  full_name: string;
  phone: string | null;
  date_of_birth: string | null;
  scan_count: number;
  last_visit: string | null; // ISO datetime or null when no linked jobs
}

/**
 * Paginated list of patient summaries.  Mirrors the JobsPage envelope so
 * PatientsPage can use the same pagination controls.
 */
export interface PatientsPage {
  items: PatientSummary[];
  total_items: number;
  page: number;
  page_size: number;
  total_pages: number;
  has_previous_page: boolean;
  has_next_page: boolean;
}

/**
 * Full patient detail including linked scan history.  Returned only by the
 * `/api/patients/:id` endpoint; the list endpoint returns PatientsPage with
 * PatientSummary items instead.
 *
 * `share_links` is intentionally typed as `unknown[]` — Phase 4 will add the
 * ShareLinkResponse type and the ShareLinksTable component.
 */
export interface PatientDetailResponse {
  id: string;
  full_name: string;
  date_of_birth: string | null;
  phone: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
  // Linked scan history — compact summaries sufficient for the scan table.
  jobs: JobSummary[];
  // Active and recently revoked share links across all of this patient's jobs.
  // Includes embedded job context (date, primary filename) so ShareLinksTable
  // can render without an additional fetch per link.
  share_links: import("@/api/shareLinks").PatientShareLinkSummary[];
}

/** Payload for creating a new patient record. */
export interface CreatePatientPayload {
  full_name: string;
  date_of_birth?: string | null;
  phone?: string | null;
  notes?: string | null;
}

/** Payload for partial patient updates.  All fields optional (PATCH semantics). */
export interface UpdatePatientPayload {
  full_name?: string;
  date_of_birth?: string | null;
  phone?: string | null;
  notes?: string | null;
}

/** Filter model for the paginated patient list used by PatientsPage. */
export interface PatientSearchFilters {
  search: string;
  page: number;
  pageSize: number;
}

// ---------------------------------------------------------------------------
// Search — typeahead
// ---------------------------------------------------------------------------

/**
 * Fetch a short list of patient summaries matching the search string.
 *
 * Designed for PatientCombobox typeahead: returns only the `items` array
 * (not the full pagination envelope) to keep call sites simple.
 *
 * @param search - Partial name or phone to match.
 * @param limit  - Maximum results to return.  Defaults to 10.
 */
export async function searchPatients(
  search: string,
  limit = 10,
): Promise<PatientSummary[]> {
  const qs = buildQueryString({ search, page: 1, page_size: limit });
  const res = await apiFetch(`/api/patients${qs}`);
  const data = (await res.json()) as PatientsPage;
  return data.items;
}

// ---------------------------------------------------------------------------
// List — paginated
// ---------------------------------------------------------------------------

/**
 * Fetch one page of patient summaries for the PatientsPage table.
 * All pagination metadata is returned so the page controls can be driven
 * directly from the response without any client-side math.
 */
export async function listPatients(
  filters: PatientSearchFilters,
): Promise<PatientsPage> {
  const params: Record<string, string | number | undefined> = {
    page: filters.page,
    page_size: filters.pageSize,
  };
  if (filters.search) params.search = filters.search;

  const res = await apiFetch(`/api/patients${buildQueryString(params)}`);
  return res.json() as Promise<PatientsPage>;
}

// ---------------------------------------------------------------------------
// Detail
// ---------------------------------------------------------------------------

/**
 * Fetch the full patient record for PatientDetailPage, including linked jobs
 * and share links.
 */
export async function getPatientDetail(
  patientId: string,
): Promise<PatientDetailResponse> {
  const res = await apiFetch(`/api/patients/${patientId}`);
  return res.json() as Promise<PatientDetailResponse>;
}

// ---------------------------------------------------------------------------
// Create
// ---------------------------------------------------------------------------

/**
 * Create a new patient record.  Returns the created patient with its
 * server-assigned ID.  Used by PatientCreateModal.
 */
export async function createPatient(
  payload: CreatePatientPayload,
): Promise<PatientResponse> {
  const res = await apiFetch("/api/patients", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json() as Promise<PatientResponse>;
}

// ---------------------------------------------------------------------------
// Update
// ---------------------------------------------------------------------------

/**
 * Partially update a patient record (PATCH semantics).  Only the fields
 * present in the payload are updated; absent fields are left unchanged.
 */
export async function updatePatient(
  patientId: string,
  payload: UpdatePatientPayload,
): Promise<PatientResponse> {
  const res = await apiFetch(`/api/patients/${patientId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json() as Promise<PatientResponse>;
}

// ---------------------------------------------------------------------------
// Delete
// ---------------------------------------------------------------------------

/**
 * Soft-delete a patient by ID.  Requires admin role (enforced server-side).
 * Returns void on success (HTTP 204 No Content).
 */
export async function deletePatient(patientId: string): Promise<void> {
  await apiFetch(`/api/patients/${patientId}`, { method: "DELETE" });
}
