// =============================================================================
// AppShell
// =============================================================================
//
// Top-level layout shell shared by all product-flow routes.  Provides the
// navigation bar, page container, and a consistent visual framing so
// Dashboard, History, Upload, Config, and Result all feel connected.

import { AppBreadcrumbs } from "@/components/layout/AppBreadcrumbs";
import { Button } from "@/components/ui/button";
import { LayoutDashboard, Clock, UploadCloud } from "lucide-react";
import type { ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { useStartNewJob } from "@/hooks/useStartNewJob";

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
            CariesSeg
          </NavLink>

          {/* Primary nav — hidden mid-flow to reduce noise */}
          <nav className="flex items-center gap-1">
            <NavItem to="/" icon={<LayoutDashboard className="h-4 w-4" />}>
              Dashboard
            </NavItem>
            <NavItem to="/history" icon={<Clock className="h-4 w-4" />}>
              History
            </NavItem>
            {/* Upload CTA is always visible for quick access */}
            <Button size="sm" className="ml-2" onClick={startNewJob}>
              <UploadCloud className="h-4 w-4 mr-1.5" />
              New Job
            </Button>
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
