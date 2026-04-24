// =============================================================================
// useJobDetailQuery
// =============================================================================
//
// Fetch a single job detail record and poll while the job remains pending or
// processing.  Stops polling automatically when the job reaches a terminal
// state (completed or failed) or when a fetch error occurs.

import { getJobDetail } from "@/api/jobs";
import { ApiError } from "@/api/types";
import { useQuery } from "@tanstack/react-query";

const POLL_INTERVAL_MS = 2_000;

// Terminal statuses for which polling should stop.
const TERMINAL_STATUSES = new Set(["completed", "failed"]);

// Query key factory for job detail.
export const jobDetailQueryKeys = {
  detail: (jobId: string) => ["jobs", "detail", jobId] as const,
};

/**
 * Fetch a single job detail record and poll while the job remains pending or
 * processing.
 *
 * @param jobId - The job UUID to fetch.  Pass `undefined` to disable the
 *   query when the id is not yet known.
 *
 * Polling rules:
 *  - Polls every 2 s while status is "pending" or "processing".
 *  - Stops automatically when status transitions to "completed" or "failed".
 *  - Stops on unrecoverable fetch errors (4xx / 5xx) to avoid flooding the
 *    server when the job record itself is broken.
 */
export function useJobDetailQuery(jobId: string | undefined) {
  return useQuery({
    queryKey: jobDetailQueryKeys.detail(jobId ?? ""),
    queryFn: () => getJobDetail(jobId!),
    // Disable the query entirely when no jobId is available.
    enabled: Boolean(jobId),
    // Derive the refetch interval from the current data.  Once the job is
    // terminal, returning `false` stops polling without any side effects.
    refetchInterval(query) {
      const data = query.state.data;
      if (!data) return false;
      if (TERMINAL_STATUSES.has(data.status)) return false;
      return POLL_INTERVAL_MS;
    },
    // Do not retry on 4xx errors — a missing or forbidden job will not
    // become available on the next attempt.
    retry(failureCount, error) {
      if (error instanceof ApiError && error.status >= 400 && error.status < 500) {
        return false;
      }
      return failureCount < 1;
    },
    // Keep previous data visible during background refetches so the viewer
    // does not flash to a loading state between polls.
    staleTime: 0,
  });
}
