import { BrowserRouter, Route, Routes } from "react-router-dom";

/**
 * Application root.
 *
 * Phase 1: renders a minimal placeholder page so the Vite dev server serves
 * something visible, confirming the React + Tailwind + shadcn/ui pipeline
 * is wired up correctly.
 *
 * Phase 4 will replace the placeholder route with the real pages:
 *   /            → UploadPage
 *   /config      → ConfigPage
 *   /result/:id  → ResultPage
 */
export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* TODO (Phase 4): replace with UploadPage, ConfigPage, ResultPage */}
        <Route path="*" element={<PlaceholderPage />} />
      </Routes>
    </BrowserRouter>
  );
}

function PlaceholderPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background">
      <div className="text-center space-y-2">
        <h1 className="text-3xl font-bold tracking-tight text-foreground">
          Caries Segmentation
        </h1>
        <p className="text-muted-foreground">
          Phase 1 scaffold — infrastructure healthy.
        </p>
      </div>
    </div>
  );
}
