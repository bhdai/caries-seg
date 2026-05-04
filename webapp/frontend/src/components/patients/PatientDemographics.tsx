// =============================================================================
// PatientDemographics
// =============================================================================
//
// Read-only card showing patient demographic information on PatientDetailPage.
// An "Edit" button toggles the card into inline form mode; Save/Cancel buttons
// commit or discard the changes.
//
// Inline editing avoids a separate edit route or modal for simple field
// updates and keeps the context visible while editing.

import { updatePatient } from "@/api/patients";
import type { PatientDetailResponse, UpdatePatientPayload } from "@/api/patients";
import { ApiError } from "@/api/http";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Pencil } from "lucide-react";
import { useCallback, useState } from "react";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import { useQueryClient } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Format an ISO date string "YYYY-MM-DD" as a human-readable date. */
function formatDate(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, {
      year: "numeric",
      month: "long",
      day: "numeric",
    });
  } catch {
    return iso;
  }
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface PatientDemographicsProps {
  /** The patient detail record to display. */
  patient: PatientDetailResponse;
  /** TanStack Query key used to refetch the patient after a successful update. */
  queryKey: readonly unknown[];
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * Display patient demographics with an inline edit mode.
 *
 * Read mode: Shows name, phone, DOB, and notes with an "Edit" button.
 * Edit mode:  Shows form fields pre-filled with current values; Save/Cancel
 *             buttons commit or discard the changes.
 */
export function PatientDemographics({ patient, queryKey }: PatientDemographicsProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);

  // ---------------------------------------------------------------------------
  // Edit-mode form state
  // ---------------------------------------------------------------------------
  const [fullName, setFullName] = useState(patient.full_name);
  const [phone, setPhone] = useState(patient.phone ?? "");
  const [dob, setDob] = useState(patient.date_of_birth ?? "");
  const [notes, setNotes] = useState(patient.notes ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleEdit = useCallback(() => {
    // Reset form to current patient values each time edit mode opens.
    setFullName(patient.full_name);
    setPhone(patient.phone ?? "");
    setDob(patient.date_of_birth ?? "");
    setNotes(patient.notes ?? "");
    setError(null);
    setEditing(true);
  }, [patient]);

  const handleCancel = useCallback(() => {
    setEditing(false);
    setError(null);
  }, []);

  const handleSave = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      const trimmedName = fullName.trim();
      if (!trimmedName) {
        setError(t("patient.create.error.nameRequired"));
        return;
      }

      setError(null);
      setSaving(true);

      const payload: UpdatePatientPayload = {
        full_name: trimmedName,
        phone: phone.trim() || null,
        date_of_birth: dob || null,
        notes: notes.trim() || null,
      };

      try {
        await updatePatient(patient.id, payload);
        // Invalidate the detail query so the page reflects the update.
        await queryClient.invalidateQueries({ queryKey });
        toast.success(t("patient.update.success"));
        setEditing(false);
      } catch (err) {
        const message =
          err instanceof ApiError
            ? err.message
            : t("patient.update.error.fallback");
        setError(message);
      } finally {
        setSaving(false);
      }
    },
    [fullName, phone, dob, notes, patient.id, queryKey, queryClient, t],
  );

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">{t("patient.demographics.title")}</CardTitle>
          {!editing && (
            <Button variant="ghost" size="sm" onClick={handleEdit}>
              <Pencil className="h-4 w-4 mr-1.5" />
              {t("common.edit")}
            </Button>
          )}
        </div>
      </CardHeader>

      <CardContent>
        {editing ? (
          /* ---------------------------------------------------------------- */
          /* Edit mode                                                         */
          /* ---------------------------------------------------------------- */
          <form onSubmit={handleSave} className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {/* Full name */}
              <div className="space-y-1.5 sm:col-span-2">
                <Label htmlFor="demo-full-name">
                  {t("patient.fields.fullName")}{" "}
                  <span className="text-destructive" aria-hidden>*</span>
                </Label>
                <Input
                  id="demo-full-name"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  required
                  autoFocus
                />
              </div>

              {/* Phone */}
              <div className="space-y-1.5">
                <Label htmlFor="demo-phone">{t("patient.fields.phone")}</Label>
                <Input
                  id="demo-phone"
                  type="tel"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                />
              </div>

              {/* Date of birth */}
              <div className="space-y-1.5">
                <Label htmlFor="demo-dob">{t("patient.fields.dob")}</Label>
                <Input
                  id="demo-dob"
                  type="date"
                  value={dob}
                  onChange={(e) => setDob(e.target.value)}
                />
              </div>

              {/* Notes */}
              <div className="space-y-1.5 sm:col-span-2">
                <Label htmlFor="demo-notes">{t("patient.fields.notes")}</Label>
                <Input
                  id="demo-notes"
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                />
              </div>
            </div>

            {error && (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            <div className="flex justify-end gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={handleCancel}
                disabled={saving}
              >
                {t("common.cancel")}
              </Button>
              <Button type="submit" disabled={saving}>
                {saving ? t("patient.update.saving") : t("common.save")}
              </Button>
            </div>
          </form>
        ) : (
          /* ---------------------------------------------------------------- */
          /* Read mode                                                         */
          /* ---------------------------------------------------------------- */
          <dl className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
            <div>
              <dt className="text-muted-foreground">{t("patient.fields.fullName")}</dt>
              <dd className="font-medium mt-0.5">{patient.full_name}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">{t("patient.fields.phone")}</dt>
              <dd className="font-medium mt-0.5">{patient.phone ?? "—"}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">{t("patient.fields.dob")}</dt>
              <dd className="font-medium mt-0.5">{formatDate(patient.date_of_birth)}</dd>
            </div>
            <div className="sm:col-span-2">
              <dt className="text-muted-foreground">{t("patient.fields.notes")}</dt>
              <dd className="font-medium mt-0.5">{patient.notes ?? "—"}</dd>
            </div>
          </dl>
        )}
      </CardContent>
    </Card>
  );
}
