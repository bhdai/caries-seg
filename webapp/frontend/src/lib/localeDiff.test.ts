// =============================================================================
// Locale Key-Diff Test
// =============================================================================
//
// Asserts that `en.json` and `vi.json` contain exactly the same set of keys.
//
// Why this test exists:
//   - A key present in en.json but absent from vi.json is silently swallowed
//     by i18next's fallback mechanism; users see English in an otherwise
//     Vietnamese UI.
//   - A key present in vi.json but absent from en.json can never be exercised
//     by the fallback and indicates a translation that was added without a
//     corresponding English source string — which usually means a typo in the
//     key name.
//
// The test runs against the raw JSON files (not the i18next instance) so it
// catches problems before the runtime ever loads the locale bundles.
// =============================================================================

import { describe, expect, it } from 'vitest';
import en from '@/locales/en.json';
import vi from '@/locales/vi.json';

// ---------------------------------------------------------------------------
// Key extraction
//
// Both locale files use flat dot-namespaced keys (e.g. "nav.dashboard").
// Object.keys() is sufficient — no deep traversal needed.
// ---------------------------------------------------------------------------

const enKeys = new Set(Object.keys(en));
const viKeys = new Set(Object.keys(vi));

describe('locale key parity (en.json ↔ vi.json)', () => {
  it('en.json and vi.json have the same number of keys', () => {
    expect(enKeys.size).toBe(viKeys.size);
  });

  it('every key in en.json is present in vi.json', () => {
    const missingFromVi = [...enKeys].filter((k) => !viKeys.has(k));
    expect(
      missingFromVi,
      `Keys in en.json but missing from vi.json: ${missingFromVi.join(', ')}`,
    ).toHaveLength(0);
  });

  it('every key in vi.json is present in en.json', () => {
    const missingFromEn = [...viKeys].filter((k) => !enKeys.has(k));
    expect(
      missingFromEn,
      `Keys in vi.json but missing from en.json: ${missingFromEn.join(', ')}`,
    ).toHaveLength(0);
  });
});
