// =============================================================================
// HistoryPage
// =============================================================================
//
// Full job list at `/history`.  Optimised for search and triage.
//
// Responsibilities owned here:
//   - Read and normalise URL query params into a validated JobFilters model.
//   - Derive the `useJobsQuery` query key from filter state so every filter
//     change triggers the correct refetch automatically.
//   - Write updated filter state back to the URL so the page is reloadable
//     and shareable.  Non-page filters reset page to 1 on change; this rule
//     is enforced in the HistoryFilters component before onChange fires.
//   - Navigate to /result/:jobId on row open and hand off rerun to the
//     useRerunJobMutation hook.
//
// Components rendered:
//   HistoryFilters  — search, dropdowns, reset button
//   JobsTable       — TanStack Table with shadcn primitives + empty states
//   JobsPagination  — page controls, page-size selector, result counts

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { HistoryFilters } from "@/components/history/HistoryFilters";
import { JobsTable } from "@/components/history/JobsTable";
import { JobsPagination } from "@/components/history/JobsPagination";
import { DEFAULT_JOB_FILTERS, filtersToParams, parseFiltersFromParams } from "@/lib/jobFilters";
import { useJobsQuery } from "@/hooks/useJobsQuery";
import { useRerunJobMutation } from "@/hooks/useRerunJobMutation";
import type { JobFilters } from "@/api/types";
import { UploadCloud } from "lucide-react";
import { useCallback, useMemo } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

/**
 * History page — full list, filters, search, and server-side pagination.
 *
 * Filter state lives exclusively in the URL so the page is reloadable,
 * shareable, and navigable via the browser back/forward buttons.  The
 * `useJobsQuery` hook re-fetches whenever the derived filter object changes.
 */
export default function HistoryPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();

  // ---------------------------------------------------------------------------
  // Filter state — parsed from URL, normalised to defaults for missing values
  // ---------------------------------------------------------------------------

  const filters: JobFilters = useMemo(
    () => parseFiltersFromParams(searchParams),
    [searchParams],
  );

  // Write the new filter state back to the URL.  `filtersToParams` omits
  // default values to keep URLs short; the absence of a key is equivalent to
  // the default, so round-tripping is lossless.
  const updateFilters = useCallback(
    (next: JobFilters) => {
      setSearchParams(filtersToParams(next), { replace: false });
    },
    [setSearchParams],
  );

  // Shortcut used by EmptyJobsState "Reset filters" — drops all non-default
  // values and returns to page 1.
  const resetFilters = useCallback(() => {
    setSearchParams(filtersToParams(DEFAULT_JOB_FILTERS), { replace: false });
  }, [setSearchParams]);

  // Page and page-size changes are small enough to handle directly here so
  // HistoryFilters only needs to deal with filter-level changes.
  const handlePageChange = useCallback(
    (nextPage: number) => {
      updateFilters({ ...filters, page: nextPage });
    },
    [filters, updateFilters],
  );

  const handlePageSizeChange = useCallback(
    (nextPageSize: number) => {
      // Changing page size resets to page 1 to avoid landing on an empty
      // page when the new size is larger than the remaining items.
      updateFilters({ ...filters, pageSize: nextPageSize, page: 1 });
    },
    [filters, updateFilters],
  );

  // ---------------------------------------------------------------------------
  // Data fetching
  // ---------------------------------------------------------------------------

  const { data, isLoading, isError, isPlaceholderData } = useJobsQuery(filters);

  // ---------------------------------------------------------------------------
  // Rerun mutation
  // ---------------------------------------------------------------------------

  // A single mutation instance covers all rows.  The `variables` field tells
  // us which job id triggered the currently-pending rerun so JobsTable can
  // highlight only that row's action button.
  const {
    mutate: rerun,
    isPending: isRerunPending,
    variables: rerunJobId,
  } = useRerunJobMutation();

  // ---------------------------------------------------------------------------
  // Active-filter detection — passed to JobsTable for empty-state selection
  // ---------------------------------------------------------------------------

  const hasActiveFilters =
    filters.search !== DEFAULT_JOB_FILTERS.search ||
    filters.status !== DEFAULT_JOB_FILTERS.status ||
    filters.pipelineType !== DEFAULT_JOB_FILTERS.pipelineType ||
    filters.modelArch !== DEFAULT_JOB_FILTERS.modelArch ||
    filters.sort !== DEFAULT_JOB_FILTERS.sort;

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="space-y-6">
      {/* ------------------------------------------------------------------ */}
      {/* Header                                                              */}
      {/* ------------------------------------------------------------------ */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">History</h1>
          <p className="text-muted-foreground mt-1">
            All inference jobs, filterable by status, pipeline, and model.
          </p>
        </div>
        <Button asChild>
          <Link to="/upload">
            <UploadCloud className="h-4 w-4 mr-2" />
            New Job
          </Link>
        </Button>
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Filters bar                                                         */}
      {/* ------------------------------------------------------------------ */}
      <HistoryFilters filters={filters} onChange={updateFilters} />

      {/* ------------------------------------------------------------------ */}
      {/* Error banner — shown when the fetch fails while no data is cached   */}
      {/* ------------------------------------------------------------------ */}
      {isError && !data && (
        <p className="text-sm text-destructive">
          Could not load job history.{" "}
          <button
            className="underline underline-offset-4 hover:opacity-80"
            onClick={() => window.location.reload()}
          >
            Refresh the page
          </button>{" "}
          to try again.
        </p>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Table card                                                          */}
      {/* ------------------------------------------------------------------ */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">All Jobs</CardTitle>
        </CardHeader>
        <CardContent className="px-0 pb-0">
          <JobsTable
            rows={data?.items ?? []}
            hasFilters={hasActiveFilters}
            isLoading={isLoading}
            isRefetching={isPlaceholderData}
            rerunPendingJobId={isRerunPending ? rerunJobId : undefined}
            onResetFilters={resetFilters}
            onOpenJob={(jobId) => navigate(`/result/${jobId}`)}
            onRerun={(jobId) => rerun(jobId)}
          />

          {/* Pagination — shown only when there is data to paginate */}
          {!isLoading && data && data.total_items > 0 && (
            <div className="px-6 pb-4">
              {/*
               * Use filters.page / filters.pageSize (from the URL) rather than
               * data.page / data.page_size (from the response) so the controls
               * reflect the user's *actual* navigation intent even while
               * isPlaceholderData is true.  During a placeholder window the
               * cached response still carries the old page number, which would
               * make Previous / Next compute the wrong target.
               */}
              <JobsPagination
                page={filters.page}
                pageSize={filters.pageSize}
                totalItems={data.total_items}
                totalPages={data.total_pages}
                isPlaceholderData={isPlaceholderData}
                onPageChange={handlePageChange}
                onPageSizeChange={handlePageSizeChange}
              />
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
