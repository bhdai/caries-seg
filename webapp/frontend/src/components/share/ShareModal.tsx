// =============================================================================
// ShareModal
// =============================================================================
//
// Two-state dialog for creating and displaying a share link for a scan job.
//
// State machine:
//   "loading"   — On open, fetches any existing active link for the job.
//   "configure" — No active link found; shows expiry dropdown + Generate button.
//   "ready"     — Active link is available; shows URL field, QR code, and actions.
//
// The "Regenerate" flow (ready → configure) asks for confirmation via an
// AlertDialog, then revokes the current link and transitions back to
// "configure" so the doctor can choose a new expiry before generating.
//
// Print behaviour: opens a dedicated browser window with only the QR code,
// URL, patient name, and scan date — appropriate for handing to patients.

import { getShareLinkForJob } from "@/api/shareLinks";
import type { ShareLinkResponse } from "@/api/shareLinks";
import {
  useCreateShareLinkMutation,
  useRevokeShareLinkMutation,
} from "@/hooks/useShareLinkMutation";
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
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { QRCodeCanvas } from "qrcode.react";
import { Copy, Download, Printer, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ShareModalProps {
  /** Whether the dialog is open. */
  open: boolean;
  /** Called to request a change in the open state. */
  onOpenChange: (open: boolean) => void;
  /** The job UUID for which to create/retrieve a share link. */
  jobId: string;
  /**
   * Display name of the linked patient.
   * Null when the job has no patient association.
   */
  patientName: string | null;
  /** ISO 8601 scan date (job.created_at) for the print header. */
  scanDate?: string;
}

/** Expiry option for the dropdown. */
type ExpiryOption = "7" | "30" | "90" | "never";

type ModalState = "loading" | "configure" | "ready";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Build the public-facing share URL from a token.
 * Uses window.location.origin so it works in both dev and production without
 * requiring the VITE_API_URL env var (which points to the backend, not the
 * frontend).
 */
function buildShareUrl(token: string): string {
  return `${window.location.origin}/shared/${token}`;
}

/** Convert a UI expiry option to the `expires_in_days` API value. */
function expiryOptionToDays(option: ExpiryOption): number | null {
  if (option === "never") return null;
  return parseInt(option, 10);
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * Share-link management dialog.
 *
 * On open: checks for an existing active link and jumps to "ready" state if
 * one is found.  In "ready" state the doctor can copy the URL, download the
 * QR code, print it, or regenerate the link (with confirmation).
 */
export function ShareModal({
  open,
  onOpenChange,
  jobId,
  patientName,
  scanDate,
}: ShareModalProps) {
  const { t } = useTranslation();

  const [modalState, setModalState] = useState<ModalState>("loading");
  const [activeLink, setActiveLink] = useState<ShareLinkResponse | null>(null);
  const [expiry, setExpiry] = useState<ExpiryOption>("30");
  const [copied, setCopied] = useState(false);
  const [regenerateDialogOpen, setRegenerateDialogOpen] = useState(false);

  // Ref to the QR code canvas element so we can export it as PNG.
  const qrContainerRef = useRef<HTMLDivElement>(null);

  // ---------------------------------------------------------------------------
  // Mutations
  // ---------------------------------------------------------------------------

  const createMutation = useCreateShareLinkMutation(jobId, {
    onSuccess(link) {
      setActiveLink(link);
      setModalState("ready");
    },
  });

  const revokeMutation = useRevokeShareLinkMutation({
    onSuccess() {
      // Transition back to configure state so the doctor can choose a new
      // expiry and generate a fresh link.
      setActiveLink(null);
      setModalState("configure");
    },
  });

  // ---------------------------------------------------------------------------
  // On open: check for existing active link
  // ---------------------------------------------------------------------------

  useEffect(() => {
    if (!open) return;

    // Reset state on each open so stale data from a previous session is
    // cleared when the modal is closed and re-opened.
    setModalState("loading");
    setActiveLink(null);
    setCopied(false);

    let cancelled = false;

    getShareLinkForJob(jobId)
      .then((link) => {
        if (cancelled) return;
        if (link?.is_active) {
          setActiveLink(link);
          setModalState("ready");
        } else {
          setModalState("configure");
        }
      })
      .catch(() => {
        if (!cancelled) {
          // If the check fails, fall back to configure state so the doctor
          // can still generate a new link manually.
          setModalState("configure");
        }
      });

    return () => {
      cancelled = true;
    };
  }, [open, jobId]);

  // ---------------------------------------------------------------------------
  // Action handlers
  // ---------------------------------------------------------------------------

  const handleGenerate = useCallback(() => {
    createMutation.mutate({
      job_id: jobId,
      expires_in_days: expiryOptionToDays(expiry),
    });
  }, [jobId, expiry, createMutation]);

  const handleCopy = useCallback(() => {
    if (!activeLink) return;
    const url = buildShareUrl(activeLink.token);
    navigator.clipboard.writeText(url).then(() => {
      setCopied(true);
      // Reset the "Copied!" feedback after 2 s.
      setTimeout(() => setCopied(false), 2_000);
    }).catch(() => {
      // Clipboard API may be denied in non-secure contexts — silently ignore.
    });
  }, [activeLink]);

  const handleDownloadQr = useCallback(() => {
    const canvas = qrContainerRef.current?.querySelector("canvas");
    if (!canvas) return;
    const dataUrl = canvas.toDataURL("image/png");
    const anchor = document.createElement("a");
    anchor.href = dataUrl;
    anchor.download = `share-qr-${jobId.slice(0, 8)}.png`;
    anchor.click();
  }, [jobId]);

  const handlePrint = useCallback(() => {
    if (!activeLink) return;
    const url = buildShareUrl(activeLink.token);
    const canvas = qrContainerRef.current?.querySelector("canvas");
    const qrDataUrl = canvas?.toDataURL("image/png") ?? "";

    const formattedDate = scanDate
      ? new Date(scanDate).toLocaleDateString(undefined, {
          year: "numeric",
          month: "long",
          day: "numeric",
        })
      : "";

    // Open a minimal print window containing only the QR code, URL, patient
    // name, and scan date.  This avoids printing the full app chrome.
    const printWindow = window.open("", "_blank", "width=600,height=700");
    if (!printWindow) return;

    printWindow.document.write(`
      <!doctype html>
      <html lang="en">
        <head>
          <meta charset="UTF-8" />
          <title>${t("share.modal.title")}</title>
          <style>
            body { font-family: sans-serif; text-align: center; padding: 40px; color: #111; }
            h2   { font-size: 1.25rem; margin-bottom: 4px; }
            p    { font-size: 0.9rem; color: #555; margin: 4px 0; }
            img  { margin: 24px auto; display: block; width: 200px; height: 200px; }
            .url { font-size: 0.8rem; word-break: break-all; margin-top: 16px; color: #333; }
          </style>
        </head>
        <body>
          <h2>${patientName ?? t("share.modal.noPatient")}</h2>
          ${formattedDate ? `<p>${formattedDate}</p>` : ""}
          ${qrDataUrl ? `<img src="${qrDataUrl}" alt="QR Code" />` : ""}
          <p class="url">${url}</p>
        </body>
      </html>
    `);
    printWindow.document.close();
    printWindow.focus();
    printWindow.print();
    printWindow.close();
  }, [activeLink, patientName, scanDate, t]);

  const handleRegenerateConfirm = useCallback(() => {
    if (!activeLink) return;
    revokeMutation.mutate(activeLink.id);
    setRegenerateDialogOpen(false);
  }, [activeLink, revokeMutation]);

  // ---------------------------------------------------------------------------
  // Derived values
  // ---------------------------------------------------------------------------

  const shareUrl = activeLink ? buildShareUrl(activeLink.token) : "";
  const isGenerating = createMutation.isPending;
  const isRevoking = revokeMutation.isPending;

  const patientLabel = patientName ?? t("share.modal.noPatient");

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t("share.modal.title")}</DialogTitle>
          </DialogHeader>

          {/* ---------------------------------------------------------------- */}
          {/* Loading state — checking for existing link                        */}
          {/* ---------------------------------------------------------------- */}
          {modalState === "loading" && (
            <div className="flex flex-col items-center gap-3 py-8">
              <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
              <p className="text-muted-foreground text-sm">
                {t("share.modal.checkingLink")}
              </p>
            </div>
          )}

          {/* ---------------------------------------------------------------- */}
          {/* Configure state — no active link; choose expiry and generate      */}
          {/* ---------------------------------------------------------------- */}
          {modalState === "configure" && (
            <div className="space-y-4">
              <p className="text-sm text-muted-foreground">
                {patientLabel}
              </p>

              <div className="space-y-2">
                <Label htmlFor="expiry-select">{t("share.modal.expiryLabel")}</Label>
                <Select
                  value={expiry}
                  onValueChange={(v) => setExpiry(v as ExpiryOption)}
                >
                  <SelectTrigger id="expiry-select">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="7">{t("share.modal.expiry7days")}</SelectItem>
                    <SelectItem value="30">{t("share.modal.expiry30days")}</SelectItem>
                    <SelectItem value="90">{t("share.modal.expiry90days")}</SelectItem>
                    <SelectItem value="never">{t("share.modal.expiryNone")}</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <DialogFooter>
                <Button
                  onClick={handleGenerate}
                  disabled={isGenerating}
                  className="w-full sm:w-auto"
                >
                  {isGenerating
                    ? t("share.modal.generating")
                    : t("share.modal.generateButton")}
                </Button>
              </DialogFooter>
            </div>
          )}

          {/* ---------------------------------------------------------------- */}
          {/* Ready state — active link available                               */}
          {/* ---------------------------------------------------------------- */}
          {modalState === "ready" && activeLink && (
            <div className="space-y-5">
              <p className="text-sm text-muted-foreground">{patientLabel}</p>

              {/* URL field + Copy button */}
              <div className="flex gap-2">
                <Input
                  readOnly
                  value={shareUrl}
                  className="font-mono text-xs"
                  aria-label={t("share.modal.copyButton")}
                />
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleCopy}
                  aria-label={copied ? t("share.modal.copied") : t("share.modal.copyButton")}
                  title={copied ? t("share.modal.copied") : t("share.modal.copyButton")}
                >
                  <Copy className="h-4 w-4" />
                  <span className="ml-1.5 hidden sm:inline">
                    {copied ? t("share.modal.copied") : t("share.modal.copyButton")}
                  </span>
                </Button>
              </div>

              {/* QR code */}
              <div className="flex flex-col items-center gap-3">
                <div ref={qrContainerRef}>
                  <QRCodeCanvas
                    value={shareUrl}
                    size={200}
                    level="M"
                    includeMargin
                  />
                </div>

                <div className="flex gap-2 flex-wrap justify-center">
                  <Button variant="outline" size="sm" onClick={handleDownloadQr}>
                    <Download className="h-4 w-4 mr-1.5" />
                    {t("share.modal.downloadQr")}
                  </Button>
                  <Button variant="outline" size="sm" onClick={handlePrint}>
                    <Printer className="h-4 w-4 mr-1.5" />
                    {t("share.modal.print")}
                  </Button>
                </div>
              </div>

              {/* Regenerate subtle link */}
              <div className="flex items-center justify-between border-t pt-3">
                <p className="text-xs text-muted-foreground">
                  {t("share.modal.footerNote")}
                </p>
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-xs text-muted-foreground hover:text-foreground shrink-0"
                  onClick={() => setRegenerateDialogOpen(true)}
                  disabled={isRevoking}
                >
                  <RefreshCw className="h-3 w-3 mr-1" />
                  {t("share.modal.regenerate")}
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* -------------------------------------------------------------------- */}
      {/* Regenerate confirmation dialog                                        */}
      {/* -------------------------------------------------------------------- */}
      <AlertDialog
        open={regenerateDialogOpen}
        onOpenChange={setRegenerateDialogOpen}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t("share.modal.regenerateConfirmTitle")}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t("share.modal.regenerateConfirmDesc")}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("common.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleRegenerateConfirm}
              disabled={isRevoking}
            >
              {t("share.modal.regenerateConfirmAction")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
