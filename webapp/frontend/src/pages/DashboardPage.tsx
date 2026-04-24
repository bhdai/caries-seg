// =============================================================================
// DashboardPage
// =============================================================================
//
// Home route at `/`.  Optimised for "what happened recently?" rather than
// exhaustive browsing.
//
// Data flow:
//   useJobsQuery(DASHBOARD_FILTERS)
//     → GET /api/jobs?page=1&page_size=5&sort=last_activity_desc
//     → passes result to RecentJobsList
//
// The filter object is defined at module scope so it is referentially stable
// across renders and does not trigger spurious re-fetches.

import { DashboardSummary } from "@/components/dashboard/DashboardSummary";
import { RecentJobsList } from "@/components/dashboard/RecentJobsList";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { useJobsQuery } from "@/hooks/useJobsQuery";
import { DEFAULT_JOB_FILTERS } from "@/lib/jobFilters";
import type { JobFilters } from "@/api/types";
import { Link } from "react-router-dom";

// Stable filter object for the dashboard recent-jobs slice.  A small page
// size keeps the request cheap and the list scannable at a glance.
const DASHBOARD_FILTERS: JobFilters = {
  ...DEFAULT_JOB_FILTERS,
  pageSize: 5,
  sort: "last_activity_desc",
};

/**
 * Dashboard home page.
 *
 * Shows the five most-recently-active jobs with quick-action buttons so
 * users can jump straight into a result or rerun an existing job without
 * navigating to the full History table.
 */
export default function DashboardPage() {
  const { data, isLoading, isError } = useJobsQuery(DASHBOARD_FILTERS);

  return (
    <div className="space-y-8">
      {/* ------------------------------------------------------------------ */}
      {/* Page header with primary CTA                                        */}
      {/* ------------------------------------------------------------------ */}
      <DashboardSummary />

      {/* ------------------------------------------------------------------ */}
      {/* Recent jobs                                                         */}
      {/* ------------------------------------------------------------------ */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Recent Jobs</CardTitle>
        </CardHeader>

        <CardContent>
          <RecentJobsList
            jobs={data?.items}
            isLoading={isLoading}
            isError={isError}
          />
        </CardContent>

        {/* Footer link to the full history table — only when there are jobs */}
        {data && data.total_items > 0 && (
          <CardFooter className="border-t pt-4">
            <Link
              to="/history"
              className="text-sm text-muted-foreground underline underline-offset-4 hover:text-foreground"
            >
              View all {data.total_items} job{data.total_items !== 1 ? "s" : ""} →
            </Link>
          </CardFooter>
        )}
      </Card>
    </div>
  );
}
