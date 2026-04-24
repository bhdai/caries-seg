/**
 * ResultPage — Step 3 of the inference workflow.
 *
 * Behaviour:
 *   - On mount: fetches GET /api/jobs/:id via the shared useJobDetailQuery hook.
 *   - While status is "pending" or "processing": the hook polls every 2 s
 *     automatically and stops when the job reaches a terminal state.
 *   - Renders image cards progressively as they become ready (`is_ready`),
 *     showing size-stable placeholder cards for images still being processed.
 *   - On partial failure (job failed after some images completed): shows both
 *     ready cards for completed images and failed placeholders for the rest.
 *
 * Shared overlay state (opacity, bounding-box visibility) is derived from
 * local state and passed down to every ready card so all canvases update
 * together when the slider is moved.
 *
 * Selection state (`selectionMode`, `selectedIds`) is initialised here in
 * preparation for the Phase 3 export toolbar.  It is inert in this phase
 * because no toolbar is rendered yet.
 */
import { JobStatusChip } from "@/components/jobs/JobStatusChip";
import { OpacitySlider } from "@/components/OpacitySlider";
import { ResultImageCard } from "@/components/result/ResultImageCard";
import {
  ResultImagePlaceholderCard,
  type PlaceholderPhase,
} from "@/components/result/ResultImagePlaceholderCard";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useJobDetailQuery } from "@/hooks/useJobDetailQuery";
import { useStartNewJob } from "@/hooks/useStartNewJob";
import { useState } from "react";
import { useParams } from "react-router-dom";

const PIPELINE_LABELS: Record<string, string> = {
  single_stage: "Single Stage",
  two_stage: "Two Stage",
};
const ARCH_LABELS: Record<string, string> = {
  unet: "UNet",
  double_unet: "Double-UNet",
};

export default function ResultPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const startNewJob = useStartNewJob();

  const { data: job, error } = useJobDetailQuery(jobId);

  const fetchError =
    error instanceof Error ? error.message : error ? "Failed to fetch job." : null;

  // ---------------------------------------------------------------------------
  // Shared overlay controls — passed to every ready card so changes propagate
  // to all visible canvases simultaneously.
  // ---------------------------------------------------------------------------
  const [opacity, setOpacity] = useState(60);
  const [showBoundingBoxes, setShowBoundingBoxes] = useState(true);

  // Show the bounding-box toggle only for two-stage jobs because single-stage
  // jobs never produce bounding-box data.
  const showBoundingBoxToggle = job?.pipeline_type === "two_stage";

  // ---------------------------------------------------------------------------
  // Selection state — inert in Phase 2, wired in Phase 3 when the export
  // toolbar is added.  Declared here so the card props are already plumbed.
  // ---------------------------------------------------------------------------
  const [selectionMode] = useState(false);
  const [selectedIds] = useState<Set<string>>(new Set());

  // ---------------------------------------------------------------------------
  // Per-image readiness classification
  //
  // Derive the placeholder phase for not-ready images from the overall job
  // status so the correct visual state is shown for each image:
  //   - pending / processing job → the image is still being worked on.
  //   - failed job              → this image will never produce output.
  //   - completed job + not-ready → invariant violation; show unavailable.
  // ---------------------------------------------------------------------------
  function derivePlaceholderPhase(jobStatus: string): PlaceholderPhase {
    if (jobStatus === "failed") return "failed";
    if (jobStatus === "processing") return "processing";
    // "pending" and the unexpected "completed-but-not-ready" case both
    // resolve to "pending" so the spinner is shown rather than a hard error.
    return "pending";
  }

  return (
    <div className="space-y-6">
      {/* ------------------------------------------------------------------ */}
      {/* Page header — always rendered, even during loading                  */}
      {/* ------------------------------------------------------------------ */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Results</h1>
          {job && (
            <p className="text-muted-foreground mt-1 text-sm">
              {PIPELINE_LABELS[job.pipeline_type] ?? job.pipeline_type} ·{" "}
              {ARCH_LABELS[job.model_arch] ?? job.model_arch}
            </p>
          )}
        </div>
        <div className="flex items-center gap-3">
          {job && <JobStatusChip status={job.status} />}
          <Button variant="outline" size="sm" onClick={startNewJob}>
            New Job
          </Button>
        </div>
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Fetch error — shown when the network request itself fails            */}
      {/* ------------------------------------------------------------------ */}
      {fetchError && (
        <Alert variant="destructive">
          <AlertDescription>{fetchError}</AlertDescription>
        </Alert>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Inference failure banner — shown alongside any ready cards so the   */}
      {/* user understands the job stopped early.                             */}
      {/* ------------------------------------------------------------------ */}
      {job?.status === "failed" && job.error_message && (
        <Alert variant="destructive">
          <AlertDescription>
            <strong>Inference failed:</strong> {job.error_message}
          </AlertDescription>
        </Alert>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Initial loading state — only while no job data exists yet           */}
      {/* ------------------------------------------------------------------ */}
      {!job && !fetchError && (
        <Card>
          <CardContent className="py-12 flex flex-col items-center gap-4">
            <div className="h-10 w-10 animate-spin rounded-full border-4 border-primary border-t-transparent" />
            <p className="text-muted-foreground text-sm">Loading job…</p>
          </CardContent>
        </Card>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Shared overlay controls — visible as soon as job data is available  */}
      {/* and there is at least one image result to show controls for.        */}
      {/* ------------------------------------------------------------------ */}
      {job && job.image_results.length > 0 && (
        <div className="flex flex-wrap items-center gap-3">
          <OpacitySlider value={opacity} onChange={setOpacity} />
          {showBoundingBoxToggle && (
            <div className="flex items-center gap-3 rounded-md border px-3 py-2">
              <Switch
                id="show-bounding-boxes"
                checked={showBoundingBoxes}
                onCheckedChange={setShowBoundingBoxes}
                aria-label="Show bounding boxes"
              />
              <Label htmlFor="show-bounding-boxes">Show bounding boxes</Label>
            </div>
          )}
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Per-image result cards — rendered in original server order.         */}
      {/* Ready images render full overlay cards; not-ready images render a   */}
      {/* size-stable placeholder so the page height remains predictable.     */}
      {/* ------------------------------------------------------------------ */}
      {job && job.image_results.length > 0 && (
        <div className="space-y-6">
          {job.image_results.map((result) => {
            if (result.is_ready) {
              return (
                <ResultImageCard
                  key={result.id}
                  result={result}
                  jobId={job.id}
                  opacity={opacity}
                  showBoundingBoxes={showBoundingBoxToggle && showBoundingBoxes}
                  selectionMode={selectionMode}
                  isSelected={selectedIds.has(result.id)}
                  onToggleSelected={() => {
                    // Selection toggling is wired in Phase 3.
                    // The callback is defined here to satisfy the prop
                    // contract and avoid a no-op prop warning.
                  }}
                />
              );
            }

            // Not ready — determine which placeholder phase to show.
            return (
              <ResultImagePlaceholderCard
                key={result.id}
                filename={result.original_filename}
                originalSize={result.original_size}
                phase={derivePlaceholderPhase(job.status)}
                errorMessage={
                  job.status === "failed" ? job.error_message : null
                }
              />
            );
          })}
        </div>
      )}
    </div>
  );
}
