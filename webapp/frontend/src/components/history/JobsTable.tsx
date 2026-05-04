// =============================================================================
// JobsTable
// =============================================================================
//
// Server-driven history table using TanStack Table v8 column definitions and
// shadcn table primitives.
//
// Column layout (left → right):
//   Select | Status | File | Pipeline · Model | Images | Last Activity | Actions
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
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
import { JobStatusChip } from "@/components/jobs/JobStatusChip";
import { JobRowActions } from "@/components/history/JobRowActions";
import { EmptyJobsState } from "@/components/history/EmptyJobsState";
import { formatRelativeTime, formatAbsoluteTime } from "@/lib/time";
import type { JobSummary } from "@/api/types";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";

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

  /** The set of currently selected job IDs. */
  selectedIds: Set<string>;

  /** Called when the user resets filters from the empty state. */
  onResetFilters: () => void;

  /** Called when the user selects "Open result" for a row. */
  onOpenJob: (jobId: string) => void;

  /** Called when the user selects "Rerun" for a row. */
  onRerun: (jobId: string) => void;

  /** Called when the user confirms deletion of a single row. */
  onDeleteOne: (jobId: string) => void;

  /** Called when the user selects "Link to Patient" or "Change Patient". */
  onLinkPatient: (jobId: string) => void;

  /**
   * Called when the user confirms "Unlink Patient" for a row.
   * The caller is responsible for firing the patchJob mutation.
   */
  onUnlinkPatient: (jobId: string) => void;

  /** Called when the user toggles the row checkbox. */
  onToggleSelect: (jobId: string) => void;

  /** Called when the user clicks the header "select all" checkbox. */
  onSelectAll: (allIds: string[]) => void;
}

// ---------------------------------------------------------------------------
// Column definitions
// ---------------------------------------------------------------------------

// Column definitions are created once outside the component so they are not
// re-instantiated on every render.

function buildColumns(
  rows: JobSummary[],
  selectedIds: Set<string>,
  rerunPendingJobId: string | undefined,
  onOpenJob: (id: string) => void,
  onRerun: (id: string) => void,
  onDeleteOne: (id: string) => void,
  onToggleSelect: (id: string) => void,
  onSelectAll: (allIds: string[]) => void,
  onLinkPatient: (id: string) => void,
  onUnlinkPatient: (id: string) => void,
  t: TFunction,
) {
  const allVisible = rows.map((r) => r.id);
  const allSelected =
    allVisible.length > 0 && allVisible.every((id) => selectedIds.has(id));
  const someSelected = !allSelected && allVisible.some((id) => selectedIds.has(id));

  return [
    // Selection checkbox — far-left column
    col.display({
      id: "select",
      // Header checkbox selects / deselects all visible rows on this page.
      header: () => (
        <Checkbox
          checked={allSelected ? true : someSelected ? "indeterminate" : false}
          onCheckedChange={() => onSelectAll(allVisible)}
          aria-label="Select all jobs on this page"
          onClick={(e) => e.stopPropagation()}
        />
      ),
      cell: ({ row }) => (
        <Checkbox
          checked={selectedIds.has(row.original.id)}
          onCheckedChange={() => onToggleSelect(row.original.id)}
          aria-label={`Select job ${row.original.id}`}
          onClick={(e) => e.stopPropagation()}
        />
      ),
      size: 40,
    }),

    // Status badge
    col.accessor("status", {
      header: t("jobsTable.colStatus"),
      cell: (info) => <JobStatusChip status={info.getValue()} />,
      size: 110,
    }),

    // Primary filename + overflow preview (e.g. "+ 2 more")
    col.accessor("primary_filename", {
      header: t("jobsTable.colFile"),
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
                {t("jobsTable.moreFiles", { n: extra })}
              </p>
            )}
          </div>
        );
      },
    }),
    // Patient link — name or dash
    col.display({
      id: "patient",
      header: t("jobsTable.colPatient"),
      cell: ({ row }) => {
        const job = row.original;
        if (job.patient_id && job.patient_name) {
          return (
            <Link
              to={`/patients/${job.patient_id}`}
              className="text-sm hover:underline underline-offset-4 font-medium"
              onClick={(e) => e.stopPropagation()}
            >
              {job.patient_name}
            </Link>
          );
        }
        return <span className="text-sm text-muted-foreground">—</span>;
      },
      size: 140,
    }),
    // Pipeline + model arch in a compact two-line cell
    col.display({
      id: "pipeline_model",
      header: t("jobsTable.colPipelineModel"),
      cell: ({ row }) => {
        const job = row.original;
        return (
          <div className="text-sm">
            <span>{job.pipeline_type === "two_stage" ? t("job.pipeline.two") : t("job.pipeline.single")}</span>
            <span className="text-muted-foreground"> · </span>
            <span className="text-muted-foreground">{job.model_arch === "double_unet" ? t("job.model.doubleUnet") : t("job.model.unet")}</span>
          </div>
        );
      },
      size: 160,
    }),

    // Image count
    col.accessor("image_count", {
      header: t("jobsTable.colImages"),
      cell: (info) => (
        <span className="text-sm tabular-nums">{t("job.images", { count: info.getValue() })}</span>
      ),
      size: 70,
    }),

    // Relative last-activity time with absolute date as tooltip
    col.accessor("last_activity_at", {
      header: t("jobsTable.colLastActivity"),
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
          patientId={row.original.patient_id}
          patientName={row.original.patient_name}
          onOpen={onOpenJob}
          onRerun={onRerun}
          onDelete={onDeleteOne}
          onLinkPatient={onLinkPatient}
          onChangePatient={onLinkPatient}
          onUnlinkPatient={onUnlinkPatient}
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
  selectedIds,
  onResetFilters,
  onOpenJob,
  onRerun,
  onDeleteOne,
  onLinkPatient,
  onUnlinkPatient,
  onToggleSelect,
  onSelectAll,
}: JobsTableProps) {
  const { t } = useTranslation();
  // Build column definitions with access to current action callbacks.
  const columns = buildColumns(
    rows,
    selectedIds,
    rerunPendingJobId,
    onOpenJob,
    onRerun,
    onDeleteOne,
    onToggleSelect,
    onSelectAll,
    onLinkPatient,
    onUnlinkPatient,
    t,
  );

  const table = useReactTable({
    data: rows,
    columns,
    getCoreRowModel: getCoreRowModel(),
    // Disable internal sorting: the server controls order.
    manualSorting: true,
    // Disable internal pagination: the server controls pages.
    manualPagination: true,
  });

  // The set of column IDs that should stop row-click propagation.
  const NON_NAVIGABLE_COLUMNS = new Set(["select", "actions"]);

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
              data-selected={selectedIds.has(row.original.id) || undefined}
            >
              {row.getVisibleCells().map((cell) => (
                <TableCell
                  key={cell.id}
                  // Stop propagation for select and actions columns so clicks
                  // on checkbox / dropdown do not trigger row navigation.
                  onClick={
                    NON_NAVIGABLE_COLUMNS.has(cell.column.id)
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
// Label helpers — kept for reference; pipeline/model labels now use t() inline.
// ---------------------------------------------------------------------------

