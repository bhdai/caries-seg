// =============================================================================
// PatientCreateModal
// =============================================================================
//
// Compact dialog for quickly creating a new patient record.  Intended as a
// quick-create flow triggered from PatientCombobox when a search returns zero
// results.  The typed search query is passed in as `defaultName` so the user
// does not have to retype the name they already entered in the combobox.
//
// On successful creation the `onCreated` callback is called with the new
// patient's ID and full name so the caller can auto-select the patient in the
// combobox without an extra round-trip.

import { createPatient } from "@/api/patients";
import { ApiError } from "@/api/http";
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
import { Alert, AlertDescription } from "@/components/ui/alert";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface PatientCreateModalProps {
  /** Whether the dialog is open. */
  open: boolean;
  /** Called to request a change in the open state (mirrors shadcn convention). */
  onOpenChange: (open: boolean) => void;
  /**
   * Pre-filled value for the Full Name field.  Populated from the last search
   * query in PatientCombobox so the user does not have to retype the name.
   */
  defaultName?: string;
  /**
   * Called with `(id, full_name)` after the patient is successfully created.
   * The caller uses this to auto-select the new patient in the combobox.
   */
  onCreated: (id: string, name: string) => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * Compact create-patient dialog.
 *
 * Layout (top → bottom):
 *   Full name (required, pre-filled from `defaultName`)
 *   Phone (optional)
 *   Date of birth (optional)
 *   Notes (optional)
 *   Error banner (shown on API failure)
 *   Cancel / Create buttons
 */
export function PatientCreateModal({
  open,
  onOpenChange,
  defaultName = "",
  onCreated,
}: PatientCreateModalProps) {
  const { t } = useTranslation();

  // ---------------------------------------------------------------------------
  // Form state — each field maps directly to the CreatePatientPayload shape.
  // ---------------------------------------------------------------------------
  const [fullName, setFullName] = useState(defaultName);
  const [phone, setPhone] = useState("");
  const [dob, setDob] = useState("");
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Sync the name field when the defaultName prop changes (the user typed
  // something different in the combobox before reopening the modal).
  useEffect(() => {
    if (open) {
      setFullName(defaultName);
      setPhone("");
      setDob("");
      setNotes("");
      setError(null);
    }
  }, [open, defaultName]);

  // ---------------------------------------------------------------------------
  // Submit
  // ---------------------------------------------------------------------------

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      const trimmedName = fullName.trim();
      if (!trimmedName) {
        setError(t("patient.create.error.nameRequired"));
        return;
      }

      setError(null);
      setSubmitting(true);

      try {
        const created = await createPatient({
          full_name: trimmedName,
          phone: phone.trim() || null,
          date_of_birth: dob || null,
          notes: notes.trim() || null,
        });
        toast.success(t("patient.create.success", { name: created.full_name }));
        onCreated(created.id, created.full_name);
      } catch (err) {
        const message =
          err instanceof ApiError
            ? err.message
            : t("patient.create.error.fallback");
        setError(message);
      } finally {
        setSubmitting(false);
      }
    },
    [fullName, phone, dob, notes, onCreated, t],
  );

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t("patient.create.title")}</DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Full name — required */}
          <div className="space-y-1.5">
            <Label htmlFor="patient-full-name">
              {t("patient.fields.fullName")}{" "}
              <span className="text-destructive" aria-hidden>*</span>
            </Label>
            <Input
              id="patient-full-name"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder={t("patient.fields.fullNamePlaceholder")}
              autoFocus
              required
            />
          </div>

          {/* Phone — optional */}
          <div className="space-y-1.5">
            <Label htmlFor="patient-phone">{t("patient.fields.phone")}</Label>
            <Input
              id="patient-phone"
              type="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder={t("patient.fields.phonePlaceholder")}
            />
          </div>

          {/* Date of birth — optional */}
          <div className="space-y-1.5">
            <Label htmlFor="patient-dob">{t("patient.fields.dob")}</Label>
            <Input
              id="patient-dob"
              type="date"
              value={dob}
              onChange={(e) => setDob(e.target.value)}
            />
          </div>

          {/* Notes — optional */}
          <div className="space-y-1.5">
            <Label htmlFor="patient-notes">{t("patient.fields.notes")}</Label>
            <Input
              id="patient-notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder={t("patient.fields.notesPlaceholder")}
            />
          </div>

          {/* Error banner */}
          {error && (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={submitting}
            >
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting
                ? t("patient.create.submitting")
                : t("patient.create.submit")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
