// =============================================================================
// useDashboardStatusSummaryQuery
// =============================================================================
//
// Fetch dashboard status counts in parallel using the existing jobs list
// endpoint with `page_size=1` and a status filter on each of the four
// possible job states.
//
// Why parallel queries?
//   The backend does not expose a single status-summary endpoint.  Instead of
//   adding one now (deferred per the plan), we issue four cheap list requests
//   in parallel and read only `total_items` from each response.  The larger
//   `staleTime` (30 s) keeps round-trips low for a typical dashboard view.
//
// Partial failure tolerance:
//   If one status query fails the hook still returns a result for the other
//   three statuses.  The `isPartiallyDegraded` flag lets the UI surface a
//   subtle hint without hiding the entire summary block.

import { listJobs } from "@/api/jobs";
import type { DashboardStatusSummary, JobStatus } from "@/api/types";
import { DEFAULT_JOB_FILTERS } from "@/lib/jobFilters";
import { useQueries } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

// One per status — each issued in parallel as a tiny list request.
const STATUSES: JobStatus[] = ["pending", "processing", "completed", "failed"];

// Human-readable labels shown in chips and chart tooltips.
const STATUS_LABELS: Record<JobStatus, string> = {
  pending: "Pending",
  processing: "Processing",
  completed: "Completed",
  failed: "Failed",
};

// CSS color tokens drawn from Tailwind / shadcn design system.  These align
// with the colour meaning used by JobStatusChip so the dashboard is visually
// consistent.
const STATUS_COLOR_TOKENS: Record<JobStatus, string> = {
  pending: "hsl(var(--muted-foreground))",
  processing: "hsl(var(--primary))",
  completed: "hsl(142, 71%, 45%)",   // green-500 equivalent
  failed: "hsl(var(--destructive))",
};

// Cache status summary counts for 30 s — much longer than job-detail polling
// — so repeated dashboard visits don't trigger a burst of requests.
const STALE_TIME_MS = 30_000;

// ---------------------------------------------------------------------------
// Return type
// ---------------------------------------------------------------------------

export interface DashboardStatusSummaryResult {
  /** Normalized summary ready for chips and chart rendering. */
  data: DashboardStatusSummary | null;
  /** True while at least one status count is being fetched. */
  isLoading: boolean;
  /** True when all four queries have settled (success or error). */
  isSettled: boolean;
  /**
   * True when at least one status query failed but at least one succeeded.
   * Used to show a subtle degraded-state hint without hiding the whole block.
   */
  isPartiallyDegraded: boolean;
  /** True when every status query failed. */
  isFullyFailed: boolean;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

/**
 * Fetch dashboard status counts in parallel using the existing jobs list
 * endpoint with `page_size=1` and a status filter.
 *
 * Returns a normalized summary object suitable for status chips and chart
 * rendering.  Tolerates one failed status query without blocking the entire
 * dashboard page.
 */
export function useDashboardStatusSummaryQuery(): DashboardStatusSummaryResult {
  const results = useQueries({
    queries: STATUSES.map((status) => ({
      queryKey: ["jobs", "statusCount", status] as const,
      queryFn: () =>
        listJobs({
          ...DEFAULT_JOB_FILTERS,
          status,
          pageSize: 1,
        }),
      staleTime: STALE_TIME_MS,
      // Avoid hammering the server on transient failures — the summary is
      // informational and stale data is better than a cascade of retries.
      retry: 1,
    })),
  });

  const isLoading = results.some((r) => r.isLoading);
  const failedCount = results.filter((r) => r.isError).length;
  const succeededCount = results.filter((r) => r.isSuccess).length;
  const isSettled = results.every((r) => r.isSuccess || r.isError);
  const isPartiallyDegraded = failedCount > 0 && succeededCount > 0;
  const isFullyFailed = failedCount === STATUSES.length;

  // Build the normalized summary only when at least one count is available.
  let data: DashboardStatusSummary | null = null;
  if (succeededCount > 0) {
    const counts: Record<JobStatus, number> = {
      pending: 0,
      processing: 0,
      completed: 0,
      failed: 0,
    };

    STATUSES.forEach((status, i) => {
      const result = results[i];
      if (result.isSuccess && result.data) {
        counts[status] = result.data.total_items;
      }
      // Silently leave as 0 for failed queries so the chart remains usable.
    });

    const total =
      counts.pending + counts.processing + counts.completed + counts.failed;

    data = {
      ...counts,
      total,
      chartData: STATUSES.map((status) => ({
        status,
        label: STATUS_LABELS[status],
        count: counts[status],
        colorToken: STATUS_COLOR_TOKENS[status],
      })),
    };
  }

  return { data, isLoading, isSettled, isPartiallyDegraded, isFullyFailed };
}
