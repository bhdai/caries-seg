// =============================================================================
// ResultImagePlaceholderCard
// =============================================================================
//
// Renders the non-ready state for one image result.  This component is used
// when `is_ready === false` and is responsible for both the in-progress and
// the failed-not-ready states.
//
// Layout goals:
//   - Preserve roughly the same card footprint as ResultImageCard so the
//     page doesn't jump when a card transitions from placeholder to ready.
//   - Communicate the current state clearly without alarming the user when
//     the job is still running.
//
// The `phase` prop distinguishes three distinct states:
//   - "pending"    — job is queued, no inference has started for this image.
//   - "processing" — inference is actively running for this image or the job.
//   - "failed"     — the overall job reached a failed terminal state before
//                    this image produced output (partial completion scenario).

import { AlertCircle, Loader2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useTranslation } from "react-i18next";

export type PlaceholderPhase = "pending" | "processing" | "failed";

export interface ResultImagePlaceholderCardProps {
  /** Original source filename shown in the card header. */
  filename: string;
  /** Natural dimensions of the source image for aspect-ratio stability. */
  originalSize: { width: number; height: number };
  /** Which non-ready state to visualise. */
  phase: PlaceholderPhase;
  /**
   * Optional error message surfaced alongside the failed state.
   * Null is acceptable; the card will show generic failure copy instead.
   */
  errorMessage: string | null;
}

// Human-readable labels per phase.
const PHASE_LABELS: Record<PlaceholderPhase, string> = {
  pending: "Waiting to start…",
  processing: "Running inference…",
  failed: "Output unavailable",
};

// Secondary description shown inside the placeholder body.
const PHASE_DESCRIPTIONS: Record<PlaceholderPhase, string> = {
  pending: "This image is queued and will be processed shortly.",
  processing: "Inference is running. The result will appear here once complete.",
  failed: "Inference did not produce output for this image.",
};

/**
 * Render a size-stable placeholder card for a not-ready image result.
 *
 * The card matches the outer dimensions of a completed result card so the
 * page layout does not reflow when results become available during polling.
 */
export function ResultImagePlaceholderCard({
  filename,
  originalSize,
  phase,
  errorMessage,
}: ResultImagePlaceholderCardProps) {
  const { t } = useTranslation();
  // Mirror the aspect-ratio logic used by OverlayCanvas so the placeholder
  // occupies the same vertical space as the eventual ready card.
  const aspectRatio =
    originalSize.width > 0 && originalSize.height > 0
      ? `${originalSize.width} / ${originalSize.height}`
      : "16 / 9";

  const isFailed = phase === "failed";

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-start justify-between gap-4 text-sm font-medium">
          <span className="truncate">{filename}</span>
          <span className="shrink-0 text-xs font-normal text-muted-foreground">
            {originalSize.width} × {originalSize.height}
          </span>
        </CardTitle>
      </CardHeader>

      <CardContent className="pt-0">
        {/* Placeholder body — same aspect ratio as the canvas it will replace */}
        <div
          className="w-full rounded-md border bg-muted/30 flex flex-col items-center justify-center gap-3"
          style={{ aspectRatio }}
        >
          {isFailed ? (
            <>
              <AlertCircle
                className="h-8 w-8 text-destructive"
                aria-hidden="true"
              />
              <div className="text-center space-y-1 px-4">
                <p className="text-sm font-medium text-destructive">
                  {t("imagePlaceholder.failed.label")}
                </p>
                <p className="text-xs text-muted-foreground">
                  {/* Prefer the job-level error message when available, fall
                      back to generic copy. */}
                  {errorMessage ?? t("imagePlaceholder.failed.description")}
                </p>
              </div>
            </>
          ) : (
            <>
              <Loader2
                className="h-8 w-8 animate-spin text-muted-foreground"
                aria-hidden="true"
              />
              <div className="text-center space-y-1 px-4">
                <p className="text-sm font-medium text-muted-foreground">
                  {t(`imagePlaceholder.${phase}.label` as Parameters<typeof t>[0])}
                </p>
                <p className="text-xs text-muted-foreground">
                  {t(`imagePlaceholder.${phase}.description` as Parameters<typeof t>[0])}
                </p>
              </div>
            </>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
