/**
 * JobStatusBadge
 *
 * Renders a colour-coded badge for the four job statuses:
 *   pending     → secondary (grey)
 *   processing  → default (primary / blue)
 *   completed   → custom green
 *   failed      → destructive (red)
 */
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

type JobStatus = "pending" | "processing" | "completed" | "failed";

interface JobStatusBadgeProps {
  status: JobStatus;
  className?: string;
}

const STATUS_LABELS: Record<JobStatus, string> = {
  pending: "Pending",
  processing: "Processing…",
  completed: "Completed",
  failed: "Failed",
};

export function JobStatusBadge({ status, className }: JobStatusBadgeProps) {
  return (
    <Badge
      variant={
        status === "failed"
          ? "destructive"
          : status === "completed"
            ? "outline"
            : status === "processing"
              ? "default"
              : "secondary"
      }
      className={cn(
        status === "completed" &&
          "border-green-600 text-green-700 bg-green-50",
        className,
      )}
    >
      {STATUS_LABELS[status]}
    </Badge>
  );
}
