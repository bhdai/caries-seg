// =============================================================================
// useShareLinkMutation
// =============================================================================
//
// TanStack Query mutation hooks for the share-link create and revoke flows.
// Both hooks accept an optional `onSuccess` callback so callers can trigger
// additional cache invalidations (e.g. patient detail query) without coupling
// the hook implementation to a specific query key or page.

import {
  createShareLink,
  revokeShareLink,
} from "@/api/shareLinks";
import type { CreateShareLinkPayload, ShareLinkResponse } from "@/api/shareLinks";
import { ApiError } from "@/api/http";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";

// ---------------------------------------------------------------------------
// Query key factory
// ---------------------------------------------------------------------------

/** Centralised query keys for share-link data so all consumers stay in sync. */
export const shareLinksQueryKeys = {
  /** Key for the "active link for a given job" query. */
  forJob: (jobId: string) => ["shareLinks", jobId] as const,
};

// ---------------------------------------------------------------------------
// Create mutation
// ---------------------------------------------------------------------------

interface UseCreateShareLinkOptions {
  /** Called with the newly created link after a successful request. */
  onSuccess?: (link: ShareLinkResponse) => void;
}

/**
 * Mutation hook for creating a new share link.
 *
 * On success: invalidates the `["shareLinks", jobId]` query so any cached
 * `getShareLinkForJob` result reflects the new link immediately.
 *
 * @param jobId   - The job UUID this link will be created for.
 * @param options - Optional success callback.
 */
export function useCreateShareLinkMutation(
  jobId: string,
  options?: UseCreateShareLinkOptions,
) {
  const queryClient = useQueryClient();
  const { t } = useTranslation();

  return useMutation({
    mutationFn: (payload: CreateShareLinkPayload) => createShareLink(payload),

    onSuccess(link) {
      // Invalidate the per-job share link query so ShareModal reflects the
      // newly created link if re-opened without a full page reload.
      void queryClient.invalidateQueries({
        queryKey: shareLinksQueryKeys.forJob(jobId),
      });
      options?.onSuccess?.(link);
    },

    onError(error) {
      const message =
        error instanceof ApiError
          ? error.message
          : t("hooks.createShareLink.error");
      toast.error(message);
    },
  });
}

// ---------------------------------------------------------------------------
// Revoke mutation
// ---------------------------------------------------------------------------

interface UseRevokeShareLinkOptions {
  /**
   * Called after a successful revoke.
   * Callers should invalidate any patient detail or per-job queries that
   * include the now-revoked link.
   */
  onSuccess?: () => void;
}

/**
 * Mutation hook for revoking a share link by its ID.
 *
 * On success: shows a toast and calls the optional `onSuccess` callback.
 * Cache invalidation is the caller's responsibility via the `onSuccess` hook
 * so this mutation remains generic across all usage sites (ResultPage,
 * PatientDetailPage, ShareLinksTable).
 *
 * @param options - Optional success callback and error configuration.
 */
export function useRevokeShareLinkMutation(
  options?: UseRevokeShareLinkOptions,
) {
  const { t } = useTranslation();

  return useMutation({
    mutationFn: (linkId: string) => revokeShareLink(linkId),

    onSuccess() {
      toast.success(t("hooks.revokeShareLink.success"));
      options?.onSuccess?.();
    },

    onError(error) {
      const message =
        error instanceof ApiError
          ? error.message
          : t("hooks.revokeShareLink.error");
      toast.error(message);
    },
  });
}
