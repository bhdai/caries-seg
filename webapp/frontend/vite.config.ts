import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    // Allow imports like `@/components/...` to resolve from src/.
    // This mirrors the path alias configured in tsconfig.json and the
    // shadcn/ui components.json.
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    // Proxy API requests to the backend so the dev server and the FastAPI
    // app can run on different ports without CORS preflight on every call.
    proxy: {
      "/api": {
        target: process.env.VITE_API_URL ?? "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  test: {
    // Vitest environment — jsdom gives us the DOM APIs React needs.
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    globals: true,
  },
});
