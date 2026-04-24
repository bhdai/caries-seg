// =============================================================================
// Relative-time formatting
// =============================================================================
//
// Centralised helpers for producing human-readable relative-time labels from
// ISO-8601 timestamp strings.  Keeping formatting here prevents inconsistent
// date handling from spreading across Dashboard, History, and Result pages.

/** Number of milliseconds in each time unit used for bucketing. */
const SECOND_MS = 1_000;
const MINUTE_MS = 60 * SECOND_MS;
const HOUR_MS = 60 * MINUTE_MS;
const DAY_MS = 24 * HOUR_MS;
const WEEK_MS = 7 * DAY_MS;
const MONTH_MS = 30 * DAY_MS;

/**
 * Format an ISO-8601 timestamp as a short relative-time label, e.g.
 * "just now", "3 min ago", "2 hr ago", "5 days ago", or the absolute date
 * for anything older than 30 days.
 *
 * @param isoString - ISO-8601 datetime string (UTC or with offset).
 * @param now       - Reference point; defaults to the current wall clock
 *                    so callers can pass a fixed value in tests.
 */
export function formatRelativeTime(
  isoString: string,
  now: Date = new Date(),
): string {
  const ts = new Date(isoString);
  const diffMs = now.getTime() - ts.getTime();

  if (diffMs < 0) {
    // Future timestamp — should not happen in normal usage, but be graceful.
    return "just now";
  }

  if (diffMs < MINUTE_MS) return "just now";
  if (diffMs < HOUR_MS) {
    const mins = Math.floor(diffMs / MINUTE_MS);
    return `${mins} min ago`;
  }
  if (diffMs < DAY_MS) {
    const hrs = Math.floor(diffMs / HOUR_MS);
    return `${hrs} hr ago`;
  }
  if (diffMs < WEEK_MS) {
    const days = Math.floor(diffMs / DAY_MS);
    return `${days} day${days !== 1 ? "s" : ""} ago`;
  }
  if (diffMs < MONTH_MS) {
    const weeks = Math.floor(diffMs / WEEK_MS);
    return `${weeks} week${weeks !== 1 ? "s" : ""} ago`;
  }

  // Older than 30 days — show the calendar date for precision.
  return ts.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
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
