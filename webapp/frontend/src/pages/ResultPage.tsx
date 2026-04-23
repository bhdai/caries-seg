/**
 * ResultPage — Step 3 of the inference workflow.
 *
 * Behaviour:
 *   - On mount: fetches GET /api/jobs/:id.
 *   - While status is "pending" or "processing": polls every 2 s.
 *   - On "completed": renders one OverlayCanvas per image result plus a
 *     shared OpacitySlider.
 *   - On "failed": renders the error_message in a destructive Alert.
 *
 * The shared opacity state (0–100, default 60) is passed to every canvas
 *  so all overlays update together when the slider is moved.
 */
import { getJob, type JobResponse } from "@/api/client";
import { JobStatusBadge } from "@/components/JobStatusBadge";
import { OpacitySlider } from "@/components/OpacitySlider";
import { OverlayCanvas } from "@/components/OverlayCanvas";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

const POLL_INTERVAL_MS = 2000;

export default function ResultPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const navigate = useNavigate();

  const [job, setJob] = useState<JobResponse | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [opacity, setOpacity] = useState(60);
  const [showBoundingBoxes, setShowBoundingBoxes] = useState(true);

  // Store interval id in a ref so cleanup is always precise.
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  function stopPolling() {
    if (intervalRef.current !== null) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }

  useEffect(() => {
    if (!jobId) return;

    let cancelled = false;

    async function fetchJob() {
      try {
        const data = await getJob(jobId!);
        if (cancelled) return;
        setJob(data);

        if (data.status === "completed" || data.status === "failed") {
          stopPolling();
        }
      } catch (err) {
        if (cancelled) return;
        setFetchError(err instanceof Error ? err.message : "Failed to fetch job.");
        stopPolling();
      }
    }

    // Fetch immediately, then start polling if not already terminal.
    void fetchJob().then(() => {
      if (cancelled) return;
      setJob((current) => {
        if (
          current &&
          current.status !== "completed" &&
          current.status !== "failed"
        ) {
          intervalRef.current = setInterval(() => {
            void fetchJob();
          }, POLL_INTERVAL_MS);
        }
        return current;
      });
    });

    return () => {
      cancelled = true;
      stopPolling();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);

  const PIPELINE_LABELS: Record<string, string> = {
    single_stage: "Single Stage",
    two_stage: "Two Stage",
  };
  const ARCH_LABELS: Record<string, string> = {
    unet: "UNet",
    double_unet: "Double-UNet",
    attention_unet: "AttentionUNet",
  };
  const showBoundingBoxToggle = job?.pipeline_type === "two_stage";

  return (
    <div className="min-h-screen bg-background px-4 py-12">
      <div className="max-w-4xl mx-auto space-y-6">
        {/* Header */}
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
            {job && <JobStatusBadge status={job.status} />}
            <Button variant="outline" size="sm" onClick={() => navigate("/")}>
              New Job
            </Button>
          </div>
        </div>

        {/* Fetch error */}
        {fetchError && (
          <Alert variant="destructive">
            <AlertDescription>{fetchError}</AlertDescription>
          </Alert>
        )}

        {/* Inference error */}
        {job?.status === "failed" && job.error_message && (
          <Alert variant="destructive">
            <AlertDescription>
              <strong>Inference failed:</strong> {job.error_message}
            </AlertDescription>
          </Alert>
        )}

        {/* Loading / processing state */}
        {(!job || job.status === "pending" || job.status === "processing") &&
          !fetchError && (
            <Card>
              <CardContent className="py-12 flex flex-col items-center gap-4">
                <div className="h-10 w-10 animate-spin rounded-full border-4 border-primary border-t-transparent" />
                <p className="text-muted-foreground text-sm">
                  {job
                    ? job.status === "processing"
                      ? "Running inference…"
                      : "Waiting to start…"
                    : "Loading job…"}
                </p>
              </CardContent>
            </Card>
          )}

        {/* Results */}
        {job?.status === "completed" && job.image_results.length > 0 && (
          <>
            {/* Opacity slider — shared across all canvases */}
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

            <div className="space-y-6">
              {job.image_results.map((result) => (
                <Card key={result.id}>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium flex items-center justify-between">
                      <span className="truncate">{result.original_filename}</span>
                      <span className="text-muted-foreground font-normal text-xs shrink-0 ml-4">
                        {result.original_size.width} × {result.original_size.height}
                        {result.inference_time_ms !== null &&
                          ` · ${result.inference_time_ms} ms`}
                        {result.bounding_boxes !== null &&
                          ` · ${result.bounding_boxes.length} tooth${
                            result.bounding_boxes.length !== 1 ? "teeth" : ""
                          } detected`}
                      </span>
                    </CardTitle>
                    {result.bounding_boxes !== null &&
                      result.bounding_boxes.length === 0 && (
                        <p className="text-xs text-muted-foreground">
                          No teeth detected in this image.
                        </p>
                      )}
                  </CardHeader>
                  <CardContent className="pt-0">
                    <OverlayCanvas
                      imageResultId={result.id}
                      opacity={opacity}
                      boundingBoxes={result.bounding_boxes}
                      showBoundingBoxes={showBoundingBoxToggle && showBoundingBoxes}
                      originalSize={result.original_size}
                    />
                  </CardContent>
                </Card>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
