// =============================================================================
// Shared API Types
// =============================================================================
//
// All frontend types for the backend contract live here so every consumer
// (API functions, hooks, components) imports from one authoritative source.
// Summary DTOs are intentionally separate from the full detail DTO so list
// routes can stay compact and cacheable.

// ---------------------------------------------------------------------------
// Shared literals
// ---------------------------------------------------------------------------

export type JobStatus = "pending" | "processing" | "completed" | "failed";
export type PipelineType = "single_stage" | "two_stage";
// AttentionUNet is intentionally excluded from the webapp per the product plan.
export type ModelArch = "unet" | "double_unet";

// ---------------------------------------------------------------------------
// Job detail — returned by create, get-detail, and rerun
// ---------------------------------------------------------------------------

export interface BBoxResponse {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  confidence: number;
}

export interface ImageResultResponse {
  id: string;
  original_filename: string;
  original_size: { width: number; height: number };
  inference_time_ms: number | null;
  bounding_boxes: BBoxResponse[] | null;
  /**
   * True when the final mask artifact exists and this image can be rendered
   * as a completed result card.  Derived server-side from `mask_path != null`.
   */
  is_ready: boolean;
}

/**
 * Full job payload returned by the create, detail, and rerun endpoints.
 * Includes the complete image_results array.
 */
export interface JobDetail {
  id: string;
  status: JobStatus;
  pipeline_type: PipelineType;
  model_arch: ModelArch;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  image_results: ImageResultResponse[];
}

// ---------------------------------------------------------------------------
// Job summary — returned by the list endpoint only
// ---------------------------------------------------------------------------

/**
 * Compact job payload used by Dashboard and History list surfaces.
 * Excludes full image_results to keep list payloads small and cacheable.
 */
export interface JobSummary {
  id: string;
  status: JobStatus;
  pipeline_type: PipelineType;
  model_arch: ModelArch;
  created_at: string;
  last_activity_at: string;
  image_count: number;
  primary_filename: string;
  filename_preview: string[];
  error_message: string | null;
}

// ---------------------------------------------------------------------------
// Pagination envelope
// ---------------------------------------------------------------------------

/**
 * One server-side page of job summaries together with the metadata needed
 * by a URL-synchronized list UI.
 */
export interface JobsPage {
  items: JobSummary[];
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
  has_previous_page: boolean;
  has_next_page: boolean;
}

// ---------------------------------------------------------------------------
// Filter model
// ---------------------------------------------------------------------------

/**
 * Represent URL-backed filter state for the History and Dashboard surfaces.
 * The model is intentionally serializable and mirrors backend query semantics
 * to avoid hidden translation rules between UI state and API params.
 */
export interface JobFilters {
  page: number;
  pageSize: number;
  status: "all" | JobStatus;
  pipelineType: "all" | PipelineType;
  modelArch: "all" | ModelArch;
  search: string;
  sort: "newest" | "oldest" | "last_activity_desc";
}

// ---------------------------------------------------------------------------
// API error
// ---------------------------------------------------------------------------

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}
