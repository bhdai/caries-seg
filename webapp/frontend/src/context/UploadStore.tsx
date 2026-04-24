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
import { createContext, useContext, useState, type ReactNode } from "react";

interface UploadStoreValue {
  files: File[];
  setFiles: (files: File[]) => void;
  /** ID of the most recently created inference job in this session. */
  lastJobId: string | null;
  setLastJobId: (id: string) => void;
}

const UploadStoreContext = createContext<UploadStoreValue | null>(null);

export function UploadStoreProvider({ children }: { children: ReactNode }) {
  const [files, setFiles] = useState<File[]>([]);
  const [lastJobId, setLastJobId] = useState<string | null>(null);
  return (
    <UploadStoreContext.Provider value={{ files, setFiles, lastJobId, setLastJobId }}>
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
