// =============================================================================
// i18next TypeScript Module Augmentation
// =============================================================================
//
// Augments the i18next module so that `t()` calls are type-checked against the
// English locale file.  Any key that does not exist in `en.json` becomes a
// TypeScript compile error, catching typos and stale keys at build time.

import type en from './locales/en.json';

declare module 'i18next' {
  interface CustomTypeOptions {
    defaultNS: 'translation';
    resources: {
      translation: typeof en;
    };
  }
}
