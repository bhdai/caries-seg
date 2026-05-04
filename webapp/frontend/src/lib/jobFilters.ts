// =============================================================================
// Job filter helpers
// =============================================================================
//
// Normalisation of query-string state, default values, and UI-to-API mapping
// for the History and Dashboard filter model.  Centralising this logic
// prevents inconsistencies between the URL state the browser stores and the
// params the API actually receives.

import type { JobFilters } from "@/api/types";

// ---------------------------------------------------------------------------
// Defaults
// ---------------------------------------------------------------------------

/**
 * Canonical default filter state.  Applied whenever a filter key is absent
 * from the URL or holds an invalid value.
 */
export const DEFAULT_JOB_FILTERS: Readonly<JobFilters> = {
  page: 1,
  pageSize: 20,
  status: "all",
  pipelineType: "all",
  modelArch: "all",
  search: "",
  sort: "last_activity_desc",
  patientId: null,
};

// ---------------------------------------------------------------------------
// URL → filters
// ---------------------------------------------------------------------------

const VALID_STATUSES = new Set(["all", "pending", "processing", "completed", "failed"]);
const VALID_PIPELINES = new Set(["all", "single_stage", "two_stage"]);
const VALID_MODEL_ARCHS = new Set(["all", "unet", "double_unet"]);
const VALID_SORTS = new Set(["newest", "oldest", "last_activity_desc"]);

/**
 * Parse a URLSearchParams instance into a validated JobFilters object.
 *
 * Each parameter is validated against its allowed value set or numeric
 * range.  Invalid or missing values fall back to the canonical defaults so
 * the page is always in a known state regardless of the URL contents.
 */
export function parseFiltersFromParams(params: URLSearchParams): JobFilters {
  const rawPage = parseInt(params.get("page") ?? "", 10);
  const page =
    Number.isFinite(rawPage) && rawPage >= 1 ? rawPage : DEFAULT_JOB_FILTERS.page;

  const rawPageSize = parseInt(params.get("page_size") ?? "", 10);
  const pageSize =
    Number.isFinite(rawPageSize) && rawPageSize >= 1 && rawPageSize <= 100
      ? rawPageSize
      : DEFAULT_JOB_FILTERS.pageSize;

  const rawStatus = params.get("status") ?? "";
  const status = VALID_STATUSES.has(rawStatus)
    ? (rawStatus as JobFilters["status"])
    : DEFAULT_JOB_FILTERS.status;

  const rawPipeline = params.get("pipeline_type") ?? "";
  const pipelineType = VALID_PIPELINES.has(rawPipeline)
    ? (rawPipeline as JobFilters["pipelineType"])
    : DEFAULT_JOB_FILTERS.pipelineType;

  const rawArch = params.get("model_arch") ?? "";
  const modelArch = VALID_MODEL_ARCHS.has(rawArch)
    ? (rawArch as JobFilters["modelArch"])
    : DEFAULT_JOB_FILTERS.modelArch;

  const search = params.get("search") ?? DEFAULT_JOB_FILTERS.search;

  const rawSort = params.get("sort") ?? "";
  const sort = VALID_SORTS.has(rawSort)
    ? (rawSort as JobFilters["sort"])
    : DEFAULT_JOB_FILTERS.sort;

  const patientId = params.get("patient_id") ?? DEFAULT_JOB_FILTERS.patientId;

  return { page, pageSize, status, pipelineType, modelArch, search, sort, patientId };
}

// ---------------------------------------------------------------------------
// Filters → URL
// ---------------------------------------------------------------------------

/**
 * Serialise a JobFilters object back to a URLSearchParams instance.
 *
 * Defaults are omitted from the output to keep URLs short and human-readable.
 * This also means that a URL with no query string is equivalent to the
 * default filter state, which avoids unnecessary redirects on first load.
 */
export function filtersToParams(filters: JobFilters): URLSearchParams {
  const params = new URLSearchParams();
  const d = DEFAULT_JOB_FILTERS;

  if (filters.page !== d.page) params.set("page", String(filters.page));
  if (filters.pageSize !== d.pageSize) params.set("page_size", String(filters.pageSize));
  if (filters.status !== d.status) params.set("status", filters.status);
  if (filters.pipelineType !== d.pipelineType) params.set("pipeline_type", filters.pipelineType);
  if (filters.modelArch !== d.modelArch) params.set("model_arch", filters.modelArch);
  if (filters.search !== d.search) params.set("search", filters.search);
  if (filters.sort !== d.sort) params.set("sort", filters.sort);
  if (filters.patientId !== d.patientId && filters.patientId !== null)
    params.set("patient_id", filters.patientId);

  return params;
}
