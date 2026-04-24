// =============================================================================
// AppBreadcrumbs
// =============================================================================
//
// Route-aware breadcrumbs shown inside the upload/config/result flow.
// The breadcrumbs communicate where the user is within the three-step
// inference workflow without cluttering the top-level nav.

import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { useUploadStore } from "@/context/UploadStore";
import { Fragment } from "react";
import { Link, useLocation } from "react-router-dom";

// ---------------------------------------------------------------------------
// Step definitions
// ---------------------------------------------------------------------------

interface Step {
  label: string;
  path: string;
  // A route matches this step when any of these pathname patterns are active.
  matches: (pathname: string) => boolean;
}

const UPLOAD_FLOW_STEPS: Step[] = [
  {
    label: "Upload",
    path: "/upload",
    matches: (p) => p === "/upload",
  },
  {
    label: "Configure",
    path: "/config",
    matches: (p) => p === "/config",
  },
  {
    label: "Result",
    path: "",
    matches: (p) => p.startsWith("/result/"),
  },
];

/**
 * Render breadcrumbs for the upload-to-result product flow.
 *
 * The current step is rendered as a non-linked page label; earlier steps
 * render as React Router <Link> elements so navigation is client-side and
 * does not destroy the in-memory UploadStore state.
 *
 * The Result step path is extracted from the current pathname directly,
 * because this component lives outside the <Routes> tree (inside AppShell)
 * and therefore useParams cannot see the :jobId segment — we read the
 * pathname instead to remain accurate on every route.
 */
export function AppBreadcrumbs() {
  const location = useLocation();
  const { lastJobId } = useUploadStore();

  // Extract jobId from the pathname when on a result route.
  // Pattern: /result/<uuid>
  const resultMatch = location.pathname.match(/^\/result\/(.+)$/);
  // Fall back to the store's last known job ID when navigating earlier in
  // the flow (e.g. back to /config), so the Result breadcrumb keeps its link.
  const jobIdFromPath = resultMatch?.[1] ?? lastJobId ?? null;

  const currentIndex = UPLOAD_FLOW_STEPS.findIndex((s) =>
    s.matches(location.pathname),
  );

  // Not in the upload flow; render nothing.
  if (currentIndex === -1) return null;

  return (
    <Breadcrumb>
      <BreadcrumbList>
        {UPLOAD_FLOW_STEPS.map((step, index) => {
          // Resolve the Result step path from the extracted jobId.  If we are
          // not currently on the result route the link is omitted (the step
          // renders as the current page label anyway once it becomes active).
          const resolvedPath =
            step.label === "Result" && jobIdFromPath
              ? `/result/${jobIdFromPath}`
              : step.path;

          const isCurrent = index === currentIndex;
          const isLast = index === UPLOAD_FLOW_STEPS.length - 1;

          return (
            // Use a Fragment so no extra DOM element sits between <ol> and
            // <li>, preserving valid list semantics and assistive-technology
            // expectations.
            <Fragment key={step.label}>
              <BreadcrumbItem>
                {isCurrent ? (
                  <BreadcrumbPage>{step.label}</BreadcrumbPage>
                ) : resolvedPath ? (
                  // BreadcrumbLink with asChild delegates rendering to
                  // React Router Link so clicks use client-side navigation
                  // and do not trigger a full page reload.
                  <BreadcrumbLink asChild>
                    <Link to={resolvedPath}>{step.label}</Link>
                  </BreadcrumbLink>
                ) : (
                  <BreadcrumbPage className="text-muted-foreground">
                    {step.label}
                  </BreadcrumbPage>
                )}
              </BreadcrumbItem>
              {!isLast && <BreadcrumbSeparator />}
            </Fragment>
          );
        })}
      </BreadcrumbList>
    </Breadcrumb>
  );
}
