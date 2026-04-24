// =============================================================================
// JobRowActions
// =============================================================================
//
// Row-level action menu for the History table.  Presents two actions via a
// compact dropdown:
//
//   • Open result  — navigate to /result/:jobId
//   • Rerun        — trigger the server-side rerun mutation
//
// The dropdown pattern keeps the table rows visually clean: a single "…"
// trigger replaces two inline buttons that would otherwise crowd narrow
// viewport widths or multi-image rows.
//
// The rerun mutation is invoked here so the loading state (spinning icon) can
// be tied directly to the trigger button without threading mutation state
// through the full table hierarchy.

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { ExternalLink, MoreHorizontal, RotateCcw } from "lucide-react";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface JobRowActionsProps {
  /** The job UUID this row represents. */
  jobId: string;

  /** True while a rerun mutation is in flight for this specific job. */
  isRerunPending: boolean;

  /** Called when the user selects "Open Result". */
  onOpen: (jobId: string) => void;

  /** Called when the user selects "Rerun". */
  onRerun: (jobId: string) => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * Render a "⋯" dropdown button with row-level actions for a single history
 * table row.  Keeps the trigger accessible via keyboard and screen reader.
 */
export function JobRowActions({
  jobId,
  isRerunPending,
  onOpen,
  onRerun,
}: JobRowActionsProps) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          aria-label={`Actions for job ${jobId}`}
          // Prevent clicks from propagating to a potential row-click handler
          // so the dropdown stays the sole interaction target.
          onClick={(e) => e.stopPropagation()}
        >
          <MoreHorizontal className="h-4 w-4" />
        </Button>
      </DropdownMenuTrigger>

      <DropdownMenuContent align="end" className="w-40">
        {/* Open result detail */}
        <DropdownMenuItem
          onSelect={() => onOpen(jobId)}
        >
          <ExternalLink className="mr-2 h-4 w-4" />
          Open result
        </DropdownMenuItem>

        <DropdownMenuSeparator />

        {/* Server-side rerun */}
        <DropdownMenuItem
          disabled={isRerunPending}
          onSelect={() => onRerun(jobId)}
        >
          <RotateCcw
            className={`mr-2 h-4 w-4${isRerunPending ? " animate-spin" : ""}`}
          />
          Rerun
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
