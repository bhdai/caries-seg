// =============================================================================
// HistoryFilters
// =============================================================================
//
// Search box, status filter, pipeline filter, model filter, sort selector,
// and an optional "Reset filters" button for the History page.
//
// URL state is owned by HistoryPage; this component is controlled: it receives
// the current filter values and fires `onChange` with the complete new filter
// object whenever any control changes.
//
// The search box maintains its own local display value so the input field
// feels responsive on every keystroke.  The filter update (and therefore the
// API refetch) is debounced — it fires 350 ms after the user stops typing,
// which prevents unnecessary network requests during fast typing.  Pressing
// Enter immediately submits the current value.
//
// Non-page filters (status, pipeline, model, sort, search) reset the page to 1
// when they change so the user always sees the first result page rather than
// a potentially empty mid-range page.

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { DEFAULT_JOB_FILTERS } from "@/lib/jobFilters";
import type { JobFilters } from "@/api/types";
import { Search, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Debounce delay in milliseconds for the search field. */
const SEARCH_DEBOUNCE_MS = 350;

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface HistoryFiltersProps {
  /** Currently active filter state read from the URL. */
  filters: JobFilters;

  /**
   * Called whenever the user changes any filter value.  The full updated
   * JobFilters object is passed so HistoryPage can write the URL in one step.
   */
  onChange: (next: JobFilters) => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * Render the search box, dropdown selectors, and reset button for the History
 * filter bar.
 *
 * The component is purely controlled: it reads from `filters` and fires
 * `onChange` on every interaction.  URL synchronisation is handled by the
 * parent page.
 */
export function HistoryFilters({ filters, onChange }: HistoryFiltersProps) {
  // Local state for the search input so the text field stays responsive while
  // the debounce timer is pending.
  const [localSearch, setLocalSearch] = useState(filters.search);

  // Keep local search value in sync when the URL changes externally, e.g.
  // browser back/forward navigation.
  useEffect(() => {
    setLocalSearch(filters.search);
  }, [filters.search]);

  // A ref that always holds the latest filters object.  Callbacks that fire
  // asynchronously (debounce timer, Enter handler) read from this ref instead
  // of closing over `filters` directly, which prevents a stale-closure race:
  // if the user types and then changes a dropdown within the debounce window,
  // the pending timeout would otherwise write back an old filter snapshot and
  // silently revert the newer dropdown selection.
  const filtersRef = useRef(filters);
  // Update unconditionally on every render so the ref is always current.
  filtersRef.current = filters;

  // Debounce the search update so we only fire onChange (and therefore
  // refetch) after the user pauses typing rather than on every keystroke.
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleSearchChange = useCallback(
    (value: string) => {
      setLocalSearch(value);

      // Clear any pending debounce timer from the previous keystroke.
      if (debounceRef.current !== null) {
        clearTimeout(debounceRef.current);
      }

      // Read filtersRef.current inside the timeout so we always merge with
      // the filter state that is current when the timer fires, not the state
      // that existed when the user started typing.
      debounceRef.current = setTimeout(() => {
        onChange({ ...filtersRef.current, search: value, page: 1 });
      }, SEARCH_DEBOUNCE_MS);
    },
    [onChange],
  );

  // Immediate submit on Enter keypress so power users don't have to wait.
  const handleSearchKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === "Enter") {
        if (debounceRef.current !== null) {
          clearTimeout(debounceRef.current);
          debounceRef.current = null;
        }
        // Same ref-based read so the Enter path cannot revert a concurrent
        // dropdown change that occurred before the key event.
        onChange({ ...filtersRef.current, search: localSearch, page: 1 });
      }
    },
    [localSearch, onChange],
  );

  // Clean up the pending debounce timer on unmount so we don't call onChange
  // after the component has been removed from the tree.
  useEffect(() => {
    return () => {
      if (debounceRef.current !== null) {
        clearTimeout(debounceRef.current);
      }
    };
  }, []);

  // ---------------------------------------------------------------------------
  // Non-search filter helpers — each one resets page to 1.
  // ---------------------------------------------------------------------------

  const handleStatusChange = useCallback(
    (value: string) => {
      onChange({
        ...filters,
        status: value as JobFilters["status"],
        page: 1,
      });
    },
    [filters, onChange],
  );

  const handlePipelineChange = useCallback(
    (value: string) => {
      onChange({
        ...filters,
        pipelineType: value as JobFilters["pipelineType"],
        page: 1,
      });
    },
    [filters, onChange],
  );

  const handleModelChange = useCallback(
    (value: string) => {
      onChange({
        ...filters,
        modelArch: value as JobFilters["modelArch"],
        page: 1,
      });
    },
    [filters, onChange],
  );

  const handleSortChange = useCallback(
    (value: string) => {
      onChange({
        ...filters,
        sort: value as JobFilters["sort"],
        page: 1,
      });
    },
    [filters, onChange],
  );

  // ---------------------------------------------------------------------------
  // Active-filter detection — determines whether to show the Reset button.
  // ---------------------------------------------------------------------------

  // A filter bar is "active" when any value differs from the canonical default.
  // Page number is intentionally excluded: being on page 3 does not mean the
  // user has active filters.
  const hasActiveFilters =
    filters.search !== DEFAULT_JOB_FILTERS.search ||
    filters.status !== DEFAULT_JOB_FILTERS.status ||
    filters.pipelineType !== DEFAULT_JOB_FILTERS.pipelineType ||
    filters.modelArch !== DEFAULT_JOB_FILTERS.modelArch ||
    filters.sort !== DEFAULT_JOB_FILTERS.sort;

  const handleReset = useCallback(() => {
    setLocalSearch("");
    if (debounceRef.current !== null) {
      clearTimeout(debounceRef.current);
      debounceRef.current = null;
    }
    onChange({ ...DEFAULT_JOB_FILTERS });
  }, [onChange]);

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="flex flex-wrap items-center gap-2">
      {/* Search box */}
      <div className="relative flex-1 min-w-[200px] max-w-sm">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
        <Input
          type="search"
          placeholder="Search by filename or job ID…"
          value={localSearch}
          onChange={(e) => handleSearchChange(e.target.value)}
          onKeyDown={handleSearchKeyDown}
          className="pl-9"
          aria-label="Search jobs"
        />
      </div>

      {/* Status selector */}
      <Select value={filters.status} onValueChange={handleStatusChange}>
        <SelectTrigger className="w-36" aria-label="Filter by status">
          <SelectValue placeholder="Status" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">All statuses</SelectItem>
          <SelectItem value="pending">Pending</SelectItem>
          <SelectItem value="processing">Processing</SelectItem>
          <SelectItem value="completed">Completed</SelectItem>
          <SelectItem value="failed">Failed</SelectItem>
        </SelectContent>
      </Select>

      {/* Pipeline selector */}
      <Select value={filters.pipelineType} onValueChange={handlePipelineChange}>
        <SelectTrigger className="w-36" aria-label="Filter by pipeline">
          <SelectValue placeholder="Pipeline" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">All pipelines</SelectItem>
          <SelectItem value="single_stage">Single Stage</SelectItem>
          <SelectItem value="two_stage">Two Stage</SelectItem>
        </SelectContent>
      </Select>

      {/* Model selector */}
      <Select value={filters.modelArch} onValueChange={handleModelChange}>
        <SelectTrigger className="w-36" aria-label="Filter by model">
          <SelectValue placeholder="Model" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">All models</SelectItem>
          <SelectItem value="unet">UNet</SelectItem>
          <SelectItem value="double_unet">Double UNet</SelectItem>
        </SelectContent>
      </Select>

      {/* Sort selector */}
      <Select value={filters.sort} onValueChange={handleSortChange}>
        <SelectTrigger className="w-44" aria-label="Sort order">
          <SelectValue placeholder="Sort" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="last_activity_desc">Last Activity</SelectItem>
          <SelectItem value="newest">Newest First</SelectItem>
          <SelectItem value="oldest">Oldest First</SelectItem>
        </SelectContent>
      </Select>

      {/* Reset button — only visible when at least one filter is non-default */}
      {hasActiveFilters && (
        <Button
          variant="ghost"
          size="sm"
          onClick={handleReset}
          aria-label="Reset all filters"
        >
          <X className="h-4 w-4 mr-1.5" />
          Reset
        </Button>
      )}
    </div>
  );
}
