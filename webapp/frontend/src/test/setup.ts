/// <reference types="vitest/globals" />
/**
 * Vitest global setup — extends expect with @testing-library/jest-dom matchers.
 *
 * Imported by vite.config.ts via `test.setupFiles`.
 */
import "@testing-library/jest-dom";

// ---------------------------------------------------------------------------
// Radix UI pointer-capture polyfills
//
// Radix UI primitives (Select, Dialog, Popover, …) call hasPointerCapture /
// setPointerCapture / releasePointerCapture during pointer events.  jsdom does
// not implement those APIs, which causes uncaught TypeErrors in component
// tests that click Radix UI triggers.  The no-op implementations below are
// sufficient for test interactions — they mirror what real browsers do when
// no element has actually captured the pointer.
// ---------------------------------------------------------------------------
window.HTMLElement.prototype.hasPointerCapture = () => false;
window.HTMLElement.prototype.setPointerCapture = () => {};
window.HTMLElement.prototype.releasePointerCapture = () => {};

// ---------------------------------------------------------------------------
// scrollIntoView polyfill
//
// Radix UI Select calls scrollIntoView on the currently highlighted item when
// the dropdown opens.  jsdom does not implement it; a no-op is enough for
// tests because layout/scroll are not under test.
// ---------------------------------------------------------------------------
window.Element.prototype.scrollIntoView = () => {};

// ---------------------------------------------------------------------------
// i18n — use English for all component tests
//
// Phase 2 sets the default language to Vietnamese, but tests assert English
// strings.  Switching to 'en' before the suite runs avoids brittle test
// failures caused by locale-dependent text output.
// ---------------------------------------------------------------------------
import i18n from '@/i18n';

beforeAll(async () => {
  await i18n.changeLanguage('en');
});
