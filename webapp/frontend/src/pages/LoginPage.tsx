// =============================================================================
// Login Page
// =============================================================================
//
// Full-page container for the login form, rendered outside AppShell so it
// has no navigation bar or sidebar. Centres LoginForm on the viewport.

import { LoginForm } from "@/components/auth/LoginForm";

export function LoginPage() {
  return (
    <div className="flex min-h-svh w-full items-center justify-center p-6 md:p-10">
      <div className="w-full max-w-sm">
        <LoginForm />
      </div>
    </div>
  );
}
