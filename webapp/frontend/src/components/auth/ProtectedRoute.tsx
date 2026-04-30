// =============================================================================
// ProtectedRoute
// =============================================================================
//
// Wraps any part of the route tree that requires authentication. On every
// render it consults the auth state from AuthContext and redirects before
// React renders children, so protected pages never receive `user === null`.
//
// Three possible outcomes:
//   1. Auth state is still loading (initial /api/auth/me in flight)
//      → show a centered skeleton so the page does not flash empty.
//   2. Not authenticated → hard redirect to /login.
//   3. Authenticated but must change password → redirect to /change-password
//      (unless already on that page to avoid an infinite loop).
//   4. Fully authenticated → render children normally.

import { Navigate, useLocation } from "react-router-dom";

import { useAuth } from "@/context/AuthContext";
import { Skeleton } from "@/components/ui/skeleton";
import type { ReactNode } from "react";

interface ProtectedRouteProps {
  children: ReactNode;
}

export function ProtectedRoute({ children }: ProtectedRouteProps) {
  const { user, isLoading } = useAuth();
  const location = useLocation();

  // While the initial session check is in flight we render a neutral
  // skeleton rather than immediately redirecting. Without this guard the
  // app would bounce every authenticated user to /login on every hard
  // refresh before the cookie round-trip completes.
  if (isLoading) {
    return (
      <div className="flex min-h-svh items-center justify-center">
        <Skeleton className="h-8 w-48 rounded-md" />
      </div>
    );
  }

  // No valid session — send to login, preserving the intended destination
  // so LoginPage can redirect back after a successful sign-in (if needed).
  if (user === null) {
    return <Navigate to="/login" replace />;
  }

  // Forced password change: the admin set must_change_pw=true when
  // provisioning the account (or resetting via admin panel). Route to the
  // change-password page for all protected pages except that page itself
  // to avoid a redirect loop.
  if (user.must_change_pw && location.pathname !== "/change-password") {
    return <Navigate to="/change-password" replace />;
  }

  return <>{children}</>;
}
