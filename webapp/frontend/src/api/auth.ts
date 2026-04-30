// =============================================================================
// Auth API Layer
// =============================================================================
//
// Typed wrappers around the backend auth endpoints. All communication with
// the server relies on httponly cookies — no client-side token management.
// The browser includes cookies automatically via `credentials: "include"`,
// which is enforced in the shared apiFetch wrapper (see http.ts).

import { apiFetch } from "@/api/http";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface User {
  id: string;
  username: string;
  role: "user" | "admin";
  must_change_pw: boolean;
  // List of OAuth provider names this account has linked, e.g. ["google"].
  // Empty array means no SSO providers are configured for this account.
  oauth_providers: string[];
}

export interface AuthResponse {
  user: User;
  message: string;
}

export interface LoginPayload {
  username: string;
  password: string;
}

export interface ChangePasswordPayload {
  current_password: string;
  new_password: string;
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

/**
 * Fetch the currently authenticated user from the server.
 *
 * Called on app mount by AuthContext as the single source of truth for
 * session state. Throws ApiError(401) when no valid session cookie exists.
 */
export async function fetchCurrentUser(): Promise<User> {
  const res = await apiFetch("/api/auth/me");
  return (await res.json()) as User;
}

/**
 * Submit username/password credentials to establish a session.
 *
 * The backend validates the credentials and sets an httponly cookie on
 * success — this function does not handle or store tokens directly.
 * Returns the authenticated user and a confirmation message.
 * Throws ApiError(401) on invalid credentials.
 */
export async function loginUser(payload: LoginPayload): Promise<AuthResponse> {
  const res = await apiFetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return (await res.json()) as AuthResponse;
}

/**
 * Terminate the current session.
 *
 * Instructs the backend to clear the auth cookie. After this resolves,
 * the user is fully unauthenticated and subsequent requests will 401.
 */
export async function logoutUser(): Promise<void> {
  await apiFetch("/api/auth/logout", { method: "POST" });
}

/**
 * Change the authenticated user's password.
 *
 * The backend verifies the current password before accepting the new one
 * and re-issues the auth cookie on success (refreshing the session).
 * Returns the updated user and a confirmation message.
 * Throws ApiError(401) when the current password is incorrect.
 */
export async function changePassword(
  payload: ChangePasswordPayload,
): Promise<AuthResponse> {
  const res = await apiFetch("/api/auth/change-password", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return (await res.json()) as AuthResponse;
}

/**
 * Complete the popup-based Google account linking flow.
 *
 * The caller obtains the authorisation `code` and `state` by opening a popup
 * to `GET /api/auth/google/link` and listening for a postMessage from the
 * popup callback page at `/auth/google/link-callback`.  The `state` is
 * validated server-side against the `oauth_link_state` CSRF cookie set during
 * flow initiation.
 *
 * Returns a confirmation message on success.
 * Throws ApiError(409) if the Google account is already linked to a
 * different user.
 */
export async function linkGoogleAccount(
  code: string,
  state: string,
): Promise<{ message: string }> {
  const res = await apiFetch("/api/auth/link-google", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code, state }),
  });
  return (await res.json()) as { message: string };
}
