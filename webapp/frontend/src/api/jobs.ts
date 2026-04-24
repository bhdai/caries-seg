// =============================================================================
// Jobs API
// =============================================================================
//
// All functions that touch /api/jobs/* live here.  Each function converts
// UI-level models into HTTP requests and returns typed response objects.

import { apiFetch, buildQueryString } from "@/api/http";
import type { JobDetail, JobFilters, JobsPage } from "@/api/types";

// ---------------------------------------------------------------------------
// Create
// ---------------------------------------------------------------------------

/**
 * Submit a new inference job with the uploaded files and selected pipeline /
 * model configuration.
 */
export async function createJob(
  files: File[],
  pipelineType: "single_stage" | "two_stage",
  modelArch: "unet" | "double_unet",
): Promise<JobDetail> {
  const form = new FormData();
  for (const file of files) {
    form.append("files", file);
  }
  form.append("pipeline_type", pipelineType);
  form.append("model_arch", modelArch);

  const res = await apiFetch("/api/jobs", { method: "POST", body: form });
  return res.json() as Promise<JobDetail>;
}

// ---------------------------------------------------------------------------
// Get detail
// ---------------------------------------------------------------------------

/**
 * Fetch the current state of a single job, including all image results.
 */
export async function getJobDetail(jobId: string): Promise<JobDetail> {
  const res = await apiFetch(`/api/jobs/${jobId}`);
  return res.json() as Promise<JobDetail>;
}

// ---------------------------------------------------------------------------
// List
// ---------------------------------------------------------------------------

/**
 * Fetch one page of compact job summaries from the backend list endpoint.
 * Convert UI filter state into query parameters and normalize API errors
 * into the shared client error type.
 */
export async function listJobs(filters: JobFilters): Promise<JobsPage> {
  // Map camelCase UI filter fields to the snake_case API contract.
  const params: Record<string, string | number | undefined> = {
    page: filters.page,
    page_size: filters.pageSize,
    sort: filters.sort,
  };

  // Omit "all" sentinel values so the backend applies no filter for those
  // dimensions, keeping the API surface clean.
  if (filters.status !== "all") params.status = filters.status;
  if (filters.pipelineType !== "all") params.pipeline_type = filters.pipelineType;
  if (filters.modelArch !== "all") params.model_arch = filters.modelArch;
  if (filters.search) params.search = filters.search;

  const res = await apiFetch(`/api/jobs${buildQueryString(params)}`);
  return res.json() as Promise<JobsPage>;
}

// ---------------------------------------------------------------------------
// Rerun
// ---------------------------------------------------------------------------

/**
 * Request a server-side rerun for an existing job.  Returns the newly created
 * job detail so the UI can navigate immediately to the new result route.
 */
export async function rerunJob(jobId: string): Promise<JobDetail> {
  const res = await apiFetch(`/api/jobs/${jobId}/rerun`, { method: "POST" });
  return res.json() as Promise<JobDetail>;
}

// ---------------------------------------------------------------------------
// Delete
// ---------------------------------------------------------------------------

/**
 * Permanently delete a job and its associated on-disk files.
 * Returns void on success (HTTP 204 No Content).
 */
export async function deleteJob(jobId: string): Promise<void> {
  await apiFetch(`/api/jobs/${jobId}`, { method: "DELETE" });
}
