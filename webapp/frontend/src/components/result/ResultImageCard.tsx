// =============================================================================
// ResultImageCard
// =============================================================================
//
// Renders one completed image result card.  This component assumes the image
// is ready (`is_ready === true`) and contains no placeholder-state branching.
//
// The card shows:
//   - The source filename and dimensions in the header.
//   - Inference timing and detected-tooth count (two-stage only) when present.
//   - A zero-tooth informational note when bounding box data exists but is
//     empty, so the user understands the model ran successfully.
//   - The OverlayCanvas compositing the original radiograph with the mask at
//     the shared opacity level.
//
// The `selectionMode` and `isSelected` props wire into the Phase 3 download
// UX.  When `selectionMode` is false, the selection affordance is hidden and
// the card behaves exactly as it did before.
//
// A forwarded ref of type `OverlayCanvasHandle` is exposed so the parent
// page can call `exportPngBlob()` to capture the current canvas state for
// single-image or batch ZIP export.

import { OverlayCanvas, type OverlayCanvasHandle } from "@/components/OverlayCanvas";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { cn } from "@/lib/utils";
import type { BBoxResponse, ImageResultResponse } from "@/api/types";
import { forwardRef } from "react";
import { Download } from "lucide-react";

export interface ResultImageCardProps {
  result: ImageResultResponse;
  /** The parent job UUID, forwarded to canvas if needed by future export. */
  jobId: string;
  /** Overlay opacity 0–100, shared across all cards on the page. */
  opacity: number;
  /** Whether bounding boxes are drawn on the canvas. */
  showBoundingBoxes: boolean;
  /**
   * True when the page is in multi-select mode.
   * Shows a checkbox on each card so users can pick images to export.
   */
  selectionMode: boolean;
  /** True when this card is currently selected for batch export. */
  isSelected: boolean;
  /** Called with the image result id when the user toggles selection. */
  onToggleSelected: (imageResultId: string) => void;
  /**
   * Called when the user requests a single-image PNG download.
   * The page layer handles the actual export so it can surface feedback.
   */
  onDownloadOne: (imageResultId: string) => Promise<void>;
}

/**
 * Render one completed image result card.
 *
 * A forwarded `OverlayCanvasHandle` ref exposes `exportPngBlob()` so the
 * parent page can capture the current overlay state for download without
 * re-implementing canvas rendering logic.
 *
 * The component is deliberately free of placeholder-state logic; all
 * not-ready paths are handled by `ResultImagePlaceholderCard`.
 */
export const ResultImageCard = forwardRef<OverlayCanvasHandle, ResultImageCardProps>(
  function ResultImageCard(
    {
      result,
      jobId: _jobId,
      opacity,
      showBoundingBoxes,
      selectionMode,
      isSelected,
      onToggleSelected,
      onDownloadOne,
    },
    ref,
  ) {
  // Build a human-readable metadata string for the card subtitle.
  // Each segment is added only when the relevant data is present so the
  // string doesn't show stray "·" separators for missing fields.
  const metaParts: string[] = [
    `${result.original_size.width} × ${result.original_size.height}`,
  ];
  if (result.inference_time_ms !== null) {
    metaParts.push(`${result.inference_time_ms} ms`);
  }
  if (result.bounding_boxes !== null) {
    const count = result.bounding_boxes.length;
    metaParts.push(`${count} ${count === 1 ? "tooth" : "teeth"} detected`);
  }

  // The bounding boxes forwarded to the canvas.  We pass them only when the
  // showBoundingBoxes flag is on so the canvas skips the draw call cheaply.
  const canvasBboxes: BBoxResponse[] | null | undefined = showBoundingBoxes
    ? result.bounding_boxes
    : null;

  return (
    <Card
      className={cn(
        "transition-colors",
        selectionMode && isSelected && "ring-2 ring-primary",
      )}
    >
      <CardHeader className="pb-2">
        <CardTitle className="flex items-start justify-between gap-4 text-sm font-medium">
          {/* Left side: checkbox (selection mode only) + filename */}
          <span className="flex min-w-0 items-center gap-2">
            {selectionMode && (
              <Checkbox
                checked={isSelected}
                onCheckedChange={() => onToggleSelected(result.id)}
                aria-label={`Select ${result.original_filename}`}
                className="shrink-0"
              />
            )}
            <span className="truncate">{result.original_filename}</span>
          </span>

          {/* Right side: metadata string + single-image download icon button */}
          <span className="flex shrink-0 items-center gap-2">
            <span className="text-xs font-normal text-muted-foreground">
              {metaParts.join(" · ")}
            </span>
            <button
              type="button"
              onClick={() => void onDownloadOne(result.id)}
              className="rounded p-1 text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              aria-label={`Download ${result.original_filename}`}
            >
              <Download className="h-4 w-4" aria-hidden="true" />
            </button>
          </span>
        </CardTitle>

        {/* Informational note when tooth detection ran but found nothing. */}
        {result.bounding_boxes !== null && result.bounding_boxes.length === 0 && (
          <p className="text-xs text-muted-foreground">
            No teeth detected in this image.
          </p>
        )}
      </CardHeader>

      <CardContent className="pt-0">
        <OverlayCanvas
          ref={ref}
          imageResultId={result.id}
          opacity={opacity}
          boundingBoxes={canvasBboxes}
          showBoundingBoxes={showBoundingBoxes}
          originalSize={result.original_size}
        />
      </CardContent>
    </Card>
  );
});

