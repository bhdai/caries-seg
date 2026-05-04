// =============================================================================
// JobStatusChip
// =============================================================================
//
// Shared colour-coded status rendering for Dashboard, History, and Result.
// Wraps the existing Badge primitive with status-specific styling so all
// surfaces display job status consistently.
//
// This component supersedes JobStatusBadge.  Both export the same visual
// output; new consumers should import from here.

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { JobStatus } from "@/api/types";
import { useTranslation } from "react-i18next";

interface JobStatusChipProps {
  status: JobStatus;
  className?: string;
}

/**
 * Render a colour-coded badge for the four job lifecycle statuses.
 *
 *  pending     → secondary (grey)
 *  processing  → default (primary / blue)
 *  completed   → green outline
 *  failed      → destructive (red)
 *
 * Status labels are resolved from the active locale via i18next so the chip
 * updates immediately when the user switches language.
 */
export function JobStatusChip({ status, className }: JobStatusChipProps) {
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
