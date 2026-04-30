// =============================================================================
// UserMenu
// =============================================================================
//
// Compact dropdown in the AppShell nav bar showing the authenticated user's
// username and providing quick access to account actions. The trigger is a
// ghost button — visually lightweight so it does not compete with the primary
// nav items.
//
// Menu items:
//   - Username + role badge (display only, non-interactive label)
//   - Change Password → /change-password
//   - Link Google Account → popup OAuth flow via /api/auth/google/link
//   - ──────────────────────────────────────
//   - Manage Users (admin only) → /admin/users
//   - ──────────────────────────────────────
//   - Log Out (clears cookie + redirects to /login)

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { LogOut, KeyRound, ChevronDown, Link2, Users } from "lucide-react";
import { toast } from "sonner";

import { useAuth } from "@/context/AuthContext";
import { linkGoogleAccount } from "@/api/auth";
import { ApiError } from "@/api/http";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  GOOGLE_LINK_CODE_MSG,
  GOOGLE_LINK_ERROR_MSG,
  type GoogleLinkCodeMessage,
  type GoogleLinkErrorMessage,
} from "@/pages/GoogleLinkCallbackPage";

export function UserMenu() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [isLinking, setIsLinking] = useState(false);

  // Should not render without a user — ProtectedRoute prevents this, but
  // guard defensively so the component is safe to import anywhere.
  if (user === null) return null;

  async function handleLogout() {
    await logout();
    navigate("/login", { replace: true });
  }

  // ---------------------------------------------------------------------------
  // Google Account Linking — popup flow
  // ---------------------------------------------------------------------------
  //
  // Opening a popup (rather than a full-page redirect) keeps the user's
  // existing session intact. Sequence:
  //   1. Open /api/auth/google/link in a popup.
  //   2. Backend redirects popup → Google consent → /auth/google/link-callback.
  //   3. Callback page reads ?code=&state= and posts them to the opener.
  //   4. We call POST /api/auth/link-google with code + state.
  //   5. Backend validates CSRF state cookie and exchanges the code.
  function handleLinkGoogle() {
    const popup = window.open(
      "/api/auth/google/link",
      "link-google",
      "width=520,height=620,popup=1,noopener=0",
    );

    if (!popup) {
      toast.error(
        "Could not open the Google sign-in popup. " +
          "Allow popups for this site and try again.",
      );
      return;
    }

    setIsLinking(true);

    function cleanup() {
      window.removeEventListener("message", handleMessage);
      clearInterval(pollInterval);
    }

    function handleMessage(
      event: MessageEvent<GoogleLinkCodeMessage | GoogleLinkErrorMessage>,
    ) {
      // Reject messages from any other origin.
      if (event.origin !== window.location.origin) return;
      const { type } = event.data;
      if (type !== GOOGLE_LINK_CODE_MSG && type !== GOOGLE_LINK_ERROR_MSG) return;

      cleanup();
      popup?.close();

      if (type === GOOGLE_LINK_CODE_MSG) {
        const { code, state } = event.data as GoogleLinkCodeMessage;
        linkGoogleAccount(code, state)
          .then(() => toast.success("Google account linked successfully."))
          .catch((err) => {
            const msg =
              err instanceof ApiError
                ? err.message
                : "Failed to link Google account. Please try again.";
            toast.error(msg);
          })
          .finally(() => setIsLinking(false));
      } else {
        setIsLinking(false);
        toast.error("Google sign-in was cancelled or failed. Please try again.");
      }
    }

    // Clean up if the user closes the popup manually without completing.
    const pollInterval = setInterval(() => {
      if (popup.closed) {
        cleanup();
        setIsLinking(false);
      }
    }, 1000);

    window.addEventListener("message", handleMessage);
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="sm" className="gap-1.5">
          {user.username}
          <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
        </Button>
      </DropdownMenuTrigger>

      <DropdownMenuContent align="end" className="w-52">
        {/* Non-interactive label showing username and role */}
        <DropdownMenuLabel className="font-normal">
          <div className="flex items-center justify-between gap-2">
            <span className="text-sm font-medium text-foreground">{user.username}</span>
            <Badge variant="secondary" className="text-xs capitalize">
              {user.role}
            </Badge>
          </div>
        </DropdownMenuLabel>

        <DropdownMenuSeparator />

        <DropdownMenuItem onClick={() => navigate("/change-password")}>
          <KeyRound className="mr-2 h-4 w-4" />
          Change Password
        </DropdownMenuItem>

        <DropdownMenuItem onClick={handleLinkGoogle} disabled={isLinking || user.oauth_providers.includes("google")}>
          <Link2 className="mr-2 h-4 w-4" />
          {user.oauth_providers.includes("google")
            ? "Google Linked"
            : isLinking
              ? "Linking…"
              : "Link Google Account"}
        </DropdownMenuItem>

        {/* Admin shortcut — duplicates the nav bar item for convenience */}
        {user.role === "admin" && (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => navigate("/admin/users")}>
              <Users className="mr-2 h-4 w-4" />
              Manage Users
            </DropdownMenuItem>
          </>
        )}

        <DropdownMenuSeparator />

        <DropdownMenuItem
          onClick={handleLogout}
          className="text-destructive focus:text-destructive"
        >
          <LogOut className="mr-2 h-4 w-4" />
          Log Out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

