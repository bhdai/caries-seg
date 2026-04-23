import { UploadStoreProvider } from "@/context/UploadStore";
import ConfigPage from "@/pages/ConfigPage";
import ResultPage from "@/pages/ResultPage";
import UploadPage from "@/pages/UploadPage";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

/**
 * Application root.
 *
 * Routes:
 *   /              → UploadPage   (file selection)
 *   /config        → ConfigPage   (pipeline + model selection, job submission)
 *   /result/:jobId → ResultPage   (polling + overlay viewer)
 *   *              → redirect to /
 */
export default function App() {
  return (
    <UploadStoreProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<UploadPage />} />
          <Route path="/config" element={<ConfigPage />} />
          <Route path="/result/:jobId" element={<ResultPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </UploadStoreProvider>
  );
}
