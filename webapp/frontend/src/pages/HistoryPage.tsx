// =============================================================================
// HistoryPage
// =============================================================================
//
// Full job list at `/history`.  Optimised for search and triage.  The
// paginated table, filter controls, and row actions are built out in
// Phase 4; this shell establishes the route, URL filter state initialisation,
// and page framing so the navigation works end-to-end after Phase 2.

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DEFAULT_JOB_FILTERS, parseFiltersFromParams } from "@/lib/jobFilters";
import type { JobFilters } from "@/api/types";
import { UploadCloud } from "lucide-react";
import { useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";

/**
 * History page — full list, filters, search, and pagination.
 *
 * Phase 2: page shell that reads and normalises URL filter state, and
 * renders a placeholder for the table that will be implemented in Phase 4.
 * URL state initialisation and the filter → query key derivation are live
 * so the data layer can be wired without layout changes in Phase 4.
 */
export default function HistoryPage() {
  const [searchParams] = useSearchParams();

  // Parse and normalise the current URL query params into a validated
  // JobFilters model.  Any missing or invalid param falls back to defaults,
  // which ensures the page is always in a known state regardless of the URL.
  const filters: JobFilters = useMemo(
    () => parseFiltersFromParams(searchParams),
    [searchParams],
  );

  // Suppress the unused-variable warning while the table is a placeholder.
  void filters;
  void DEFAULT_JOB_FILTERS;

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
      {/* Job table — placeholder for Phase 4                                */}
      {/* ------------------------------------------------------------------ */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">All Jobs</CardTitle>
        </CardHeader>
        <CardContent>
          {/* TODO(Phase 4): Replace this placeholder with HistoryFilters +
              JobsTable + JobsPagination. */}
          <p className="text-sm text-muted-foreground">
            Job history will appear here.{" "}
            <Link to="/upload" className="underline underline-offset-4 hover:text-foreground">
              Upload an X-ray
            </Link>{" "}
            to create your first job.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
