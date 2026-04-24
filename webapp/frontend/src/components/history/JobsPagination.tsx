// =============================================================================
// JobsPagination
// =============================================================================
//
// Page controls, page-size selector, and result counts for the History table.
//
// Responsibility: render the navigation strip at the bottom of the job table.
// Data fetching and URL state are owned by the parent (HistoryPage); this
// component is purely presentational and fires callbacks when the user
// interacts with the controls.
//
// When `isPlaceholderData` is true the previous page's data is still showing
// while the next page loads.  In that state the "Next" button is kept visually
// active but disabled to avoid triggering a second navigation while the first
// is in flight, and a subtle loading indicator signals background activity.

import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ChevronLeft, ChevronRight, Loader2 } from "lucide-react";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** The page-size values surfaced in the selector. */
const PAGE_SIZE_OPTIONS = [10, 20, 50] as const;

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface JobsPaginationProps {
  /** Current one-based page number. */
  page: number;

  /** Number of rows per page. */
  pageSize: number;

  /** Total matching jobs across all pages. */
  totalItems: number;

  /** Total number of pages for the current query. */
  totalPages: number;

  /**
   * True when TanStack Query is showing the previous page's data while
   * the next page is loading.  Used to show a subtle loader on the controls.
   */
  isPlaceholderData: boolean;

  /** Called when the user navigates to a different page. */
  onPageChange: (nextPage: number) => void;

  /** Called when the user selects a different page size. */
  onPageSizeChange: (nextPageSize: number) => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * Render the pagination strip below the History table.
 *
 * Shows a result-count summary, Previous / Next navigation buttons, and a
 * page-size selector.  While a page transition is in flight (isPlaceholderData)
 * a small spinner appears next to the count and the Next button is disabled.
 */
export function JobsPagination({
  page,
  pageSize,
  totalItems,
  totalPages,
  isPlaceholderData,
  onPageChange,
  onPageSizeChange,
}: JobsPaginationProps) {
  // Derive the inclusive range of items currently displayed for the summary
  // label, e.g. "21 – 40 of 83 jobs".
  const firstItem = totalItems === 0 ? 0 : (page - 1) * pageSize + 1;
  const lastItem = Math.min(page * pageSize, totalItems);

  const hasPrevious = page > 1 && !isPlaceholderData;
  // Disable Next while placeholder data is shown to avoid double-navigation.
  const hasNext = page < totalPages && !isPlaceholderData;

  return (
    <div className="flex items-center justify-between gap-4 pt-3">
      {/* ------------------------------------------------------------------ */}
      {/* Result count + optional loading indicator                          */}
      {/* ------------------------------------------------------------------ */}
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        {isPlaceholderData && (
          <Loader2 className="h-3.5 w-3.5 animate-spin shrink-0" aria-hidden />
        )}
        {totalItems === 0 ? (
          <span>No results</span>
        ) : (
          <span>
            {firstItem}–{lastItem} of {totalItems} job{totalItems !== 1 ? "s" : ""}
          </span>
        )}
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Navigation controls                                                */}
      {/* ------------------------------------------------------------------ */}
      <div className="flex items-center gap-2">
        {/* Page-size selector — changing it resets the page via the parent. */}
        <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
          <span className="hidden sm:inline">Rows per page</span>
          <Select
            value={String(pageSize)}
            onValueChange={(v) => onPageSizeChange(Number(v))}
          >
            <SelectTrigger className="h-8 w-16" aria-label="Rows per page">
              <SelectValue />
            </SelectTrigger>
            <SelectContent side="top">
              {PAGE_SIZE_OPTIONS.map((n) => (
                <SelectItem key={n} value={String(n)}>
                  {n}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Previous page */}
        <Button
          variant="outline"
          size="icon"
          className="h-8 w-8"
          disabled={!hasPrevious}
          onClick={() => onPageChange(page - 1)}
          aria-label="Previous page"
        >
          <ChevronLeft className="h-4 w-4" />
        </Button>

        {/* Current page indicator */}
        <span className="text-sm tabular-nums min-w-[4rem] text-center">
          {totalItems === 0 ? "–" : `${page} / ${totalPages}`}
        </span>

        {/* Next page */}
        <Button
          variant="outline"
          size="icon"
          className="h-8 w-8"
          disabled={!hasNext}
          onClick={() => onPageChange(page + 1)}
          aria-label="Next page"
        >
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
