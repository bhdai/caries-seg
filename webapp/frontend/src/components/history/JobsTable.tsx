// =============================================================================
// JobsTable
// =============================================================================
//
// Server-driven history table using TanStack Table v8 column definitions and
// shadcn table primitives.
//
// Column layout (left → right):
//   Status | File | Pipeline · Model | Images | Last Activity | Actions
//
// TanStack Table is used here for its column-definition API and the ability
// to add client-side sorting or column visibility toggles in a later phase
// without a full rewrite.  Server-side pagination is handled entirely by the
// parent (HistoryPage); this component only renders the page of rows it
// receives.
//
// States handled:
//   Loading     → fixed number of skeleton rows so the layout does not jump.
//   Refetching  → rows remain visible; JobsPagination shows a loader instead.
//   Empty       → EmptyJobsState (variant chosen by the caller).
//   Populated   → one row per job summary with actions dropdown.
//
// The component does not own any fetch logic, mutation logic, or navigation.
// Those concerns are handled by the parent page and the JobRowActions
// component, which receives callback props for each action.

import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from "@tanstack/react-table";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { JobStatusChip } from "@/components/jobs/JobStatusChip";
import { JobRowActions } from "@/components/history/JobRowActions";
import { EmptyJobsState } from "@/components/history/EmptyJobsState";
import { formatRelativeTime, formatAbsoluteTime } from "@/lib/time";
import type { JobSummary } from "@/api/types";

// ---------------------------------------------------------------------------
// Column helper
// ---------------------------------------------------------------------------

const col = createColumnHelper<JobSummary>();

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface JobsTableProps {
  /** The page of job summaries to display. */
  rows: JobSummary[];

  /** True when a filter/search is active (used by EmptyJobsState). */
  hasFilters: boolean;

  /** True while the initial fetch (hard reload) is in flight. */
  isLoading: boolean;

  /**
   * True while TanStack Query fetches a new page in the background and the
   * previous page's rows are still displayed as placeholder data.
   */
  isRefetching: boolean;

  /**
   * True when the rerun mutation is currently in flight.
   * The specific job id being rerun is tracked separately so only that row's
   * action button shows a spinner.
   */
  rerunPendingJobId: string | undefined;

  /** Called when the user resets filters from the empty state. */
  onResetFilters: () => void;

  /** Called when the user selects "Open result" for a row. */
  onOpenJob: (jobId: string) => void;

  /** Called when the user selects "Rerun" for a row. */
  onRerun: (jobId: string) => void;
}

// ---------------------------------------------------------------------------
// Column definitions
// ---------------------------------------------------------------------------

// Column definitions are created once outside the component so they are not
// re-instantiated on every render.

function buildColumns(
  rerunPendingJobId: string | undefined,
  onOpenJob: (id: string) => void,
  onRerun: (id: string) => void,
) {
  return [
    // Status badge
    col.accessor("status", {
      header: "Status",
      cell: (info) => <JobStatusChip status={info.getValue()} />,
      size: 110,
    }),

    // Primary filename + overflow preview (e.g. "+ 2 more")
    col.accessor("primary_filename", {
      header: "File",
      cell: (info) => {
        const job = info.row.original;
        const extra = job.filename_preview.length;
        return (
          <div className="min-w-0">
            <p className="text-sm font-medium truncate leading-snug">
              {info.getValue()}
            </p>
            {extra > 0 && (
              <p className="text-xs text-muted-foreground mt-0.5">
                +{extra} more
              </p>
            )}
          </div>
        );
      },
    }),

    // Pipeline + model arch in a compact two-line cell
    col.display({
      id: "pipeline_model",
      header: "Pipeline / Model",
      cell: ({ row }) => {
        const job = row.original;
        return (
          <div className="text-sm">
            <span>{formatPipelineLabel(job.pipeline_type)}</span>
            <span className="text-muted-foreground"> · </span>
            <span className="text-muted-foreground">{formatModelLabel(job.model_arch)}</span>
          </div>
        );
      },
      size: 160,
    }),

    // Image count
    col.accessor("image_count", {
      header: "Images",
      cell: (info) => (
        <span className="text-sm tabular-nums">{info.getValue()}</span>
      ),
      size: 70,
    }),

    // Relative last-activity time with absolute date as tooltip
    col.accessor("last_activity_at", {
      header: "Last Activity",
      cell: (info) => {
        const iso = info.getValue();
        return (
          <span
            className="text-sm text-muted-foreground whitespace-nowrap"
            title={formatAbsoluteTime(iso)}
          >
            {formatRelativeTime(iso)}
          </span>
        );
      },
      size: 130,
    }),

    // Row-level actions dropdown
    col.display({
      id: "actions",
      header: "",
      cell: ({ row }) => (
        <JobRowActions
          jobId={row.original.id}
          isRerunPending={rerunPendingJobId === row.original.id}
          onOpen={onOpenJob}
          onRerun={onRerun}
        />
      ),
      size: 48,
    }),
  ];
}

// ---------------------------------------------------------------------------
// Skeleton rows
// ---------------------------------------------------------------------------

/** Number of skeleton rows to show during the initial load. */
const SKELETON_ROW_COUNT = 5;

function SkeletonRows({ columnCount }: { columnCount: number }) {
  return (
    <>
      {Array.from({ length: SKELETON_ROW_COUNT }).map((_, rowIdx) => (
        <TableRow key={rowIdx}>
          {Array.from({ length: columnCount }).map((_, colIdx) => (
            <TableCell key={colIdx}>
              <Skeleton className="h-4 w-full max-w-[120px]" />
            </TableCell>
          ))}
        </TableRow>
      ))}
    </>
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * Render the canonical History table using TanStack Table column definitions
 * and shadcn table primitives.
 *
 * The component is server-driven: all pagination and filtering happens outside
 * this component.  It renders the rows it receives, handles loading and empty
 * states, and fires callbacks for row-level actions.
 */
export function JobsTable({
  rows,
  hasFilters,
  isLoading,
  isRefetching: _isRefetching,
  rerunPendingJobId,
  onResetFilters,
  onOpenJob,
  onRerun,
}: JobsTableProps) {
  // Build column definitions with access to current action callbacks.
  // Memoisation is not strictly required here because TanStack Table handles
  // its own internal reconciliation, but stable references help React avoid
  // unnecessary work on re-renders that do not change filter or action props.
  const columns = buildColumns(rerunPendingJobId, onOpenJob, onRerun);

  const table = useReactTable({
    data: rows,
    columns,
    getCoreRowModel: getCoreRowModel(),
    // Disable internal sorting: the server controls order.
    manualSorting: true,
    // Disable internal pagination: the server controls pages.
    manualPagination: true,
  });

  return (
    <Table>
      {/* ------------------------------------------------------------------ */}
      {/* Header                                                              */}
      {/* ------------------------------------------------------------------ */}
      <TableHeader>
        {table.getHeaderGroups().map((headerGroup) => (
          <TableRow key={headerGroup.id}>
            {headerGroup.headers.map((header) => (
              <TableHead
                key={header.id}
                style={header.column.columnDef.size !== undefined
                  ? { width: header.column.columnDef.size }
                  : undefined}
              >
                {header.isPlaceholder
                  ? null
                  : flexRender(
                      header.column.columnDef.header,
                      header.getContext(),
                    )}
              </TableHead>
            ))}
          </TableRow>
        ))}
      </TableHeader>

      {/* ------------------------------------------------------------------ */}
      {/* Body                                                               */}
      {/* ------------------------------------------------------------------ */}
      <TableBody>
        {/* Loading state: show skeleton rows while the first fetch runs. */}
        {isLoading ? (
          <SkeletonRows columnCount={columns.length} />
        ) : rows.length === 0 ? (
          /* Empty state: no rows to show — either no jobs or no filter match. */
          <TableRow>
            <TableCell
              colSpan={columns.length}
              className="p-0"
            >
              <EmptyJobsState
                hasFilters={hasFilters}
                onResetFilters={onResetFilters}
              />
            </TableCell>
          </TableRow>
        ) : (
          /* Populated state: one row per job summary. */
          table.getRowModel().rows.map((row) => (
            <TableRow
              key={row.id}
              // Allow the whole row to be clicked to open the result, in
              // addition to the explicit "Open result" action in the dropdown.
              className="cursor-pointer"
              onClick={() => onOpenJob(row.original.id)}
            >
              {row.getVisibleCells().map((cell) => (
                <TableCell
                  key={cell.id}
                  // Stop propagation for the actions column so clicking the
                  // dropdown does not also trigger the row-click navigation.
                  onClick={
                    cell.column.id === "actions"
                      ? (e) => e.stopPropagation()
                      : undefined
                  }
                >
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </TableCell>
              ))}
            </TableRow>
          ))
        )}
      </TableBody>
    </Table>
  );
}

// ---------------------------------------------------------------------------
// Label helpers
// ---------------------------------------------------------------------------

/** Convert a snake_case pipeline_type value to a readable display label. */
function formatPipelineLabel(pipelineType: string): string {
  return pipelineType === "two_stage" ? "Two Stage" : "Single Stage";
}

/** Convert a snake_case model_arch value to a readable display label. */
function formatModelLabel(modelArch: string): string {
  return modelArch === "double_unet" ? "Double UNet" : "UNet";
}
