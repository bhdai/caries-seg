// =============================================================================
// i18next Singleton Initialisation
// =============================================================================
//
// This module creates and exports the configured i18next instance.  It must be
// imported as the **first** import in `src/main.tsx` so the instance is ready
// before any React component renders.
//
// Inline resources are used (no async JSON loading) so init() is synchronous
// and i18n.language is available immediately after this module executes.
//
// React components should use `useTranslation()` from 'react-i18next' rather
// than importing this module directly.  Direct imports are only needed for
// code outside React (toast handlers, lib utilities, etc.).

import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';
import en from './locales/en.json';
import vi from './locales/vi.json';

i18n
  // Detect language from localStorage (key: 'i18nextLng') so user preference
  // persists across sessions.
  .use(LanguageDetector)
  // Wire i18next into the React rendering lifecycle so components re-render
  // automatically when the active language changes.
  .use(initReactI18next)
  .init({
    // Default locale for new users who have no localStorage entry yet.
    lng: 'vi',
    // Fall back to English for any key that is absent from the vi translation.
    fallbackLng: 'en',
    resources: {
      en: { translation: en },
      vi: { translation: vi },
    },
    detection: {
      // Only consult localStorage — avoids relying on browser Accept-Language
      // headers which could cause flickering between languages on first load.
      order: ['localStorage'],
      lookupLocalStorage: 'i18nextLng',
      caches: ['localStorage'],
    },
    interpolation: {
      // React already escapes output; double-escaping would corrupt HTML
      // entities in translated strings.
      escapeValue: false,
    },
  });

export default i18n;
