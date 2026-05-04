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
import { useTranslation } from "react-i18next";

import { useAuth } from "@/context/AuthContext";
import { ApiError } from "@/api/http";
import { translateApiError } from "@/lib/apiErrors";

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
// Translated using i18next; unknown keys fall back to the generic error key.
const OAUTH_ERROR_KEYS: Record<string, string> = {
  google_not_linked: "auth.login.error.googleNotLinked",
  // invalid_state maps to the generic fallback — no dedicated locale key yet.
  invalid_state: "auth.login.error.fallback",
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function LoginForm({ className, ...props }: ComponentProps<"div">) {
  const auth = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { t } = useTranslation();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Translate any ?error= query param into a human-readable message on mount.
  // This handles error redirects from the Google OAuth callback.
  useEffect(() => {
    const errorKey = searchParams.get("error");
    if (errorKey) {
      const i18nKey = OAUTH_ERROR_KEYS[errorKey] ?? "auth.login.error.fallback";
      setError(t(i18nKey as Parameters<typeof t>[0]));
    }
  }, [searchParams, t]);

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
        setError(translateApiError(err));
      } else {
        setError(t("auth.login.error.fallback"));
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
          <CardTitle className="text-xl">{t("auth.login.title")}</CardTitle>
          <CardDescription>{t("auth.login.description")}</CardDescription>
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
                <Label htmlFor="username">{t("auth.login.username")}</Label>
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
                <Label htmlFor="password">{t("auth.login.password")}</Label>
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
                {isSubmitting ? t("auth.login.submitting") : t("auth.login.submit")}
              </Button>

              {/* Separator */}
              <div className="relative text-center text-sm after:absolute after:inset-0 after:top-1/2 after:z-0 after:flex after:items-center after:border-t after:border-border">
                <span className="relative z-10 bg-card px-2 text-muted-foreground">
                  {t("auth.login.or")}
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
                {t("auth.login.google")}
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
