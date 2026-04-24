// =============================================================================
// RecentJobsList
// =============================================================================
//
// Compact recent-jobs presentation for the Dashboard home page.  Handles
// loading, empty, error, and populated states so DashboardPage only needs to
// pass through query result flags and the job data.
//
// Each row shows: status, primary filename, pipeline/model summary, image
// count, relative last-activity time, and two quick-action buttons — "Open"
// (navigate to result) and "Rerun" (server-side clone via the mutation hook).
//
// The rerun mutation is owned here so navigation-on-success and error toasts
// are co-located with the trigger, keeping DashboardPage free of mutation
// wiring.

import { JobStatusChip } from "@/components/jobs/JobStatusChip";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useRerunJobMutation } from "@/hooks/useRerunJobMutation";
import { formatRelativeTime } from "@/lib/time";
import { cn } from "@/lib/utils";
import type { JobSummary } from "@/api/types";
import { ExternalLink, RotateCcw, UploadCloud } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface RecentJobsListProps {
  /** Compact job records returned by the list endpoint. */
  jobs: JobSummary[] | undefined;
  /** True while the initial fetch (or a hard reload) is in flight. */
  isLoading: boolean;
  /** True when the last fetch attempt resulted in an error. */
  isError: boolean;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * Render a compact list of recent inference jobs for the Dashboard home page.
 *
 * States handled:
 *  - Loading  → skeleton placeholder rows.
 *  - Error    → inline recoverable message; does not flash away existing data.
 *  - Empty    → first-use prompt directing the user to Upload.
 *  - Populated → one compact row per job with open-result and rerun actions.
 */
export function RecentJobsList({ jobs, isLoading, isError }: RecentJobsListProps) {
  const navigate = useNavigate();

  // A single mutation instance covers all rows.  `variables` tells us which
  // job id triggered the currently-pending rerun so we can highlight only
  // that row's button.
  const {
    mutate: rerun,
    isPending: isRerunPending,
    variables: rerunJobId,
  } = useRerunJobMutation();

  // ------------------------------------------------------------------
  // Loading state — show skeleton rows while the first fetch is live.
  // ------------------------------------------------------------------
  if (isLoading) {
    return (
      <div className="divide-y">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="flex items-center gap-4 py-4">
            <Skeleton className="h-5 w-20 shrink-0" />
            <div className="flex-1 space-y-1.5 min-w-0">
              <Skeleton className="h-4 w-48" />
              <Skeleton className="h-3.5 w-32" />
            </div>
            <Skeleton className="h-3.5 w-20 shrink-0" />
            <Skeleton className="h-8 w-16 shrink-0" />
            <Skeleton className="h-8 w-16 shrink-0" />
          </div>
        ))}
      </div>
    );
  }

  // ------------------------------------------------------------------
  // Error state — show a recoverable inline message without clearing any
  // previously visible data (though in this branch data is undefined).
  // ------------------------------------------------------------------
  if (isError) {
    return (
      <div className="py-6 text-center text-sm text-muted-foreground">
        Could not load recent jobs.{" "}
        <button
          className="underline underline-offset-4 hover:text-foreground"
          onClick={() => window.location.reload()}
        >
          Refresh the page
        </button>{" "}
        to try again.
      </div>
    );
  }

  // ------------------------------------------------------------------
  // Empty state — guide the user toward their first upload.
  // ------------------------------------------------------------------
  if (!jobs || jobs.length === 0) {
    return (
      <div className="py-8 flex flex-col items-center gap-3">
        <p className="text-sm text-muted-foreground">No inference jobs yet.</p>
        <Button asChild variant="outline" size="sm">
          <Link to="/upload">
            <UploadCloud className="h-4 w-4 mr-1.5" />
            Upload your first X-ray
          </Link>
        </Button>
      </div>
    );
  }

  // ------------------------------------------------------------------
  // Populated state — one compact row per job.
  // ------------------------------------------------------------------
  return (
    <div className="divide-y">
      {jobs.map((job) => {
        const isThisRerunning = isRerunPending && rerunJobId === job.id;

        return (
          <div
            key={job.id}
            className="flex items-center gap-4 py-4 min-w-0"
          >
            {/* Status badge */}
            <JobStatusChip status={job.status} className="shrink-0" />

            {/* Primary filename + pipeline · model · image count summary */}
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium truncate leading-snug">
                {job.primary_filename}
              </p>
              <p className="text-xs text-muted-foreground mt-0.5">
                {formatPipelineLabel(job.pipeline_type)}
                {" · "}
                {formatModelLabel(job.model_arch)}
                {" · "}
                {job.image_count === 1 ? "1 image" : `${job.image_count} images`}
              </p>
            </div>

            {/* Relative last-activity timestamp */}
            <span className="text-xs text-muted-foreground whitespace-nowrap shrink-0">
              {formatRelativeTime(job.last_activity_at)}
            </span>

            {/* Quick actions */}
            <div className="flex items-center gap-1.5 shrink-0">
              {/* Open result */}
              <Button
                variant="ghost"
                size="sm"
                onClick={() => navigate(`/result/${job.id}`)}
                aria-label={`Open result for job ${job.id}`}
              >
                <ExternalLink className="h-4 w-4 mr-1" />
                Open
              </Button>

              {/* Quick rerun */}
              <Button
                variant="outline"
                size="sm"
                disabled={isRerunPending}
                onClick={() => rerun(job.id)}
                aria-label={`Rerun job ${job.id}`}
              >
                <RotateCcw
                  className={cn(
                    "h-4 w-4 mr-1",
                    isThisRerunning && "animate-spin",
                  )}
                />
                Rerun
              </Button>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Label helpers
// ---------------------------------------------------------------------------

// Keep these as module-level functions so they are not recreated on every
// render and remain easy to unit-test independently.

/** Convert a snake_case pipeline_type value to a readable display label. */
function formatPipelineLabel(pipelineType: string): string {
  return pipelineType === "two_stage" ? "Two Stage" : "Single Stage";
}

/** Convert a snake_case model_arch value to a readable display label. */
function formatModelLabel(modelArch: string): string {
  return modelArch === "double_unet" ? "Double UNet" : "UNet";
}
