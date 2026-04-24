// =============================================================================
// DashboardStatusOverview
// =============================================================================
//
// Renders the dashboard status summary section: four count chips (one per
// job lifecycle status) and one compact status-distribution chart.
//
// Data is fetched by `useDashboardStatusSummaryQuery`, which issues four
// parallel list requests to derive counts without requiring a new backend
// endpoint.  This component owns the loading, partial-error, and full-error
// display states so DashboardPage stays focused on layout composition.

import { DashboardStatusChart } from "@/components/dashboard/DashboardStatusChart";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useDashboardStatusSummaryQuery } from "@/hooks/useDashboardStatusSummaryQuery";
import type { JobStatus } from "@/api/types";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Status chip styles
// ---------------------------------------------------------------------------

// Each status maps to a subtle colour pair (text + background) so the chips
// feel consistent with the JobStatusChip used elsewhere in the app.
const STATUS_CHIP_STYLES: Record<JobStatus, string> = {
  pending:    "bg-muted text-muted-foreground",
  processing: "bg-primary/10 text-primary",
  completed:  "bg-green-500/10 text-green-700 dark:text-green-400",
  failed:     "bg-destructive/10 text-destructive",
};

const STATUS_LABELS: Record<JobStatus, string> = {
  pending:    "Pending",
  processing: "Processing",
  completed:  "Completed",
  failed:     "Failed",
};

const STATUS_ORDER: JobStatus[] = ["pending", "processing", "completed", "failed"];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * Render four status summary chips and a compact distribution chart.
 *
 * States handled:
 *  - Loading          → skeleton chips and chart placeholder.
 *  - Fully failed     → non-destructive error notice; the rest of the
 *                        dashboard (recent jobs) remains visible.
 *  - Partially degraded → show available counts with a subtle hint that
 *                        some figures may be incomplete.
 *  - Success          → chips with counts and the stacked-bar chart.
 */
export function DashboardStatusOverview() {
  const { data, isLoading, isFullyFailed, isPartiallyDegraded } =
    useDashboardStatusSummaryQuery();

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Status Overview</CardTitle>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* ---------------------------------------------------------------- */}
        {/* Loading state — skeleton chips                                   */}
        {/* ---------------------------------------------------------------- */}
        {isLoading && !data && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-14 w-full rounded-md" />
            ))}
          </div>
        )}

        {/* ---------------------------------------------------------------- */}
        {/* Fully failed — no counts available                               */}
        {/* ---------------------------------------------------------------- */}
        {isFullyFailed && (
          <p className="text-sm text-muted-foreground py-2">
            Status counts unavailable — dashboard data could not be loaded.
          </p>
        )}

        {/* ---------------------------------------------------------------- */}
        {/* Status chips — shown once any count data is available            */}
        {/* ---------------------------------------------------------------- */}
        {data && (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {STATUS_ORDER.map((status) => (
                <div
                  key={status}
                  className={cn(
                    "flex flex-col items-center justify-center rounded-md py-3 px-2 text-center",
                    STATUS_CHIP_STYLES[status],
                  )}
                >
                  <span className="text-2xl font-bold leading-none tabular-nums">
                    {data[status]}
                  </span>
                  <span className="text-xs mt-1 font-medium">
                    {STATUS_LABELS[status]}
                  </span>
                </div>
              ))}
            </div>

            {/* Compact stacked-bar distribution chart */}
            <DashboardStatusChart summary={data} />

            {/* Subtle note when one count query failed */}
            {isPartiallyDegraded && (
              <p className="text-xs text-muted-foreground">
                Some counts may be incomplete due to a fetch error.
              </p>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
