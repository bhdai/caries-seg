// =============================================================================
// PatientsPage
// =============================================================================
//
// Full patient list at `/patients`.  URL-synced search and pagination using
// the same pattern as HistoryPage — filter state lives in the URL so the page
// is reloadable and shareable.
//
// Table columns: Name (clickable link to detail), Phone, DOB, Scans, Last
// Visit, Actions.
//
// Admin-only actions: Delete patient (AlertDialog confirmation).
// All users: View detail.
//
// "+ Add Patient" in the header and the empty state both open
// PatientCreateModal.

import { listPatients, deletePatient } from "@/api/patients";
import type { PatientSummary } from "@/api/patients";
import { ApiError } from "@/api/http";
import { PatientCreateModal } from "@/components/patients/PatientCreateModal";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
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
import { useAuth } from "@/context/AuthContext";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { formatRelativeTime, formatAbsoluteTime } from "@/lib/time";
import { Search, Trash2, UserPlus, UserX } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";

// ---------------------------------------------------------------------------
// Query key factory
// ---------------------------------------------------------------------------

const patientsQueryKeys = {
  all: ["patients"] as const,
  list: (search: string, page: number, pageSize: number) =>
    ["patients", "list", search, page, pageSize] as const,
};

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const DEFAULT_PAGE_SIZE = 20;
const SEARCH_DEBOUNCE_MS = 350;

// ---------------------------------------------------------------------------
// Page component
// ---------------------------------------------------------------------------

/**
 * Patient list page at `/patients`.
 *
 * URL query params:
 *   search    — partial name or phone filter
 *   page      — 1-indexed page number
 *   page_size — rows per page (default 20)
 */
export default function PatientsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const { t } = useTranslation();
  const queryClient = useQueryClient();

  const isAdmin = user?.role === "admin";

  // ---------------------------------------------------------------------------
  // URL-synced filter state
  // ---------------------------------------------------------------------------

  const search = searchParams.get("search") ?? "";
  const page = Math.max(1, parseInt(searchParams.get("page") ?? "1", 10) || 1);
  const pageSize =
    parseInt(searchParams.get("page_size") ?? String(DEFAULT_PAGE_SIZE), 10) ||
    DEFAULT_PAGE_SIZE;

  // Local debounced copy for the input field so it stays responsive while
  // the URL update (and therefore the fetch) is deferred.
  const [localSearch, setLocalSearch] = useState(search);
  const debounceRef = useMemo(() => ({ current: null as ReturnType<typeof setTimeout> | null }), []);

  const updateParams = useCallback(
    (updates: Record<string, string>) => {
      const next = new URLSearchParams(searchParams);
      for (const [key, value] of Object.entries(updates)) {
        if (value) {
          next.set(key, value);
        } else {
          next.delete(key);
        }
      }
      setSearchParams(next, { replace: false });
    },
    [searchParams, setSearchParams],
  );

  const handleSearchChange = useCallback(
    (value: string) => {
      setLocalSearch(value);
      if (debounceRef.current !== null) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => {
        updateParams({ search: value, page: "1" });
      }, SEARCH_DEBOUNCE_MS);
    },
    [debounceRef, updateParams],
  );

  const handlePageChange = useCallback(
    (nextPage: number) => {
      updateParams({ page: String(nextPage) });
    },
    [updateParams],
  );

  // ---------------------------------------------------------------------------
  // Data fetching
  // ---------------------------------------------------------------------------

  const { data, isLoading, isError } = useQuery({
    queryKey: patientsQueryKeys.list(search, page, pageSize),
    queryFn: () => listPatients({ search, page, pageSize }),
    placeholderData: keepPreviousData,
  });

  // ---------------------------------------------------------------------------
  // Create modal
  // ---------------------------------------------------------------------------

  const [createModalOpen, setCreateModalOpen] = useState(false);

  const handleCreated = useCallback(
    (id: string) => {
      void queryClient.invalidateQueries({ queryKey: patientsQueryKeys.all });
      setCreateModalOpen(false);
      navigate(`/patients/${id}`);
    },
    [queryClient, navigate],
  );

  // ---------------------------------------------------------------------------
  // Delete mutation — admin only
  // ---------------------------------------------------------------------------

  const [deleteTarget, setDeleteTarget] = useState<PatientSummary | null>(null);

  const { mutate: deleteOne } = useMutation({
    mutationFn: (patientId: string) => deletePatient(patientId),
    onSuccess() {
      void queryClient.invalidateQueries({ queryKey: patientsQueryKeys.all });
      toast.success(t("patient.delete.success"));
    },
    onError(err) {
      const message =
        err instanceof ApiError ? err.message : t("patient.delete.error.fallback");
      toast.error(t("patient.delete.error.title"), { description: message });
    },
  });

  const handleDeleteConfirm = useCallback(() => {
    if (deleteTarget) {
      deleteOne(deleteTarget.id);
      setDeleteTarget(null);
    }
  }, [deleteTarget, deleteOne]);

  // ---------------------------------------------------------------------------
  // Render helpers
  // ---------------------------------------------------------------------------

  function formatDob(iso: string | null): string {
    if (!iso) return "—";
    try {
      return new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
      });
    } catch {
      return iso;
    }
  }

  const totalPages = data?.total_pages ?? 1;
  const hasPrev = (data?.has_previous_page ?? false);
  const hasNext = (data?.has_next_page ?? false);

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="space-y-6">
      {/* ------------------------------------------------------------------ */}
      {/* Header                                                              */}
      {/* ------------------------------------------------------------------ */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">
            {t("patient.list.title")}
          </h1>
          <p className="text-muted-foreground mt-1">{t("patient.list.subtitle")}</p>
        </div>
        <Button onClick={() => setCreateModalOpen(true)}>
          <UserPlus className="h-4 w-4 mr-2" />
          {t("patient.list.addPatient")}
        </Button>
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Search bar                                                          */}
      {/* ------------------------------------------------------------------ */}
      <div className="relative max-w-sm">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
        <Input
          type="search"
          placeholder={t("patient.list.searchPlaceholder")}
          value={localSearch}
          onChange={(e) => handleSearchChange(e.target.value)}
          className="pl-9"
          aria-label={t("patient.list.searchPlaceholder")}
        />
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Error banner                                                        */}
      {/* ------------------------------------------------------------------ */}
      {isError && (
        <p className="text-sm text-destructive">
          {t("patient.list.loadError")}
        </p>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Table card                                                          */}
      {/* ------------------------------------------------------------------ */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">{t("patient.list.allPatients")}</CardTitle>
        </CardHeader>
        <CardContent className="px-0 pb-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("patient.fields.fullName")}</TableHead>
                <TableHead>{t("patient.fields.phone")}</TableHead>
                <TableHead>{t("patient.fields.dob")}</TableHead>
                <TableHead>{t("patient.list.colScans")}</TableHead>
                <TableHead>{t("patient.list.colLastVisit")}</TableHead>
                <TableHead className="text-right">
                  {t("patient.list.colActions")}
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                /* Skeleton loading state */
                Array.from({ length: 5 }).map((_, i) => (
                  <TableRow key={i}>
                    {Array.from({ length: 6 }).map((_, j) => (
                      <TableCell key={j}>
                        <Skeleton className="h-4 w-full max-w-[120px]" />
                      </TableCell>
                    ))}
                  </TableRow>
                ))
              ) : data && data.items.length > 0 ? (
                data.items.map((patient) => (
                  <TableRow
                    key={patient.id}
                    className="cursor-pointer"
                    onClick={() => navigate(`/patients/${patient.id}`)}
                  >
                    {/* Name — clickable link */}
                    <TableCell
                      className="font-medium"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <Link
                        to={`/patients/${patient.id}`}
                        className="hover:underline underline-offset-4"
                      >
                        {patient.full_name}
                      </Link>
                    </TableCell>

                    {/* Phone */}
                    <TableCell className="text-sm text-muted-foreground">
                      {patient.phone ?? "—"}
                    </TableCell>

                    {/* DOB */}
                    <TableCell className="text-sm text-muted-foreground">
                      {formatDob(patient.date_of_birth)}
                    </TableCell>

                    {/* Scan count */}
                    <TableCell className="text-sm tabular-nums">
                      {patient.scan_count}
                    </TableCell>

                    {/* Last visit */}
                    <TableCell className="text-sm text-muted-foreground">
                      {patient.last_visit ? (
                        <span title={formatAbsoluteTime(patient.last_visit)}>
                          {formatRelativeTime(patient.last_visit)}
                        </span>
                      ) : (
                        "—"
                      )}
                    </TableCell>

                    {/* Actions */}
                    <TableCell
                      className="text-right"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <div className="flex justify-end gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => navigate(`/patients/${patient.id}`)}
                        >
                          {t("common.view")}
                        </Button>
                        {isAdmin && (
                          <Button
                            variant="ghost"
                            size="sm"
                            className="text-destructive hover:text-destructive"
                            onClick={() => setDeleteTarget(patient)}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))
              ) : (
                /* Empty state */
                <TableRow>
                  <TableCell colSpan={6} className="py-12">
                    <div className="flex flex-col items-center gap-4 text-center">
                      <UserX className="h-10 w-10 text-muted-foreground" />
                      <div>
                        <p className="font-medium">{t("patient.list.emptyTitle")}</p>
                        <p className="text-sm text-muted-foreground mt-1">
                          {t("patient.list.emptyDesc")}
                        </p>
                      </div>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setCreateModalOpen(true)}
                      >
                        <UserPlus className="h-4 w-4 mr-1.5" />
                        {t("patient.list.addPatient")}
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>

          {/* Pagination controls */}
          {!isLoading && data && data.total_items > 0 && (
            <div className="flex items-center justify-between px-6 py-4 border-t text-sm text-muted-foreground">
              <span>
                {t("patient.list.paginationInfo", {
                  total: data.total_items,
                  page,
                  totalPages,
                })}
              </span>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handlePageChange(page - 1)}
                  disabled={!hasPrev}
                >
                  {t("common.previous")}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handlePageChange(page + 1)}
                  disabled={!hasNext}
                >
                  {t("common.next")}
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* ------------------------------------------------------------------ */}
      {/* Create patient modal                                                */}
      {/* ------------------------------------------------------------------ */}
      <PatientCreateModal
        open={createModalOpen}
        onOpenChange={setCreateModalOpen}
        onCreated={(id, _name) => handleCreated(id)}
      />

      {/* ------------------------------------------------------------------ */}
      {/* Delete confirmation dialog                                          */}
      {/* ------------------------------------------------------------------ */}
      <AlertDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => { if (!open) setDeleteTarget(null); }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("patient.delete.confirmTitle")}</AlertDialogTitle>
            <AlertDialogDescription>
              {t("patient.delete.confirmDesc", {
                name: deleteTarget?.full_name ?? "",
              })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("common.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={handleDeleteConfirm}
            >
              {t("patient.delete.confirm")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
