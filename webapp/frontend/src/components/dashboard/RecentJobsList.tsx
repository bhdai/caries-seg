// =============================================================================
// RecentJobsList
// =============================================================================
//
// Compact recent-jobs presentation for the Dashboard home page.  Handles
// loading, empty, error, and populated states so DashboardPage only needs to
// pass through query result flags and the job data.
//
// Each card shows: status, primary filename, pipeline/model summary, image
// count, relative last-activity time, and two quick-action buttons — "Open"
// (navigate to result) and "Rerun" (server-side clone via the mutation hook).
//
// The rerun mutation is owned here so navigation-on-success and error toasts
// are co-located with the trigger, keeping DashboardPage free of mutation
// wiring.

import { RecentJobCard } from "@/components/dashboard/RecentJobCard";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useRerunJobMutation } from "@/hooks/useRerunJobMutation";
import type { JobSummary } from "@/api/types";
import { UploadCloud } from "lucide-react";
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
 * Render a card grid of recent inference jobs for the Dashboard home page.
 *
 * States handled:
 *  - Loading  → skeleton placeholder cards.
 *  - Error    → inline recoverable message; does not flash away existing data.
 *  - Empty    → first-use prompt directing the user to Upload.
 *  - Populated → one card per job with open-result and rerun actions.
 */
export function RecentJobsList({ jobs, isLoading, isError }: RecentJobsListProps) {
  const navigate = useNavigate();

  // A single mutation instance covers all cards.  `variables` tells us which
  // job id triggered the currently-pending rerun so we can highlight only
  // that card's button.
  const {
    mutate: rerun,
    isPending: isRerunPending,
    variables: rerunJobId,
  } = useRerunJobMutation();

  // ------------------------------------------------------------------
  // Loading state — show skeleton cards while the first fetch is live.
  // ------------------------------------------------------------------
  if (isLoading) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="rounded-lg border p-4 space-y-3">
            <div className="flex items-center justify-between">
              <Skeleton className="h-5 w-20" />
              <Skeleton className="h-3.5 w-16" />
            </div>
            <Skeleton className="h-4 w-48" />
            <Skeleton className="h-3.5 w-32" />
            <div className="flex gap-2 pt-1">
              <Skeleton className="h-8 flex-1" />
              <Skeleton className="h-8 flex-1" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  // ------------------------------------------------------------------
  // Error state — only shown when there are no cached cards to display.
  //
  // TanStack Query sets `isError` on both initial-load failures and
  // background-refetch failures.  In the refetch case, the previous page
  // of jobs is still available in `jobs`, so we should keep those cards
  // visible and surface the error as a non-destructive inline banner
  // instead of wiping the list.  The "hard error" path below handles the
  // initial-load failure where `jobs` is undefined.
  // ------------------------------------------------------------------
  if (isError && (!jobs || jobs.length === 0)) {
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
  // Populated state — one card per job.
  //
  // When `isError` is true here, a prior successful fetch populated `jobs`
  // and a subsequent background refetch failed.  We keep the stale cards
  // visible and add a non-destructive inline notice above the grid.
  // ------------------------------------------------------------------
  return (
    <div>
      {/* Inline refetch-error notice — shown while stale cards are still visible */}
      {isError && (
        <p className="text-xs text-muted-foreground px-1 pb-3">
          Could not refresh — showing last known results.{" "}
          <button
            className="underline underline-offset-2 hover:text-foreground"
            onClick={() => window.location.reload()}
          >
            Reload
          </button>
        </p>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {jobs.map((job) => (
          <RecentJobCard
            key={job.id}
            job={job}
            isRerunPending={isRerunPending}
            rerunJobId={rerunJobId}
            onOpen={(jobId) => navigate(`/result/${jobId}`)}
            onRerun={(jobId) => rerun(jobId)}
          />
        ))}
      </div>
    </div>
  );
}


