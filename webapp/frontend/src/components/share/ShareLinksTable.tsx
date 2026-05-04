// =============================================================================
// ShareLinksTable
// =============================================================================
//
// Renders the patient-level share links table on PatientDetailPage.  Shows all
// active and recently expired links for the patient's jobs, with per-row
// actions: Copy Link, Show QR (inline Popover), and Revoke (AlertDialog).
//
// Data is received from the parent (PatientDetailPage) via the `shareLinks`
// prop, sourced from the patient detail response — no additional fetch.
//
// The revoke flow: AlertDialog confirmation → `useRevokeShareLinkMutation` →
// calls `onRevokeSuccess` so PatientDetailPage can invalidate the patient
// detail query and refresh the table.

import type { PatientShareLinkSummary } from "@/api/shareLinks";
import { useRevokeShareLinkMutation } from "@/hooks/useShareLinkMutation";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatRelativeTime, formatAbsoluteTime } from "@/lib/time";
import { QRCodeCanvas } from "qrcode.react";
import { Copy, QrCode, Trash2 } from "lucide-react";
import { useCallback, useState } from "react";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface ShareLinksTableProps {
  /** All share link records for this patient (from patient detail response). */
  shareLinks: PatientShareLinkSummary[];
  /**
   * Called after a successful revoke so the parent can invalidate its query
   * and refresh the table.
   */
  onRevokeSuccess: () => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Build the public-facing share URL for display and clipboard copy.
 * Uses window.location.origin so it works in dev and production alike.
 */
function buildShareUrl(token: string): string {
  return `${window.location.origin}/shared/${token}`;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * Render the share links management table for a patient.
 *
 * Each row represents one share link.  Active links can be copied, previewed
 * via an inline QR popover, or revoked.  Expired and revoked links are shown
 * with an "Expired" badge and read-only actions.
 */
export function ShareLinksTable({
  shareLinks,
  onRevokeSuccess,
}: ShareLinksTableProps) {
  const { t } = useTranslation();

  // Track which link's revoke confirmation dialog is open.
  const [revokeTargetId, setRevokeTargetId] = useState<string | null>(null);

  const revokeMutation = useRevokeShareLinkMutation({ onSuccess: onRevokeSuccess });

  const handleCopyLink = useCallback(
    (token: string) => {
      const url = buildShareUrl(token);
      navigator.clipboard.writeText(url).then(() => {
        toast.success(t("share.table.copySuccess"));
      }).catch(() => {
        // Clipboard API denied — silently ignore.
      });
    },
    [t],
  );

  const handleRevokeConfirm = useCallback(() => {
    if (!revokeTargetId) return;
    revokeMutation.mutate(revokeTargetId);
    setRevokeTargetId(null);
  }, [revokeTargetId, revokeMutation]);

  // ---------------------------------------------------------------------------
  // Render — empty state
  // ---------------------------------------------------------------------------

  if (shareLinks.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("share.table.title")}</CardTitle>
        </CardHeader>
        <CardContent className="py-10 flex flex-col items-center gap-2 text-center">
          <p className="text-sm font-medium">{t("share.table.emptyTitle")}</p>
          <p className="text-xs text-muted-foreground">{t("share.table.emptyDesc")}</p>
        </CardContent>
      </Card>
    );
  }

  // ---------------------------------------------------------------------------
  // Render — table
  // ---------------------------------------------------------------------------

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("share.table.title")}</CardTitle>
        </CardHeader>
        <CardContent className="px-0 pb-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("share.table.colJob")}</TableHead>
                <TableHead>{t("share.table.colCreated")}</TableHead>
                <TableHead>{t("share.table.colExpires")}</TableHead>
                <TableHead>{t("share.table.colStatus")}</TableHead>
                <TableHead className="text-right">{t("share.table.colActions")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {shareLinks.map((link) => {
                const shareUrl = buildShareUrl(link.token);

                return (
                  <TableRow key={link.id}>
                    {/* Job — scan date + primary filename */}
                    <TableCell>
                      <div className="min-w-0">
                        <p className="text-sm font-medium truncate leading-snug">
                          {link.job_primary_filename}
                        </p>
                        <p
                          className="text-xs text-muted-foreground mt-0.5"
                          title={formatAbsoluteTime(link.job_date)}
                        >
                          {formatRelativeTime(link.job_date)}
                        </p>
                      </div>
                    </TableCell>

                    {/* Created */}
                    <TableCell>
                      <span
                        className="text-sm text-muted-foreground whitespace-nowrap"
                        title={formatAbsoluteTime(link.created_at)}
                      >
                        {formatRelativeTime(link.created_at)}
                      </span>
                    </TableCell>

                    {/* Expires */}
                    <TableCell>
                      <span className="text-sm text-muted-foreground whitespace-nowrap">
                        {link.expires_at
                          ? new Date(link.expires_at).toLocaleDateString(undefined, {
                              year: "numeric",
                              month: "short",
                              day: "numeric",
                            })
                          : t("share.table.noExpiry")}
                      </span>
                    </TableCell>

                    {/* Status badge */}
                    <TableCell>
                      <Badge variant={link.is_active ? "default" : "secondary"}>
                        {link.is_active
                          ? t("share.table.statusActive")
                          : t("share.table.statusExpired")}
                      </Badge>
                    </TableCell>

                    {/* Actions */}
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-1">
                        {/* Copy Link */}
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleCopyLink(link.token)}
                          aria-label={t("share.table.copyLink")}
                          title={t("share.table.copyLink")}
                        >
                          <Copy className="h-4 w-4" />
                        </Button>

                        {/* Show QR — inline Popover */}
                        <Popover>
                          <PopoverTrigger asChild>
                            <Button
                              variant="ghost"
                              size="sm"
                              aria-label={t("share.table.showQr")}
                              title={t("share.table.showQr")}
                            >
                              <QrCode className="h-4 w-4" />
                            </Button>
                          </PopoverTrigger>
                          <PopoverContent className="w-auto p-3 flex flex-col items-center gap-2">
                            <QRCodeCanvas
                              value={shareUrl}
                              size={160}
                              level="M"
                              includeMargin
                            />
                            <p className="text-xs text-muted-foreground break-all max-w-[200px] text-center">
                              {shareUrl}
                            </p>
                          </PopoverContent>
                        </Popover>

                        {/* Revoke — only for active links */}
                        {link.is_active && (
                          <Button
                            variant="ghost"
                            size="sm"
                            className="text-destructive hover:text-destructive"
                            onClick={() => setRevokeTargetId(link.id)}
                            aria-label={t("share.table.revoke")}
                            title={t("share.table.revoke")}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* -------------------------------------------------------------------- */}
      {/* Revoke confirmation dialog                                            */}
      {/* -------------------------------------------------------------------- */}
      <AlertDialog
        open={revokeTargetId !== null}
        onOpenChange={(open) => {
          if (!open) setRevokeTargetId(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("share.table.revokeConfirmTitle")}</AlertDialogTitle>
            <AlertDialogDescription>
              {t("share.table.revokeConfirmDesc")}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("common.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleRevokeConfirm}
              disabled={revokeMutation.isPending}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {t("share.table.revokeConfirmAction")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
