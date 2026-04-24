/**
 * UploadStore
 *
 * A lightweight React context that carries the selected File[] objects
 * from UploadPage through to ConfigPage without prop-drilling or adding
 * a third-party state library.
 *
 * Also stores the last-created job ID so the breadcrumbs in AppBreadcrumbs
 * can link back to the Result step even after the user navigates away from
 * the result route to an earlier step in the flow.
 *
 * Usage:
 *   Wrap <App> (or the Router root) with <UploadStoreProvider>.
 *   In any descendant component, call `useUploadStore()`.
 */
import { createContext, useCallback, useContext, useState, type ReactNode } from "react";

interface UploadStoreValue {
  files: File[];
  setFiles: (files: File[]) => void;
  /** ID of the most recently created inference job in this session. */
  lastJobId: string | null;
  setLastJobId: (id: string) => void;
  /**
   * Clear all draft state so the next upload starts from a clean slate.
   * Call this before navigating to `/upload` via an explicit "New Job" CTA
   * so stale previews and breadcrumb state do not bleed through.
   */
  resetDraft: () => void;
}

const UploadStoreContext = createContext<UploadStoreValue | null>(null);

export function UploadStoreProvider({ children }: { children: ReactNode }) {
  const [files, setFiles] = useState<File[]>([]);
  const [lastJobId, setLastJobId] = useState<string | null>(null);

  // Clears both files and the last-job breadcrumb reference in one
  // atomic step so callers do not need to know internal store shape.
  const resetDraft = useCallback(() => {
    setFiles([]);
    setLastJobId(null);
  }, []);

  return (
    <UploadStoreContext.Provider value={{ files, setFiles, lastJobId, setLastJobId, resetDraft }}>
      {children}
    </UploadStoreContext.Provider>
  );
}

export function useUploadStore(): UploadStoreValue {
  const ctx = useContext(UploadStoreContext);
  if (!ctx) {
    throw new Error("useUploadStore must be used inside UploadStoreProvider");
  }
  return ctx;
}
