// =============================================================================
// useStartNewJob
// =============================================================================
//
// Single canonical action for every "New Job" CTA in the application.
//
// The hook returns one callback that:
//   1. Clears the upload draft (selected files + last-job breadcrumb).
//   2. Navigates to `/upload` so the user lands on a clean dropzone.
//
// Centralising this here prevents drift when new entry points (Dashboard,
// History, Result, AppShell) are added or refactored — they all import this
// hook instead of duplicating the reset + navigate pattern by hand.

import { useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useUploadStore } from "@/context/UploadStore";

/**
 * Return the single canonical "New Job" callback for the application.
 *
 * The returned function clears all upload draft state and navigates to
 * `/upload`.  Plain navigation to `/upload` without calling this function
 * is treated as "continue/edit the current draft" and does **not** clear
 * any state — only an explicit New Job action should wipe the slate.
 */
export function useStartNewJob(): () => void {
  const { resetDraft } = useUploadStore();
  const navigate = useNavigate();

  return useCallback(() => {
    // Clear files and last-job breadcrumb reference before navigation so
    // UploadPage never hydrates previews from a previous session.
    resetDraft();
    navigate("/upload");
  }, [resetDraft, navigate]);
}
