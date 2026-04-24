// =============================================================================
// useJobsQuery
// =============================================================================
//
// Cache-aware list fetching for Dashboard and History.  Derives stable query
// keys from filter state, preserves the previous page during pagination
// changes to avoid visible table flicker, and keeps background-refetch state
// visible to the consuming component.

import { listJobs } from "@/api/jobs";
import type { JobFilters } from "@/api/types";
import { keepPreviousData, useQuery } from "@tanstack/react-query";

// Query key factory.  Including the full filter object ensures that any
// filter change automatically invalidates and refetches the correct slice
// of data without manual key management at the call site.
export const jobsQueryKeys = {
  all: ["jobs"] as const,
  list: (filters: JobFilters) => ["jobs", "list", filters] as const,
};

/**
 * Provide cache-aware list fetching for Dashboard and History.
 *
 * Preserves the previous page during pagination changes so the table does
 * not flash to empty while new data is loading.  The `isPlaceholderData`
 * flag from the result can be used to show a subtle loading indicator on
 * the pagination controls without hiding existing rows.
 */
export function useJobsQuery(filters: JobFilters) {
  return useQuery({
    queryKey: jobsQueryKeys.list(filters),
    queryFn: () => listJobs(filters),
    // Keep previous page data visible while the next page is fetching.
    // This prevents the blank-table flash that would otherwise appear
    // whenever the user changes a filter or turns a page.
    placeholderData: keepPreviousData,
  });
}
