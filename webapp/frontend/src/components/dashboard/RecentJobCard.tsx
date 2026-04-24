// =============================================================================
// RecentJobCard
// =============================================================================
//
// A richer card representation of one recent job on the Dashboard, replacing
// the previous compact row layout.  The card displays enough metadata for
// the user to identify the job at a glance and provides the same quick-action
// buttons (Open, Rerun) that the former row offered.
//
// Fields shown:
//   - Job status chip
//   - Primary filename (truncated) and optional overflow count when the job
//     contains more images than shown in the filename preview.
//   - Pipeline type and model architecture label.
//   - Image count.
//   - Relative last-activity timestamp.
//   - Open result and Rerun actions.
//
// The Rerun mutation is *not* owned here; the component receives callbacks
// so the parent list can share a single mutation instance across all cards.

import { JobStatusChip } from "@/components/jobs/JobStatusChip";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardFooter } from "@/components/ui/card";
import { formatRelativeTime } from "@/lib/time";
import { cn } from "@/lib/utils";
import type { JobSummary } from "@/api/types";
import { ExternalLink, RotateCcw } from "lucide-react";

// ---------------------------------------------------------------------------
// Label helpers — defined at module scope to avoid recreation on every render.
// ---------------------------------------------------------------------------

function formatPipelineLabel(pipelineType: string): string {
  return pipelineType === "two_stage" ? "Two Stage" : "Single Stage";
}

function formatModelLabel(modelArch: string): string {
  return modelArch === "double_unet" ? "Double UNet" : "UNet";
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface RecentJobCardProps {
  job: JobSummary;
  /** True while the rerun mutation is pending for *any* job in the list. */
  isRerunPending: boolean;
  /** The job ID that triggered the currently-pending rerun (if any). */
  rerunJobId: string | undefined;
  /** Called when the user requests to open the job result page. */
  onOpen: (jobId: string) => void;
  /** Called when the user requests to rerun the job. */
  onRerun: (jobId: string) => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * Render one recent job as a card on the Dashboard.
 *
 * The card preserves the status chip, filename, pipeline/model summary,
 * image count, relative timestamp, and quick-action buttons from the
 * previous row layout while offering more visual breathing room and
 * easier scanning when multiple jobs are present.
 */
export function RecentJobCard({
  job,
  isRerunPending,
  rerunJobId,
  onOpen,
  onRerun,
}: RecentJobCardProps) {
  const isThisRerunning = isRerunPending && rerunJobId === job.id;

  const imageCountLabel =
    job.image_count === 1 ? "1 image" : `${job.image_count} images`;

  // Build a secondary label showing pipeline · model · image count so the
  // card conveys the full job configuration without requiring a tooltip.
  const metaLabel = [
    formatPipelineLabel(job.pipeline_type),
    formatModelLabel(job.model_arch),
    imageCountLabel,
  ].join(" · ");

  return (
    <Card className="flex flex-col">
      <CardContent className="flex-1 pt-4 pb-2 space-y-2">
        {/* Top row: status chip + relative timestamp */}
        <div className="flex items-center justify-between gap-2">
          <JobStatusChip status={job.status} />
          <span className="text-xs text-muted-foreground whitespace-nowrap">
            {formatRelativeTime(job.last_activity_at)}
          </span>
        </div>

        {/* Primary filename */}
        <p className="text-sm font-medium leading-snug truncate">
          {job.primary_filename}
        </p>

        {/* Pipeline · model · image count meta */}
        <p className="text-xs text-muted-foreground">{metaLabel}</p>
      </CardContent>

      <CardFooter className="border-t pt-3 pb-3 flex items-center gap-2">
        {/* Open result */}
        <Button
          variant="outline"
          size="sm"
          className="flex-1"
          onClick={() => onOpen(job.id)}
          aria-label={`Open result for job ${job.id}`}
        >
          <ExternalLink className="h-4 w-4 mr-1.5" aria-hidden="true" />
          Open
        </Button>

        {/* Rerun */}
        <Button
          variant="ghost"
          size="sm"
          className="flex-1"
          disabled={isRerunPending}
          onClick={() => onRerun(job.id)}
          aria-label={`Rerun job ${job.id}`}
        >
          <RotateCcw
            className={cn("h-4 w-4 mr-1.5", isThisRerunning && "animate-spin")}
            aria-hidden="true"
          />
          Rerun
        </Button>
      </CardFooter>
    </Card>
  );
}
