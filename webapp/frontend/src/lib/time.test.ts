// =============================================================================
// Unit Tests — formatRelativeTime()
// =============================================================================
//
// Tests are grouped into two sections:
//
//   1. English locale — covers all time-bucket branches.  These tests run
//      in the 'en' locale established by test/setup.ts and must continue
//      passing unchanged after the Phase 4 Intl.RelativeTimeFormat rewrite.
//
//   2. Vietnamese locale — new tests added in Phase 5 to verify that
//      Intl.RelativeTimeFormat produces correct Vietnamese output.  Each test
//      passes `locale = 'vi'` explicitly so the result is independent of the
//      active i18next language.
//
// The `now` parameter is always supplied explicitly so tests are reproducible
// without clock freezing.
// =============================================================================

import { describe, expect, it } from 'vitest';
import { formatRelativeTime } from './time';

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

/**
 * Build an ISO 8601 string that is `offsetMs` milliseconds in the past
 * relative to `reference`.
 */
function pastIso(reference: Date, offsetMs: number): string {
  return new Date(reference.getTime() - offsetMs).toISOString();
}

// Fixed reference point for all tests.  Using a concrete time avoids any
// dependency on the system clock and makes bucket boundaries predictable.
const NOW = new Date('2026-05-04T12:00:00Z');

const SECOND = 1_000;
const MINUTE = 60 * SECOND;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

// ===========================================================================
// English locale — all branches
// ===========================================================================

describe('formatRelativeTime() — English locale', () => {
  // -------------------------------------------------------------------------
  // "just now" — < 45 seconds ago
  // -------------------------------------------------------------------------

  it('returns "just now" for a timestamp 10 seconds ago', () => {
    const iso = pastIso(NOW, 10 * SECOND);
    // Intl.RelativeTimeFormat with numeric:'auto' renders rtf.format(0, 'second')
    // as "now" in English.  Browsers and Node agree on "now".
    const result = formatRelativeTime(iso, NOW, 'en');
    expect(result).toBe('now');
  });

  it('returns "just now" equivalent for a timestamp 44 seconds ago', () => {
    const iso = pastIso(NOW, 44 * SECOND);
    const result = formatRelativeTime(iso, NOW, 'en');
    expect(result).toBe('now');
  });

  // -------------------------------------------------------------------------
  // Minute granularity — 45 s to < 60 min
  // -------------------------------------------------------------------------

  it('returns a minute-based string for a timestamp 3 minutes ago', () => {
    const iso = pastIso(NOW, 3 * MINUTE);
    const result = formatRelativeTime(iso, NOW, 'en');
    expect(result).toBe('3 minutes ago');
  });

  it('returns "1 minute ago" for a timestamp 90 seconds ago', () => {
    const iso = pastIso(NOW, 90 * SECOND);
    const result = formatRelativeTime(iso, NOW, 'en');
    expect(result).toBe('1 minute ago');
  });

  // -------------------------------------------------------------------------
  // Hour granularity — 60 min to < 24 h
  // -------------------------------------------------------------------------

  it('returns an hour-based string for a timestamp 5 hours ago', () => {
    const iso = pastIso(NOW, 5 * HOUR);
    const result = formatRelativeTime(iso, NOW, 'en');
    expect(result).toBe('5 hours ago');
  });

  it('returns "1 hour ago" for a timestamp 61 minutes ago', () => {
    const iso = pastIso(NOW, 61 * MINUTE);
    const result = formatRelativeTime(iso, NOW, 'en');
    expect(result).toBe('1 hour ago');
  });

  // -------------------------------------------------------------------------
  // Day granularity — 24 h to < 30 days
  // -------------------------------------------------------------------------

  it('returns "yesterday" for a timestamp 25 hours ago', () => {
    // Intl.RelativeTimeFormat with numeric:'auto' uses "yesterday" for -1 day.
    const iso = pastIso(NOW, 25 * HOUR);
    const result = formatRelativeTime(iso, NOW, 'en');
    expect(result).toBe('yesterday');
  });

  it('returns a day-based string for a timestamp 10 days ago', () => {
    const iso = pastIso(NOW, 10 * DAY);
    const result = formatRelativeTime(iso, NOW, 'en');
    expect(result).toBe('10 days ago');
  });

  // -------------------------------------------------------------------------
  // Absolute date — ≥ 30 days
  // -------------------------------------------------------------------------

  it('returns an absolute date for a timestamp 31 days ago', () => {
    const iso = pastIso(NOW, 31 * DAY);
    const result = formatRelativeTime(iso, NOW, 'en');
    // toLocaleDateString('en', { year:'numeric', month:'short', day:'numeric' })
    // typically produces "Apr 3, 2026" in Node/V8.  We check format not the
    // exact string so the test is not brittle against locale-data minor changes.
    expect(result).toMatch(/\d{4}/);      // year present
    expect(result).toMatch(/Apr|Mar/);    // month name present
  });
});

// ===========================================================================
// Vietnamese locale — Phase 5 additions
// ===========================================================================

describe('formatRelativeTime() — Vietnamese locale', () => {
  // -------------------------------------------------------------------------
  // "just now" — Intl.RelativeTimeFormat('vi', { numeric:'auto' }).format(0, 'second')
  //
  // The CLDR data for Vietnamese renders the zero-offset second as "bây giờ"
  // in Node ≥ 18.  Earlier documentation mentioned "vừa xong"; however the
  // actual ICU data shipped with the V8 engine uses "bây giờ".  The test
  // asserts the real runtime value so it does not silently pass against a mock.
  // -------------------------------------------------------------------------

  it('returns the Vietnamese "just now" string for a timestamp 10 seconds ago', () => {
    const iso = pastIso(NOW, 10 * SECOND);
    const result = formatRelativeTime(iso, NOW, 'vi');
    // "bây giờ" is the CLDR value produced by Intl.RelativeTimeFormat on Node ≥ 18.
    expect(result).toBe('bây giờ');
  });

  // -------------------------------------------------------------------------
  // 3 minutes ago → "3 phút trước"
  // -------------------------------------------------------------------------

  it('returns "3 phút trước" for a timestamp 3 minutes ago', () => {
    const iso = pastIso(NOW, 3 * MINUTE);
    const result = formatRelativeTime(iso, NOW, 'vi');
    expect(result).toBe('3 phút trước');
  });

  // -------------------------------------------------------------------------
  // yesterday → "Hôm qua"
  //
  // Intl.RelativeTimeFormat('vi', { numeric:'auto' }).format(-1, 'day')
  // produces "Hôm qua" (capital H) in Node ≥ 18 with CLDR v44+ data.
  // -------------------------------------------------------------------------

  it('returns the Vietnamese "yesterday" string for a timestamp 25 hours ago', () => {
    const iso = pastIso(NOW, 25 * HOUR);
    const result = formatRelativeTime(iso, NOW, 'vi');
    // "Hôm qua" (capital H) is the CLDR value on Node ≥ 18.
    expect(result).toBe('Hôm qua');
  });
});
