/**
 * JobStatusBadge
 *
 * Renders a colour-coded badge for the four job statuses:
 *   pending     → secondary (grey)
 *   processing  → default (primary / blue)
 *   completed   → custom green
 *   failed      → destructive (red)
 *
 * @deprecated Use JobStatusChip from components/jobs/JobStatusChip.tsx instead.
 */
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { useTranslation } from "react-i18next";

type JobStatus = "pending" | "processing" | "completed" | "failed";

interface JobStatusBadgeProps {
  status: JobStatus;
  className?: string;
}

export function JobStatusBadge({ status, className }: JobStatusBadgeProps) {
  const { t } = useTranslation();

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
      {t(`job.status.${status}`)}
    </Badge>
  );
}
