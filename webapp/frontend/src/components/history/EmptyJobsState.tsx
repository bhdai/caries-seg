// =============================================================================
// EmptyJobsState
// =============================================================================
//
// Two distinct empty states for the History table:
//
//   1. "first-use" — no jobs exist at all in the database.  Direct the user
//      to Upload so they can create their first job.
//
//   2. "no-results" — filters / search returned zero matches while jobs do
//      exist.  Explain what happened and offer a one-click reset.
//
// The caller selects the correct variant by passing `hasFilters=true` when
// any non-default filter is active.

import { Button } from "@/components/ui/button";
import { ClipboardList, SearchX, UploadCloud } from "lucide-react";
import { Link } from "react-router-dom";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface EmptyJobsStateProps {
  /**
   * True when at least one filter/search value differs from the default.
   * Switches from the first-use variant to the no-results variant.
   */
  hasFilters: boolean;

  /** Called when the user clicks "Reset filters" in the no-results variant. */
  onResetFilters: () => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * Render the appropriate empty state for the history table.
 *
 * First-use variant:  No jobs exist yet.  Guide the user to Upload.
 * No-results variant: Active filters returned zero matches.  Let the user
 *                     reset filters with a single click.
 */
export function EmptyJobsState({ hasFilters, onResetFilters }: EmptyJobsStateProps) {
  if (hasFilters) {
    return <NoResultsEmpty onReset={onResetFilters} />;
  }
  return <FirstUseEmpty />;
}

// ---------------------------------------------------------------------------
// First-use variant
// ---------------------------------------------------------------------------

function FirstUseEmpty() {
  return (
    <div className="py-16 flex flex-col items-center gap-4 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-muted">
        <ClipboardList className="h-6 w-6 text-muted-foreground" />
      </div>

      <div className="space-y-1 max-w-xs">
        <p className="text-sm font-medium">No inference jobs yet</p>
        <p className="text-xs text-muted-foreground">
          Upload a dental X-ray to run your first caries segmentation job. Results
          will appear here once the job completes.
        </p>
      </div>

      <Button asChild size="sm">
        <Link to="/upload">
          <UploadCloud className="h-4 w-4 mr-1.5" />
          Upload X-ray
        </Link>
      </Button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// No-results variant
// ---------------------------------------------------------------------------

interface NoResultsEmptyProps {
  onReset: () => void;
}

function NoResultsEmpty({ onReset }: NoResultsEmptyProps) {
  return (
    <div className="py-16 flex flex-col items-center gap-4 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-muted">
        <SearchX className="h-6 w-6 text-muted-foreground" />
      </div>

      <div className="space-y-1 max-w-xs">
        <p className="text-sm font-medium">No matching jobs</p>
        <p className="text-xs text-muted-foreground">
          No jobs match the current filters or search text.  Try adjusting your
          criteria or clear all filters to see all jobs.
        </p>
      </div>

      <Button variant="outline" size="sm" onClick={onReset}>
        Reset filters
      </Button>
    </div>
  );
}
