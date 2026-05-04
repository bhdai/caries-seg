// =============================================================================
// API Error Translation
// =============================================================================
//
// Provides `translateApiError()` — a single function that converts an
// ApiError instance into a user-facing, localised string.
//
// Lookup logic:
//   1. If `err.code` is defined, attempt `t('apiError.' + err.code)`.
//   2. If the translation key exists (i.e. the returned string is not the key
//      itself), return the translated string.
//   3. Otherwise, return `err.message` verbatim (English fallback).
//
// This function NEVER throws.  Missing codes produce a graceful fallback to
// the raw English detail string from the backend.

import i18n from '@/i18n';
import type { ApiError } from '@/api/types';

/**
 * Return a user-facing translated message for an API error.
 *
 * Uses the active i18next locale, so the result changes immediately after
 * a call to `i18next.changeLanguage()`.
 *
 * @param err - An ApiError instance from a failed apiFetch() call.
 * @returns A localised string safe to display directly in the UI.
 *
 * @example
 * try {
 *   await apiFetch('/api/auth/login', { method: 'POST', body: ... });
 * } catch (err) {
 *   if (err instanceof ApiError) {
 *     toast.error(translateApiError(err));
 *   }
 * }
 */
export function translateApiError(err: ApiError): string {
  if (err.code) {
    const key = `apiError.${err.code}` as const;
    // i18next returns the raw key string when no translation entry is found.
    // Comparing against the key is the conventional way to detect a miss
    // without throwing or checking namespace existence separately.
    const translated = i18n.t(key);
    if (translated !== key) return translated;
  }
  // No code, or no translation registered for this code — fall back to the
  // human-readable English detail string supplied by the backend.
  return err.message;
}
