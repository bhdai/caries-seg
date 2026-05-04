// =============================================================================
// useRerunJobMutation
// =============================================================================
//
// Manages the server-side rerun mutation.  On success, invalidates the
// dashboard and history list caches and navigates to the new result detail
// route.  On failure, surfaces an actionable error via toast without
// disturbing the existing list state.

import { rerunJob } from "@/api/jobs";
import { ApiError } from "@/api/http";
import { jobsQueryKeys } from "@/hooks/useJobsQuery";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { translateApiError } from "@/lib/apiErrors";

/**
 * Create and manage the server-side rerun mutation.
 *
 * On success:
 *  - Invalidates all jobs list queries so Dashboard and History show the
 *    newly created job without requiring a manual refresh.
 *  - Navigates to /result/:newJobId so the user sees live inference progress.
 *
 * On failure:
 *  - Surfaces a user-facing error toast with the server's error message.
 *  - Does not clear or modify the existing list state.
 */
export function useRerunJobMutation() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { t } = useTranslation();

  return useMutation({
    mutationFn: (jobId: string) => rerunJob(jobId),

    onSuccess(newJob) {
      // Invalidate all jobs list queries so the new pending job appears in
      // Dashboard and History immediately.
      void queryClient.invalidateQueries({ queryKey: jobsQueryKeys.all });

      // Navigate to the new result route so the user sees inference progress.
      navigate(`/result/${newJob.id}`);
    },

    onError(error) {
      const message = error instanceof ApiError
        ? translateApiError(error)
        : error.message;
      toast.error(t("hooks.rerunJob.errorTitle"), { description: message });
    },
  });
}
