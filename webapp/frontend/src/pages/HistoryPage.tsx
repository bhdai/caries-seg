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
//   - Manage row selection state (Set<string>) for bulk operations.
//   - Bulk-delete selected jobs with a confirmation dialog.
//
// Components rendered:
//   HistoryFilters  — search, dropdowns, reset button
//   JobsTable       — TanStack Table with shadcn primitives + empty states
//   JobsPagination  — page controls, page-size selector, result counts

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { HistoryFilters } from "@/components/history/HistoryFilters";
import { JobsTable } from "@/components/history/JobsTable";
import { JobsPagination } from "@/components/history/JobsPagination";
import { PatientLinkModal } from "@/components/patients/PatientLinkModal";
import { DEFAULT_JOB_FILTERS, filtersToParams, parseFiltersFromParams } from "@/lib/jobFilters";
import { useJobsQuery } from "@/hooks/useJobsQuery";
import { useRerunJobMutation } from "@/hooks/useRerunJobMutation";
import { useDeleteJobMutation } from "@/hooks/useDeleteJobMutation";
import { patchJob } from "@/api/jobs";
import type { JobFilters } from "@/api/types";
import { Trash2, UploadCloud } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { useStartNewJob } from "@/hooks/useStartNewJob";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

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
  const startNewJob = useStartNewJob();
  const { t } = useTranslation();

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
  // Delete mutation
  // ---------------------------------------------------------------------------

  const { mutate: deleteOne, isPending: isDeletePending } = useDeleteJobMutation();

  // ---------------------------------------------------------------------------
  // Row selection state
  // ---------------------------------------------------------------------------

  // Selected job IDs are stored as a Set for O(1) membership tests.  The Set
  // is re-created on each mutation so React sees a reference change and
  // re-renders dependants.  Selection is scoped to the current page view;
  // navigating to a new page (via filter/page change) clears the selection
  // to prevent phantom selections of rows the user can no longer see.
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  const handleToggleSelect = useCallback((jobId: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(jobId)) {
        next.delete(jobId);
      } else {
        next.add(jobId);
      }
      return next;
    });
  }, []);

  // Select-all / deselect-all over the currently visible rows.
  const handleSelectAll = useCallback((allIds: string[]) => {
    setSelectedIds((prev) => {
      const allSelected = allIds.every((id) => prev.has(id));
      if (allSelected) {
        // Deselect all visible rows while keeping any selections on other pages.
        const next = new Set(prev);
        allIds.forEach((id) => next.delete(id));
        return next;
      }
      // Select all visible rows.
      return new Set([...prev, ...allIds]);
    });
  }, []);

  // ---------------------------------------------------------------------------
  // Bulk delete
  // ---------------------------------------------------------------------------

  const [bulkDeleteDialogOpen, setBulkDeleteDialogOpen] = useState(false);

  const handleBulkDeleteConfirm = useCallback(() => {
    const ids = [...selectedIds];
    setSelectedIds(new Set());
    // Fire one mutation per selected job.  Each mutation invalidates the query
    // cache on success; the last one triggers a refetch that removes all
    // deleted rows in one shot.
    ids.forEach((id) => deleteOne(id));
  }, [selectedIds, deleteOne]);

  // ---------------------------------------------------------------------------
  // Active-filter detection — passed to JobsTable for empty-state selection
  // ---------------------------------------------------------------------------

  const hasActiveFilters =
    filters.search !== DEFAULT_JOB_FILTERS.search ||
    filters.status !== DEFAULT_JOB_FILTERS.status ||
    filters.pipelineType !== DEFAULT_JOB_FILTERS.pipelineType ||
    filters.modelArch !== DEFAULT_JOB_FILTERS.modelArch ||
    filters.sort !== DEFAULT_JOB_FILTERS.sort ||
    filters.patientId !== DEFAULT_JOB_FILTERS.patientId;

  const selectedCount = selectedIds.size;

  // ---------------------------------------------------------------------------
  // Patient link modal
  // ---------------------------------------------------------------------------

  // The job the patient link modal is currently targeting, or null when closed.
  const [linkTargetJobId, setLinkTargetJobId] = useState<string | null>(null);
  const queryClient = useQueryClient();

  // Derive the current patient info for the targeted job so PatientLinkModal
  // can show the current link state and pre-fill the combobox.
  const linkTargetJob = data?.items.find((j) => j.id === linkTargetJobId) ?? null;

  const handleLinkPatient = useCallback((jobId: string) => {
    setLinkTargetJobId(jobId);
  }, []);

  // Unlink is handled inline here (not via PatientLinkModal) because the
  // confirmation dialog is already embedded in JobRowActions.  The caller
  // expects us to fire patchJob directly.
  const handleUnlinkPatient = useCallback(
    async (jobId: string) => {
      try {
        await patchJob(jobId, { patient_id: null });
        void queryClient.invalidateQueries({ queryKey: ["jobs"] });
        toast.success(t("patient.link.successUnlinked"));
      } catch {
        toast.error(t("patient.link.error.fallback"));
      }
    },
    [queryClient, t],
  );

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
          <h1 className="text-3xl font-bold tracking-tight">{t("history.title")}</h1>
          <p className="text-muted-foreground mt-1">
            {t("history.subtitle")}
          </p>
        </div>
        <Button onClick={startNewJob}>
          <UploadCloud className="h-4 w-4 mr-2" />
          {t("nav.newJob")}
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
          {t("history.loadError")}{" "}
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
          <div className="flex items-center justify-between">
            <CardTitle className="text-base">{t("history.allJobs")}</CardTitle>
            {selectedCount > 0 && (
              <div className="flex items-center gap-2">
                <span className="text-sm text-muted-foreground">
                  {selectedCount} job{selectedCount !== 1 ? "s" : ""} selected
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setSelectedIds(new Set())}
                >
                  Clear selection
                </Button>
                <Button
                  variant="destructive"
                  size="sm"
                  disabled={isDeletePending}
                  onClick={() => setBulkDeleteDialogOpen(true)}
                >
                  <Trash2 className="h-4 w-4 mr-1.5" />
                  {t("history.deleteNJobs", { count: selectedCount })}
                </Button>
              </div>
            )}
          </div>
        </CardHeader>
        <CardContent className="px-0 pb-0">
          <JobsTable
            rows={data?.items ?? []}
            hasFilters={hasActiveFilters}
            isLoading={isLoading}
            isRefetching={isPlaceholderData}
            rerunPendingJobId={isRerunPending ? rerunJobId : undefined}
            selectedIds={selectedIds}
            onResetFilters={resetFilters}
            onOpenJob={(jobId) => navigate(`/result/${jobId}`)}
            onRerun={(jobId) => rerun(jobId)}
            onDeleteOne={(jobId) => deleteOne(jobId)}
            onLinkPatient={handleLinkPatient}
            onUnlinkPatient={(jobId) => { void handleUnlinkPatient(jobId); }}
            onToggleSelect={handleToggleSelect}
            onSelectAll={handleSelectAll}
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

      {/* ------------------------------------------------------------------ */}
      {/* Bulk delete confirmation dialog                                     */}
      {/* ------------------------------------------------------------------ */}
      <AlertDialog open={bulkDeleteDialogOpen} onOpenChange={setBulkDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t("history.deleteConfirm", { count: selectedCount })}
            </AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently remove the selected job
              {selectedCount !== 1 ? "s" : ""} and all their result files.
              This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("jobRow.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={handleBulkDeleteConfirm}
            >
              {t("history.deleteNJobs", { count: selectedCount })}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      {/* ------------------------------------------------------------------ */}
      {/* Patient link modal — opened when user picks link/change from row   */}
      {/* ------------------------------------------------------------------ */}
      <PatientLinkModal
        open={linkTargetJobId !== null}
        onOpenChange={(open) => { if (!open) setLinkTargetJobId(null); }}
        jobId={linkTargetJobId ?? ""}
        currentPatientId={linkTargetJob?.patient_id ?? null}
        currentPatientName={linkTargetJob?.patient_name ?? null}
        onLinked={() => {
          void queryClient.invalidateQueries({ queryKey: ["jobs"] });
          setLinkTargetJobId(null);
        }}
      />
    </div>
  );
}

