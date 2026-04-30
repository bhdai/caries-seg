// =============================================================================
// Auth Context
// =============================================================================
//
// Provides the authenticated user and auth actions to the entire component
// tree. The context treats `GET /api/auth/me` as the single source of truth
// for session state — no client-side JWT parsing, no localStorage tokens.
//
// The 401 event dispatched by apiFetch (http.ts) is the escape hatch for
// any component that triggers an unauthorised request mid-session; the
// provider listens for it globally and clears the user without requiring
// each call site to handle session expiry themselves.

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

import {
  fetchCurrentUser,
  loginUser,
  logoutUser,
  type LoginPayload,
  type User,
} from "@/api/auth";

// ---------------------------------------------------------------------------
// Context shape
// ---------------------------------------------------------------------------

export interface AuthContextValue {
  user: User | null;
  isLoading: boolean;
  login: (payload: LoginPayload) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  // isLoading stays true until the initial /api/auth/me round-trip completes
  // so ProtectedRoute can render a spinner rather than a premature redirect.
  const [isLoading, setIsLoading] = useState(true);

  // ---------------------------------------------------------------------------
  // Initial session check
  // ---------------------------------------------------------------------------
  //
  // On mount we ask the backend whether a valid cookie already exists. A 401
  // means the user is not authenticated; any other error is unexpected but
  // should not crash the app — we treat it the same way (unauthenticated).
  useEffect(() => {
    let cancelled = false;

    fetchCurrentUser()
      .then((u) => {
        if (!cancelled) setUser(u);
      })
      .catch(() => {
        if (!cancelled) setUser(null);
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  // ---------------------------------------------------------------------------
  // Global 401 listener
  // ---------------------------------------------------------------------------
  //
  // apiFetch dispatches "auth:unauthorized" whenever any request receives a
  // 401 response. We listen at the window level so mid-session expiry is
  // handled automatically without each call site needing explicit handling.
  useEffect(() => {
    function handleUnauth() {
      setUser(null);
    }

    window.addEventListener("auth:unauthorized", handleUnauth);
    return () => {
      window.removeEventListener("auth:unauthorized", handleUnauth);
    };
  }, []);

  // ---------------------------------------------------------------------------
  // Auth actions
  // ---------------------------------------------------------------------------

  // Log in with username/password. On success the backend sets the cookie and
  // returns the User in the response body, so we update state immediately.
  // Errors are intentionally not caught here — callers (LoginForm) own error
  // display logic.
  const login = useCallback(async (payload: LoginPayload) => {
    const response = await loginUser(payload);
    setUser(response.user);
  }, []);

  // Log out by asking the backend to clear the cookie, then drop the local
  // user reference so ProtectedRoute redirects to /login.
  const logout = useCallback(async () => {
    await logoutUser();
    setUser(null);
  }, []);

  // Re-fetch the current user from the server. Used after password change so
  // the must_change_pw flag is refreshed without requiring a full page reload.
  const refreshUser = useCallback(async () => {
    const u = await fetchCurrentUser();
    setUser(u);
  }, []);

  return (
    <AuthContext.Provider value={{ user, isLoading, login, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

/**
 * Read the current auth state and actions anywhere inside AuthProvider.
 *
 * Throws if called outside the provider tree — this is a programming error
 * that should surface immediately during development.
 */
export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  assert(ctx !== null, "useAuth must be called inside <AuthProvider>");
  return ctx;
}

// Internal guard — keeps the assertion message close to the throw site.
function assert(condition: boolean, message: string): asserts condition {
  if (!condition) throw new Error(message);
}
