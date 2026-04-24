// =============================================================================
// DashboardSummary
// =============================================================================
//
// High-level dashboard header with the primary "New Job" CTA and contextual
// framing for the recent-activity section below it.  Kept as a dedicated
// component so DashboardPage stays focused on data orchestration while this
// component owns presentation of the page title and primary quick-action.

import { Button } from "@/components/ui/button";
import { UploadCloud } from "lucide-react";
import { Link } from "react-router-dom";

/**
 * Render the dashboard page header: title, subtitle, and the primary
 * "New Job" CTA that launches the upload flow.
 *
 * This component is intentionally stateless — it provides framing only.
 * Data-driven content (recent jobs, stats) lives in sibling components on
 * DashboardPage.
 */
export function DashboardSummary() {
  return (
    <div className="flex items-start justify-between">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground mt-1">
          Recent inference jobs and quick actions.
        </p>
      </div>

      {/* Primary CTA — always visible to encourage the upload flow. */}
      <Button asChild>
        <Link to="/upload">
          <UploadCloud className="h-4 w-4 mr-2" />
          New Job
        </Link>
      </Button>
    </div>
  );
}
