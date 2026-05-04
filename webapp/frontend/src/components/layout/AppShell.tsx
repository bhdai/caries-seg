// =============================================================================
// AppShell
// =============================================================================
//
// Top-level layout shell shared by all product-flow routes.  Provides the
// navigation bar, page container, and a consistent visual framing so
// Dashboard, History, Upload, Config, and Result all feel connected.

import { AppBreadcrumbs } from "@/components/layout/AppBreadcrumbs";
import { UserMenu } from "@/components/layout/UserMenu";
import { Button } from "@/components/ui/button";
import { LayoutDashboard, Clock, UploadCloud, ShieldCheck } from "lucide-react";
import type { ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { useStartNewJob } from "@/hooks/useStartNewJob";
import { useAuth } from "@/context/AuthContext";
import { useTranslation } from "react-i18next";

interface AppShellProps {
  children: ReactNode;
}

/**
 * Wrap a page in the shared application chrome: top nav and page container.
 *
 * The nav highlights the active route using NavLink's `isActive` callback so
 * the active state follows the URL automatically without extra state.
 */
export function AppShell({ children }: AppShellProps) {
  const location = useLocation();
  const startNewJob = useStartNewJob();
  const { user } = useAuth();
  const { t } = useTranslation();

  // Determine whether we are in the multi-step upload flow so we can hide
  // redundant nav items and keep the flow focused.
  const isUploadFlow =
    location.pathname === "/upload" ||
    location.pathname === "/config" ||
    location.pathname.startsWith("/result/");

  return (
    <div className="min-h-screen bg-background flex flex-col">
      {/* ------------------------------------------------------------------ */}
      {/* Top nav                                                             */}
      {/* ------------------------------------------------------------------ */}
      <header className="border-b bg-background sticky top-0 z-40">
        <div className="max-w-6xl mx-auto px-4 h-14 flex items-center justify-between">
          {/* Brand */}
          <NavLink
            to="/"
            className="text-sm font-semibold tracking-tight hover:opacity-80 transition-opacity"
          >
            {t("nav.brand")}
          </NavLink>

          {/* Primary nav — hidden mid-flow to reduce noise */}
          <nav className="flex items-center gap-1">
            <NavItem to="/" icon={<LayoutDashboard className="h-4 w-4" />}>
              {t("nav.dashboard")}
            </NavItem>
            <NavItem to="/history" icon={<Clock className="h-4 w-4" />}>
              {t("nav.history")}
            </NavItem>
            {/* Admin panel link — only rendered for users with the admin role */}
            {user?.role === "admin" && (
              <NavItem to="/admin/users" icon={<ShieldCheck className="h-4 w-4" />}>
                {t("nav.admin")}
              </NavItem>
            )}
            {/* Upload CTA is always visible for quick access */}
            <Button size="sm" className="ml-2" onClick={startNewJob}>
              <UploadCloud className="h-4 w-4 mr-1.5" />
              {t("nav.newJob")}
            </Button>
            {/* User account menu — logout and change password */}
            <UserMenu />
          </nav>
        </div>

        {/* Breadcrumbs — shown in upload flow to indicate progress */}
        {isUploadFlow && (
          <div className="max-w-6xl mx-auto px-4 pb-2">
            <AppBreadcrumbs />
          </div>
        )}
      </header>

      {/* ------------------------------------------------------------------ */}
      {/* Page content                                                        */}
      {/* ------------------------------------------------------------------ */}
      <main className="flex-1 max-w-6xl mx-auto w-full px-4 py-8">
        {children}
      </main>
    </div>
  );
}

// ---------------------------------------------------------------------------
// NavItem — styled NavLink with active indicator
// ---------------------------------------------------------------------------

interface NavItemProps {
  to: string;
  icon: ReactNode;
  children: ReactNode;
}

function NavItem({ to, icon, children }: NavItemProps) {
  return (
    <NavLink
      to={to}
      end
      className={({ isActive }) =>
        [
          "inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
          isActive
            ? "bg-accent text-accent-foreground"
            : "text-muted-foreground hover:text-foreground hover:bg-accent/50",
        ].join(" ")
      }
    >
      {icon}
      {children}
    </NavLink>
  );
}
