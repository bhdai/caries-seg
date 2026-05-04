// =============================================================================
// usePatientSearchQuery
// =============================================================================
//
// Debounced patient search hook for PatientCombobox typeahead.  The debounce
// prevents a network request on every keystroke; the query only fires when the
// debounced value is at least 1 character long and the hook is enabled.

import { searchPatients } from "@/api/patients";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

/** Debounce delay for the patient search input. */
const DEBOUNCE_MS = 300;

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

/**
 * Debounced patient typeahead hook backed by TanStack Query.
 *
 * @param search  - The raw search string from the input (updated on every keystroke).
 * @param enabled - Set to false to suppress the query entirely (e.g. when the
 *                  combobox popover is closed).  Defaults to true.
 *
 * Returns the same shape as `useQuery` but restricts `data` to
 * `PatientSummary[]` and defaults to an empty array when disabled or pending.
 */
export function usePatientSearchQuery(search: string, enabled = true) {
  // Maintain the debounced copy of the search string.  Updates happen inside
  // a useEffect with a clearTimeout teardown so the timer is always cancelled
  // before setting a new one or on unmount.
  const [debouncedSearch, setDebouncedSearch] = useState(search);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
    }

    timerRef.current = setTimeout(() => {
      setDebouncedSearch(search);
    }, DEBOUNCE_MS);

    return () => {
      if (timerRef.current !== null) {
        clearTimeout(timerRef.current);
      }
    };
  }, [search]);

  const isQueryEnabled = enabled && debouncedSearch.length >= 1;

  const query = useQuery({
    queryKey: ["patients", "search", debouncedSearch],
    queryFn: () => searchPatients(debouncedSearch, 10),
    enabled: isQueryEnabled,
    // Keep previous results visible while a new search is in-flight so the
    // dropdown does not flash to empty between keystrokes.
    placeholderData: (prev) => prev,
    // Patient names rarely change mid-session; a short stale window prevents
    // redundant refetches when the user clears and retypes the same name.
    staleTime: 10_000,
  });

  return {
    data: query.data ?? [],
    isLoading: query.isFetching,
    error: query.error,
  };
}
