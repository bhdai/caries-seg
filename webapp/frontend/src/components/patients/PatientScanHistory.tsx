// =============================================================================
// PatientScanHistory
// =============================================================================
//
// Shows a table of inference jobs linked to the patient on PatientDetailPage.
// Linked jobs are included in the PatientDetailResponse.jobs array so no
// additional fetch is required — the component renders the data it receives.
//
// Each row shows:
//   Date | Status | Files | Pipeline · Model | Actions (View Result)
//
// An empty state is shown when the patient has no linked scans, with a
// "Go to Upload" link to guide the doctor to the workflow start.

import { JobStatusChip } from "@/components/jobs/JobStatusChip";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { JobSummary } from "@/api/types";
import { formatRelativeTime, formatAbsoluteTime } from "@/lib/time";
import { ExternalLink, UploadCloud } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface PatientScanHistoryProps {
  /** Compact job summaries linked to this patient. */
  jobs: JobSummary[];
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * Render the patient's linked scan history table.
 *
 * The component is presentational — it receives the job list from
 * PatientDetailPage and fires navigate() for the "View Result" action.
 */
export function PatientScanHistory({ jobs }: PatientScanHistoryProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{t("patient.scanHistory.title")}</CardTitle>
      </CardHeader>
      <CardContent className="px-0 pb-0">
        {jobs.length === 0 ? (
          /* ---------------------------------------------------------------- */
          /* Empty state                                                       */
          /* ---------------------------------------------------------------- */
          <div className="py-12 flex flex-col items-center gap-4 text-center px-6">
            <p className="text-muted-foreground text-sm">
              {t("patient.scanHistory.empty")}
            </p>
            <Button asChild variant="outline" size="sm">
              <Link to="/upload">
                <UploadCloud className="h-4 w-4 mr-1.5" />
                {t("patient.scanHistory.goToUpload")}
              </Link>
            </Button>
          </div>
        ) : (
          /* ---------------------------------------------------------------- */
          /* Scan table                                                        */
          /* ---------------------------------------------------------------- */
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("patient.scanHistory.colDate")}</TableHead>
                <TableHead>{t("patient.scanHistory.colStatus")}</TableHead>
                <TableHead>{t("patient.scanHistory.colFiles")}</TableHead>
                <TableHead>{t("jobsTable.colPipelineModel")}</TableHead>
                <TableHead className="text-right">{t("patient.scanHistory.colActions")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {jobs.map((job) => (
                <TableRow
                  key={job.id}
                  className="cursor-pointer"
                  onClick={() => navigate(`/result/${job.id}`)}
                >
                  {/* Date — relative with absolute tooltip */}
                  <TableCell>
                    <span
                      className="text-sm text-muted-foreground whitespace-nowrap"
                      title={formatAbsoluteTime(job.created_at)}
                    >
                      {formatRelativeTime(job.created_at)}
                    </span>
                  </TableCell>

                  {/* Status badge */}
                  <TableCell>
                    <JobStatusChip status={job.status} />
                  </TableCell>

                  {/* Primary filename + overflow count */}
                  <TableCell>
                    <div className="min-w-0">
                      <p className="text-sm font-medium truncate leading-snug">
                        {job.primary_filename}
                      </p>
                      {job.filename_preview.length > 0 && (
                        <p className="text-xs text-muted-foreground mt-0.5">
                          {t("jobsTable.moreFiles", {
                            n: job.filename_preview.length,
                          })}
                        </p>
                      )}
                    </div>
                  </TableCell>

                  {/* Pipeline · Model */}
                  <TableCell>
                    <div className="text-sm">
                      <span>
                        {job.pipeline_type === "two_stage"
                          ? t("job.pipeline.two")
                          : t("job.pipeline.single")}
                      </span>
                      <span className="text-muted-foreground"> · </span>
                      <span className="text-muted-foreground">
                        {job.model_arch === "double_unet"
                          ? t("job.model.doubleUnet")
                          : t("job.model.unet")}
                      </span>
                    </div>
                  </TableCell>

                  {/* View Result action */}
                  <TableCell
                    className="text-right"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => navigate(`/result/${job.id}`)}
                    >
                      <ExternalLink className="h-4 w-4 mr-1.5" />
                      {t("patient.scanHistory.viewResult")}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
