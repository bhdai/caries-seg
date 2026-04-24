// =============================================================================
// QueryProvider
// =============================================================================
//
// Creates and exposes the TanStack Query client for the whole application.
// Centralised here so stale-time, retry policies, and default options can
// be tuned in one place without touching individual hooks.

import {
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";
import type { ReactNode } from "react";

// A single QueryClient instance is created outside the component to prevent
// re-creation on every render.  The defaults below are chosen for a
// short-lived inference dashboard:
//
//  staleTime: 30 s  — list data is considered fresh for 30 s so switching
//    between Dashboard and History does not fire redundant network requests.
//  retry: 1         — surface API errors quickly; inference failures are not
//    transient so aggressive retries would only delay error feedback.
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
    },
  },
});

interface QueryProviderProps {
  children: ReactNode;
}

/**
 * Wrap the application tree with the TanStack Query client context.
 * Must be placed above any component that calls a `useQuery` or
 * `useMutation` hook.
 */
export function QueryProvider({ children }: QueryProviderProps) {
  return (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}
