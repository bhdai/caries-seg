// =============================================================================
// useDeleteJobMutation
// =============================================================================
//
// Manages the permanent job deletion mutation.  On success, invalidates the
// dashboard and history list caches so the deleted job disappears from all
// views without a manual refresh.  On failure, surfaces an error toast without
// disturbing the existing list state.

import { deleteJob } from "@/api/jobs";
import { jobsQueryKeys } from "@/hooks/useJobsQuery";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

/**
 * Create and manage the job deletion mutation.
 *
 * On success:
 *  - Invalidates all jobs list queries so Dashboard and History no longer
 *    show the deleted job.
 *  - Shows a brief success toast for feedback.
 *
 * On failure:
 *  - Surfaces a user-facing error toast with the server's error message.
 *  - Does not modify the existing list state.
 */
export function useDeleteJobMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (jobId: string) => deleteJob(jobId),

    onSuccess() {
      void queryClient.invalidateQueries({ queryKey: jobsQueryKeys.all });
      toast.success("Job deleted");
    },

    onError(error) {
      const message =
        error instanceof Error ? error.message : "Failed to delete the job.";
      toast.error("Delete failed", { description: message });
    },
  });
}
