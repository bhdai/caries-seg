import React from "react";
import ReactDOM from "react-dom/client";
import { Toaster } from "@/components/ui/sonner";
import App from "./App";
import { QueryProvider } from "@/app/providers/QueryProvider";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryProvider>
      <App />
      {/* Sonner toast container — placed at the root so toasts render above
          all page content regardless of which route is active. */}
      <Toaster />
    </QueryProvider>
  </React.StrictMode>
);
