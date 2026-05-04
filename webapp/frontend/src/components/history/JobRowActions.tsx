// =============================================================================
// JobRowActions
// =============================================================================
//
// Row-level action menu for the History table.  Presents three actions via a
// compact dropdown:
//
//   • Open result  — navigate to /result/:jobId
//   • Rerun        — trigger the server-side rerun mutation
//   • Delete       — permanently remove the job (with confirmation dialog)
//
// The dropdown pattern keeps the table rows visually clean: a single "…"
// trigger replaces multiple inline buttons that would otherwise crowd narrow
// viewport widths or multi-image rows.
//
// The delete confirmation uses an AlertDialog so the destructive action
// cannot be triggered by an accidental single click.

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { ExternalLink, MoreHorizontal, RotateCcw, Trash2 } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

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

  /** Called when the user confirms deletion. */
  onDelete: (jobId: string) => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * Render a "⋯" dropdown button with row-level actions for a single history
 * table row.  Keeps the trigger accessible via keyboard and screen reader.
 *
 * The AlertDialog for deletion confirmation is co-located here so all the
 * state related to a single-row destructive action stays in one file.
 */
export function JobRowActions({
  jobId,
  isRerunPending,
  onOpen,
  onRerun,
  onDelete,
}: JobRowActionsProps) {
  // Controls the delete confirmation dialog independently of the dropdown so
  // the dialog stays open even after the dropdown closes.
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const { t } = useTranslation();

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            aria-label={`Actions for job ${jobId}`}
            // Prevent clicks from propagating to the row-click handler so the
            // dropdown stays the sole interaction target.
            onClick={(e) => e.stopPropagation()}
          >
            <MoreHorizontal className="h-4 w-4" />
          </Button>
        </DropdownMenuTrigger>

        <DropdownMenuContent align="end" className="w-40">
          {/* Open result detail */}
          <DropdownMenuItem onSelect={() => onOpen(jobId)}>
            <ExternalLink className="mr-2 h-4 w-4" />
            {t("jobRow.openResult")}
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
            {t("jobRow.rerun")}
          </DropdownMenuItem>

          <DropdownMenuSeparator />

          {/* Delete — opens confirmation dialog; does not delete immediately */}
          <DropdownMenuItem
            className="text-destructive focus:text-destructive"
            onSelect={(e) => {
              // Prevent the dropdown from stealing focus before the dialog mounts.
              e.preventDefault();
              setDeleteDialogOpen(true);
            }}
          >
            <Trash2 className="mr-2 h-4 w-4" />
            {t("jobRow.delete")}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      {/* ------------------------------------------------------------------ */}
      {/* Delete confirmation dialog                                          */}
      {/* ------------------------------------------------------------------ */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent onClick={(e) => e.stopPropagation()}>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("jobRow.deleteConfirmTitle")}</AlertDialogTitle>
            <AlertDialogDescription>
              {t("jobRow.deleteConfirmDescription")}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("jobRow.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => {
                setDeleteDialogOpen(false);
                onDelete(jobId);
              }}
            >
              {t("jobRow.delete")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}

