// =============================================================================
// Relative-time formatting
// =============================================================================
//
// Centralised helpers for producing human-readable relative-time labels from
// ISO-8601 timestamp strings.  Keeping formatting here prevents inconsistent
// date handling from spreading across Dashboard, History, and Result pages.
//
// Phase 4 update: formatRelativeTime() now uses Intl.RelativeTimeFormat for
// locale-aware output (e.g. "3 phút trước" in Vietnamese, "3 minutes ago" in
// English) rather than hand-rolled English string templates.

import i18n from '@/i18n';

/** Number of milliseconds in each time unit used for bucketing. */
const SECOND_MS = 1_000;
const MINUTE_MS = 60 * SECOND_MS;
const HOUR_MS = 60 * MINUTE_MS;
const DAY_MS = 24 * HOUR_MS;
const MONTH_MS = 30 * DAY_MS;

// Timestamps within this window are treated as "just now" rather than
// computing a minute count that rounds to 0, which would produce the less
// natural "this minute" instead of "just now" / "vừa xong".
const JUST_NOW_MS = 45 * SECOND_MS;

/**
 * Format an ISO 8601 timestamp as a human-readable relative time string
 * in the given locale.
 *
 * Uses Intl.RelativeTimeFormat for locale-aware output, e.g.:
 *   - 'vi': "3 phút trước", "vừa xong", "hôm qua"
 *   - 'en': "3 minutes ago", "just now", "yesterday"
 *
 * For timestamps older than 30 days, returns an absolute date string via
 * toLocaleDateString(locale, { year: 'numeric', month: 'short', day: 'numeric' }).
 *
 * @param isoString - ISO 8601 date-time string, e.g. "2026-05-01T10:30:00Z".
 * @param now       - Reference point for "now". Defaults to new Date().
 *                    Injected for testing.
 * @param locale    - BCP 47 locale tag. Defaults to i18n.language ?? 'vi'.
 *                    Pass explicitly in tests to avoid dependency on runtime state.
 * @returns Localised relative time string.
 */
export function formatRelativeTime(
  isoString: string,
  now: Date = new Date(),
  locale: string = i18n.language ?? 'vi',
): string {
  const ts = new Date(isoString);
  const diffMs = now.getTime() - ts.getTime();

  // Build the formatter once — reused across all buckets below.
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' });

  if (diffMs < 0) {
    // Future timestamp — should not happen in normal usage, but be graceful.
    return rtf.format(0, 'second');
  }

  // Bucket selection mirrors common relative-time UX conventions:
  //   < 45 s   → "just now" / "vừa xong"
  //   < 60 min → minute granularity
  //   < 24 h   → hour granularity
  //   < 30 d   → day granularity
  //   ≥ 30 d   → absolute calendar date
  if (diffMs < JUST_NOW_MS) return rtf.format(0, 'second');
  if (diffMs < HOUR_MS) return rtf.format(-Math.floor(diffMs / MINUTE_MS), 'minute');
  if (diffMs < DAY_MS) return rtf.format(-Math.floor(diffMs / HOUR_MS), 'hour');
  if (diffMs < MONTH_MS) return rtf.format(-Math.floor(diffMs / DAY_MS), 'day');

  // Older than 30 days — show the calendar date for precision.
  return ts.toLocaleDateString(locale, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

/**
 * Format an ISO-8601 timestamp as a short absolute datetime string, e.g.
 * "Apr 24, 2026, 10:35 AM".  Used as tooltip text or in detail views where
 * the full date and time matter.
 */
export function formatAbsoluteTime(isoString: string): string {
  return new Date(isoString).toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
