// =============================================================================
// PatientDetailPage
// =============================================================================
//
// Patient detail view at `/patients/:patientId`.
//
// Sections (top → bottom):
//   Header          — Patient name, "← Back to Patients" link
//   PatientDemographics — Inline-editable demographics card
//   PatientScanHistory  — Table of linked inference jobs
//   (ShareLinksTable placeholder — Phase 4)
//
// Data is fetched once on mount via TanStack Query with the patient UUID from
// the route params.  Both PatientDemographics (on save) and PatientScanHistory
// (no mutations) share the same query key so the demographics save invalidates
// the query and causes PatientScanHistory to reflect any relevant changes.

import { getPatientDetail } from "@/api/patients";
import { PatientDemographics } from "@/components/patients/PatientDemographics";
import { PatientScanHistory } from "@/components/patients/PatientScanHistory";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

// ---------------------------------------------------------------------------
// Query key factory — exported so PatientDemographics can invalidate on save
// ---------------------------------------------------------------------------

export const patientDetailQueryKeys = {
  detail: (patientId: string) =>
    ["patients", "detail", patientId] as const,
};

// ---------------------------------------------------------------------------
// Page component
// ---------------------------------------------------------------------------

/**
 * Patient detail page at `/patients/:patientId`.
 *
 * Renders a loading skeleton while the initial fetch is in flight, an error
 * banner on failure, and the three content sections once data is available.
 */
export default function PatientDetailPage() {
  const { patientId } = useParams<{ patientId: string }>();
  const { t } = useTranslation();

  const queryKey = patientDetailQueryKeys.detail(patientId ?? "");

  const { data: patient, isLoading, error } = useQuery({
    queryKey,
    queryFn: () => getPatientDetail(patientId!),
    enabled: Boolean(patientId),
    // Patient data does not change frequently — a 30-second stale window
    // prevents unnecessary refetches when navigating back to this page.
    staleTime: 30_000,
  });

  const fetchError =
    error instanceof Error ? error.message : error ? t("patient.detail.loadError") : null;

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="space-y-6">
      {/* ------------------------------------------------------------------ */}
      {/* Back navigation                                                     */}
      {/* ------------------------------------------------------------------ */}
      <Button variant="ghost" size="sm" asChild className="-ml-2">
        <Link to="/patients">
          <ArrowLeft className="h-4 w-4 mr-1.5" />
          {t("patient.detail.backToList")}
        </Link>
      </Button>

      {/* ------------------------------------------------------------------ */}
      {/* Page header                                                         */}
      {/* ------------------------------------------------------------------ */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">
          {isLoading ? (
            <Skeleton className="h-9 w-48" />
          ) : (
            (patient?.full_name ?? t("patient.detail.unknownPatient"))
          )}
        </h1>
        {patient && (
          <p className="text-muted-foreground mt-1 text-sm">
            {t("patient.detail.subtitle", { id: patient.id.slice(0, 8) })}
          </p>
        )}
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Fetch error                                                         */}
      {/* ------------------------------------------------------------------ */}
      {fetchError && (
        <Alert variant="destructive">
          <AlertDescription>{fetchError}</AlertDescription>
        </Alert>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Loading skeleton — three placeholder cards                          */}
      {/* ------------------------------------------------------------------ */}
      {isLoading && (
        <div className="space-y-6">
          {[1, 2].map((i) => (
            <Card key={i}>
              <CardContent className="p-6 space-y-3">
                <Skeleton className="h-5 w-32" />
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-3/4" />
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Content sections — rendered once data is available                 */}
      {/* ------------------------------------------------------------------ */}
      {patient && (
        <>
          {/* Demographics — inline-editable card */}
          <PatientDemographics patient={patient} queryKey={queryKey} />

          {/* Linked scan history */}
          <PatientScanHistory jobs={patient.jobs} />

          {/* TODO(phase-4): Replace with <ShareLinksTable /> when the
              share-links feature is implemented. */}
        </>
      )}
    </div>
  );
}
