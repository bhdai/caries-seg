import { UploadStoreProvider } from "@/context/UploadStore";
import { AppShell } from "@/components/layout/AppShell";
import ConfigPage from "@/pages/ConfigPage";
import DashboardPage from "@/pages/DashboardPage";
import HistoryPage from "@/pages/HistoryPage";
import ResultPage from "@/pages/ResultPage";
import UploadPage from "@/pages/UploadPage";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

/**
 * Application root.
 *
 * Routes:
 *   /              → DashboardPage (home, recent jobs, quick actions)
 *   /upload        → UploadPage    (file selection — step 1)
 *   /config        → ConfigPage    (pipeline + model selection — step 2)
 *   /result/:jobId → ResultPage    (polling + overlay viewer — step 3)
 *   /history       → HistoryPage   (full job list with filters and pagination)
 *   *              → redirect to /
 *
 * All routes are wrapped in AppShell, which provides the shared navigation
 * bar and page container.  UploadStoreProvider wraps the whole tree so the
 * upload-to-config file handoff context is available everywhere.
 */
export default function App() {
  return (
    <UploadStoreProvider>
      <BrowserRouter>
        <AppShell>
          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/upload" element={<UploadPage />} />
            <Route path="/config" element={<ConfigPage />} />
            <Route path="/result/:jobId" element={<ResultPage />} />
            <Route path="/history" element={<HistoryPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </AppShell>
      </BrowserRouter>
    </UploadStoreProvider>
  );
}
