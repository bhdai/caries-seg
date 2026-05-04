// =============================================================================
// PatientLinkModal
// =============================================================================
//
// Dialog for retroactively linking or unlinking a job to a patient.  Used by:
//   - JobRowActions — "Link to Patient" / "Change Patient" menu items.
//   - ResultPage    — "Link" button shown alongside job header.
//
// The modal presents a PatientCombobox for selection and Confirm / Cancel
// buttons.  When the job already has a linked patient, an "Unlink" button
// is also shown so the doctor can remove the association directly without
// having to re-open the dropdown.
//
// On confirm:   PATCH /api/jobs/:jobId with { patient_id: <selected> }
// On unlink:    AlertDialog confirmation → PATCH with { patient_id: null }

import { patchJob } from "@/api/jobs";
import { ApiError } from "@/api/http";
import { PatientCombobox } from "@/components/patients/PatientCombobox";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
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
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { useCallback, useState } from "react";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface PatientLinkModalProps {
  /** Whether the dialog is open. */
  open: boolean;
  /** Called to request a change in the open state. */
  onOpenChange: (open: boolean) => void;
  /** The job UUID to link. */
  jobId: string;
  /** Currently linked patient UUID (null when unlinked). */
  currentPatientId: string | null;
  /** Currently linked patient display name (null when unlinked). */
  currentPatientName: string | null;
  /** Called after a successful link or unlink operation. */
  onLinked: () => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * Render the link-to-patient dialog for a single job.
 *
 * The "Unlink" button is only shown when `currentPatientId` is non-null.
 * Clicking it opens a nested AlertDialog confirmation before firing the
 * PATCH request to avoid accidental unlinking.
 */
export function PatientLinkModal({
  open,
  onOpenChange,
  jobId,
  currentPatientId,
  currentPatientName,
  onLinked,
}: PatientLinkModalProps) {
  const { t } = useTranslation();

  // Local selection state — initialised from the current linked patient so
  // the combobox shows the existing association when the modal opens.
  const [selectedId, setSelectedId] = useState<string | null>(currentPatientId);
  const [selectedName, setSelectedName] = useState<string | null>(
    currentPatientName,
  );
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [unlinkDialogOpen, setUnlinkDialogOpen] = useState(false);

  const handleSelectionChange = useCallback(
    (id: string | null, name: string | null) => {
      setSelectedId(id);
      setSelectedName(name);
    },
    [],
  );

  // ---------------------------------------------------------------------------
  // Confirm link — PATCH with the selected patient UUID
  // ---------------------------------------------------------------------------

  const handleConfirm = useCallback(async () => {
    if (selectedId === currentPatientId) {
      // No change — close without a network request.
      onOpenChange(false);
      return;
    }

    setError(null);
    setSubmitting(true);

    try {
      await patchJob(jobId, { patient_id: selectedId });
      const msg = selectedId
        ? t("patient.link.successLinked", { name: selectedName })
        : t("patient.link.successUnlinked");
      toast.success(msg);
      onLinked();
      onOpenChange(false);
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : t("patient.link.error.fallback");
      setError(message);
    } finally {
      setSubmitting(false);
    }
  }, [selectedId, selectedName, currentPatientId, jobId, onLinked, onOpenChange, t]);

  // ---------------------------------------------------------------------------
  // Confirm unlink — PATCH with patient_id: null
  // ---------------------------------------------------------------------------

  const handleUnlink = useCallback(async () => {
    setUnlinkDialogOpen(false);
    setError(null);
    setSubmitting(true);

    try {
      await patchJob(jobId, { patient_id: null });
      toast.success(t("patient.link.successUnlinked"));
      onLinked();
      onOpenChange(false);
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : t("patient.link.error.fallback");
      setError(message);
    } finally {
      setSubmitting(false);
    }
  }, [jobId, onLinked, onOpenChange, t]);

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t("patient.link.title")}</DialogTitle>
          </DialogHeader>

          <div className="space-y-4">
            <PatientCombobox
              value={selectedId}
              valueName={selectedName}
              onChange={handleSelectionChange}
              placeholder={t("patient.combobox.placeholder")}
            />

            {error && (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
          </div>

          <DialogFooter className="gap-2 sm:gap-0">
            {/* Unlink button — only shown when the job has an existing patient */}
            {currentPatientId && (
              <Button
                variant="ghost"
                className="text-destructive hover:text-destructive mr-auto"
                onClick={() => setUnlinkDialogOpen(true)}
                disabled={submitting}
              >
                {t("patient.link.unlink")}
              </Button>
            )}
            <Button
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={submitting}
            >
              {t("common.cancel")}
            </Button>
            <Button onClick={handleConfirm} disabled={submitting}>
              {submitting ? t("patient.link.confirming") : t("patient.link.confirm")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Unlink confirmation dialog — separate from the main dialog so the
          confirmation can stay open after the main dialog transitions. */}
      <AlertDialog open={unlinkDialogOpen} onOpenChange={setUnlinkDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("patient.link.unlinkConfirmTitle")}</AlertDialogTitle>
            <AlertDialogDescription>
              {t("patient.link.unlinkConfirmDesc", {
                name: currentPatientName ?? "",
              })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("common.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={handleUnlink}
            >
              {t("patient.link.unlink")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
