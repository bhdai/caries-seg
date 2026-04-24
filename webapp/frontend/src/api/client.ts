// =============================================================================
// API Client
// =============================================================================
//
// Typed wrappers around fetch for the three backend endpoints used by
// the frontend.  All functions throw ApiError on non-2xx responses.

// ---------------------------------------------------------------------------
// Types
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
}

export interface JobResponse {
  id: string;
  status: "pending" | "processing" | "completed" | "failed";
  pipeline_type: "single_stage" | "two_stage";
  model_arch: "unet" | "double_unet";
  error_message: string | null;
  created_at: string;
  image_results: ImageResultResponse[];
}

// ---------------------------------------------------------------------------
// Error type
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

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function checkResponse(res: Response): Promise<Response> {
  if (!res.ok) {
    let message = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") {
        message = body.detail;
      } else if (body.detail) {
        message = JSON.stringify(body.detail);
      }
    } catch {
      // Ignore JSON parse failures; use the default status message.
    }
    throw new ApiError(res.status, message);
  }
  return res;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Submit an inference job.
 *
 * Builds a multipart/form-data request containing all uploaded files plus
 * the selected pipeline and model architecture, then returns the created
 * job record.
 */
export async function createJob(
  files: File[],
  pipelineType: "single_stage" | "two_stage",
  modelArch: "unet" | "double_unet",
): Promise<JobResponse> {
  const form = new FormData();
  for (const file of files) {
    form.append("files", file);
  }
  form.append("pipeline_type", pipelineType);
  form.append("model_arch", modelArch);

  const res = await fetch("/api/jobs", { method: "POST", body: form });
  await checkResponse(res);
  return res.json() as Promise<JobResponse>;
}

/**
 * Fetch the current state of a job including all image results.
 */
export async function getJob(jobId: string): Promise<JobResponse> {
  const res = await fetch(`/api/jobs/${jobId}`);
  await checkResponse(res);
  return res.json() as Promise<JobResponse>;
}

/**
 * Return the backend URL for a processed image file.
 *
 * No network request is made; the string is suitable for use as an
 * HTMLImageElement `src` attribute.
 */
export function fileUrl(
  imageResultId: string,
  kind: "original" | "mask",
): string {
  return `/api/files/${imageResultId}/${kind}`;
}
