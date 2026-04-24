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
 * Shared overlay state (opacity, bounding-box visibility) is passed down to
 * every ready card so all canvases update together when the slider is moved.
 *
 * Export flow:
 *   - Each ready ResultImageCard exposes an OverlayCanvasHandle ref that can
 *     produce the current canvas state as a PNG Blob.
 *   - The ResultToolbar surfaces selection mode, "download selected", and
 *     "download all ready" actions.
 *   - Single-image downloads use the per-card "Download" button which calls
 *     exportSingleResultPng directly.
 *   - Batch downloads delegate to exportReadyResultsZip and show a partial-
 *     success message when some images failed to export.
 */
import { JobStatusChip } from "@/components/jobs/JobStatusChip";
import { OpacitySlider } from "@/components/OpacitySlider";
import { type OverlayCanvasHandle } from "@/components/OverlayCanvas";
import { ResultImageCard } from "@/components/result/ResultImageCard";
import {
  ResultImagePlaceholderCard,
  type PlaceholderPhase,
} from "@/components/result/ResultImagePlaceholderCard";
import { ResultToolbar } from "@/components/result/ResultToolbar";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useJobDetailQuery } from "@/hooks/useJobDetailQuery";
import { useStartNewJob } from "@/hooks/useStartNewJob";
import {
  exportReadyResultsZip,
  exportSingleResultPng,
} from "@/lib/resultExport";
import { useCallback, useRef, useState } from "react";
import { toast } from "sonner";
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
  // Selection state — drives the ResultToolbar and per-card checkboxes.
  // ---------------------------------------------------------------------------
  const [selectionMode, setSelectionMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [isBatchExporting, setIsBatchExporting] = useState(false);

  const toggleSelectionMode = useCallback(() => {
    setSelectionMode((prev) => {
      if (prev) setSelectedIds(new Set());
      return !prev;
    });
  }, []);

  const toggleSelected = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  const selectAllReady = useCallback(() => {
    const readyIds = job?.image_results
      .filter((r) => r.is_ready)
      .map((r) => r.id) ?? [];
    setSelectedIds(new Set(readyIds));
  }, [job]);

  const clearSelection = useCallback(() => {
    setSelectedIds(new Set());
  }, []);

  // ---------------------------------------------------------------------------
  // Canvas refs — keyed by image-result ID so the export handlers can locate
  // each card's OverlayCanvas by its result ID.
  // ---------------------------------------------------------------------------
  const canvasRefs = useRef<Map<string, OverlayCanvasHandle>>(new Map());

  const setCanvasRef = useCallback(
    (resultId: string) => (handle: OverlayCanvasHandle | null) => {
      if (handle) {
        canvasRefs.current.set(resultId, handle);
      } else {
        canvasRefs.current.delete(resultId);
      }
    },
    [],
  );

  // ---------------------------------------------------------------------------
  // Export handlers
  // ---------------------------------------------------------------------------

  // Single-image download: export the canvas for the given result ID.
  const handleDownloadOne = useCallback(
    async (resultId: string) => {
      const handle = canvasRefs.current.get(resultId);
      if (!handle) {
        toast.error("Could not export image — canvas not available.");
        return;
      }
      const result = job?.image_results.find((r) => r.id === resultId);
      const filename = result?.original_filename ?? "result";
      try {
        await exportSingleResultPng(filename, () => handle.exportPngBlob());
      } catch {
        toast.error(`Failed to export "${filename}".`);
      }
    },
    [job],
  );

  // Build the export item list for the given result IDs, filtering to those
  // that have a mounted canvas handle.
  const buildExportItems = useCallback(
    (resultIds: string[]) => {
      return resultIds.flatMap((id) => {
        const handle = canvasRefs.current.get(id);
        const result = job?.image_results.find((r) => r.id === id);
        if (!handle || !result) return [];
        return [
          {
            imageResultId: id,
            originalFilename: result.original_filename,
            exportCanvas: () => handle.exportPngBlob(),
          },
        ];
      });
    },
    [job],
  );

  // Batch download of all ready images.
  const handleDownloadAllReady = useCallback(async () => {
    if (!job) return;
    const readyIds = job.image_results.filter((r) => r.is_ready).map((r) => r.id);
    const items = buildExportItems(readyIds);
    if (items.length === 0) {
      toast.error("No ready images to download.");
      return;
    }
    setIsBatchExporting(true);
    try {
      const outcome = await exportReadyResultsZip(job.id, items);
      if (outcome.failedItems.length > 0) {
        toast.warning(
          `Downloaded ${outcome.succeededCount} image(s). ` +
            `${outcome.failedItems.length} could not be exported.`,
        );
      } else {
        toast.success(`Downloaded ${outcome.succeededCount} image(s) as ZIP.`);
      }
    } catch {
      toast.error("Batch export failed — no images were downloaded.");
    } finally {
      setIsBatchExporting(false);
    }
  }, [job, buildExportItems]);

  // Batch download of selected images only.
  const handleDownloadSelected = useCallback(async () => {
    if (!job) return;
    const items = buildExportItems([...selectedIds]);
    if (items.length === 0) {
      toast.error("No selected images are available for export.");
      return;
    }
    setIsBatchExporting(true);
    try {
      const outcome = await exportReadyResultsZip(job.id, items);
      if (outcome.failedItems.length > 0) {
        toast.warning(
          `Downloaded ${outcome.succeededCount} of ${items.length} selected image(s). ` +
            `${outcome.failedItems.length} could not be exported.`,
        );
      } else {
        toast.success(
          `Downloaded ${outcome.succeededCount} selected image(s) as ZIP.`,
        );
      }
    } catch {
      toast.error("Batch export failed — no images were downloaded.");
    } finally {
      setIsBatchExporting(false);
    }
  }, [job, buildExportItems, selectedIds]);

  // ---------------------------------------------------------------------------
  // Per-image readiness classification
  // ---------------------------------------------------------------------------
  function derivePlaceholderPhase(jobStatus: string): PlaceholderPhase {
    if (jobStatus === "failed") return "failed";
    if (jobStatus === "processing") return "processing";
    return "pending";
  }

  // Counts used by the toolbar.
  const readyCount = job?.image_results.filter((r) => r.is_ready).length ?? 0;
  const totalCount = job?.image_results.length ?? 0;

  // The toolbar is shown whenever there are images so the user can begin
  // selecting / downloading as soon as the first result arrives.
  const showToolbar = totalCount > 0;

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
      {/* Result toolbar — selection mode, download actions, ready count      */}
      {/* ------------------------------------------------------------------ */}
      {showToolbar && job && (
        <ResultToolbar
          readyCount={readyCount}
          totalCount={totalCount}
          selectedReadyIds={[...selectedIds]}
          isSelectionMode={selectionMode}
          isBatchExporting={isBatchExporting}
          onToggleSelectionMode={toggleSelectionMode}
          onSelectAllReady={selectAllReady}
          onClearSelection={clearSelection}
          onDownloadAllReady={handleDownloadAllReady}
          onDownloadSelected={handleDownloadSelected}
        />
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
                  ref={setCanvasRef(result.id)}
                  result={result}
                  jobId={job.id}
                  opacity={opacity}
                  showBoundingBoxes={showBoundingBoxToggle && showBoundingBoxes}
                  selectionMode={selectionMode}
                  isSelected={selectedIds.has(result.id)}
                  onToggleSelected={toggleSelected}
                  onDownloadOne={handleDownloadOne}
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
