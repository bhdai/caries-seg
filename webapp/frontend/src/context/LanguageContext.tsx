// =============================================================================
// Language Context
// =============================================================================
//
// Exposes the active locale and the locale-change function to the React tree.
// Components should use `useLanguage()` rather than importing i18n.ts directly
// so that locale changes trigger React re-renders on non-i18next consumers
// (e.g. components that branch on `locale` for conditional logic).
//
// i18next's LanguageDetector already persists the choice to localStorage under
// the key 'i18nextLng', so `setLocale` does not need to write it manually.

import React, { createContext, useContext, useState } from 'react';
import i18next from '@/i18n';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type Locale = 'vi' | 'en';

interface LanguageContextValue {
  /** Currently active locale code, e.g. 'vi' or 'en'. */
  locale: Locale;

  /**
   * Switch the active locale.
   *
   * Calls `i18next.changeLanguage(l)`, which triggers re-render of all
   * `useTranslation()` consumers, and also updates local React state so that
   * components consuming `useLanguage().locale` directly also re-render.
   * The LanguageDetector persists the choice to localStorage automatically.
   */
  setLocale: (l: Locale) => void;
}

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

const LanguageContext = createContext<LanguageContextValue | null>(null);

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

/**
 * Provider that must wrap the application router (outermost in App.tsx).
 * Reads the initial locale from the live i18next language at mount time so
 * it stays in sync with whatever the LanguageDetector resolved from
 * localStorage.
 */
export function LanguageProvider({
  children,
}: {
  children: React.ReactNode;
}): JSX.Element {
  // Initialise from the i18next language that was resolved at startup so that
  // the React state matches the actual translation language immediately.
  const [locale, setLocaleState] = useState<Locale>(
    (i18next.language as Locale) ?? 'vi',
  );

  function setLocale(l: Locale): void {
    // Delegate to i18next so all useTranslation() subscribers re-render and
    // the LanguageDetector persists the choice to localStorage.
    void i18next.changeLanguage(l);
    // Also update React state so consumers of useLanguage().locale re-render.
    setLocaleState(l);
  }

  return (
    <LanguageContext.Provider value={{ locale, setLocale }}>
      {children}
    </LanguageContext.Provider>
  );
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

/**
 * Consume the language context.
 *
 * @throws {Error} if called outside `<LanguageProvider>`.
 * @returns `{ locale, setLocale }`
 */
export function useLanguage(): LanguageContextValue {
  const ctx = useContext(LanguageContext);
  assert(ctx !== null, 'useLanguage must be called inside <LanguageProvider>');
  return ctx;
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

function assert(condition: boolean, message: string): asserts condition {
  if (!condition) throw new Error(message);
}
