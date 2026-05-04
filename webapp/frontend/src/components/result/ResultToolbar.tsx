// =============================================================================
// ResultToolbar
// =============================================================================
//
// Shared action bar rendered above the result image cards.
//
// The toolbar is responsible for:
//   - Displaying ready/total image counts so the user knows how far along
//     the job is before all images are available.
//   - Toggling selection mode so individual cards can be checked.
//   - Selecting all currently ready images in one click.
//   - Clearing the current selection.
//   - Triggering single-archive ("download all ready") and selective
//     ("download selected") exports.
//
// Disabled states are derived from the ready count and selection state so
// the toolbar never offers an action that cannot produce output.  A progress
// indicator is shown while a batch export is in flight.

import { Button } from "@/components/ui/button";
import { CheckSquare, Download, Loader2, Square, X } from "lucide-react";
import { useTranslation } from "react-i18next";

// =============================================================================
// Props
// =============================================================================

export interface ResultToolbarProps {
  /** Number of images whose `is_ready` flag is true. */
  readyCount: number;
  /** Total number of images in the job (ready + not-ready). */
  totalCount: number;
  /**
   * IDs of image results currently selected by the user.
   * Must only contain IDs of ready images.
   */
  selectedReadyIds: string[];
  /** Whether the page is in multi-select mode. */
  isSelectionMode: boolean;
  /** True while a batch export ZIP is being built. */
  isBatchExporting: boolean;
  /** Toggle selection mode on or off. */
  onToggleSelectionMode: () => void;
  /** Select every currently ready image. */
  onSelectAllReady: () => void;
  /** Clear the current selection without leaving selection mode. */
  onClearSelection: () => void;
  /** Download all ready images as a ZIP. */
  onDownloadAllReady: () => Promise<void>;
  /** Download only the currently selected ready images as a ZIP. */
  onDownloadSelected: () => Promise<void>;
}

// =============================================================================
// Component
// =============================================================================

/**
 * Render the shared action bar above result cards.
 *
 * The toolbar is only mounted when the result page has at least one image
 * (see ResultPage usage), so internal guards assume `totalCount >= 1`.
 */
export function ResultToolbar({
  readyCount,
  totalCount,
  selectedReadyIds,
  isSelectionMode,
  isBatchExporting,
  onToggleSelectionMode,
  onSelectAllReady,
  onClearSelection,
  onDownloadAllReady,
  onDownloadSelected,
}: ResultToolbarProps) {
  const selectedCount = selectedReadyIds.length;
  const { t } = useTranslation();

  // Progress copy shown to the right of the action buttons.
  const progressCopy = t("resultToolbar.progress", { ready: readyCount, total: totalCount });

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-md border bg-muted/20 px-3 py-2">
      {/* ------------------------------------------------------------------ */}
      {/* Progress summary                                                    */}
      {/* ------------------------------------------------------------------ */}
      <span className="text-xs text-muted-foreground mr-auto">{progressCopy}</span>

      {/* ------------------------------------------------------------------ */}
      {/* Selection-mode controls                                             */}
      {/* Shown only while selection mode is active.                          */}
      {/* ------------------------------------------------------------------ */}
      {isSelectionMode && (
        <>
          <Button
            variant="ghost"
            size="sm"
            onClick={onSelectAllReady}
            disabled={readyCount === 0 || selectedCount === readyCount || isBatchExporting}
          >
            <CheckSquare className="mr-1.5 h-4 w-4" aria-hidden="true" />
            {t("resultToolbar.selectAll")}
          </Button>

          <Button
            variant="ghost"
            size="sm"
            onClick={onClearSelection}
            disabled={selectedCount === 0 || isBatchExporting}
          >
            <X className="mr-1.5 h-4 w-4" aria-hidden="true" />
            {t("resultToolbar.clear")}
          </Button>
        </>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Selection mode toggle                                               */}
      {/* ------------------------------------------------------------------ */}
      <Button
        variant={isSelectionMode ? "secondary" : "outline"}
        size="sm"
        onClick={onToggleSelectionMode}
        disabled={isBatchExporting}
        aria-pressed={isSelectionMode}
      >
        <Square className="mr-1.5 h-4 w-4" aria-hidden="true" />
        {isSelectionMode ? t("resultToolbar.cancelSelection") : t("resultToolbar.select")}
      </Button>

      {/* ------------------------------------------------------------------ */}
      {/* Download selected                                                   */}
      {/* Only shown while selection mode is active.                          */}
      {/* ------------------------------------------------------------------ */}
      {isSelectionMode && (
        <Button
          variant="outline"
          size="sm"
          onClick={onDownloadSelected}
          disabled={selectedCount === 0 || isBatchExporting}
          aria-label={t("resultToolbar.downloadSelectedAria", { n: selectedCount })}
        >
          {isBatchExporting ? (
            <Loader2 className="mr-1.5 h-4 w-4 animate-spin" aria-hidden="true" />
          ) : (
            <Download className="mr-1.5 h-4 w-4" aria-hidden="true" />
          )}
          {t("resultToolbar.downloadSelected", { n: selectedCount })}
        </Button>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Download all ready                                                  */}
      {/* Always visible so users can export without entering selection mode. */}
      {/* ------------------------------------------------------------------ */}
      <Button
        size="sm"
        onClick={onDownloadAllReady}
        disabled={readyCount === 0 || isBatchExporting}
        aria-label={t("resultToolbar.downloadAllReadyAria", { n: readyCount })}
      >
        {isBatchExporting ? (
          <Loader2 className="mr-1.5 h-4 w-4 animate-spin" aria-hidden="true" />
        ) : (
          <Download className="mr-1.5 h-4 w-4" aria-hidden="true" />
        )}
        {isSelectionMode ? t("resultToolbar.downloadAllReady") : t("resultToolbar.downloadAll")}
      </Button>
    </div>
  );
}
