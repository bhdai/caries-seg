// =============================================================================
// DashboardPage
// =============================================================================
//
// New home route at `/`.  Optimised for "what happened recently?" rather
// than exhaustive browsing.  The full recent-jobs list, quick-rerun actions,
// and status cards are built out in Phase 3; this shell establishes the
// route, page framing, and primary CTA so the navigation works end-to-end
// after Phase 2.

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { UploadCloud } from "lucide-react";
import { Link } from "react-router-dom";

/**
 * Dashboard home page.
 *
 * Phase 2: page shell with header, primary CTA, and a placeholder for the
 * recent-jobs section that will be implemented in Phase 3.
 */
export default function DashboardPage() {
  return (
    <div className="space-y-8">
      {/* ------------------------------------------------------------------ */}
      {/* Header                                                              */}
      {/* ------------------------------------------------------------------ */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
          <p className="text-muted-foreground mt-1">
            Recent inference jobs and quick actions.
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
      {/* Recent jobs — placeholder for Phase 3                              */}
      {/* ------------------------------------------------------------------ */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Recent Jobs</CardTitle>
        </CardHeader>
        <CardContent>
          {/* TODO(Phase 3): Replace this placeholder with RecentJobsList. */}
          <p className="text-sm text-muted-foreground">
            Recent jobs will appear here.{" "}
            <Link to="/upload" className="underline underline-offset-4 hover:text-foreground">
              Upload your first X-ray
            </Link>{" "}
            to get started.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
