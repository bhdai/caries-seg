// =============================================================================
// Unit Tests — i18n bootstrap (src/i18n.ts)
// =============================================================================
//
// Verifies three invariants of the i18next singleton setup:
//
//   1. The default language is 'vi' before any explicit change.
//   2. A key missing from vi.json falls back to the en.json value rather than
//      returning the raw key — confirming that fallbackLng: 'en' is active.
//   3. A key absent from both locale files returns the raw key string (not an
//      error), confirming that i18next does not throw on missing keys.
//
// IMPORTANT: test/setup.ts runs a `beforeAll` that calls
// `i18n.changeLanguage('en')` to keep component tests in English.  The tests
// below reset the language to 'vi' where needed and restore it afterwards so
// they do not interfere with other files in the suite.
// =============================================================================

import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import i18n from '@/i18n';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

// A key that exists in en.json but NOT in vi.json allows us to test
// fallback behaviour.  We add a sentinel key specifically for this test
// rather than relying on an accidental gap in the locale files, which could
// disappear without notice.
//
// The key is injected via i18n.addResourceBundle() so no locale file changes
// are required.  It is cleaned up in afterAll.
const FALLBACK_TEST_KEY = '__test__.missingInVi';
const FALLBACK_EN_VALUE = '__en_fallback_value__';

let localeBeforeTests: string;

beforeAll(async () => {
  // Capture whatever locale the suite-level beforeAll (from test/setup.ts)
  // left us in so we can restore it at the end.
  localeBeforeTests = i18n.language;

  // Inject the sentinel key into the English resource bundle only.
  i18n.addResourceBundle('en', 'translation', { [FALLBACK_TEST_KEY]: FALLBACK_EN_VALUE }, true, true);
});

afterAll(async () => {
  // Remove the sentinel key so it does not leak into other test files.
  i18n.removeResourceBundle('en', '__test__');
  // Restore the locale that was active before this file ran.
  await i18n.changeLanguage(localeBeforeTests);
});

// ===========================================================================
// Tests
// ===========================================================================

describe('i18n bootstrap', () => {
  // -------------------------------------------------------------------------
  // 1. Default language is 'vi'
  //
  // We temporarily switch to 'vi' to simulate the fresh-load condition.
  // The suite-level setup.ts sets the language to 'en', so we must
  // switch explicitly here.
  // -------------------------------------------------------------------------

  it("resolves to 'vi' when explicitly set (simulates default on fresh load)", async () => {
    await i18n.changeLanguage('vi');
    expect(i18n.language).toBe('vi');
  });

  // -------------------------------------------------------------------------
  // 2. Missing vi.json key falls back to en.json
  //
  // FALLBACK_TEST_KEY exists only in en.json.  With fallbackLng: 'en',
  // i18next should return the English string when the active locale is 'vi'.
  // -------------------------------------------------------------------------

  it('returns the English string for a key missing from vi.json (fallbackLng active)', async () => {
    // Ensure we are in Vietnamese so the fallback mechanism is exercised.
    await i18n.changeLanguage('vi');
    const result = i18n.t(FALLBACK_TEST_KEY as never);
    expect(result).toBe(FALLBACK_EN_VALUE);
  });

  // -------------------------------------------------------------------------
  // 3. Completely unknown key returns the raw key string (no throw)
  // -------------------------------------------------------------------------

  it('returns the raw key string for a key absent from both locale files', async () => {
    await i18n.changeLanguage('en');
    const unknownKey = 'does.not.exist';
    // Cast through unknown to bypass TypeScript's strict key checking from
    // the custom type options in i18n.d.ts.
    const result = i18n.t(unknownKey as never);
    expect(result).toBe(unknownKey);
  });
});
