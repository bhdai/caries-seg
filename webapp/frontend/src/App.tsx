import { LanguageProvider } from "@/context/LanguageContext";
import { AuthProvider } from "@/context/AuthContext";
import { UploadStoreProvider } from "@/context/UploadStore";
import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { AppShell } from "@/components/layout/AppShell";
import { AdminUsersPage } from "@/pages/AdminUsersPage";
import ConfigPage from "@/pages/ConfigPage";
import DashboardPage from "@/pages/DashboardPage";
import HistoryPage from "@/pages/HistoryPage";
import ResultPage from "@/pages/ResultPage";
import UploadPage from "@/pages/UploadPage";
import { LoginPage } from "@/pages/LoginPage";
import { ChangePasswordPage } from "@/pages/ChangePasswordPage";
import { GoogleLinkCallbackPage } from "@/pages/GoogleLinkCallbackPage";
import { BrowserRouter, Navigate, Outlet, Route, Routes } from "react-router-dom";

/**
 * Application root.
 *
 * Route tree:
 *   /login             → LoginPage        (public, no AppShell)
 *   /change-password   → ChangePasswordPage (protected, no AppShell)
 *   /                  → DashboardPage    (protected, inside AppShell)
 *   /upload            → UploadPage       (protected, inside AppShell)
 *   /config            → ConfigPage       (protected, inside AppShell)
 *   /result/:jobId     → ResultPage       (protected, inside AppShell)
 *   /history           → HistoryPage      (protected, inside AppShell)
 *   *                  → redirect to /
 *
 * AuthProvider is the outermost wrapper so auth state is available to all
 * components including ProtectedRoute. UploadStoreProvider stays inside
 * BrowserRouter so its reset helper can be called from navigation hooks.
 *
 * Layout routes (pathless <Route element={...}>) group routes that share
 * the same chrome — ProtectedRoute + AppShell for product pages —
 * without repeating those wrappers on every individual route.
 */
export default function App() {
  return (
    <LanguageProvider>
      <AuthProvider>
      <UploadStoreProvider>
        <BrowserRouter>
          <Routes>
            {/* Public route — no auth required, no nav bar */}
            <Route path="/login" element={<LoginPage />} />

            {/* Popup callback for Google account linking — public, no AppShell */}
            <Route path="/auth/google/link-callback" element={<GoogleLinkCallbackPage />} />

            {/* Forced password-change — authenticated but no AppShell */}
            <Route
              path="/change-password"
              element={
                <ProtectedRoute>
                  <ChangePasswordPage />
                </ProtectedRoute>
              }
            />

            {/* All product routes share ProtectedRoute + AppShell */}
            <Route
              element={
                <ProtectedRoute>
                  <AppShell>
                    <Outlet />
                  </AppShell>
                </ProtectedRoute>
              }
            >
              <Route path="/" element={<DashboardPage />} />
              <Route path="/upload" element={<UploadPage />} />
              <Route path="/config" element={<ConfigPage />} />
              <Route path="/result/:jobId" element={<ResultPage />} />
              <Route path="/history" element={<HistoryPage />} />
              <Route path="/admin/users" element={<AdminUsersPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </UploadStoreProvider>
      </AuthProvider>
    </LanguageProvider>
  );
}
