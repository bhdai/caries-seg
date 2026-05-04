// =============================================================================
// Unit Tests — translateApiError()
// =============================================================================
//
// Verifies the four paths through translateApiError():
//   1. Known code, active locale = vi  → Vietnamese translation
//   2. Known code, active locale = en  → English translation
//   3. Unknown code                    → falls back to err.message
//   4. No code at all                  → falls back to err.message
//
// The test/setup.ts `beforeAll` sets the locale to 'en' for the entire suite.
// Tests that require a specific locale explicitly call i18n.changeLanguage()
// and restore it in afterEach to avoid bleed-through to other test files.
// =============================================================================

import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import i18n from '@/i18n';
import { ApiError } from '@/api/types';
import { translateApiError } from './apiErrors';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Build an ApiError with the given properties without extra boilerplate. */
function mkError(status: number, message: string, code?: string): ApiError {
  return new ApiError(status, message, code);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('translateApiError()', () => {
  let originalLocale: string;

  beforeEach(() => {
    // Capture the locale that test/setup.ts established (usually 'en').
    originalLocale = i18n.language;
  });

  afterEach(async () => {
    // Always restore locale so subsequent tests are not affected.
    await i18n.changeLanguage(originalLocale);
  });

  // -------------------------------------------------------------------------
  // Known code — Vietnamese locale
  // -------------------------------------------------------------------------

  it('returns the Vietnamese translation when locale is vi and code is known', async () => {
    await i18n.changeLanguage('vi');

    const err = mkError(401, 'Invalid credentials', 'auth.invalidCredentials');
    // The Vietnamese locale file maps this code to the string below.
    expect(translateApiError(err)).toBe('Tên đăng nhập hoặc mật khẩu không đúng.');
  });

  // -------------------------------------------------------------------------
  // Known code — English locale
  // -------------------------------------------------------------------------

  it('returns the English translation when locale is en and code is known', async () => {
    await i18n.changeLanguage('en');

    const err = mkError(401, 'Invalid credentials', 'auth.invalidCredentials');
    // The English locale file maps this code to the string below.
    expect(translateApiError(err)).toBe('Invalid credentials.');
  });

  // -------------------------------------------------------------------------
  // Unknown code — falls back to err.message
  // -------------------------------------------------------------------------

  it('falls back to err.message when code is not present in locale files', async () => {
    // Both locale files lack a key for "unknown.code", so i18next returns the
    // raw key string.  translateApiError() detects this and uses err.message.
    const err = mkError(500, 'Server error', 'unknown.code');
    expect(translateApiError(err)).toBe('Server error');
  });

  // -------------------------------------------------------------------------
  // No code at all — falls back to err.message
  // -------------------------------------------------------------------------

  it('falls back to err.message when err.code is undefined', () => {
    const err = mkError(404, 'Not found', undefined);
    expect(translateApiError(err)).toBe('Not found');
  });
});
