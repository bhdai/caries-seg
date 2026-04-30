// =============================================================================
// Google Link Callback Page
// =============================================================================
//
// Minimal popup page served at /auth/google/link-callback after Google
// completes the consent flow initiated by UserMenu → "Link Google Account".
//
// Sequence:
//   1. UserMenu opens a popup to GET /api/auth/google/link?redirect_uri=<this page>
//   2. Backend redirects the popup to Google's consent screen.
//   3. Google redirects the popup back here with ?code=... or ?error=...
//   4. This page reads the query params, sends a postMessage to the opener,
//      and closes the popup.
//   5. UserMenu's message listener receives the code and calls
//      POST /api/auth/link-google to complete the exchange.
//
// If the page is visited outside of a popup context (window.opener is null)
// we show a message rather than crashing, so direct navigation produces a
// meaningful error instead of a blank page.

import { useEffect, useState } from "react";

// Message type constants — must match the listener in UserMenu.tsx.
export const GOOGLE_LINK_CODE_MSG = "google-link-code" as const;
export const GOOGLE_LINK_ERROR_MSG = "google-link-error" as const;

export interface GoogleLinkCodeMessage {
  type: typeof GOOGLE_LINK_CODE_MSG;
  code: string;
  state: string;
}

export interface GoogleLinkErrorMessage {
  type: typeof GOOGLE_LINK_ERROR_MSG;
  error: string;
}

export function GoogleLinkCallbackPage() {
  const [status, setStatus] = useState<"pending" | "no-opener">("pending");

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get("code");
    const error = params.get("error");

    if (!window.opener) {
      // Navigated directly — not inside a popup.
      setStatus("no-opener");
      return;
    }

    // Relay the result back to the parent window.  target origin is the
    // same as this page's origin, so the parent's message listener accepts it.
    if (code) {
      const msg: GoogleLinkCodeMessage = { type: GOOGLE_LINK_CODE_MSG, code, state: params.get("state") ?? "" };
      (window.opener as Window).postMessage(msg, window.location.origin);
    } else {
      const msg: GoogleLinkErrorMessage = {
        type: GOOGLE_LINK_ERROR_MSG,
        error: error ?? "unknown",
      };
      (window.opener as Window).postMessage(msg, window.location.origin);
    }

    // Close the popup after posting — the parent window handles the rest.
    window.close();
  }, []);

  if (status === "no-opener") {
    return (
      <div className="flex min-h-svh items-center justify-center p-6">
        <p className="text-muted-foreground text-sm">
          This page is only accessible as a popup during Google account linking.
        </p>
      </div>
    );
  }

  return (
    <div className="flex min-h-svh items-center justify-center p-6">
      <p className="text-muted-foreground text-sm">Completing Google sign-in…</p>
    </div>
  );
}
