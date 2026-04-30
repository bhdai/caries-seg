// =============================================================================
// Login Form
// =============================================================================
//
// Username + password sign-in form, adapted from the shadcn login-01 block.
// Uses existing Card, Input, Label, Button, and Alert components only —
// no new UI primitives are introduced.
//
// Error sources that this component handles:
//   1. URL ?error= param on mount (e.g. google_not_linked from OAuth callback)
//   2. ApiError thrown by auth.login() during form submission

import type { ComponentProps } from "react";
import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { useAuth } from "@/context/AuthContext";
import { ApiError } from "@/api/http";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

// ---------------------------------------------------------------------------
// URL error → human-readable message mapping
// ---------------------------------------------------------------------------

// Errors that the backend can pass back via query string after an OAuth
// redirect. Each key maps to the value of the `?error=` param.
const OAUTH_ERROR_MESSAGES: Record<string, string> = {
  google_not_linked:
    "No account is linked to this Google identity. Contact your admin.",
  invalid_state:
    "OAuth login failed (invalid state). Please try again.",
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function LoginForm({ className, ...props }: ComponentProps<"div">) {
  const auth = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Translate any ?error= query param into a human-readable message on mount.
  // This handles error redirects from the Google OAuth callback.
  useEffect(() => {
    const errorKey = searchParams.get("error");
    if (errorKey) {
      setError(
        OAUTH_ERROR_MESSAGES[errorKey] ??
          "An error occurred during sign in. Please try again.",
      );
    }
  }, [searchParams]);

  // ---------------------------------------------------------------------------
  // Form submission
  // ---------------------------------------------------------------------------

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setIsSubmitting(true);
    setError(null);

    try {
      await auth.login({ username, password });
      // ProtectedRoute handles must_change_pw redirection — we navigate
      // to "/" unconditionally and let the route tree sort it out.
      navigate("/", { replace: true });
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("An unexpected error occurred. Please try again.");
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className={className} {...props}>
      <Card>
        <CardHeader className="text-center">
          <CardTitle className="text-xl">Login to your account</CardTitle>
          <CardDescription>Enter your credentials below</CardDescription>
        </CardHeader>

        <CardContent>
          <form onSubmit={handleSubmit} noValidate>
            <div className="grid gap-6">
              {/* Error banner — shown for both URL errors and submission failures */}
              {error !== null && (
                <Alert variant="destructive">
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              )}

              {/* Username field */}
              <div className="grid gap-2">
                <Label htmlFor="username">Username</Label>
                <Input
                  id="username"
                  type="text"
                  autoComplete="username"
                  required
                  autoFocus
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  disabled={isSubmitting}
                />
              </div>

              {/* Password field */}
              <div className="grid gap-2">
                <Label htmlFor="password">Password</Label>
                <Input
                  id="password"
                  type="password"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={isSubmitting}
                />
              </div>

              {/* Primary submit button */}
              <Button type="submit" className="w-full" disabled={isSubmitting}>
                {isSubmitting ? "Signing in…" : "Login"}
              </Button>

              {/* Separator */}
              <div className="relative text-center text-sm after:absolute after:inset-0 after:top-1/2 after:z-0 after:flex after:items-center after:border-t after:border-border">
                <span className="relative z-10 bg-card px-2 text-muted-foreground">
                  Or
                </span>
              </div>

              {/* Google sign-in — redirects to backend, which handles OAuth */}
              <Button
                type="button"
                variant="outline"
                className="w-full"
                disabled={isSubmitting}
                onClick={() => {
                  window.location.href = "/api/auth/google";
                }}
              >
                Sign in with Google
              </Button>

              {/*
               * No "Sign up" link — accounts are admin-provisioned only.
               * No "Forgot password" link — deferred (see D1 in decisions).
               */}
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
