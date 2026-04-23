/**
 * UploadStore
 *
 * A lightweight React context that carries the selected File[] objects
 * from UploadPage through to ConfigPage without prop-drilling or adding
 * a third-party state library.
 *
 * Usage:
 *   Wrap <App> (or the Router root) with <UploadStoreProvider>.
 *   In any descendant component, call `useUploadStore()`.
 */
import { createContext, useContext, useState, type ReactNode } from "react";

interface UploadStoreValue {
  files: File[];
  setFiles: (files: File[]) => void;
}

const UploadStoreContext = createContext<UploadStoreValue | null>(null);

export function UploadStoreProvider({ children }: { children: ReactNode }) {
  const [files, setFiles] = useState<File[]>([]);
  return (
    <UploadStoreContext.Provider value={{ files, setFiles }}>
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
